# The t3api command

Installing `t3api-utils` adds a `t3api` command. It covers logging in,
profiles, secret keys, and the common data tasks, without writing Python.

```bash
t3api --help
t3api pull --help
```

How to run it:

| Setup | Command |
|---|---|
| Installed with pip, or `uv tool install t3api-utils` | `t3api ...` |
| In a uv project that depends on `t3api-utils` | `uv run t3api ...` |
| Nothing installed | `uvx --from t3api-utils t3api ...` |

## Conventions

- **Profiles.** Every command that uses a credential takes `--profile` / `-p`.
  Without it, the profile is `T3_PROFILE`, then the default profile, then one
  named `default`. Credentials are found the same way as
  [`connect()`](authentication.md#how-connect-finds-a-credential), so
  `T3_SECRET_KEY` works here too.
- **Licenses.** `--license` / `-l` takes a license number. On `pull` and
  `report`, repeat it for several licenses. Leave it out to use the profile's
  default license.
- **Output.** Data (tables, IDs, URLs) goes to stdout. Messages, prompts and
  progress go to stderr, so `t3api ... > file` captures only the data.
- **Exit codes.** 0 on success, 1 on an error (with a red ✗ message), 130 when
  cancelled with Ctrl-C.
- **Global options**, before the command: `--verbose` / `-v` shows the
  library's progress logs, `--version` prints the version, and `--sandbox`
  uses the [Metrc sandbox](authentication.md#sandbox).
- **Sandbox.** `t3api --sandbox COMMAND` (or `T3_SANDBOX=1`) runs `whoami`,
  `pull`, `report` and the `tag-lists` commands against the Metrc sandbox.
  The profile's default license is ignored there, so pass `-l` with a sandbox
  license (or pick one when asked). `login`, `logout`, `keys` and `license`
  manage the credential and the profile, and always use the real account.

  ```bash
  t3api --sandbox whoami
  t3api --sandbox pull METRC_ACTIVE_PLANTBATCHES -l SF-SBX-1-101 -o batches.csv
  ```

## Logging in

### login

```bash
t3api login [--profile P] [--host URL]
```

Runs the [login flow](authentication.md#the-login-flow): paste an existing
secret key, or log in with Metrc credentials and accept the offer to create
one. Saves it to the profile (creating the profile if needed) and optionally
sets a default license. The first profile becomes the default.

`--host` sets the T3 API base URL for the profile. It defaults to
`T3_API_HOST`, then the profile's saved host, then
`https://api.trackandtrace.tools`.

### logout

```bash
t3api logout [--profile P] [--everywhere]
```

Removes the profile's saved credential from the keyring (or secrets file). The
profile and its settings stay. A secret key itself keeps working; delete it
with `t3api keys revoke` if it's no longer needed.

`--everywhere` first calls `POST /v2/auth/logout`, which logs out all of the
account's Metrc sessions.

### whoami

```bash
t3api whoami [--profile P]
```

Shows the profile, credential type, API host and default license, plus the
username, Metrc hostname and subscription details T3 reports. With
`t3api --sandbox whoami` it adds a `sandbox` row and shows the sandbox's
hostname.

## Profiles

```bash
t3api profiles list              # every profile; the default is ticked
t3api profiles use NAME          # make NAME the default
t3api profiles remove NAME       # delete NAME and its saved credential
```

`profiles list` shows each profile's credential type, Metrc host, username,
default license and API host. Secrets are never shown.

## Default license

```bash
t3api license [--profile P]                # show it
t3api license pick [--profile P]           # choose from the account's licenses
t3api license set LIC-00001 [--profile P]  # set it directly
```

Scripts pick it up as `client.license`, and calls that need a license use it
when you leave `license=` out.

## Secret keys

```bash
t3api keys list [--profile P]
t3api keys create [--profile P]
t3api keys rotate [KEY] [--profile P]
t3api keys revoke KEY [--profile P] [--yes]
```

| Command | What it does |
|---|---|
| `keys list` | Every secret key on the account, masked to the last 4 characters, with whether it's enabled, managed, when it was created and last used, and which one this profile uses. |
| `keys create` | Asks for Metrc hostname, username and password (plus email or OTP seed where the state needs them), creates a key, prints it **once**, and offers to save it to the profile. |
| `keys rotate` | After a Metrc password, email or OTP change: asks for the new login details and updates the key. The key value doesn't change. Without `KEY`, rotates the profile's saved key. |
| `keys revoke` | Deletes a key after asking for confirmation (`--yes` skips the question). Anything using it stops working, including report URLs that contain it. Removes it from any profile that saved it. |

See [Managing secret keys](authentication.md#managing-secret-keys).

## Data

### endpoints

```bash
t3api endpoints [QUERY] [--kind KIND] [--profile P]
```

Searches the T3 spec. Every word of `QUERY` must appear in the endpoint ID,
path, summary or tags. `--kind` / `-k` is one of `collection`, `report`,
`metrc_write`, `immediate_write`, `file`, `object` or `other`.

```bash
t3api endpoints harvest
t3api endpoints transfers incoming --kind collection
t3api endpoints --kind report
```

It needs no credential, only the spec. `T3_SPEC=bundled t3api endpoints ...`
works offline.

### pull

```bash
t3api pull [ENDPOINT] [-l LIC]... [-f FILTER]... [--sort S] [--mask FIELDS] [-o FILE] [--inspect] [-p P]
```

Loads a whole collection, as `client.collect()` does, and writes it to a file
or opens it in the inspector.

| Option | What it does |
|---|---|
| `ENDPOINT` | A collection's endpoint ID or path. Leave it out to pick one from a searchable table. |
| `-l`, `--license` | License number. Repeat for several. Without it, the profile's default license is used, or you're asked to pick one. |
| `-f`, `--filter` | `field__op:value`. Repeat for several (all must match). |
| `--sort` | `field:asc` or `field:desc`. |
| `--mask` | Comma-separated fields to return. |
| `-o`, `--output` | File to write. `.json` writes JSON, `.jsonl` JSON Lines, anything else CSV. Without it, a CSV named after the data model, license and time. |
| `--inspect` | Open the rows in the inspector instead of writing a file (needs `[tui]`). |

```bash
t3api pull METRC_ACTIVE_PACKAGES -l LIC-00001 -o packages.csv
t3api pull METRC_ACTIVE_ITEMS -l LIC-00001 -l LIC-00002 -f name__contains:flower --sort name:asc -o items.json
t3api pull /v2/harvests/active --mask id,name,currentWeight
t3api pull --inspect
```

### report

```bash
t3api report ENDPOINT [-l LIC]... [--format F] [-o FILE] [--columns C] [-f FILTER]... [--sort S] [--url] [-p P]
```

Downloads a [server-side report](reports-and-tag-lists.md#reports).

| Option | What it does |
|---|---|
| `ENDPOINT` | A report's endpoint ID or path, e.g. `ITEMS_REPORT`. |
| `-l`, `--license` | License number. Repeat for up to 20. |
| `--format` | `csv`, `xlsx`, `json` or `googleSheets`. Defaults to the extension of `-o`, else `csv`. |
| `-o`, `--output` | File to write. Without it, `<ENDPOINT>__<time>.<format>` in the current folder. |
| `--columns` | Comma-separated columns. |
| `-f`, `--filter`, `--sort` | As for `pull`. |
| `--url` | Print a report URL containing the secret key instead of downloading. See [the warning](reports-and-tag-lists.md#report-urls-for-spreadsheets). |

With `--format googleSheets`, it prints the new sheet's URL.

```bash
t3api report ITEMS_REPORT -l LIC-00001 -o items.xlsx
t3api report ACTIVE_PACKAGES_REPORT -l LIC-00001 -l LIC-00002 --columns label,quantity,locationName -o packages.csv
t3api report ACTIVE_PACKAGES_REPORT -l LIC-00001 --url
```

### inspect

```bash
t3api inspect FILE
```

Opens a JSON, JSON Lines or CSV file in the [inspector](local-data.md#the-inspector).
Needs the `[tui]` extra.

## Tag lists

```bash
t3api tag-lists list [-l LIC] [-p P]
t3api tag-lists create FILE --column COL [--name N] [--endpoint E] [-l LIC] [--shared] [-p P]
t3api tag-lists resolve LIST_ID [--endpoint E] [-o FILE] [-p P]
```

| Command | What it does |
|---|---|
| `tag-lists list` | Your tag lists with their ID, name, license, endpoint, entry count and scanned count. |
| `tag-lists create` | Creates a list from one column (`--column` / `-c`) of a CSV or TSV file. `--name` defaults to the file name. `--endpoint` / `-e` sets the collection it resolves against by default. `--shared` makes it visible to everyone with access to the license. Prints the new list's ID on stdout. |
| `tag-lists resolve` | Resolves a list to its objects and writes them like `pull` does (`-o` picks CSV, JSON or JSON Lines). `--endpoint` / `-e` resolves against a different collection. If any handle doesn't resolve, prints a table of them and exits 1. |

```bash
LIST_ID=$(t3api tag-lists create labels.csv -c label -e METRC_ACTIVE_PACKAGES --name "Room A")
t3api tag-lists resolve "$LIST_ID" -o room-a.csv
```

See [Tag lists](reports-and-tag-lists.md#tag-lists).

## The spec

```bash
t3api spec info [-p P]
t3api spec refresh [-p P]
```

`spec info` shows which copy of the T3 OpenAPI spec is in use (cached, live,
stale or bundled), how old it is, its version, and how many operations of each
kind it has. `spec refresh` fetches the live spec now and caches it, for
example right after T3 announces a new endpoint. See
[Where the spec comes from](endpoints-and-spec.md#where-the-spec-comes-from).
