# Writes

## Two kinds of write

How a write behaves depends on the route's [kind](endpoints-and-spec.md#endpoint-kinds)
in the spec:

| Route kind | `submit` left out | `submit=True` |
|---|---|---|
| `metrc_write` (85 routes today: creating packages, discontinuing items, adjusting, finishing, ...) | **Dry run.** T3 validates the request and nothing reaches Metrc. | Sent to Metrc. |
| `immediate_write` (28 routes: auth, tag lists, label layouts, saved reports, support tickets, photo uploads) | Takes effect immediately. | Raises `ValueError`: the route has no dry run. |

So a forgotten `submit=True` costs you a harmless dry run, never an accidental
change in Metrc. Passing `submit=` at all, `True` or `False`, to an immediate
route raises `ValueError`, so you can't mistake one kind for the other.

Check a route's kind with `t3api endpoints discontinue` or
`client.spec.endpoint("/v2/items/discontinue").kind`.

## One write

```python
import t3api_utils as t3

with t3.connect() as client:
    lic = "LIC-00001"

    # Dry run: validated by T3, not sent to Metrc
    result = client.post("/v2/items/discontinue", license=lic, json={"id": 12345})
    print(result.dry_run, result.message)      # True Dry run

    # The real thing
    result = client.post("/v2/items/discontinue", license=lic, json={"id": 12345}, submit=True)
    print(result.dry_run, result.message)      # False Success
```

`post()`, `put()`, `patch()` and `delete()` take:

| Argument | What it does |
|---|---|
| `endpoint` | A path (write routes don't have endpoint IDs in today's spec). |
| `license` | Fills `licenseNumber`. Defaults to the client's default license when the route requires one. |
| `json` | The request body. |
| `params` | Other query parameters, by their spec names. |
| `files`, `data` | Multipart or form bodies, as in httpx2 (not on `delete()`). |
| `submit` | `True` sends a Metrc write for real. |
| `timeout` | Override the request timeout for this call. |
| `**path_params` | Path parameters such as `tag_list_id=`. |

Each returns a `WriteResult`:

| Attribute | What it holds |
|---|---|
| `dry_run` | `True` if T3 only validated the request. |
| `message` | The server's `message`: `"Dry run"` or `"Success"` for Metrc writes. |
| `data` | The parsed response body. |
| `response` | The `httpx2.Response`. |

Every dry run also logs `dry run: pass submit=True to send ... to Metrc` at
INFO on the `t3api_utils` logger, so a script that forgot `submit=True` says so
when logging is on.

**Errors.** A rejected write raises an `APIError` subclass, usually
`ValidationError` (400 or 422), with the server's explanation in `.detail` and
any per-field problems in `.errors`:

```python
try:
    client.post("/v2/items/discontinue", license=lic, json={"id": 12345}, submit=True)
except t3.ValidationError as exc:
    print(exc.detail)
```

**Never repeated.** A write is retried only when T3 answered 429 (rate
limited, so it was rejected) or the connection failed before the request was
sent. A 5xx or a timeout after sending might mean the write reached Metrc, so
it's raised to you instead of being sent again. See
[Retries](errors-and-logging.md#retries).

Many create routes accept an array of objects in one request. Send the array
as `json=` yourself when you want one request for many rows; use `bulk()`
below when you want each row validated and reported separately.

## Many writes: bulk()

`bulk()` sends one request per row, safely:

```python
items = client.collect(
    "METRC_ACTIVE_ITEMS",
    license=lic,
    filter=["name__startswith:TEST"],
    mask=["id", "name"],
)
result = client.bulk(
    "/v2/items/discontinue",
    rows=[{"id": item["id"]} for item in items],
    license=lic,
    submit=True,
    log_to="discontinue-results.csv",
)
print(result.summary())     # POST /v2/items/discontinue: 42 submitted
```

For a `metrc_write` route:

1. **Validate.** Every row is sent as a dry run, and each result recorded.
2. **If any row failed validation**, nothing is submitted yet:
    - With `submit=False` (the default), `bulk()` stops here and returns.
    - In a terminal, it shows the failures and asks whether to submit only the
      valid rows (default no).
    - Without a terminal it returns without submitting, unless you passed
      `on_error="skip"`, which submits the valid rows without asking.
3. **Submit**, only with `submit=True`: each valid row is sent with
   `submit=true`, one at a time, in order. With `on_error="stop"` (the
   default), the first row that fails stops the rest; `on_error="skip"` carries
   on.
4. **Return** a `BulkResult`. `log_to=` also writes it to a CSV file.

An `AuthError` stops `bulk()` immediately whatever `on_error` says, since every
later row would fail the same way.

### Validate first, submit later

Leave out `submit=True` to check every row without touching Metrc:

```python
check = client.bulk("/v2/items/discontinue", rows=rows, license=lic)
if check.ok:
    client.bulk("/v2/items/discontinue", rows=rows, license=lic, submit=True)
else:
    for r in check.invalid:
        print(r.index, r.row, r.message)
```

### Row statuses

| Status | Meaning |
|---|---|
| `valid` | Passed the dry run and wasn't submitted (yet). |
| `invalid` | Failed the dry run. `message` says why. |
| `submitted` | Sent with `submit=true` and accepted. |
| `failed` | Sent with `submit=true` and rejected. `message` says why. |
| `not_sent` | Never sent, because an earlier row failed with `on_error="stop"`. |

### BulkResult

| Member | What it gives you |
|---|---|
| `rows` (or iterate the result) | One `RowResult` per input row, in input order, with `index`, `row`, `status`, `message`, `data` and `error` (the `APIError`, if any). |
| `ok` | `True` when no row was invalid or failed. |
| `submitted` | `True` if the submit pass ran. |
| `invalid`, `failed` | The rows with that status. |
| `by_status("valid")` | The rows with any status. |
| `counts()` | `{"submitted": 40, "failed": 2}` and so on. |
| `summary()` | One line, e.g. `POST /v2/items/discontinue: 2 failed, 40 submitted`. |
| `to_csv(path)` | One line per row: `index`, `status`, `message`, and the row as JSON. |

### Immediate routes

Immediate routes have no dry run, so `bulk()` can't validate first. It refuses
to run unless you pass `confirm=True`:

```python
tl = client.tag_lists.create("Room A", license=lic)
labels = ["1A4000000000000000000001", "1A4000000000000000000002"]

client.bulk(
    "/v2/tag-lists/{tag_list_id}/entries",
    rows=[{"entries": [{"handle": label}]} for label in labels],
    method="POST",
    tag_list_id=tl.id,
    confirm=True,
)
```

(For tag lists, `client.tag_lists` is simpler; this only shows the shape.)
`method=` picks the operation when a path has several write methods.

## A complete script

This is `scripts/discontinue-items.py` from the repository. It discontinues
every item named in `input.csv`, which has a `name` column:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["t3api-utils>=2.0"]
# ///
"""Discontinue every item named in input.csv."""

from pathlib import Path

import t3api_utils as t3

INPUT = Path(__file__).with_name("input.csv")


def main() -> None:
    with t3.connect() as client:
        license = client.license or client.pick_license()
        items = client.collect("METRC_ACTIVE_ITEMS", license=license, mask=["id", "name"])
        matches = t3.filter_rows(items, INPUT, columns=["name"], on_unmatched="error")
        result = client.bulk(
            "/v2/items/discontinue",
            rows=[{"id": item["id"]} for item in matches],
            license=license,
            submit=True,
            log_to="discontinue-results.csv",
        )
        print(result.summary())


if __name__ == "__main__":
    main()
```

`on_unmatched="error"` stops the script before any write if a name in the CSV
doesn't match an active item.
