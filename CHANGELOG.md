# Changelog

## 2.0.1

Fixes and additions from porting the T3 example scripts to 2.0. Use this
release instead of 2.0.0.

### Fixed

- **`bulk()` on list routes.** Most Metrc write routes (68 of 85) take a JSON
  list, even for one object, and answer a bare object with an unexplained
  HTTP 500. `bulk()` sent every row as an object, so on those routes every row
  came back `invalid`. It now wraps each row in a list where the spec says the
  body is one. You still pass one dict per object.
- **Production licenses in the sandbox.** `connect(sandbox=True)` kept
  `T3_LICENSE` or the profile's license, and the sandbox answers a request
  for a license it doesn't have with an empty 200, so scripts quietly found
  nothing. In the sandbox those defaults are now ignored (an explicit
  `connect(license=...)` still counts), `enter_sandbox()` clears
  `client.license`, and a call naming a license the sandbox session doesn't
  have logs a warning.
- **Dry-run wording.** A dry run is static validation: format, required fields
  and types, not whether the records a request names exist. The docs,
  docstrings and `BulkResult.summary()` now say so. `summary()` reads
  `12 passed validation, 1 failed validation` rather than `12 valid, 1 invalid`
  (the row statuses themselves are unchanged), and lists statuses in pipeline
  order: passed validation, failed validation, submitted, failed, not sent.

### Added

- **`bulk(submit="ask")`** validates every row, shows the route, license,
  counts and any failures (and says "sandbox" in the sandbox), then asks
  whether to submit, default no. Without a terminal it raises `NotInteractive`
  before sending anything. A script can map its flag in one line:
  `submit=True if args.yes else "ask"`. On routes with no dry run it asks
  instead of needing `confirm=True`.
- **`bulk(batch_size=N)`** sends up to N rows per request on list routes. A
  failed request marks every row in it. The default stays 1.
- **`dynamic=True`** on `post()`, `put()`, `patch()`, `delete()` and `bulk()`
  sends `applyDynamicValidation=true`, for the routes that offer it.
- **A warning when a `json=` body's shape doesn't match the route**: an object
  sent to a list route, or a list to an object route.
- **`t3.confirm()`, `t3.ask()` and `t3.choose()`**, public prompts that match
  the library's pickers and raise `NotInteractive` without a terminal.
  `confirm()` defaults to no. `ask(parse=float)` asks again until `parse`
  succeeds. `choose()` (the existing picker, now exported) turns filtering on
  for more than 10 items unless `filterable=` says otherwise. New guide page:
  Prompts and pickers.
- **Sandbox:** the `T3_SANDBOX` environment variable (`1`, `true`, `yes` or
  `on`), a global `t3api --sandbox` option for the data commands,
  `client.sandbox`, `client.hostname` (the Metrc hostname, from `whoami`), and
  an INFO log line on entering the sandbox. `t3api whoami` shows a `sandbox`
  row there.
- **`client.download(endpoint, to, ...)`** streams a `file` endpoint (manifest
  and COA PDFs, item photos) to disk through a temporary file that's renamed
  when complete, so a failed download never leaves a partial file.
- **`include=`** on `collect()`, `iter_rows()` and `get()` for super
  endpoints, sent as a repeated parameter (the server rejects a comma-joined
  one). Values the spec doesn't list are warned about.
- **`to_csv()` and `to_json()` accept a folder**: an existing folder, or a
  path ending in `/`, gets the default `<dataModel>__<license>__<time>` file
  name inside it.
- `Endpoint.body_type` / `Endpoint.body_is_array` and `Param.choices` in the
  spec registry.
- Docs: array bodies, uploads with `files=`, downloads, super collections and
  `include`, and the difference between `bulk(confirm=True)` and
  `submit="ask"`.

### Changed

- `connect(sandbox=True)` now calls `whoami` once even with `validate=False`,
  to log the sandbox hostname.

## 2.0.0

A hard-break rewrite. No 1.x import path still works, and there is no
compatibility layer. The [migration guide](https://classvsoftware.github.io/t3api-python-utils/migration/)
maps every 1.x name to its replacement and shows the example scripts before
and after.

### Highlights

- **`t3.connect()`** is the one way in. It finds a credential (argument, then
  `T3_SECRET_KEY` / `T3_JWT`, then the saved profile, then an interactive
  login only when a person can answer), validates it, and returns a
  `T3Client`. Scripts get from `import` to data in three lines.
- **Secret keys first.** `t3api login` creates a T3 secret key from your Metrc
  login and saves it to a named profile, with the secret in the OS keyring.
  The Metrc password is never stored. `client.secret_keys` and `t3api keys`
  list, create, rotate and revoke keys. JWTs remain as a fallback.
- **Spec-driven endpoints.** Endpoints are named by T3 endpoint ID
  (`METRC_ACTIVE_ITEMS`) or path, checked against the T3 OpenAPI spec at
  runtime. A live copy is fetched and cached per host, with the spec bundled
  in the package as a fallback, so new endpoints work without a release.
  Missing required parameters fail before any request is sent.
- **Collections:** `client.collect()` loads every page of any of the 187
  paginated endpoints in parallel behind one shared rate limiter; 1.x's
  picker found 138. `client.iter_rows()` streams large collections. Rows are
  plain dicts, exactly as the API returns them.
- **Safe writes.** Metrc writes are a dry run unless `submit=True`. Routes
  with no dry run reject `submit=`. `client.bulk()` validates every row before
  submitting any, and can log each row's outcome to CSV.
- **Server-side reports:** `client.report()` downloads any of the 83 report
  endpoints as CSV, XLSX, JSON or a Google Sheet, for up to 20 licenses.
  `client.report_url()` builds a secret-key URL for spreadsheets to pull.
- **Tag lists:** `client.tag_lists` creates lists from a CSV column or rows and
  resolves them to packages, items, harvests and more, with per-handle errors
  when something doesn't match.
- **A `t3api` command** for login, profiles, keys, default license, endpoint
  search, `pull` (collection to CSV/JSON or the inspector), `report`,
  `tag-lists`, `inspect` and `spec info` / `spec refresh`.
- **Local helpers:** `t3.filter_rows()` (indexed, with dotted paths),
  `t3.to_csv()` (UTF-8 with BOM for Excel, lists as JSON), `t3.to_json()`
  (optionally JSON Lines), `t3.read_rows()`, and `t3.pick_file()`.
- **The Textual inspector** is kept as `t3.inspect()`, behind the optional
  `[tui]` extra.
- **Errors keep their response.** Every `APIError` has `status_code`,
  `detail`, `errors`, `code` and the `response`; 1.x always reported
  `status_code=None`. Auth errors say whether to rotate a key or log in again.
- Runs the same on Linux, macOS, Windows and in Jupyter. CI covers all three
  operating systems on Python 3.12 and 3.13, with 100% line and branch
  coverage.

### Fixed (compared with 1.x)

- Writes are no longer retried after a 5xx or a timeout, and a POST that gets
  a 400 is sent once, not three times. Reads retry only on connection errors,
  429, 502, 503 and 504, honouring `Retry-After`.
- The rate limiter really limits: 1.x let 20 requests through in 0.2 seconds.
- HTTP debug logging masks auth headers, secret keys in paths and queries, and
  password, OTP, OTP seed, secret key and token fields in bodies. 1.x logged
  credential-login bodies, password included.
- Secret keys are sent in the `X-T3-API-Key` header instead of the URL.
- Exported CSV lists are JSON text instead of Python reprs.

### Removed

- The async `T3APIClient`, its sync wrappers, `send_api_request`, the
  `request_*` helpers and the `get_collection` / `load_all_data_*` /
  `parallel_load_*` family. Use `T3Client` methods, or `client.http` for the
  configured `httpx2.Client`.
- `get_authenticated_client_or_error()` and the other ~22 auth functions,
  including the `*_with_validation` variants.
- API-key auth (`/v2/auth/apikey`, `API_KEY`, `API_STATE_CODE`).
- The `.t3.env` file, `ConfigManager` and the 37 `EnvKeys`. 2.0 reads eight
  environment variables: `T3_SECRET_KEY`, `T3_JWT`, `T3_PROFILE`,
  `T3_LICENSE`, `T3_API_HOST`, `T3_SPEC`, `T3_LOG_HTTP`, `T3_LOG_FILE`.
- DuckDB and pyarrow, and the `db/` module (relational tables, schema export).
- `interactive_collection_handler` and the numbered menu, `match_collection_from_csv`,
  `save_collection_to_*` / `save_dicts_to_*`, `pick_collection`.
- The `MetrcObject`, `MetrcCollectionResponse` and other TypedDicts.
- The public `style/` module and `logging.setup_logging()`.
- The `intro.py` tutorial, now the Getting started docs page.
- Dependencies: `httpx` (replaced by `httpx2`), `duckdb`, `pyarrow`,
  `questionary`, `python-dotenv`, `certifi`.

### Packaging

- Still published as `t3api-utils`, imported as `t3api_utils`, for Python
  3.12 or later. License GPL-3.0-only. Built with `uv_build`.
- Core dependencies: `httpx2`, `rich`, `typer`, `keyring`, `platformdirs`,
  `pyotp`, `tomli-w`. Textual is no longer installed by default; it's in the
  `[tui]` extra.

## 1.5.0

Final 1.x release. 1.x is frozen: no further releases or fixes. Pin
`t3api-utils<2` to keep using it.
