# Getting started

This page walks through the whole library in the order you'd use it: log in,
connect, pick a license, load data, look at it, write it back, and use the
server's reports and tag lists. Each step links to a guide page with the
details.

The examples use `LIC-00001` as the license number. Use one of yours.

## 1. Run scripts with uv

[uv](https://docs.astral.sh/uv/) can install a script's dependencies for you.
Put this header at the top of the file:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["t3api-utils[tui]>=2.0"]
# ///

import t3api_utils as t3

client = t3.connect()
print(client.whoami()["username"])
```

and run it with:

```bash
uv run my_script.py
```

uv builds a throwaway environment with `t3api-utils` in it. The `[tui]` extra
is only needed for the inspector in step 7; drop it otherwise. If you work in a
uv project instead, `uv add t3api-utils` and run scripts with `uv run` as
usual.

## 2. Log in and save a secret key

The T3 API accepts two kinds of credential:

| Credential | Lasts | Use it for |
|---|---|---|
| **Secret key** | Until you delete it, or until the Metrc login behind it changes | Everything. This is the default. |
| JWT | 24 hours | A quick session when you don't want a key |

A secret key is made from your Metrc login once. After that T3 signs in to
Metrc for you, so scripts never need your password. Create one with:

```bash
t3api login
```

(`uv run t3api login` inside a uv project, or
`uvx --from t3api-utils t3api login` with nothing installed.)

It asks:

1. **Do you already have a T3 secret key?** If you do, paste it and you're done.
2. **Metrc hostname, username and password.** Type a state abbreviation such as
   `CA`, or a hostname such as `ca.metrc.com`. States that need an email or a
   one-time password are asked for them.
3. **Create a secret key so you don't have to log in again?** Say yes. In
   states with a one-time password, you'll be asked for your **OTP seed**: the
   base32 secret behind your authenticator app, not a 6-digit code. T3 needs
   the seed because it signs in to Metrc for you later.
4. **Pick a default license for this profile?** Optional, but it saves passing
   `license=` everywhere.

The key goes into your OS keyring (macOS Keychain, Windows Credential Manager,
or Secret Service on Linux) under a profile named `default`. Your Metrc
password is not stored.

If you decline the secret key, `t3api login` saves a JWT instead. It expires
after 24 hours, and the next `connect()` in a terminal asks you to log in again
and offers the key again.

You can also create a key in the browser at
<https://api.trackandtrace.tools/v2/pages/secret-key> and paste it in step 1.

More in [Authentication](guide/authentication.md).

## 3. Connect

```python
import t3api_utils as t3

client = t3.connect()
```

`connect()` looks for a credential in this order and stops at the first one it
finds:

1. `connect(secret_key=...)` or `connect(jwt=...)`
2. The `T3_SECRET_KEY` or `T3_JWT` environment variable
3. The saved profile
4. The login flow from step 2, but only if a person is there to answer (a
   terminal or Jupyter). Otherwise it raises `AuthRequired` with setup
   instructions, so scheduled jobs fail fast instead of hanging.

It then checks the credential with one `GET /v2/auth/whoami` call.

Use the client as a context manager so its connections close when the script
is done:

```python
with t3.connect() as client:
    ...
```

Several Metrc logins? Save each to its own profile and pick one by name:

```bash
t3api login --profile mi-prod
```

```python
client = t3.connect(profile="mi-prod")
```

## 4. Licenses

Most endpoints need a license number.

```python
for lic in client.licenses():
    print(lic["licenseNumber"], lic["licenseName"])
```

In a terminal, `client.pick_license()` shows them as a numbered table and
returns the number you choose. A common pattern is to use the profile's default
license when there is one, and ask otherwise:

```python
lic = client.license or client.pick_license()
```

`client.license` is the default license: `connect(license=...)`, then
`T3_LICENSE`, then the profile's. Set the profile's with
`t3api license pick` or `t3api license set LIC-00001`. When there is a default,
calls that need a license use it, and you can leave `license=` out.

## 5. Load a collection

`collect()` loads every page of a collection, fetching pages in parallel:

```python
packages = client.collect("METRC_ACTIVE_PACKAGES", license=lic)
print(len(packages), packages[0]["label"])
```

Each row is a plain dict, exactly as the API returns it. Every row carries its
own `licenseNumber`.

Let the server do the narrowing. Filters use `field__operator:value`, sorting
uses `field:asc` or `field:desc`, and `mask` returns only the fields you name:

```python
flower = client.collect(
    "METRC_ACTIVE_ITEMS",
    license=lic,
    filter=["name__contains:flower"],
    sort="name:asc",
    mask=["id", "name", "productCategoryName"],
)
```

`license` also takes a list, which loads each license in turn and joins the
results:

```python
packages = client.collect("METRC_ACTIVE_PACKAGES", license=["LIC-00001", "LIC-00002"])
```

For collections too big to hold in memory, `iter_rows()` takes the same
arguments and yields rows one page at a time:

```python
for row in client.iter_rows("METRC_ACTIVE_PACKAGES", license=lic):
    ...
```

One object by its Metrc ID:

```python
item = client.get("METRC_ACTIVE_ITEMS", object_id=12345, license=lic)
```

More in [Collections](guide/collections.md).

## 6. Find endpoints

`METRC_ACTIVE_ITEMS` is a T3 endpoint ID. Any path from the spec works too:
`client.collect("/v2/items", license=lic)` is the same call. To find one,
search from the command line:

```bash
t3api endpoints harvest --kind collection
```

or from Python:

```python
for ep in client.spec.find("harvest", kind="collection"):
    print(ep.id, ep.path, ep.summary)
```

In a terminal, `client.pick_endpoint()` shows a searchable table of
collections. The library reads the T3 OpenAPI spec at runtime, so endpoints T3
adds later work without upgrading. More in
[Endpoints and the spec](guide/endpoints-and-spec.md).

## 7. Inspect rows

With the `[tui]` extra installed, browse rows in a full-screen terminal viewer:

```python
t3.inspect(packages, title="Active packages")
```

Use ++left++ and ++right++ to move between rows, ++slash++ to search every
nested value, ++question++ for help and ++q++ or ++esc++ to quit. The same
viewer opens files from the command line: `t3api inspect packages.csv`.

## 8. Filter against a CSV and export

`filter_rows()` keeps the rows that match a CSV file. The CSV's header names
the columns to compare:

```text title="wanted.csv"
label
1A4000000000000000000001
1A4000000000000000000002
```

```python
wanted = t3.filter_rows(packages, "wanted.csv", on_unmatched="warn")
```

Lines in the CSV that match no row are logged as a warning
(`on_unmatched="error"` raises instead). Dotted columns such as `item.name`
reach into nested fields.

Export to CSV or JSON:

```python
t3.to_csv(wanted, "wanted-packages.csv")
t3.to_json(wanted, "wanted-packages.json")
```

CSV files are written as UTF-8 with a byte-order mark so Excel opens them
correctly. Nested objects become dotted columns (`item.name`) and lists are
written as JSON text. Leave the path out and the file is named after the data
model, license and time. More in [Local data](guide/local-data.md).

## 9. Write to Metrc

Writes that reach Metrc are a **dry run unless you pass `submit=True`**. A dry
run sends the request to T3, which checks its format, required fields and types
and stops before Metrc. It doesn't check that the records you name exist:

```python
result = client.post("/v2/items/discontinue", license=lic, json={"id": 12345})
print(result.dry_run, result.message)   # True Dry run
```

When the dry run passes, send it for real:

```python
result = client.post("/v2/items/discontinue", license=lic, json={"id": 12345}, submit=True)
print(result.dry_run, result.message)   # False Success
```

A validation failure raises `t3.ValidationError` with the server's explanation
in `.detail`.

Most Metrc write routes take a list of objects, even for one, so their `json=`
is `[{...}]`. `/v2/items/discontinue` is one of the few that take a single
object.

A few T3 routes, such as tag lists and secret keys, act immediately and have
no dry run. Passing `submit=` to one of them raises `ValueError`, so you can't
mistake one for the other. More in [Writes](guide/writes.md).

## 10. Write many rows

`bulk()` validates every row with a dry run first, and only then submits:

```python
items = client.collect("METRC_ACTIVE_ITEMS", license=lic, filter=["name__contains:sample"])
result = client.bulk(
    "/v2/items/discontinue",
    rows=[{"id": item["id"]} for item in items],
    license=lic,
    submit=True,
    log_to="discontinue-results.csv",
)
print(result.summary())
```

If any row fails validation, nothing is submitted. In a terminal you're shown
the failures and asked whether to send just the valid rows; in a script,
`on_error="skip"` does that without asking. Leave out `submit=True` to only
validate, or pass `submit="ask"` to see the results and be asked before
anything is submitted. `log_to` writes one line per row with its status and
message.

## 11. Download a report

T3 builds reports on the server. They're faster than loading a collection when
all you want is a spreadsheet:

```python
client.report("ITEMS_REPORT", licenses=[lic], to="items.xlsx")
```

The format follows the file extension (`.csv`, `.xlsx` or `.json`), or pass
`format=`. Choose columns, filter and sort the same way as `collect()`:

```python
client.report(
    "ACTIVE_PACKAGES_REPORT",
    licenses=["LIC-00001", "LIC-00002"],
    to="packages.csv",
    columns=["label", "quantity", "unitOfMeasureAbbreviation", "locationName"],
    filter=["isOnHold__eq:false"],
    sort="label:asc",
)
```

List every report with `t3api endpoints --kind report`. More in
[Reports and tag lists](guide/reports-and-tag-lists.md#reports).

## 12. Tag lists

A tag list is a list of handles (usually package tag labels) kept on the
server. T3 resolves it to the objects those handles stand for. It's the
quickest way to go from a column of scanned labels to full package records:

```python
tl = client.tag_lists.from_csv(
    "labels.csv",
    column="label",
    license=lic,
    endpoint="METRC_ACTIVE_PACKAGES",
    name="Room A",
)
packages = tl.resolve()
```

Resolving is all or nothing. If any label matches no package, or more than one,
`resolve()` raises `t3.TagListResolveError` listing each problem handle:

```python
try:
    packages = tl.resolve()
except t3.TagListResolveError as exc:
    for problem in exc.errors:
        print(problem["handle"], problem["reason"])
```

More in [Reports and tag lists](guide/reports-and-tag-lists.md#tag-lists).

## 13. See the HTTP traffic

To see every request and response, set `T3_LOG_HTTP`:

```bash
T3_LOG_HTTP=1 uv run my_script.py
T3_LOG_HTTP=1 T3_LOG_FILE=t3_http.log uv run my_script.py
```

Secret keys, tokens, passwords and OTP values are masked in the log. More in
[Errors and logging](guide/errors-and-logging.md).

## 14. Use the command line

Much of the above works without writing Python:

```bash
t3api whoami
t3api pull METRC_ACTIVE_PACKAGES -l LIC-00001 -o packages.csv
t3api pull METRC_ACTIVE_ITEMS --filter name__contains:flower --inspect
t3api report ITEMS_REPORT -l LIC-00001 -o items.xlsx
t3api tag-lists create labels.csv --column label --endpoint METRC_ACTIVE_PACKAGES
t3api tag-lists resolve <list-id> -o room-a.csv
```

Every command is listed in [The t3api command](guide/cli.md).

## Troubleshooting

| What you see | What to do |
|---|---|
| `AuthRequired: No T3 credential found` | Run `t3api login` in a terminal, or set `T3_SECRET_KEY`. |
| `AuthError` with a secret key | The key was deleted, or your Metrc password, email or OTP changed. Run `t3api keys rotate`. |
| `AuthError` with a JWT | It expired (JWTs last 24 hours). Run `t3api login` and accept the secret key. |
| `SpecError: ... needs: license=` | Pass `license=`, or set a default with `t3api license pick`. |
| `UnknownEndpoint` | Check the spelling against `t3api endpoints`. If T3 added it recently, run `t3api spec refresh`. |
| `NotInteractive` | A picker or prompt ran without a terminal. Pass the value in code instead. |
| `ImportError` mentioning Textual | Install the extra: `pip install "t3api-utils[tui]"`. |
| No rows, or fewer than expected | Check the license and filters, then rerun with `T3_LOG_HTTP=1` to see what the API sent back. |

## Next steps

- The Guide pages cover each topic in depth.
- [Example scripts](https://github.com/classvsoftware/t3-api-examples)
- [T3 API docs](https://api.trackandtrace.tools/v2/docs) and the
  [T3 wiki](https://www.trackandtrace.tools/wiki)
- Coming from 1.x? See [Migrating from 1.x](migration.md).
