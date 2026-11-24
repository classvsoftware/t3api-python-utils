# Endpoints and the spec

The library has no hand-written method per endpoint. Everything it knows about
endpoints, such as their paths, parameters and whether they're paginated, comes
from the T3 OpenAPI spec, read at runtime. When T3 adds an endpoint, it works
in your script as soon as the library sees the new spec, without an upgrade.

## Naming an endpoint

Every method that calls the API takes an endpoint as its first argument, in one
of two forms:

**An endpoint ID**, the spec's `x-t3-endpoint-id`:

```python
client.collect("METRC_ACTIVE_PACKAGES", license="LIC-00001")
```

**A path** from the spec, either as a template or filled in:

```python
client.collect("/v2/packages/active", license="LIC-00001")
client.get("/v2/items/{object_id}", object_id=12345, license="LIC-00001")
client.get("/v2/items/12345", license="LIC-00001")
```

Path parameters such as `{object_id}` or `{tag_list_id}` are keyword arguments.
Query parameters the library doesn't name itself go in `params=`.

**One ID can name several operations.** `METRC_ACTIVE_ITEMS` is both
`GET /v2/items` (the collection) and `GET /v2/items/{object_id}` (one item).
The method you call picks between them: `collect()` takes the collection,
`get(..., object_id=...)` takes the single-object route, and `report()` takes a
report.

**Writes use paths.** In today's spec, routes that write to Metrc don't have
endpoint IDs, so name them by path: `client.post("/v2/items/discontinue", ...)`.

## Finding endpoints

From the command line:

```bash
t3api endpoints                          # everything
t3api endpoints harvest                  # every word must appear in the ID, path, summary or tags
t3api endpoints package --kind report    # narrow by kind
```

From Python, through `client.spec`:

```python
client.spec.find("harvest", kind="collection")   # list[Endpoint]
client.spec.list(kind="report")                  # every report
client.spec.endpoint("METRC_ACTIVE_ITEMS", kind="collection")
client.spec.ids()                                # every endpoint ID, sorted
```

Each `Endpoint` has:

| Attribute | Example |
|---|---|
| `id` | `"METRC_ACTIVE_ITEMS"`, or `None` for routes without one |
| `method` | `"GET"` |
| `path` | `"/v2/items"` |
| `kind` | `"collection"` (see below) |
| `tags` | `("Items",)` |
| `summary` | `"List of active items"` |
| `params` | the operation's parameters, each with `name`, `location`, `required`, `description` and `schema` |
| `body_type` | `"array"` or `"object"` for routes with a JSON body, else `None`. `body_is_array` is `True` for the [list routes](writes.md#array-bodies). |

`ep.param("licenseNumber")` returns one parameter, and `ep.label()` gives a
readable `GET /v2/items (METRC_ACTIVE_ITEMS)`. A parameter's `choices` are the
values the spec allows, such as a super collection's `include` values, or `()`
when it doesn't list any.

In a terminal, `client.pick_endpoint()` shows a numbered table of collections
that you can narrow by typing. `client.pick_endpoint(kind=None)` shows every
endpoint, and `kind="report"` shows reports.

Some collections have a companion `fields` route that lists the fields you can
filter on, for example:

```python
client.get("/v2/items/fields", license="LIC-00001")
```

## Endpoint kinds

Each operation in the spec gets exactly one kind, worked out from its
structure. The rules are checked top to bottom:

| Kind | Rule | Count today | Call it with |
|---|---|---|---|
| `collection` | GET whose 200 response is paginated (uses the spec's `Pagination` schema) | 187 | `collect()`, `iter_rows()` |
| `report` | Can respond with CSV or XLSX | 83 | `report()`, `report_url()` |
| `metrc_write` | Non-GET that takes the `submit` parameter | 85 | `post()` / `put()` / `patch()` / `delete()`, `bulk()` |
| `immediate_write` | Non-GET without `submit` | 28 | the same, without `submit=` |
| `file` | GET returning a PDF or an image | 5 | `download()` to a file, or `get()`, which returns `bytes` |
| `object` | GET with an `{object_id}` path parameter | 144 | `get(..., object_id=...)` |
| `other` | Everything else, e.g. `/v2/licenses`, `/v2/auth/whoami` | 124 | `get()` / `request()` |

The counts come from the spec bundled with this release and will drift. The
rules don't depend on them. `t3api spec info` shows the counts for the copy
you're using.

Calling a method on the wrong kind raises `SpecError` and lists what the ID
does have, for example `collect()` on a report.

## Parameter checks

Before sending anything, the client resolves the operation's parameters from
the spec:

- **A missing required parameter** raises `SpecError` before any request goes
  out, naming it the way you'd pass it: `GET /v2/items (METRC_ACTIVE_ITEMS)
  needs: license=.`
- **A missing required body** raises `SpecError`: `needs a request body (json=...)`.
- **An unknown query parameter** logs a warning and is sent anyway. Your
  cached spec can lag the server, and a hard error would block a parameter T3
  has only just added.

The common collection parameters have Python names:

| Python | Query parameter |
|---|---|
| `license` | `licenseNumber` |
| `filter` (string or list) | one `filter=` per item |
| `filter_logic` | `filterLogic` |
| `sort` | `sort` |
| `mask` (string or list) | `collectionMask`, comma-joined |
| `include` (string or list) | one `include=` per item |
| `page_size` | `pageSize` |

`page`, `submit` and `secretKey` are managed by the library; don't pass them in
`params=`.

## Calling any endpoint

`client.request()` is the general form behind `get()`, `post()` and the rest:

```python
client.request("GET", "/v2/tag-lists/{tag_list_id}/entries", tag_list_id="abc123")
client.request("GET", "/v2/saved-reports", params={"pageSize": 50})
```

It returns parsed JSON for JSON responses, `bytes` for anything else (PDFs,
images, CSV), and `None` for an empty body. Non-2xx responses raise an
[`APIError`](errors-and-logging.md#exceptions) subclass.

`get()` on a collection returns only the first page, as the raw response.
Use `collect()` for all of it.

## Where the spec comes from

The spec is loaded the first time something needs it, never at import, and at
most once per client. Raw `client.http` calls never need it.

1. **Cached copy.** A live copy is cached per API host, so a sandbox or staging
   host gets its own. A copy less than an hour old is used as is. An older one
   is revalidated with `If-None-Match`; an unchanged spec costs one small 304
   response.
2. **Live fetch** from `<api host>/v2/spec/openapi.json` (5 second timeout),
   saved to the cache.
3. **Stale cache**, if the fetch fails. A warning says so.
4. **Bundled copy**, the gzipped spec that ships inside the package.

The cache lives in the user cache folder: `~/Library/Caches/t3api-utils/spec/`
on macOS, `~/.cache/t3api-utils/spec/` on Linux, and
`%LOCALAPPDATA%\t3api-utils\Cache\spec\` on Windows.

Other controls:

- `connect(spec="bundled")` or `T3_SPEC=bundled` pins the bundled copy. Use it
  for reproducible runs, or offline.
- `t3api spec info` shows which copy is in use, how old it is and the count of
  each kind. `t3api spec refresh` forces a fresh fetch.
- `client.refresh_spec()` does the same from Python.
- `client.spec.source.describe()` says which copy a client loaded.

An endpoint that isn't in the spec raises `UnknownEndpoint`, with close
matches when there are any:

```text
'METRC_ACTIVE_ITEM' is not in the T3 OpenAPI spec. Close matches: METRC_ACTIVE_ITEMS, ...
```

If T3 added the endpoint recently, `t3api spec refresh` picks it up.

## The escape hatch: client.http

`client.http` is the underlying `httpx2.Client`, already configured with your
credential, the base URL, retries, rate limiting and HTTP logging. Use it for
routes that aren't in the published spec, or when you want the raw response:

```python
response = client.http.get("/v2/anything-new", params={"licenseNumber": "LIC-00001"})
response.raise_for_status()
data = response.json()
```

Calls through `client.http` skip the spec entirely: no endpoint lookup, no
parameter checks, no default license, and non-2xx responses are returned
rather than raised.
