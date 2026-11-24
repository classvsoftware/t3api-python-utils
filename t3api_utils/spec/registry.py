"""Endpoints from the OpenAPI spec: classification, lookup and parameter checks."""

from __future__ import annotations

import builtins
import difflib
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from t3api_utils.errors import SpecError, UnknownEndpoint
from t3api_utils.spec.loader import SpecSource

logger = logging.getLogger("t3api_utils")

Kind = Literal[
    "collection", "report", "metrc_write", "immediate_write", "file", "object", "other"
]
KINDS: tuple[str, ...] = get_args(Kind)

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PAGINATION_REF = "#/components/schemas/Pagination"

# Query parameters the client manages itself, so callers never pass them.
MANAGED_QUERY_PARAMS = frozenset({"page", "submit", "secretKey"})


@dataclass(frozen=True)
class Param:
    """One operation parameter, with ``$ref``s resolved."""

    name: str
    location: str
    required: bool = False
    description: str = ""
    schema: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_array(self) -> bool:
        return self.schema.get("type") == "array"

    @property
    def choices(self) -> tuple[str, ...]:
        """The values the spec allows (its ``enum``, or its items' for an array), else ``()``."""
        schema = self.schema.get("items") if self.is_array else self.schema
        enum = schema.get("enum") if isinstance(schema, Mapping) else None
        return tuple(str(v) for v in enum) if isinstance(enum, list) else ()


@dataclass(frozen=True)
class Endpoint:
    """One operation (method + path) in the spec.

    Attributes:
        body_type: The JSON schema ``type`` of the JSON request body
            (``"array"`` or ``"object"``), or ``None`` when the route takes no
            JSON body.
    """

    id: str | None
    method: str
    path: str
    kind: Kind
    tags: tuple[str, ...] = ()
    summary: str = ""
    params: tuple[Param, ...] = ()
    body_required: bool = False
    has_body: bool = False
    response_types: tuple[str, ...] = ()
    public: bool = False
    body_type: str | None = None

    @property
    def body_is_array(self) -> bool:
        """True when the JSON body is a list. Most Metrc write routes take one, even for one object."""
        return self.body_type == "array"

    def param(self, name: str) -> Param | None:
        for p in self.params:
            if p.name == name:
                return p
        return None

    @property
    def path_params(self) -> tuple[Param, ...]:
        return tuple(p for p in self.params if p.location == "path")

    @property
    def query_params(self) -> tuple[Param, ...]:
        return tuple(p for p in self.params if p.location == "query")

    @property
    def is_write(self) -> bool:
        return self.method not in READ_METHODS

    def label(self) -> str:
        name = f" ({self.id})" if self.id else ""
        return f"{self.method} {self.path}{name}"

    def __str__(self) -> str:
        return self.label()


class _Resolver:
    def __init__(self, spec: Mapping[str, Any]) -> None:
        self.spec = spec

    def deref(self, node: Any, depth: int = 0) -> Any:
        while isinstance(node, Mapping) and "$ref" in node and depth < 20:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                return node
            target: Any = self.spec
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, Mapping) or part not in target:
                    return node
                target = target[part]
            node = target
            depth += 1
        return node


def _json_schema(response: Mapping[str, Any], resolver: _Resolver) -> Any:
    content = resolver.deref(response).get("content", {}) or {}
    for ctype, media in content.items():
        if "json" in ctype:
            return media.get("schema")
    return None


def _is_paginated(schema: Any, resolver: _Resolver) -> bool:
    if not isinstance(schema, Mapping):
        return False
    if schema.get("$ref") == PAGINATION_REF:
        return True
    resolved = resolver.deref(schema)
    if not isinstance(resolved, Mapping):
        return False
    for part in resolved.get("allOf", []) or []:
        if isinstance(part, Mapping) and part.get("$ref") == PAGINATION_REF:
            return True
    return False


def _body_type(body: Mapping[str, Any], resolver: _Resolver) -> str | None:
    for ctype, media in (body.get("content") or {}).items():
        if "json" in ctype and isinstance(media, Mapping):
            schema = resolver.deref(media.get("schema") or {})
            kind = schema.get("type") if isinstance(schema, Mapping) else None
            return str(kind) if isinstance(kind, str) else None
    return None


def _response_types(op: Mapping[str, Any], resolver: _Resolver) -> tuple[str, ...]:
    types: list[str] = []
    for response in (op.get("responses") or {}).values():
        content = resolver.deref(response).get("content", {}) or {}
        for ctype in content:
            if ctype not in types:
                types.append(ctype)
    return tuple(types)


def classify(
    method: str,
    path: str,
    op: Mapping[str, Any],
    params: Iterable[Param],
    resolver: _Resolver,
) -> Kind:
    """Give an operation exactly one kind, from its structure alone."""
    method = method.upper()
    params = list(params)
    if method == "GET":
        ok = (op.get("responses") or {}).get("200")
        if ok is not None and _is_paginated(_json_schema(ok, resolver), resolver):
            return "collection"
    types = _response_types(op, resolver)
    if "text/csv" in types or XLSX in types:
        return "report"
    if method not in READ_METHODS:
        if any(p.name == "submit" and p.location == "query" for p in params):
            return "metrc_write"
        return "immediate_write"
    if method == "GET" and any(t == "application/pdf" or t.startswith("image/") for t in types):
        return "file"
    if method == "GET" and "{object_id}" in path:
        return "object"
    return "other"


def _template_regex(path: str) -> re.Pattern[str]:
    pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path))
    return re.compile(f"^{pattern}$")


class Registry:
    """Every operation in one copy of the spec."""

    def __init__(self, spec: Mapping[str, Any], source: SpecSource | None = None) -> None:
        self.raw = spec
        self.source = source
        self._resolver = _Resolver(spec)
        self.endpoints: builtins.list[Endpoint] = self._build()
        self._by_id: dict[str, builtins.list[Endpoint]] = {}
        self._by_path: dict[str, builtins.list[Endpoint]] = {}
        for ep in self.endpoints:
            if ep.id:
                self._by_id.setdefault(ep.id, []).append(ep)
            self._by_path.setdefault(ep.path, []).append(ep)
        self._templates = [(_template_regex(p), p) for p in self._by_path if "{" in p]

    # ------------------------------------------------------------------ building

    def _params(self, item: Mapping[str, Any], op: Mapping[str, Any]) -> tuple[Param, ...]:
        merged: dict[tuple[str, str], Param] = {}
        for raw in list(item.get("parameters") or []) + list(op.get("parameters") or []):
            p = self._resolver.deref(raw)
            if not isinstance(p, Mapping) or "name" not in p:
                continue
            schema = self._resolver.deref(p.get("schema") or {})
            param = Param(
                name=str(p["name"]),
                location=str(p.get("in", "query")),
                required=bool(p.get("required", False)) or p.get("in") == "path",
                description=str(p.get("description") or ""),
                schema=schema if isinstance(schema, Mapping) else {},
            )
            merged[(param.location, param.name)] = param
        return tuple(merged.values())

    def _build(self) -> builtins.list[Endpoint]:
        global_security = self.raw.get("security")
        endpoints: builtins.list[Endpoint] = []
        for path, item in (self.raw.get("paths") or {}).items():
            if not isinstance(item, Mapping):
                continue
            for method in HTTP_METHODS:
                op = item.get(method)
                if not isinstance(op, Mapping):
                    continue
                params = self._params(item, op)
                body = self._resolver.deref(op.get("requestBody") or {})
                security = op.get("security", global_security)
                endpoint_id = op.get("x-t3-endpoint-id")
                summary = str(op.get("summary") or "").strip()
                if endpoint_id and summary.endswith(f" · {endpoint_id}"):
                    summary = summary[: -len(f" · {endpoint_id}")].rstrip()
                endpoints.append(
                    Endpoint(
                        id=str(endpoint_id) if endpoint_id else None,
                        method=method.upper(),
                        path=str(path),
                        kind=classify(method, path, op, params, self._resolver),
                        tags=tuple(str(t) for t in op.get("tags") or ()),
                        summary=summary,
                        params=params,
                        has_body=bool(body),
                        body_required=bool(body.get("required", False)) if body else False,
                        response_types=_response_types(op, self._resolver),
                        public=security == [],
                        body_type=_body_type(body, self._resolver) if body else None,
                    )
                )
        return endpoints

    # ------------------------------------------------------------------ discovery

    @property
    def version(self) -> str:
        info = self.raw.get("info") or {}
        return str(info.get("version", ""))

    def list(self, kind: Kind | None = None) -> builtins.list[Endpoint]:
        """Every endpoint, or every endpoint of one kind."""
        if kind is not None and kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        return [ep for ep in self.endpoints if kind is None or ep.kind == kind]

    def find(self, query: str = "", kind: Kind | None = None) -> builtins.list[Endpoint]:
        """Endpoints whose ID, path, summary or tags contain every word of ``query``."""
        words = query.lower().split()
        found = []
        for ep in self.list(kind):
            text = " ".join([ep.id or "", ep.path, ep.summary, *ep.tags]).lower()
            if all(w in text for w in words):
                found.append(ep)
        return found

    def ids(self) -> builtins.list[str]:
        return sorted(self._by_id)

    def endpoint(
        self,
        name: str,
        *,
        method: str | None = None,
        kind: Kind | Iterable[Kind] | None = None,
        path_params: Iterable[str] | None = None,
    ) -> Endpoint:
        """Find one operation by endpoint ID or path.

        One ID or path can name several operations. ``method``, ``kind`` and
        the names of the path parameters you have narrow it down to one.
        """
        candidates = self.candidates(name)
        if not candidates:
            raise UnknownEndpoint(name, self._suggest(name))

        pool = candidates
        if method is not None:
            pool = [ep for ep in pool if ep.method == method.upper()]
        kinds: set[str] | None = None
        if kind is not None:
            kinds = {kind} if isinstance(kind, str) else set(kind)
            pool = [ep for ep in pool if ep.kind in kinds]
        if not pool:
            wanted = " ".join(
                part for part in (method and method.upper(), kinds and "/".join(sorted(kinds))) if part
            )
            available = "; ".join(ep.label() + f" [{ep.kind}]" for ep in candidates)
            raise SpecError(f"{name!r} has no {wanted} operation. It has: {available}.")
        if len(pool) == 1:
            return pool[0]

        given = set(path_params or ())
        fillable = [ep for ep in pool if {p.name for p in ep.path_params} <= given]
        if fillable:
            best = max(len(ep.path_params) for ep in fillable)
            fillable = [ep for ep in fillable if len(ep.path_params) == best]
            if len(fillable) == 1:
                return fillable[0]
            pool = fillable
        options = "; ".join(ep.label() + f" [{ep.kind}]" for ep in pool)
        raise SpecError(
            f"{name!r} matches more than one operation: {options}. Pass a path, or the "
            "method or path parameters that pick one."
        )

    def candidates(self, name: str) -> builtins.list[Endpoint]:
        if name in self._by_id:
            return list(self._by_id[name])
        if name.startswith("/"):
            path = name.split("?", 1)[0].rstrip("/") or "/"
            if path in self._by_path:
                return list(self._by_path[path])
            for regex, template in self._templates:
                if regex.match(path):
                    return list(self._by_path[template])
        return []

    def _suggest(self, name: str) -> builtins.list[str]:
        pool = list(self._by_path) if name.startswith("/") else list(self._by_id)
        close = difflib.get_close_matches(name, pool, n=5, cutoff=0.6)
        if not close and not name.startswith("/"):
            needle = name.upper()
            close = [i for i in pool if needle in i][:5]
        return close

    # ------------------------------------------------------------------ checks

    def check_params(
        self,
        endpoint: Endpoint,
        query: Mapping[str, Any],
        path_values: Mapping[str, Any],
        *,
        has_body: bool,
        python_names: Mapping[str, str] | None = None,
    ) -> None:
        """Raise :class:`SpecError` for missing required parameters, warn about unknown ones."""
        names = dict(python_names or {})
        missing: builtins.list[str] = []
        for p in endpoint.params:
            if not p.required or p.name in MANAGED_QUERY_PARAMS:
                continue
            if p.location == "path" and path_values.get(p.name) in (None, ""):
                missing.append(f"{p.name}= (path)")
            elif p.location == "query" and query.get(p.name) in (None, "", []):
                hint = names.get(p.name)
                missing.append(f"{hint}=" if hint else f"{p.name} (query)")
        if missing:
            raise SpecError(f"{endpoint.label()} needs: {', '.join(missing)}.")
        if endpoint.body_required and not has_body:
            raise SpecError(f"{endpoint.label()} needs a request body (json=...).")

        known = {p.name for p in endpoint.query_params} | MANAGED_QUERY_PARAMS
        unknown = [k for k in query if k not in known]
        if unknown:
            logger.warning(
                "%s doesn't list query parameter(s) %s in the spec; sending anyway.",
                endpoint.label(),
                ", ".join(sorted(unknown)),
            )
