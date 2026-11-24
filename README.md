# t3api-utils

A Python library and `t3api` command for the [T3 API](https://api.trackandtrace.tools/v2/docs)
(Track & Trace Tools), which serves Metrc cannabis-compliance data. It handles
login and secret keys, loads whole collections, sends writes safely (dry run
unless you say otherwise), downloads server-side reports and builds tag lists.

**Documentation: <https://classvsoftware.github.io/t3api-python-utils/>**

> 2.0 is a rewrite and doesn't share an API with 1.x. See
> [Migrating from 1.x](https://classvsoftware.github.io/t3api-python-utils/migration/).
> 1.x is frozen at 1.5.0.

## Install

Python 3.12 or later.

```bash
uv add t3api-utils
pip install "t3api-utils[tui]"    # [tui] adds the terminal row inspector
```

## Quickstart

Log in once. This creates a T3 secret key from your Metrc login and saves it to
your OS keyring; your Metrc password isn't stored.

```bash
t3api login
```

Then, in a script:

```python
import t3api_utils as t3

client = t3.connect()
items = client.collect("METRC_ACTIVE_ITEMS", license="LIC-00001")
t3.to_csv(items, "items.csv")
```

For scheduled jobs and CI, set `T3_SECRET_KEY` instead of logging in.

A few more things it does:

```python
# Writes are a dry run unless submit=True
client.post("/v2/items/discontinue", license="LIC-00001", json={"id": 12345}, submit=True)

# Validate every row, then submit
client.bulk("/v2/items/discontinue", rows=[{"id": i["id"]} for i in items], license="LIC-00001", submit=True)

# Server-side report straight to a file
client.report("ITEMS_REPORT", licenses=["LIC-00001"], to="items.xlsx")

# A column of tag labels to full package records
tl = client.tag_lists.from_csv("labels.csv", column="label", license="LIC-00001",
                               endpoint="METRC_ACTIVE_PACKAGES")
packages = tl.resolve()
```

## The t3api command

```bash
t3api login                                                   # save a secret key to a profile
t3api pull METRC_ACTIVE_PACKAGES -l LIC-00001 -o packages.csv # a whole collection to CSV or JSON
t3api report ITEMS_REPORT -l LIC-00001 -o items.xlsx          # a server-side report
t3api endpoints harvest --kind collection                     # search the T3 spec
t3api keys list                                               # manage secret keys
```

`t3api --help` lists every command.

## Development

```bash
uv sync
uv run pytest
uv run mypy
uv run mkdocs serve
```

See [CLAUDE.md](CLAUDE.md) for the project layout and conventions, and
[CHANGELOG.md](CHANGELOG.md) for release notes.

## License

[GPL-3.0-only](LICENSE).

## Links

- [Documentation](https://classvsoftware.github.io/t3api-python-utils/)
- [T3 API docs](https://api.trackandtrace.tools/v2/docs)
- [T3 website](https://www.trackandtrace.tools) and [wiki](https://www.trackandtrace.tools/wiki)
- [Example scripts](https://github.com/classvsoftware/t3-api-examples)
