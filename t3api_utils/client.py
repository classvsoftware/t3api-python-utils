"""T3Client: generic requests checked against the spec, collections, writes."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import FIRST_EXCEPTION, Future, ThreadPoolExecutor, wait
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, Self
from urllib.parse import quote

import httpx2

from t3api_utils import _api, _console
from t3api_utils._http import DEFAULT_HOST, DEFAULT_TIMEOUT, build_client
from t3api_utils.auth.credentials import BearerAuth, CredentialKind, SecretKeyAuth, credential_kind
from t3api_utils.auth.secret_keys import SecretKeys
from t3api_utils.auth.states import fetch_states
from t3api_utils.errors import APIError, SpecError
from t3api_utils.spec.loader import SpecMode, load_spec
from t3api_utils.spec.registry import Endpoint, Kind, Registry
from t3api_utils.writes import BulkResult, OnError, WriteResult, _message

if TYPE_CHECKING:
    from t3api_utils.auth.store import Profile
    from t3api_utils.tag_lists import TagLists

logger = logging.getLogger("t3api_utils")

LicenseArg = str | Sequence[str] | None
_PLACEHOLDER = re.compile(r"\{([^}]+)\}")

COLLECTION_PARAM_NAMES = {
    "licenseNumber": "license",
    "filter": "filter",
    "filterLogic": "filter_logic",
    "sort": "sort",
    "collectionMask": "mask",
    "pageSize": "page_size",
    "include": "include",
}


class T3Client:
    """A configured connection to the T3 API.

    Usually made by :func:`t3api_utils.connect`. Use it as a context manager,
    or call :meth:`close`, to release its connection pool.
    """

    def __init__(
        self,
        *,
        auth: httpx2.Auth | None = None,
        base_url: str = DEFAULT_HOST,
        license: str | None = None,
        profile: Profile | None = None,
        spec: SpecMode = "auto",
        rate_limit: float | None = 10.0,
        concurrency: int = 10,
        timeout: float = DEFAULT_TIMEOUT,
        log_http: bool = False,
        transport: httpx2.BaseTransport | None = None,
        verify: bool | str = True,
        proxy: str | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self.base_url = base_url.rstrip("/")
        self.license = license
        self.profile = profile
        self.concurrency = concurrency
        self._spec_mode: SpecMode = spec
        self._registry: Registry | None = None
        self._spec_lock = threading.Lock()
        self._sandbox = False
        self._whoami: dict[str, Any] | None = None
        self._session_licenses: frozenset[str] | None = None
        self._warned_licenses: set[str] = set()
        self.http: httpx2.Client = build_client(
            base_url=self.base_url,
            auth=auth,
            timeout=timeout,
            rate_limit=rate_limit,
            log_http=log_http,
            transport=transport,
            verify=verify,
            proxy=proxy,
        )
        """The underlying ``httpx2.Client``: auth, base URL, retries and logging
        are already set. Use it for routes missing from the published spec."""

    # ------------------------------------------------------------------ lifecycle

    def close(self) -> None:
        """Close the connection pool. The client can't be used afterwards."""
        self.http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        profile = f" profile={self.profile.name!r}" if self.profile else ""
        sandbox = " sandbox" if self._sandbox else ""
        return f"<T3Client {self.base_url} credential={self.credential_kind}{profile}{sandbox}>"

    @property
    def credential_kind(self) -> CredentialKind | None:
        """``"secret_key"``, ``"jwt"`` or ``None``."""
        return credential_kind(self.http.auth)

    @property
    def sandbox(self) -> bool:
        """True once the client uses a Metrc sandbox credential (:meth:`enter_sandbox`)."""
        return self._sandbox

    @property
    def hostname(self) -> str | None:
        """The Metrc hostname behind the credential, such as ``sandbox-me.metrc.com``.

        It comes from :meth:`whoami`, which is called the first time it's needed.
        """
        who = self._whoami if self._whoami is not None else self.whoami()
        value = who.get("hostname")
        return str(value) if value else None

    # ------------------------------------------------------------------ namespaces

    @property
    def spec(self) -> Registry:
        """The endpoint registry, loaded the first time it is needed."""
        if self._registry is None:
            with self._spec_lock:
                if self._registry is None:
                    raw, source = load_spec(self.http, self.base_url, self._spec_mode)
                    self._registry = Registry(raw, source)
        return self._registry

    def refresh_spec(self) -> Registry:
        """Fetch the live spec now, replacing the copy in use."""
        raw, source = load_spec(self.http, self.base_url, "refresh")
        self._registry = Registry(raw, source)
        return self._registry

    @property
    def secret_keys(self) -> SecretKeys:
        """List, create, rotate and delete secret keys (:class:`~t3api_utils.auth.secret_keys.SecretKeys`)."""
        return SecretKeys(self)

    @property
    def tag_lists(self) -> TagLists:
        """Create, fill and resolve tag lists (:class:`~t3api_utils.tag_lists.TagLists`)."""
        from t3api_utils.tag_lists import TagLists

        return TagLists(self)

    # ------------------------------------------------------------------ low level

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx2.Response:
        return _api.send(self.http, method, url, credential_kind=self.credential_kind, **kwargs)

    def _call(self, method: str, url: str, **kwargs: Any) -> Any:
        return _api.parse(self._send(method, url, **kwargs))

    def _resolve(
        self,
        endpoint: str,
        *,
        method: str | None = None,
        kind: Kind | Iterable[Kind] | None = None,
        path_params: Iterable[str] = (),
    ) -> Endpoint:
        if "?" in endpoint:
            # The spec lookup ignores a query string, so it would be dropped silently.
            raise ValueError(f"{endpoint}: pass query parameters with params= (or license=, filter=...).")
        return self.spec.endpoint(endpoint, method=method, kind=kind, path_params=path_params)

    @staticmethod
    def _fill_path(ep: Endpoint, name: str, path_params: Mapping[str, Any]) -> str:
        placeholders = _PLACEHOLDER.findall(ep.path)
        extra = sorted(set(path_params) - set(placeholders))
        if extra:
            raise TypeError(
                f"{ep.label()} has no path parameter(s) {', '.join(extra)}. "
                f"Use params= for query parameters."
            )
        concrete = name.split("?", 1)[0].rstrip("/")
        if name.startswith("/") and "{" not in concrete and concrete != ep.path:
            if path_params:
                raise TypeError(f"{name} already contains its path parameters.")
            return concrete

        def fill(match: re.Match[str]) -> str:
            key = match.group(1)
            value = path_params.get(key)
            if value is None or value == "":
                raise SpecError(f"{ep.label()} needs {key}=.")
            return quote(str(value), safe="")

        return _PLACEHOLDER.sub(fill, ep.path)

    def _license_for(self, ep: Endpoint, license: Any) -> Any:
        if license is not None:
            return license
        param = ep.param("licenseNumber")
        if param is not None and param.required and self.license:
            return [self.license] if param.is_array else self.license
        return None

    def _check_license(self, license: Any) -> None:
        """In the sandbox, warn once about each license the session doesn't have.

        The sandbox answers a request for another license (a production one,
        say) with an empty 200 rather than an error, so nothing else would
        catch it.
        """
        if not self._sandbox or license is None:
            return
        values = [str(v) for v in license] if isinstance(license, (list, tuple)) else [str(license)]
        if self._session_licenses is None:
            try:
                numbers = {str(lic.get("licenseNumber")) for lic in self.licenses()}
            except APIError as exc:
                logger.debug("Couldn't list the sandbox licenses to check %s: %s", ", ".join(values), exc)
                numbers = set()
            self._session_licenses = frozenset(numbers)
        known = self._session_licenses
        for value in values:
            if known and value not in known and value not in self._warned_licenses:
                self._warned_licenses.add(value)
                logger.warning(
                    "%s isn't one of this sandbox session's licenses (%s). The sandbox answers "
                    "requests for other licenses with no rows instead of an error.",
                    value,
                    ", ".join(sorted(known)),
                )

    @staticmethod
    def _include(ep: Endpoint, include: str | Sequence[str]) -> list[str]:
        """``include=`` as a list (sent repeated), with values the spec doesn't list warned about."""
        raw = include.split(",") if isinstance(include, str) else include
        values = [str(v).strip() for v in raw if str(v).strip()]
        param = ep.param("include")
        allowed = param.choices if param is not None else ()
        unknown = [v for v in values if allowed and v not in allowed]
        if unknown:
            logger.warning(
                "%s doesn't list include value(s) %s in the spec (it lists %s); sending anyway.",
                ep.label(),
                ", ".join(unknown),
                ", ".join(allowed),
            )
        return values

    @staticmethod
    def _check_body(ep: Endpoint, json: Any) -> None:
        """Warn when a JSON body's top-level type doesn't match the spec's."""
        if ep.body_is_array and isinstance(json, Mapping):
            logger.warning(
                "%s takes a list of objects, even for one object: send json=[body]. The server "
                "answers a single object with a 500.",
                ep.label(),
            )
        elif ep.body_type == "object" and isinstance(json, (list, tuple)):
            logger.warning("%s takes one object, not a list.", ep.label())

    def _prepare(
        self,
        method: str,
        endpoint: str,
        *,
        license: Any,
        params: Mapping[str, Any] | None,
        has_body: bool,
        submit: bool | None,
        path_params: Mapping[str, Any],
        kind: Kind | Iterable[Kind] | None = None,
        include: str | Sequence[str] | None = None,
        dynamic: bool = False,
    ) -> tuple[Endpoint, str, dict[str, Any]]:
        concrete = endpoint.startswith("/") and "{" not in endpoint
        ep = self._resolve(endpoint, method=method, kind=kind, path_params=path_params.keys())
        url = self._fill_path(ep, endpoint, path_params)
        query: dict[str, Any] = dict(params or {})
        lic = self._license_for(ep, license)
        if lic is not None:
            query["licenseNumber"] = lic
            self._check_license(lic)
        if include:
            query["include"] = self._include(ep, include)
        if dynamic:
            if ep.param("applyDynamicValidation") is None:
                raise ValueError(
                    f"{ep.label()} doesn't offer dynamic validation (the spec lists no "
                    "applyDynamicValidation parameter for it)."
                )
            query["applyDynamicValidation"] = "true"
        if submit is not None:
            if ep.kind == "metrc_write":
                if submit:
                    query["submit"] = "true"
            elif ep.kind == "immediate_write":
                raise ValueError(
                    f"{ep.label()} takes effect immediately and has no dry run, so it doesn't "
                    "take submit=. Leave it out."
                )
            else:
                raise ValueError(f"submit= only applies to writes; {ep.label()} is a {ep.kind}.")
        path_values = dict(path_params)
        if concrete:
            path_values.update({p.name: "given" for p in ep.path_params})
        self.spec.check_params(
            ep, query, path_values, has_body=has_body, python_names={"licenseNumber": "license"}
        )
        return ep, url, query

    # ------------------------------------------------------------------ requests

    def _execute(
        self,
        method: str,
        endpoint: str,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        submit: bool | None = None,
        timeout: float | None = None,
        path_params: Mapping[str, Any],
        include: str | Sequence[str] | None = None,
        dynamic: bool = False,
    ) -> tuple[Endpoint, httpx2.Response]:
        has_body = json is not None or files is not None or data is not None
        ep, url, query = self._prepare(
            method,
            endpoint,
            license=license,
            params=params,
            has_body=has_body,
            submit=submit,
            path_params=path_params,
            include=include,
            dynamic=dynamic,
        )
        kwargs: dict[str, Any] = {"params": query}
        if json is not None:
            self._check_body(ep, json)
            kwargs["json"] = json
        if files is not None:
            kwargs["files"] = files
        if data is not None:
            kwargs["data"] = data
        if timeout is not None:
            kwargs["timeout"] = timeout
        return ep, self._send(ep.method, url, **kwargs)

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        submit: bool | None = None,
        timeout: float | None = None,
        **path_params: Any,
    ) -> Any:
        """Call any endpoint in the spec.

        ``endpoint`` is an endpoint ID (``METRC_ACTIVE_ITEMS``) or a path
        (``/v2/items`` or ``/v2/items/{object_id}``). Path parameters are
        keyword arguments. ``license`` fills ``licenseNumber``; it defaults to
        the client's license when the endpoint requires one.

        Returns parsed JSON, ``bytes`` for other content, or ``None`` for an
        empty body.
        """
        _, response = self._execute(
            method,
            endpoint,
            license=license,
            params=params,
            json=json,
            files=files,
            data=data,
            submit=submit,
            timeout=timeout,
            path_params=path_params,
        )
        return _api.parse(response)

    def get(
        self,
        endpoint: str,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        include: str | Sequence[str] | None = None,
        timeout: float | None = None,
        **path_params: Any,
    ) -> Any:
        """GET an endpoint. ``object_id=`` picks the single-object route.

        ``include=`` attaches related data on super endpoints, as in :meth:`collect`.
        """
        _, response = self._execute(
            "GET", endpoint, license=license, params=params, timeout=timeout,
            path_params=path_params, include=include,
        )  # fmt: skip
        return _api.parse(response)

    def download(
        self,
        endpoint: str,
        to: str | Path,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        **path_params: Any,
    ) -> Path:
        """Save a ``file`` endpoint (a manifest or COA PDF, an item photo) to ``to``.

        The response is streamed to a temporary file next to ``to`` and renamed
        when it's complete, so a failed download never leaves a partial file.
        Parent folders are created. Returns the path.

        ```python
        client.download("/v2/transfers/manifest", "manifests/0001234567.pdf",
                        license="LIC-00001", params={"manifestNumber": "0001234567"})
        ```
        """
        _, url, query = self._prepare(
            "GET", endpoint, license=license, params=params, has_body=False, submit=None,
            path_params=path_params, kind="file",
        )  # fmt: skip
        kwargs: dict[str, Any] = {"params": query}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return _api.download(self.http, url, Path(to), credential_kind=self.credential_kind, **kwargs)

    def _write(
        self,
        method: str,
        endpoint: str,
        *,
        license: Any,
        params: Mapping[str, Any] | None,
        json: Any,
        files: Any,
        data: Any,
        submit: bool | None,
        timeout: float | None,
        path_params: Mapping[str, Any],
        dynamic: bool = False,
    ) -> WriteResult:
        ep, response = self._execute(
            method,
            endpoint,
            license=license,
            params=params,
            json=json,
            files=files,
            data=data,
            submit=submit,
            timeout=timeout,
            path_params=path_params,
            dynamic=dynamic,
        )
        body = _api.parse(response)
        dry_run = ep.kind == "metrc_write" and not submit
        if dry_run:
            logger.info("dry run: pass submit=True to send %s to Metrc", ep.label())
        return WriteResult(dry_run=dry_run, message=_message(body), data=body, response=response)

    def post(
        self,
        endpoint: str,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        submit: bool | None = None,
        dynamic: bool = False,
        timeout: float | None = None,
        **path_params: Any,
    ) -> WriteResult:
        """POST. Routes that write to Metrc are a dry run unless ``submit=True``.

        Most Metrc write routes take a list, even for one object (``json=[body]``).
        ``dynamic=True`` asks T3 to run the route's dynamic checks as well
        (``applyDynamicValidation``). See the writes guide.
        """
        return self._write(
            "POST", endpoint, license=license, params=params, json=json, files=files, data=data,
            submit=submit, timeout=timeout, path_params=path_params, dynamic=dynamic,
        )  # fmt: skip

    def put(
        self,
        endpoint: str,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        submit: bool | None = None,
        dynamic: bool = False,
        timeout: float | None = None,
        **path_params: Any,
    ) -> WriteResult:
        """PUT. Routes that write to Metrc are a dry run unless ``submit=True``.

        Most Metrc write routes take a list, even for one object (``json=[body]``).
        ``dynamic=True`` asks T3 to run the route's dynamic checks as well
        (``applyDynamicValidation``). See the writes guide.
        """
        return self._write(
            "PUT", endpoint, license=license, params=params, json=json, files=files, data=data,
            submit=submit, timeout=timeout, path_params=path_params, dynamic=dynamic,
        )  # fmt: skip

    def patch(
        self,
        endpoint: str,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        submit: bool | None = None,
        dynamic: bool = False,
        timeout: float | None = None,
        **path_params: Any,
    ) -> WriteResult:
        """PATCH. Routes that write to Metrc are a dry run unless ``submit=True``.

        Most Metrc write routes take a list, even for one object (``json=[body]``).
        ``dynamic=True`` asks T3 to run the route's dynamic checks as well
        (``applyDynamicValidation``). See the writes guide.
        """
        return self._write(
            "PATCH", endpoint, license=license, params=params, json=json, files=files, data=data,
            submit=submit, timeout=timeout, path_params=path_params, dynamic=dynamic,
        )  # fmt: skip

    def delete(
        self,
        endpoint: str,
        *,
        license: Any = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        submit: bool | None = None,
        dynamic: bool = False,
        timeout: float | None = None,
        **path_params: Any,
    ) -> WriteResult:
        """DELETE. Routes that write to Metrc are a dry run unless ``submit=True``."""
        return self._write(
            "DELETE", endpoint, license=license, params=params, json=json, files=None, data=None,
            submit=submit, timeout=timeout, path_params=path_params, dynamic=dynamic,
        )  # fmt: skip

    # ------------------------------------------------------------------ collections

    def _license_list(self, ep: Endpoint, license: LicenseArg) -> list[str | None]:
        if license is None:
            return [self._license_for(ep, None)]
        if isinstance(license, str):
            return [license]
        licenses = list(license)
        if not licenses:
            raise ValueError("license= is an empty list.")
        return list(licenses)

    def _collection_plan(
        self,
        endpoint: str,
        *,
        license: LicenseArg,
        filter: str | Sequence[str] | None,
        filter_logic: str | None,
        sort: str | None,
        mask: str | Sequence[str] | None,
        page_size: int | None,
        params: Mapping[str, Any] | None,
        path_params: Mapping[str, Any],
        include: str | Sequence[str] | None = None,
    ) -> tuple[Endpoint, list[tuple[str, dict[str, Any]]]]:
        ep = self._resolve(endpoint, method="GET", kind="collection", path_params=path_params.keys())
        base: dict[str, Any] = dict(params or {})
        if filter:
            base["filter"] = [filter] if isinstance(filter, str) else list(filter)
        if filter_logic:
            base["filterLogic"] = filter_logic
        if sort:
            base["sort"] = sort
        if mask:
            base["collectionMask"] = mask if isinstance(mask, str) else ",".join(mask)
        if include:
            base["include"] = self._include(ep, include)
        if page_size is not None and ep.param("pageSize") is not None:
            base["pageSize"] = page_size
        url = self._fill_path(ep, endpoint, path_params)
        concrete = endpoint.startswith("/") and "{" not in endpoint
        path_values = dict(path_params)
        if concrete:
            path_values.update({p.name: "given" for p in ep.path_params})
        plans: list[tuple[str, dict[str, Any]]] = []
        for lic in self._license_list(ep, license):
            query = dict(base)
            if lic is not None:
                query["licenseNumber"] = lic
                self._check_license(lic)
            self.spec.check_params(
                ep, query, path_values, has_body=False, python_names=COLLECTION_PARAM_NAMES
            )
            plans.append((url, query))
        return ep, plans

    def collect(
        self,
        endpoint: str,
        *,
        license: LicenseArg = None,
        filter: str | Sequence[str] | None = None,
        filter_logic: Literal["and", "or"] | None = None,
        sort: str | None = None,
        mask: str | Sequence[str] | None = None,
        include: str | Sequence[str] | None = None,
        page_size: int | None = 100,
        progress: bool | None = None,
        params: Mapping[str, Any] | None = None,
        **path_params: Any,
    ) -> list[dict[str, Any]]:
        """Load every page of a collection, in parallel, as one list.

        Args:
            endpoint: A collection's endpoint ID or path.
            license: One license, or a list to load one after another.
                Defaults to the client's license.
            filter: ``field__op:value`` filters (one string or a list).
            filter_logic: ``"and"`` (default on the server) or ``"or"``.
            sort: ``field:asc`` or ``field:desc``.
            mask: Fields to return (``collectionMask``).
            include: Related data to attach, on super collections
                (``/v2/packages/active/super`` and so on): a list such as
                ``["labResults", "history"]``. Each value is sent as its own
                ``include`` parameter. Values the spec doesn't list are warned about.
            page_size: Rows per page.
            progress: Show a progress bar. Defaults to on when stderr is a terminal.
            params: Any other query parameters, by their spec names.

        A page that still fails after retries fails the whole call.
        """
        ep, plans = self._collection_plan(
            endpoint, license=license, filter=filter, filter_logic=filter_logic, sort=sort,
            mask=mask, page_size=page_size, params=params, path_params=path_params,
            include=include,
        )  # fmt: skip
        rows: list[dict[str, Any]] = []
        for url, query in plans:
            label = ep.id or ep.path
            if query.get("licenseNumber"):
                label += f" · {query['licenseNumber']}"
            rows.extend(self._load_pages(url, query, label=label, progress=progress))
        return rows

    def iter_rows(
        self,
        endpoint: str,
        *,
        license: LicenseArg = None,
        filter: str | Sequence[str] | None = None,
        filter_logic: Literal["and", "or"] | None = None,
        sort: str | None = None,
        mask: str | Sequence[str] | None = None,
        include: str | Sequence[str] | None = None,
        page_size: int | None = 100,
        params: Mapping[str, Any] | None = None,
        **path_params: Any,
    ) -> Iterator[dict[str, Any]]:
        """Like :meth:`collect`, but yields rows one page at a time."""
        _, plans = self._collection_plan(
            endpoint, license=license, filter=filter, filter_logic=filter_logic, sort=sort,
            mask=mask, page_size=page_size, params=params, path_params=path_params,
            include=include,
        )  # fmt: skip
        for url, query in plans:
            yield from self._iter_pages(url, query)

    def _get_page(self, url: str, query: Mapping[str, Any], page: int) -> dict[str, Any]:
        params = dict(query)
        if page > 1:
            params["page"] = page
        body = self._call("GET", url, params=params)
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise SpecError(f"GET {url} didn't return a paginated collection.")
        return body

    def _iter_pages(self, url: str, query: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        seen: set[Any] = set()
        dropped = 0
        page, total = 1, 1
        while page <= total:
            body = self._get_page(url, query, page)
            total = int(body.get("totalPages") or 1)
            for row in body["data"]:
                if _is_duplicate(row, seen):
                    dropped += 1
                    continue
                yield row
            page += 1
        _log_dropped(dropped, url)

    def _load_pages(
        self,
        url: str,
        query: Mapping[str, Any],
        *,
        label: str,
        progress: bool | None = None,
    ) -> list[dict[str, Any]]:
        first = self._get_page(url, query, 1)
        total = int(first.get("totalPages") or 1)
        pages: dict[int, list[dict[str, Any]]] = {1: first["data"]}
        show = _console.stderr_is_terminal() if progress is None else progress
        if total > 1:
            with _console.progress_bar(label, total, show and total > 1) as advance:
                advance(1)
                self._fetch_rest(url, query, total, pages, advance)
        rows: list[dict[str, Any]] = []
        seen: set[Any] = set()
        dropped = 0
        for number in range(1, total + 1):
            for row in pages[number]:
                if _is_duplicate(row, seen):
                    dropped += 1
                    continue
                rows.append(row)
        _log_dropped(dropped, url)
        return rows

    def _fetch_rest(
        self,
        url: str,
        query: Mapping[str, Any],
        total: int,
        pages: dict[int, list[dict[str, Any]]],
        advance: Callable[[int], None],
    ) -> None:
        workers = min(self.concurrency, total - 1)
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="t3api-page")
        try:
            futures: dict[Future[dict[str, Any]], int] = {
                pool.submit(self._get_page, url, query, number): number
                for number in range(2, total + 1)
            }
            pending: set[Future[dict[str, Any]]] = set(futures)
            while pending:
                done, pending = wait(pending, return_when=FIRST_EXCEPTION)
                for future in done:
                    number = futures[future]
                    exc = future.exception()
                    if exc is not None:
                        exc.add_note(f"Failed loading page {number} of {total} from {url}.")
                        raise exc
                    pages[number] = future.result()["data"]
                    advance(1)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    # ------------------------------------------------------------------ writes, reports

    def bulk(
        self,
        endpoint: str,
        rows: Iterable[Mapping[str, Any]],
        *,
        license: str | None = None,
        method: str | None = None,
        submit: bool | Literal["ask"] = False,
        confirm: bool = False,
        on_error: OnError = "stop",
        log_to: str | Path | None = None,
        progress: bool | None = None,
        dynamic: bool = False,
        batch_size: int = 1,
        **path_params: Any,
    ) -> BulkResult:
        """Validate every row with a dry run, then submit (see :func:`t3api_utils.writes.bulk`)."""
        from t3api_utils.writes import bulk

        return bulk(
            self, endpoint, rows, license=license, method=method, submit=submit, confirm=confirm,
            on_error=on_error, log_to=log_to, progress=progress, path_params=path_params,
            dynamic=dynamic, batch_size=batch_size,
        )  # fmt: skip

    def report(
        self,
        endpoint: str,
        *,
        licenses: LicenseArg = None,
        format: str | None = None,
        to: str | Path | None = None,
        columns: str | Sequence[str] | None = None,
        filter: str | Sequence[str] | None = None,
        filter_logic: Literal["and", "or"] | None = None,
        sort: str | None = None,
        row_limit: int | None = None,
        delivery: Literal["inline", "email"] | None = None,
        email: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Download a server-side report (see :func:`t3api_utils.reports.report`)."""
        from t3api_utils.reports import report

        return report(
            self, endpoint, licenses=licenses, format=format, to=to, columns=columns,
            filter=filter, filter_logic=filter_logic, sort=sort, row_limit=row_limit,
            delivery=delivery, email=email, params=params,
        )  # fmt: skip

    def report_url(
        self,
        endpoint: str,
        *,
        licenses: LicenseArg = None,
        format: str = "csv",
        columns: str | Sequence[str] | None = None,
        filter: str | Sequence[str] | None = None,
        filter_logic: Literal["and", "or"] | None = None,
        sort: str | None = None,
        row_limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> str:
        """A report URL with the secret key in it, for spreadsheets (see :func:`t3api_utils.reports.report_url`)."""
        from t3api_utils.reports import report_url

        return report_url(
            self, endpoint, licenses=licenses, format=format, columns=columns, filter=filter,
            filter_logic=filter_logic, sort=sort, row_limit=row_limit, params=params,
        )  # fmt: skip

    # ------------------------------------------------------------------ helpers

    def whoami(self) -> dict[str, Any]:
        """The authenticated user (``GET /v2/auth/whoami``)."""
        data = self._call("GET", "/v2/auth/whoami")
        self._whoami = data if isinstance(data, dict) else {}
        return self._whoami

    def licenses(self) -> list[dict[str, Any]]:
        """Licenses this credential can use (``GET /v2/licenses``)."""
        data = self._call("GET", "/v2/licenses")
        return data if isinstance(data, list) else []

    def states(self) -> list[dict[str, Any]]:
        """Every Metrc state, with ``requiresEmail`` and ``requiresOtp`` (cached)."""
        return fetch_states(self.http, self.base_url) or []

    def enter_sandbox(self) -> None:
        """Swap the credential for a Metrc sandbox JWT (``POST /v2/auth/sandbox``).

        It also clears :attr:`license`: the sandbox has its own licenses, and
        it answers a request for a production license with no rows rather
        than an error. Then it calls :meth:`whoami` and logs the sandbox
        hostname at INFO.
        """
        data = self._call("POST", "/v2/auth/sandbox")
        self.http.auth = BearerAuth(_api.require_field(data, "accessToken", "POST /v2/auth/sandbox"))
        self._sandbox = True
        self.license = None
        self._session_licenses = None
        self._warned_licenses.clear()
        logger.info("Using the Metrc sandbox (%s).", self.whoami().get("hostname") or "unknown host")

    def pick_license(self) -> str:
        """Pick one of this credential's licenses in a terminal; returns the license number."""
        from t3api_utils.pickers import pick_license

        return pick_license(self.licenses())

    def pick_endpoint(self, kind: Kind | None = "collection") -> Endpoint:
        """Pick an endpoint from the spec in a terminal."""
        from t3api_utils.pickers import pick_endpoint

        return pick_endpoint(self.spec.list(kind))

    @property
    def secret_key(self) -> str | None:
        """The secret key in use, if the credential is one."""
        auth = self.http.auth
        return auth.key if isinstance(auth, SecretKeyAuth) else None


def _is_duplicate(row: Any, seen: set[Any]) -> bool:
    if not isinstance(row, dict):
        return False
    row_id = row.get("id")
    if row_id is None:
        return False
    try:
        if row_id in seen:
            return True
        seen.add(row_id)
    except TypeError:
        return False
    return False


def _log_dropped(dropped: int, url: str) -> None:
    if dropped:
        logger.info(
            "Dropped %d duplicate row(s) from %s: the data changed while pages were loading.",
            dropped,
            url,
        )
