# Reports and tag lists

Both are built on the T3 server, so they do work that would otherwise take
many requests and some local code.

## Reports

A report endpoint builds a whole collection into one CSV, XLSX or JSON file on
the server. When you want a spreadsheet, it's usually quicker than
`collect()` plus `to_csv()`. There are 83 report endpoints today:

```bash
t3api endpoints --kind report
t3api endpoints package --kind report
```

```python
client.spec.list(kind="report")
```

### Downloading

```python
import t3api_utils as t3

with t3.connect() as client:
    client.report("ITEMS_REPORT", licenses=["LIC-00001"], to="items.xlsx")
```

With `to=`, the report streams straight to the file (written to a temporary
file first, then renamed, so a failed download never leaves half a file) and
`report()` returns the path.

| Argument | What it does |
|---|---|
| `endpoint` | A report's endpoint ID (`ITEMS_REPORT`, `ACTIVE_PACKAGES_REPORT`, ...) or path. |
| `licenses` | One license or a list of up to 20. Defaults to the client's default license. More than 20 raises `ValueError`. |
| `format` | `"csv"`, `"xlsx"`, `"json"` or `"googleSheets"`. Defaults to the extension of `to` (`.csv`, `.xlsx`, `.json`), else `"csv"`. |
| `to` | File to write. |
| `columns` | Columns to include, in order, as a list or comma-separated string. Each report has its own default set. An unknown name fails with a 400 that lists the valid ones. |
| `filter`, `filter_logic`, `sort` | As in [`collect()`](collections.md#arguments). |
| `row_limit` | Return only the first this-many rows. |
| `delivery`, `email` | `delivery="email"` with `email=` asks the server to email the report instead. |
| `params` | Any other query parameters, by their spec names. |

What comes back:

| Call | Returns |
|---|---|
| `to="..."` | The `Path` written |
| no `to`, `format="csv"` or `"xlsx"` | `bytes` |
| no `to`, `format="json"` | Parsed JSON: an envelope with `data`, `filters`, `sort` and so on |
| `format="googleSheets"` | The URL of a new Google Sheet. `email=` shares it with that address. |
| `delivery="email"` | The server's delivery receipt; the report arrives by email |

Report downloads get a 5 minute timeout instead of the usual 30 seconds.

```python
# Several licenses, chosen columns, filtered and sorted, to CSV
client.report(
    "ACTIVE_PACKAGES_REPORT",
    licenses=["LIC-00001", "LIC-00002"],
    to="packages.csv",
    columns=["label", "quantity", "unitOfMeasureAbbreviation", "locationName"],
    filter=["isOnHold__eq:false"],
    sort="label:asc",
)

# Straight into memory
csv_bytes = client.report("ITEMS_REPORT", licenses="LIC-00001", format="csv")

# Emailed instead of downloaded
client.report("ITEMS_REPORT", licenses="LIC-00001", format="xlsx",
              delivery="email", email="me@example.com")
```

**Row caps.** A report returns at most 50,000 rows, and a super report
(`.../super/report`) at most 5,000. A collection larger than the cap is
rejected rather than silently cut short. Narrow it with `filter`, or pass
`row_limit` to ask for the first rows on purpose.

**Saved reports and schedules** (`/v2/saved-reports`) have no helper yet. Reach
them with `client.request()`:

```python
client.request("GET", "/v2/saved-reports")
```

### Report URLs for spreadsheets

`client.report_url()` builds a report URL with your secret key in it, for Excel
or Google Sheets to pull directly. It takes the same arguments as `report()`,
except `to`, `delivery` and `email`, and `format` defaults to `"csv"`:

```python
url = client.report_url("ACTIVE_PACKAGES_REPORT", licenses=["LIC-00001"])
```

Paste the URL into Google Sheets as `=IMPORTDATA("<url>")`, or into Excel with
**Data → From Web**. The spreadsheet refreshes from T3 whenever it reloads.

!!! warning "The URL is a credential"
    Anyone who has the URL can use your secret key, for anything the key can
    do. Every call logs a warning to remind you.

    Rotating a key keeps the same key value, so it does not cut off a leaked
    URL. **Deleting the key** (`t3api keys revoke KEY`) is the only way.
    Consider a separate key just for spreadsheet URLs, so you can revoke it
    without breaking your scripts.

`report_url()` sends no request. It needs a secret key; with a JWT it raises
`T3Error`, because a JWT in a URL would stop working within 24 hours.

From the command line: `t3api report ACTIVE_PACKAGES_REPORT -l LIC-00001 --url`.

## Tag lists

A tag list is a list of **handles** kept on the T3 server, usually Metrc tag
labels. T3 resolves the list to the objects those handles stand for. It's the
quickest way from a column of scanned labels to full package records, and the
list can be shared with everyone on the license.

`client.tag_lists` wraps `/v2/tag-lists`.

### From a CSV to packages

```text title="labels.csv"
label
1A4000000000000000000001
1A4000000000000000000002
1A4000000000000000000003
```

```python
with t3.connect() as client:
    tl = client.tag_lists.from_csv(
        "labels.csv",
        column="label",
        license="LIC-00001",
        endpoint="METRC_ACTIVE_PACKAGES",
        name="Room A",
    )
    packages = tl.resolve()
    t3.to_csv(packages, "room-a-packages.csv")
```

`endpoint` is the collection the list resolves against by default. `name`
defaults to the file name. A TSV file works the same way.

### Creating lists

| Method | Creates a list from |
|---|---|
| `create(name, license=None, endpoint=None, visibility="USER", handles=None, metadata=None)` | A list of handles (strings) or entry dicts |
| `from_csv(path, column, *, name=None, license=None, endpoint=None, visibility="USER")` | One column of a CSV or TSV file |
| `from_rows(rows, field, *, name, license=None, endpoint=None, visibility="USER")` | One field of each row, e.g. from `collect()`. Dotted paths such as `item.name` work. |

- `license` defaults to the client's default license.
- `visibility="USER"` keeps the list to yourself. `"LICENSE"` lets anyone on
  the same Metrc hostname with access to the license read the list and add,
  remove and scan entries. Only the creator can rename or archive it.
- Handles are trimmed, blanks are dropped, and repeats are skipped. Matching
  ignores case and surrounding whitespace, and so does the repeat check.
- An entry can be a dict with more than a handle, such as
  `{"handle": "1A4000000000000000000001", "name": "Vault shelf 3"}`.
- Each request carries at most 5,000 entries, so larger lists are sent in
  chunks. A list can grow past 5,000, but the server only resolves lists of up
  to 5,000 entries, so `create()` warns when a list is bigger. Split it to use
  `resolve()`.

Each of these returns a `TagList`.

### Working with a list

A `TagList` has the list's fields and the `client.tag_lists` methods bound to
its ID:

```python
tl.id, tl.name, tl.license, tl.endpoint     # common fields
tl["entryCount"]                             # any field, from tl.data

tl.add(["1A4000000000000000000004"])         # {"created": 1, "updated": 0}
tl.remove(["1A4000000000000000000001"])      # counts, plus handlesNotFound
tl.scan(["1A4000000000000000000002"])        # mark as scanned
tl.entries()                                 # every entry
tl.update(name="Room A (done)")              # change fields, e.g. archived=True
tl.refresh()                                 # reload from the server
```

To find an existing list:

```python
lists = client.tag_lists.list(license="LIC-00001")
tl = client.tag_lists.get(lists[0]["id"])
```

`list()` also takes `visibility=`, `endpoint=` and `archived=`.

### Resolving

`resolve()` returns the objects the list's handles stand for, in the order the
entries were added, paged like a collection:

```python
packages = tl.resolve()
superpackages = tl.resolve("METRC_ACTIVE_SUPERPACKAGES")
slim = tl.resolve(mask=["label", "item.name", "quantity"])
```

Each collection matches on one field, decided by the server: `label` for
packages, plants and tags; `packageLabel` for transferred packages;
`manifestNumber` for transfers; `name` for items, harvests, plant batches and
strains. A list can be resolved against any of the collections T3 supports for
tag lists, not just its default. `include=` attaches related data, and is only
accepted with a `/super` collection.

**All or nothing.** If any handle matches no object, or more than one, the
server rejects the whole resolve with a 422, and `resolve()` raises
`TagListResolveError`. Its `errors` holds one dict per problem handle, with
`handle`, `reason` (`NOT_FOUND` or `AMBIGUOUS`) and `matchCount`:

```python
try:
    packages = tl.resolve()
except t3.TagListResolveError as exc:
    for problem in exc.errors:
        print(f"{problem['handle']}: {problem['reason']} ({problem['matchCount']} matches)")
```

Fix the CSV, `tl.remove()` the bad handles, or resolve against a different
collection (for example inactive packages) and try again.

**When tag lists don't fit**, for example matching on a field the server
doesn't match on, or on several columns at once, load the collection and use
[`t3.filter_rows()`](local-data.md#filtering-against-a-csv) instead.

**COA extraction** has no helper yet. Call the route directly:
`client.post("/v2/tag-lists/{tag_list_id}/coa-extraction", tag_list_id=tl.id, json={...})`,
with the body the [T3 API docs](https://api.trackandtrace.tools/v2/docs) describe.

### From the command line

```bash
t3api tag-lists create labels.csv --column label --endpoint METRC_ACTIVE_PACKAGES --name "Room A"
t3api tag-lists list -l LIC-00001
t3api tag-lists resolve <list-id> -o room-a.csv
```

`create` prints the new list's ID on stdout, so a shell script can capture it.
If `resolve` fails, it prints a table of the handles that didn't resolve.
