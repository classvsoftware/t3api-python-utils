"""Server-side reports: any endpoint the spec classifies as ``report``."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from t3api_utils import _api
from t3api_utils._http import REPORT_TIMEOUT
from t3api_utils.errors import T3Error

if TYPE_CHECKING:
    from t3api_utils.client import LicenseArg, T3Client

logger = logging.getLogger("t3api_utils")

FORMATS = ("json", "csv", "xlsx", "googleSheets")
MAX_LICENSES = 20
_SUFFIX_FORMATS = {".csv": "csv", ".xlsx": "xlsx", ".json": "json"}


def _licenses(client: T3Client, licenses: LicenseArg) -> list[str]:
    if licenses is None:
        if not client.license:
            raise ValueError("Pass licenses=[...] (or set a default license on the profile).")
        values = [client.license]
    else:
        values = [licenses] if isinstance(licenses, str) else list(licenses)
    if not values:
        raise ValueError("licenses= is empty.")
    if len(values) > MAX_LICENSES:
        raise ValueError(f"A report covers at most {MAX_LICENSES} licenses; got {len(values)}.")
    client._check_license(values)
    return values


def _query(
    client: T3Client,
    *,
    licenses: LicenseArg,
    format: str,
    columns: str | Sequence[str] | None,
    filter: str | Sequence[str] | None,
    filter_logic: str | None,
    sort: str | None,
    row_limit: int | None,
    params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if format not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}.")
    query: dict[str, Any] = dict(params or {})
    query["licenseNumber"] = _licenses(client, licenses)
    query["contentType"] = format
    if columns:
        query["columns"] = columns if isinstance(columns, str) else ",".join(columns)
    if filter:
        query["filter"] = [filter] if isinstance(filter, str) else list(filter)
    if filter_logic:
        query["filterLogic"] = filter_logic
    if sort:
        query["sort"] = sort
    if row_limit is not None:
        query["rowLimit"] = row_limit
    return query


def report(
    client: T3Client,
    endpoint: str,
    *,
    licenses: LicenseArg = None,
    format: str | None = None,
    to: str | Path | None = None,
    columns: str | Sequence[str] | None = None,
    filter: str | Sequence[str] | None = None,
    filter_logic: str | None = None,
    sort: str | None = None,
    row_limit: int | None = None,
    delivery: str | None = None,
    email: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> Any:
    """Download a report.

    Args:
        endpoint: A report's endpoint ID (``ITEMS_REPORT``) or path.
        licenses: Up to 20 licenses. Defaults to the client's license.
        format: ``json``, ``csv``, ``xlsx`` or ``googleSheets``. Defaults to
            the extension of ``to``, else ``csv``.
        to: Stream the report to this file and return its path.
        columns: Columns to include, in order.
        filter: ``field__op:value`` filters, as in :meth:`T3Client.collect`.
        filter_logic: ``"and"`` or ``"or"``, as in :meth:`T3Client.collect`.
        sort: ``field:asc`` or ``field:desc``.
        row_limit: Stop after this many rows.
        delivery: ``"email"`` asks the server to email the report to ``email``.
        params: Any other query parameters, by their spec names.

    Returns:
        The file path with ``to=``; parsed JSON for ``format="json"`` or email
        delivery; the sheet URL for ``googleSheets``; otherwise ``bytes``.
    """
    if format is None:
        format = _SUFFIX_FORMATS.get(Path(to).suffix.lower(), "csv") if to else "csv"
    if delivery == "email" and not email:
        raise ValueError('delivery="email" needs email=.')
    if email and delivery != "email" and format != "googleSheets":
        raise ValueError('email= only applies with delivery="email".')
    ep = client._resolve(endpoint, method="GET", kind="report")
    query = _query(
        client, licenses=licenses, format=format, columns=columns, filter=filter,
        filter_logic=filter_logic, sort=sort, row_limit=row_limit, params=params,
    )  # fmt: skip
    if delivery:
        query["delivery"] = delivery
    if email:
        query["email"] = email
    client.spec.check_params(
        ep, query, {}, has_body=False, python_names={"licenseNumber": "licenses"}
    )

    if delivery == "email":
        return client._call("GET", ep.path, params=query, timeout=REPORT_TIMEOUT)
    if format == "googleSheets":
        response = client._send("GET", ep.path, params=query, timeout=REPORT_TIMEOUT)
        body = _api.parse(response)
        sheet_url = body.get("sheetUrl") if isinstance(body, dict) else None
        url = response.headers.get("Location") or sheet_url
        return url or body
    if to is None:
        return client._call("GET", ep.path, params=query, timeout=REPORT_TIMEOUT)
    return _api.download(
        client.http, ep.path, Path(to), credential_kind=client.credential_kind,
        params=query, timeout=REPORT_TIMEOUT,
    )  # fmt: skip


def report_url(
    client: T3Client,
    endpoint: str,
    *,
    licenses: LicenseArg = None,
    format: str = "csv",
    columns: str | Sequence[str] | None = None,
    filter: str | Sequence[str] | None = None,
    filter_logic: str | None = None,
    sort: str | None = None,
    row_limit: int | None = None,
    params: Mapping[str, Any] | None = None,
) -> str:
    """A report URL with the secret key in ``?secretKey=``, for Excel or Google Sheets.

    It sends no request. Anyone with the URL can use the key: deleting the key
    (``t3api keys revoke``) is the only way to cut off a leaked URL, because
    rotating keeps the same key value.
    """
    key = client.secret_key
    if key is None:
        raise T3Error(
            "report_url() needs a secret key: a JWT in a URL would stop working within "
            "24 hours. Run `t3api login` and accept the secret key offer."
        )
    ep = client._resolve(endpoint, method="GET", kind="report")
    query = _query(
        client, licenses=licenses, format=format, columns=columns, filter=filter,
        filter_logic=filter_logic, sort=sort, row_limit=row_limit, params=params,
    )  # fmt: skip
    client.spec.check_params(
        ep, query, {}, has_body=False, python_names={"licenseNumber": "licenses"}
    )
    query["secretKey"] = key
    logger.warning(
        "This report URL contains your secret key. Anyone with it can use the key. "
        "Deleting the key (`t3api keys revoke`) is the only way to cut off a leaked URL."
    )
    return f"{client.base_url}{ep.path}?{urlencode(query, doseq=True)}"
