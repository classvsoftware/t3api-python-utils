# Writes

## Two kinds of write

How a write behaves depends on the route's [kind](endpoints-and-spec.md#endpoint-kinds)
in the spec:

| Route kind | `submit` left out | `submit=True` |
|---|---|---|
| `metrc_write` (85 routes today: creating packages, discontinuing items, adjusting, finishing, ...) | **Dry run.** T3 checks the request (see [What a dry run checks](#what-a-dry-run-checks)) and nothing reaches Metrc. | Sent to Metrc. |
| `immediate_write` (28 routes: auth, tag lists, label layouts, saved reports, support tickets, photo uploads) | Takes effect immediately. | Raises `ValueError`: the route has no dry run. |

So a forgotten `submit=True` costs you a harmless dry run, never an accidental
change in Metrc. Passing `submit=` at all, `True` or `False`, to an immediate
route raises `ValueError`, so you can't mistake one kind for the other.

Check a route's kind with `t3api endpoints discontinue` or
`client.spec.endpoint("/v2/items/discontinue").kind`.

## What a dry run checks

A dry run is **static validation**: the request's format, required fields and
types. It doesn't check whether the records a request names exist. A dry run
that moves package `id: 0` to location `locationId: 0` passes.

So a dry run catches a missing field, a wrong type or a malformed body. It
won't tell you that a package ID is wrong, or that Metrc will refuse the
change. Check that the records exist yourself first, for example by loading
them with `collect()` and matching on them. This is what `bulk()` means when it
calls a row `valid`: it passed validation, not that Metrc will accept it.

`dynamic=True` on any write method or `bulk()` also asks T3 for the route's
dynamic checks (`applyDynamicValidation=true`). What those cover varies by
route, and some routes have none yet, so treat them as an extra and not as a
guarantee. A route whose spec doesn't offer them raises `ValueError`.

## Array bodies

Most Metrc write routes (68 of 85 today) take a **list** of objects as the
body, even when you send one. They include the common bulk jobs: adjusting,
moving, finishing and noting packages; creating items and strains; and every
plant, plant batch and harvest write. The others, such as
`/v2/items/discontinue`, `/v2/packages/discontinue` and the void routes, take
one object.

Send a list to a list route, even for one object:

```python
client.post(
    "/v2/packages/change-locations",
    license=lic,
    json=[{"id": 123456, "locationId": 42, "actualDate": "2026-11-23"}],
)
```

The server answers a bare object on a list route with an unexplained HTTP 500,
so the library logs a warning first when a `json=` body's shape doesn't match
the spec. Check a route with `client.spec.endpoint(path).body_is_array`.
`bulk()` handles this for you: you give it one dict per object, and it wraps
them in a list for routes that take one.

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
| `json` | The request body. A list for [array routes](#array-bodies). |
| `params` | Other query parameters, by their spec names. |
| `files`, `data` | Multipart or form bodies, as in httpx2 (not on `delete()`). See [Uploads](#uploads). |
| `submit` | `True` sends a Metrc write for real. |
| `dynamic` | `True` also asks for the route's dynamic checks. See [What a dry run checks](#what-a-dry-run-checks). |
| `timeout` | Override the request timeout for this call. |
| `**path_params` | Path parameters such as `tag_list_id=`. |

Each returns a `WriteResult`:

| Attribute | What it holds |
|---|---|
| `dry_run` | `True` if T3 only checked the request (statically) and nothing reached Metrc. |
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

### Uploads

Two routes take a file as `multipart/form-data`: `POST /v2/items/images/file`
(an immediate write that uploads an item photo) and
`POST /v2/packages/labresults/document/file` (a Metrc write, so a dry run
unless `submit=True`). Pass the file with `files=`, in httpx's
`(name, content, content type)` form, and any other form fields with `data=`:

```python
from pathlib import Path

photo = Path("blue-dream.png")
client.post(
    "/v2/items/images/file",
    license=lic,
    files={"file": (photo.name, photo.read_bytes(), "image/png")},
)
```

Each route's entry in the [T3 API docs](https://api.trackandtrace.tools/v2/docs)
names its form fields.

### Downloads

Routes of kind `file` (manifest and COA PDFs, item photos) return `bytes` from
`get()`. `client.download()` streams one straight to disk instead, through a
temporary file that's renamed only when the download completes, so a failure
never leaves half a PDF behind:

```python
client.download(
    "/v2/transfers/manifest",
    f"manifests/{number}.pdf",
    license=lic,
    params={"manifestNumber": number},
)
```

It creates missing folders and returns the path.

## Many writes: bulk()

`bulk()` validates every row, then submits them. Give it one dict per object,
whatever the route's body shape:

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
   Remember that a dry run [only checks format](#what-a-dry-run-checks).
2. **Decide**, according to `submit`:

    | `submit=` | What happens |
    |---|---|
    | `False` (the default) | Stops here and returns. Nothing is submitted. |
    | `"ask"` | Shows the route, the license, the counts (and "sandbox" in the [sandbox](authentication.md#sandbox)), lists any rows that failed, and asks whether to submit the rest. The default answer is no. |
    | `True` | Submits without asking when every row passed. If some failed: in a terminal it shows them and asks whether to submit only the valid rows (default no); without a terminal it returns without submitting, unless `on_error="skip"`, which submits the valid rows without asking. |

3. **Submit**: each valid row is sent with `submit=true`, in order. With
   `on_error="stop"` (the default), the first row that fails stops the rest;
   `on_error="skip"` carries on.
4. **Return** a `BulkResult`. `log_to=` also writes it to a CSV file.

An `AuthError` stops `bulk()` immediately whatever `on_error` says, since every
later row would fail the same way.

### Asking before submitting

`submit="ask"` is the validate, show, confirm, submit pattern in one call. Each
row is validated once:

```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--yes", action="store_true", help="submit without asking")
args = parser.parse_args()

result = client.bulk(
    "/v2/packages/change-locations",
    rows=moves,
    license=lic,
    submit=True if args.yes else "ask",
)
```

```text
── POST /v2/packages/change-locations ──
License: LIC-00001
Rows: 12 passed validation
ℹ A dry run checks format, required fields and types, not whether the records it names exist.
Submit 12 row(s) to Metrc for LIC-00001? [y/n] (n):
```

Without a terminal, `submit="ask"` raises `NotInteractive` before sending
anything: "submit="ask" needs a terminal to ask in. Pass submit=True to submit
without asking." A scheduled job that forgot `--yes` fails loudly instead of
quietly submitting nothing.

!!! note "`confirm=` is a different thing"
    `confirm=True` doesn't ask anything. It means "I know this
    [immediate route](#immediate-routes) has no dry run; send the rows
    anyway". To be asked, use `submit="ask"`.

### Batches

Array routes take many objects in one request. `batch_size=N` sends up to N
rows per request, in both the validation and submit passes:

```python
client.bulk("/v2/packages/adjust", rows=adjustments, license=lic, submit=True, batch_size=50)
```

That's far fewer requests, but a request that fails marks **every row in it**
with the same error, because the server answers for the whole request. The
default, `batch_size=1`, keeps each row's error separate. `batch_size` above 1
on a route that takes one object raises `ValueError`.

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

The second call validates every row again before submitting. To show the
results and decide in between without that, use
[`submit="ask"`](#asking-before-submitting).

### Row statuses

| Status | Meaning |
|---|---|
| `valid` | Passed validation (the dry run's static checks) and wasn't submitted (yet). It doesn't mean Metrc will accept it. |
| `invalid` | Failed validation. `message` says why. |
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
| `summary()` | One line, e.g. `POST /v2/items/discontinue: 40 submitted, 2 failed`, or `12 passed validation, 1 failed validation` before submitting. |
| `to_csv(path)` | One line per row: `index`, `status`, `message`, and the row as JSON. |

### Immediate routes

Immediate routes have no dry run, so `bulk()` can't validate first. It refuses
to run unless you pass `confirm=True`, or `submit="ask"` to have a person
confirm in the terminal:

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
