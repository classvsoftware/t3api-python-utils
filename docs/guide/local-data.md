# Local data

Helpers for what happens after the data arrives: matching it against a file,
writing it out, reading it back and looking through it. None of them make
network calls.

## Filtering against a CSV

`t3.filter_rows()` keeps the rows that match a CSV or TSV file, or a list of
dicts:

```python
import t3api_utils as t3

with t3.connect() as client:
    packages = client.collect("METRC_ACTIVE_PACKAGES", license="LIC-00001")

wanted = t3.filter_rows(packages, "wanted.csv")
```

```text title="wanted.csv"
label
1A4000000000000000000001
1A4000000000000000000002
```

| Argument | What it does |
|---|---|
| `rows` | The rows to filter, e.g. from `collect()`. |
| `match` | A CSV or TSV path, or a list of dicts. |
| `columns` | Columns to compare. Defaults to every column of the match file. |
| `on_unmatched` | What to do when a line of `match` finds no row: `"warn"` (log a warning, the default), `"error"` (raise `ValueError`) or `"skip"` (say nothing). |

How matching works:

- **Every column must match.** With a header of `item.name,locationName`, a
  row matches when both values are equal.
- **Dotted paths** such as `item.name` reach into nested objects.
- **Values compare as trimmed strings**, so `12345` in the CSV matches the
  number `12345` in a row, and `true` matches `True`.
- **Results follow the order of `match`**, and each row appears at most once.
- A column that no row has raises `ValueError` and lists the columns that do
  exist, which catches typos in the CSV header.

Match on some of the file's columns only:

```python
t3.filter_rows(items, "input.csv", columns=["name"], on_unmatched="error")
```

or against a list built in code:

```python
t3.filter_rows(items, [{"name": "Blue Dream Flower"}, {"name": "Gelato Pre-Roll"}])
```

Matching happens on your machine, after loading the whole collection. For a
long list of tag labels, a server-side
[tag list](reports-and-tag-lists.md#tag-lists) avoids loading everything
first.

`filter_rows()` never prompts. For an interactive script, ask for the file
first with [`t3.pick_file()`](#picking-a-file) and pass the result in.

## Exporting

```python
t3.to_csv(rows, "packages.csv")
t3.to_json(rows, "packages.json")
t3.to_json(rows, "packages.jsonl", lines=True)
```

Both return the `Path` they wrote, and create missing folders.

**`to_csv(rows, path=None, *, columns=None, strip_empty=False)`**

- Nested objects become dotted columns: `item.name`, `item.productCategoryName`.
- Lists are written as JSON text, so they can be parsed back.
- Empty values and `None` become empty cells.
- Columns are ordered with the common identifying fields first (`hostname`,
  `licenseNumber`, `retrievedAt`, `dataModel`, `index`, `id`, `label`,
  `name`), then every other column alphabetically.
- `columns=[...]` picks and orders the columns yourself, using the dotted names.
- `strip_empty=True` drops columns that are empty in every row.
- The file is UTF-8 with a byte-order mark, so Excel on Windows opens it
  without garbling accents and symbols.

**`to_json(rows, path=None, *, lines=False)`**

- Indented JSON, exactly as the API returned it (no flattening).
- `lines=True` writes JSON Lines: one object per line, which is easier to
  stream and append to.
- It also accepts a single dict.

**Default file names.** Leave `path` out and the file goes in the current
folder, named from the first row's data model and license plus the time, for
example `MetrcPackage__LIC-00001__2026-11-23T14-05-09.csv`.

## Reading files back

`t3.read_rows()` reads JSON, JSON Lines, CSV or TSV into a list of dicts:

```python
rows = t3.read_rows("packages.json")
```

A JSON file holding a T3 response envelope (`{"data": [...], ...}`) gives you
its `data`. Values read from CSV are strings.

## The inspector

`t3.inspect()` opens a full-screen terminal viewer that shows one row at a time
as formatted JSON:

```python
t3.inspect(rows, title="Active packages")
```

| Key | Action |
|---|---|
| ++left++ / ++right++ | Previous / next row |
| ++home++ / ++end++ | First / last row |
| ++slash++ | Search every nested value |
| ++ctrl+l++ | Clear the search |
| ++question++ | Help |
| ++q++ or ++esc++ | Quit |

It needs the `tui` extra, which installs Textual:

```bash
pip install "t3api-utils[tui]"
uv add "t3api-utils[tui]"
```

Without it, `t3.inspect()` raises an `ImportError` that names the install
command. Textual is imported only when you call `inspect()`, so scripts that
don't use it pay nothing.

From the command line, `t3api inspect FILE` opens a JSON, JSON Lines or CSV
file, and `t3api pull ENDPOINT --inspect` opens a collection straight from the
API.

## Picking a file

`t3.pick_file()` lists the CSV, TSV, JSON and JSON Lines files in a folder,
newest first, as a numbered table, and returns the chosen `Path`:

```python
path = t3.pick_file()                                # current folder
path = t3.pick_file("exports", patterns=["*.csv"])   # one folder, CSVs only
```

Type a number to choose, or some text to narrow the list. If the folder has no
matching files, it asks for a path instead. Like every picker, it raises
`NotInteractive` without a terminal, and Ctrl-C raises `KeyboardInterrupt`.

## Putting it together

This is `scripts/example.py` from the repository: pick a license and a
collection, load all of it, browse it, then keep and save the rows that match
`input.csv`.

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["t3api-utils[tui]>=2.0"]
# ///
"""Pick a collection, load all of it, and browse the rows that match input.csv."""

from pathlib import Path

import t3api_utils as t3

INPUT = Path(__file__).with_name("input.csv")


def main() -> None:
    with t3.connect() as client:
        license = client.license or client.pick_license()
        endpoint = client.pick_endpoint(kind="collection")
        rows = client.collect(endpoint.id or endpoint.path, license=license)
        t3.inspect(rows, title=endpoint.id or endpoint.path)

        matches = t3.filter_rows(rows, INPUT, on_unmatched="warn")
        print(f"Saved {len(matches)} matching rows to {t3.to_csv(matches)}")
        t3.inspect(matches, title="matches")


if __name__ == "__main__":
    main()
```
