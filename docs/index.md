# t3api-utils

A Python library and command-line tool for the
[T3 API](https://api.trackandtrace.tools/v2/docs) (Track & Trace Tools), which
serves Metrc cannabis-compliance data. It handles login and secret keys, loads
whole collections, sends writes safely, downloads server-side reports and
builds tag lists, so a script can go from `import` to data in three lines.

!!! note "2.0 is a rewrite"
    2.0 doesn't share an API with 1.x. If you have 1.x scripts, see
    [Migrating from 1.x](migration.md). 1.x is frozen at 1.5.0.

## Install

Python 3.12 or later.

=== "uv"

    ```bash
    uv add t3api-utils
    ```

=== "pip"

    ```bash
    pip install "t3api-utils[tui]"
    ```

The `[tui]` extra adds [Textual](https://textual.textualize.io/) for the row
inspector (`t3.inspect()` and `t3api inspect`). Leave it out if you only run
scripts. With uv: `uv add "t3api-utils[tui]"`.

For a one-file script, put the dependency in the script itself and
[`uv run`](https://docs.astral.sh/uv/guides/scripts/) installs it for you:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["t3api-utils>=2.0"]
# ///
```

## Quickstart

Log in once. This saves a secret key to your OS keyring, so later runs don't
prompt:

```bash
t3api login
```

Inside a uv project, that's `uv run t3api login`. Without installing anything
first, `uvx --from t3api-utils t3api login` does the same.

Then:

```python
import t3api_utils as t3

client = t3.connect()
items = client.collect("METRC_ACTIVE_ITEMS", license="LIC-00001")
t3.to_csv(items, "items.csv")
```

`connect()` finds the saved key, `collect()` loads every page of active items
in parallel, and `to_csv()` writes them out with nested fields flattened.

## What it does

**Secret keys first.** `t3api login` creates a T3 secret key from your Metrc
login and saves it to a named profile. Your Metrc password is never stored.
`connect()` then works with no prompts, in scripts, scheduled jobs and CI (set
`T3_SECRET_KEY`). See [Authentication](guide/authentication.md).

**Every endpoint, by name.** Endpoints are named by their T3 endpoint ID
(`METRC_ACTIVE_PACKAGES`) or path (`/v2/packages/active`) and checked against
the T3 OpenAPI spec at runtime, so new endpoints work without a library
release. See [Endpoints and the spec](guide/endpoints-and-spec.md).

**Whole collections.** `client.collect()` fetches every page of any paginated
endpoint (187 of them today) in parallel, behind one rate limiter, and hands back plain
dicts exactly as the API returns them. See [Collections](guide/collections.md).

**Safe writes.** Writes that reach Metrc are a dry run unless you pass
`submit=True`. `client.bulk()` validates every row before sending any of them,
and writes are never retried after a server error. See [Writes](guide/writes.md).

**Server-side reports and tag lists.** `client.report()` downloads any report
endpoint (83 today) as CSV, XLSX or JSON. `client.tag_lists` turns a column of
tag labels into the packages they stand for. See
[Reports and tag lists](guide/reports-and-tag-lists.md).

**Local helpers.** Filter rows against a CSV, export to CSV or JSON, and browse
rows in a terminal inspector. See [Local data](guide/local-data.md).

**A `t3api` command.** Log in, manage keys and profiles, pull a collection to a
file, download a report, or search the spec without writing any Python. See
[The t3api command](guide/cli.md).

```bash
t3api pull METRC_ACTIVE_PACKAGES -l LIC-00001 -o packages.csv
t3api report ITEMS_REPORT -l LIC-00001 -o items.xlsx
t3api endpoints harvest --kind collection
```

## Where next

- [Getting started](getting-started.md): a walk through the whole library, start to finish.
- The **Guide** pages: one topic each, with the details.
- The **Reference** pages: every public class and function, from the docstrings.
- [T3 API docs](https://api.trackandtrace.tools/v2/docs): what each endpoint returns.
- [T3 wiki](https://www.trackandtrace.tools/wiki) and
  [example scripts](https://github.com/classvsoftware/t3-api-examples).
