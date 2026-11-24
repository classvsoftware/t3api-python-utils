# Collections

A collection is any paginated list endpoint: active packages, items, harvests,
transfers, plants and so on. `collect()` loads all of it.

```python
import t3api_utils as t3

with t3.connect() as client:
    packages = client.collect("METRC_ACTIVE_PACKAGES", license="LIC-00001")
```

The result is a `list[dict]`, each row exactly as the API returns it. Nothing
is renamed or dropped, and fields T3 adds later show up without a library
change. Every row carries its `licenseNumber`.

## Arguments

```python
client.collect(
    "METRC_ACTIVE_ITEMS",
    license="LIC-00001",
    filter=["name__contains:flower", "productCategoryName__contains:bud"],
    filter_logic="and",
    sort="name:asc",
    mask=["id", "name", "productCategoryName"],
    page_size=500,
)
```

| Argument | What it does |
|---|---|
| `license` | One license number, or a list (see [several licenses](#several-licenses)). Defaults to the client's default license. |
| `filter` | One `field__operator:value` string, or a list of them. |
| `filter_logic` | `"and"` (the server's default: every filter must match) or `"or"` (any). |
| `sort` | `field:asc` or `field:desc`. One field, root level only. |
| `mask` | Fields to return, as a list or comma-separated string. Dotted paths such as `item.name` work. Smaller rows load faster. |
| `page_size` | Rows per request. Default 100; the server allows up to 500 on most collections, which means fewer requests. |
| `progress` | Show a progress bar. On by default when stderr is a terminal. |
| `params` | Any other query parameters, by their spec names. |

Path parameters, for the few collections that have them, are keyword
arguments.

### Filter operators

Filters run on the server, before paging, and string comparisons ignore case.

| Field type | Operators |
|---|---|
| String | `contains`, `doesnotcontain`, `eq`, `neq`, `startswith`, `endswith` |
| Number, date-time | `lt`, `lte`, `eq`, `neq`, `gt`, `gte` |
| Boolean | `eq` (`true` or `false`) |

Date-times are ISO 8601, for example
`packagedDate__gte:2026-01-01T00:00:00.000Z`. A filter on a field the
collection doesn't have fails with a 400 that lists the fields it accepts.
Packages also accept four nested item fields: `item.name`, `item.strainName`,
`item.productCategoryName` and `item.unitThcContent`.

```python
on_hold = client.collect(
    "METRC_ACTIVE_PACKAGES",
    license="LIC-00001",
    filter=["isOnHold__eq:true"],
)
large_or_old = client.collect(
    "METRC_ACTIVE_PACKAGES",
    license="LIC-00001",
    filter=["quantity__gte:1000", "packagedDate__lt:2026-01-01T00:00:00.000Z"],
    filter_logic="or",
)
```

## How loading works

1. The endpoint is resolved to its collection operation. Anything else raises
   `SpecError`.
2. Page 1 is fetched. Its `totalPages` says how many more there are.
3. The remaining pages are fetched in parallel on a thread pool (10 workers by
   default), all through one rate limiter (10 requests per second by default).
4. Rows come back in page order.

Change the defaults on `connect()`:

```python
client = t3.connect(rate_limit=5, concurrency=4)
```

**Failures.** A page that still fails after [retries](errors-and-logging.md#retries)
fails the whole call, and the error notes which page it was. `collect()` never
returns partial results silently.

**Data that changes while loading.** Pages are read at slightly different
moments. If rows are added or removed mid-load, a row can shift from one page
to the next and be read twice. `collect()` drops any row whose `id` it has
already seen and logs how many it dropped. A row that shifts the other way,
into a page that was already read, can't be recovered. If you need an exact
snapshot, load at a quiet time or use a [report](reports-and-tag-lists.md#reports).

## Several licenses

Pass a list to load each license in turn and join the results:

```python
licenses = [lic["licenseNumber"] for lic in client.licenses()]
packages = client.collect("METRC_ACTIVE_PACKAGES", license=licenses)
```

Each row's `licenseNumber` tells you where it came from.

## Large collections

`iter_rows()` takes the same arguments as `collect()` (except `progress`) but
yields rows as each page arrives, one page at a time, so memory stays flat:

```python
import csv

with t3.connect() as client, open("packages.csv", "w", newline="") as f:
    writer = csv.writer(f)
    for row in client.iter_rows("METRC_ACTIVE_PACKAGES", license="LIC-00001", mask=["label", "quantity"]):
        writer.writerow([row["label"], row["quantity"]])
```

It fetches pages one after another rather than in parallel, so it's slower than
`collect()` for collections that fit in memory.

## One object

Collections with an `{object_id}` route share their endpoint ID with it:

```python
item = client.get("METRC_ACTIVE_ITEMS", object_id=12345, license="LIC-00001")
package = client.get("METRC_ACTIVE_PACKAGES", object_id=67890, license="LIC-00001")
```

`object_id` is the record's Metrc `id`.

## Licenses and the default license

`license=` can be left out when the client has a default license
(`connect(license=...)`, `T3_LICENSE`, or the profile's). It's filled in only
for endpoints that require a `licenseNumber`. A license passed in the call
always wins.

```python
client = t3.connect(license="LIC-00001")
items = client.collect("METRC_ACTIVE_ITEMS")   # uses LIC-00001
```

## Picking interactively

For scripts a person runs in a terminal:

```python
with t3.connect() as client:
    lic = client.license or client.pick_license()
    endpoint = client.pick_endpoint()            # collections, searchable
    rows = client.collect(endpoint.id or endpoint.path, license=lic)
```

Both pickers raise `NotInteractive` without a terminal, and Ctrl-C raises
`KeyboardInterrupt` to your script. `pick_license()` returns at once, without
asking, when the account has only one license.

## From the command line

```bash
t3api pull METRC_ACTIVE_PACKAGES -l LIC-00001 -o packages.csv
t3api pull METRC_ACTIVE_ITEMS -l LIC-00001 -l LIC-00002 --filter name__contains:flower -o items.json
t3api pull --inspect          # pick a collection, then browse it
```

See [The t3api command](cli.md#pull).
