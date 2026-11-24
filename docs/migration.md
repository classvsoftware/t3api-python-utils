# Migrating from 1.x

2.0 is a rewrite with no compatibility layer: every 1.x import path is gone.
Most scripts get shorter. 1.x is frozen at 1.5.0 and gets no further releases,
so pin `t3api-utils<2` if you need to keep a 1.x script running unchanged.

## What changed, in short

- **httpx2, sync only.** HTTP is [httpx2](https://pypi.org/project/httpx2/),
  and there is no async API. Python 3.12 or later, as before.
- **Textual is optional.** The inspector needs the `[tui]` extra:
  `t3api-utils[tui]`.
- **One way in.** `t3.connect()` replaces the two dozen `get_*_client_*`
  functions. It returns a `T3Client`.
- **Secret keys instead of `.t3.env`.** Credentials live in named profiles,
  with secrets in the OS keyring. The Metrc password is never stored. API-key
  auth is removed.
- **Endpoints by name, checked against the spec.** `client.collect("METRC_ACTIVE_ITEMS")`
  replaces `load_all_data_sync(path="/v2/items")`, and new endpoints work
  without a release.
- **Plain dicts.** Rows are exactly what the API returns. The `MetrcObject`
  TypedDicts are gone.
- **Writes are a dry run unless `submit=True`**, and are never retried after a
  server error. 1.x could send the same failed POST three times.
- **No DuckDB or pyarrow.** Export to CSV or JSON. (DuckDB caused install
  problems on Windows.)
- **Server-side reports and tag lists** are first-class.
- **A `t3api` command** replaces the numbered interactive menu and the
  tutorial script.

## Steps

1. **Update the dependency.** In a script header,
   `dependencies = ["t3api-utils>=2.0"]` (add `[tui]` if you use the
   inspector) and `requires-python = ">=3.12"`. Drop `duckdb`, `pyarrow`,
   `httpx` and `python-dotenv` unless you use them yourself.
2. **Log in once** with `t3api login` and accept the secret key. This replaces
   the credentials in `.t3.env`.
3. **Delete `.t3.env`.** It held your Metrc password in plain text, and 2.0
   doesn't read it.
4. **Replace calls** using the table below.
5. **Check every write.** Pass `submit=True` where you mean to change Metrc.
   Consider `client.bulk()` for loops of writes: it validates every row first.

## Name by name

| 1.x | 2.0 |
|---|---|
| `get_authenticated_client_or_error()` and about 22 other auth functions | [`t3.connect()`](guide/authentication.md) |
| `*_with_validation` variants | `connect(validate=True)`, the default |
| API-key auth, `API_KEY`, `API_STATE_CODE` | Removed. Use a secret key. |
| `?secretKey=` query transport | Header only for requests; [`client.report_url()`](guide/reports-and-tag-lists.md#report-urls-for-spreadsheets) for spreadsheet URLs |
| `.t3.env`, `ConfigManager`, 37 `EnvKeys` | Profiles and keyring, plus [8 env vars](guide/authentication.md#environment-variables) |
| `T3APIClient` (async) and its sync wrappers | `T3Client` (sync) |
| `send_api_request[_async]`, 8 `request_*` helpers | `client.request()`, `client.get()` / `post()` / ..., `client.http` |
| `get_collection[_async]`, `load_all_data_*`, `parallel_load_*`, `load_collection` | [`client.collect()`](guide/collections.md), `client.iter_rows()` |
| `RateLimiter` | Internal; `connect(rate_limit=..., concurrency=...)` |
| `pick_collection`, `get_collection_endpoints` | `client.pick_endpoint()`, [`client.spec`](guide/endpoints-and-spec.md), `t3api endpoints` |
| `pick_license`, `pick_file` | `client.pick_license()`, `t3.pick_file()` |
| `interactive_collection_handler`, `main/handlers.py` | `t3api pull`, `t3.inspect()` |
| `inspect_collection` | `t3.inspect()` (needs `[tui]`) |
| `match_collection_from_csv` | [`client.tag_lists`](guide/reports-and-tag-lists.md#tag-lists), [`t3.filter_rows()`](guide/local-data.md#filtering-against-a-csv) |
| `save_collection_to_*`, `save_dicts_to_*` | [`t3.to_csv()`, `t3.to_json()`](guide/local-data.md#exporting) |
| `db/` (DuckDB tables, schema export) | Removed |
| `style/`, `logging.setup_logging()` | Internal, or gone. Use the standard `logging` module. |
| `intro.py` | The [Getting started](getting-started.md) page |
| `MetrcObject`, `MetrcCollectionResponse` and other TypedDicts | Plain dicts |

## .t3.env settings

| 1.x setting | 2.0 |
|---|---|
| `METRC_HOSTNAME`, `METRC_USERNAME`, `METRC_PASSWORD`, `METRC_EMAIL`, `OTP_SEED` | Enter them once in `t3api login`, which creates a secret key. Only the key is kept. |
| `JWT_TOKEN` | `T3_JWT`, or `connect(jwt=...)`. Better: a secret key in `T3_SECRET_KEY`. |
| `API_KEY`, `API_STATE_CODE` | Removed |
| `T3_API_HOST` | `T3_API_HOST` (unchanged), `connect(api_host=...)`, or `t3api login --host` |
| `HTTP_TIMEOUT`, `HTTP_CONNECT_TIMEOUT`, `HTTP_READ_TIMEOUT` | `connect(timeout=...)` |
| `VERIFY_SSL` | `connect(verify=...)` |
| `MAX_WORKERS` | `connect(concurrency=...)` |
| `RATE_LIMIT_RPS` | `connect(rate_limit=...)` |
| `RATE_LIMIT_BURST`, `BATCH_SIZE`, `RETRY_*` | Fixed internally. See [Retries](guide/errors-and-logging.md#retries). |
| `OTP_WHITELIST`, `EMAIL_WHITELIST` | Read from T3's `GET /v2/states` |
| `T3_LOG_HTTP`, `T3_LOG_FILE` | Unchanged. Secrets are now masked in the log. |
| `LOG_LEVEL`, `LOG_FORMAT`, `DEBUG_MODE` | Configure the standard `logging` module in your script |
| `OUTPUT_DIR`, `DEFAULT_FILE_FORMAT` and other output settings | Pass a path to `t3.to_csv()` / `t3.to_json()` |

## Before and after: browsing a collection

`scripts/example.py` picks a license and a collection, loads all of it,
browses it, then keeps the rows that match `input.csv`.

=== "1.x"

    ```python
    #!/usr/bin/env python3
    # /// script
    # requires-python = ">=3.8"
    # dependencies = [
    #     "duckdb",
    #     "httpx",
    #     "typer",
    #     "rich",
    #     "pyarrow"
    # ]
    # ///

    from typing import Any, Dict, List

    from t3api_utils.api.interfaces import MetrcObject
    from t3api_utils.api.parallel import load_all_data_sync
    from t3api_utils.main.utils import (get_authenticated_client_or_error,
                                        interactive_collection_handler,
                                        match_collection_from_csv, pick_license)
    from t3api_utils.openapi import pick_collection
    from t3api_utils.style import print_warning


    def main():
        # Get authenticated httpx-based client
        api_client = get_authenticated_client_or_error()

        # Pick a license interactively
        license = pick_license(api_client=api_client)

        selected_collection = pick_collection()

        # Load all data for the selected collection and license
        collection: List[MetrcObject] = load_all_data_sync(
            client=api_client,
            path=selected_collection["path"],
            license_number=license["licenseNumber"],
        )

        interactive_collection_handler(data=collection)

        filtered_collection = match_collection_from_csv(
            data=collection, on_no_match="error"
        )

        interactive_collection_handler(data=filtered_collection)


    if __name__ == "__main__":
        main()
    ```

=== "2.0"

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

What changed:

- `connect()` uses the saved secret key with no prompts, and the `with` block
  closes the connection pool.
- `client.license or client.pick_license()` skips the picker when the profile
  has a default license.
- The collection picker now finds every paginated endpoint in the spec (1.x
  found 138 of today's 187).
- `filter_rows()` takes the CSV path directly instead of prompting for it, and
  compares through an index rather than every row against every line.
- The numbered `interactive_collection_handler` menu is replaced by the
  inspector and an explicit `to_csv()`.

## Before and after: discontinuing items

`scripts/discontinue-items.py` discontinues every item named in `input.csv`.

=== "1.x"

    ```python
    #!/usr/bin/env python3
    # /// script
    # requires-python = ">=3.8"
    # dependencies = [
    #     "duckdb",
    #     "httpx",
    #     "typer",
    #     "rich",
    #     "pyarrow"
    # ]
    # ///

    from typing import Any, Dict, List

    from t3api_utils.api.interfaces import MetrcObject
    from t3api_utils.api.operations import send_api_request
    from t3api_utils.api.parallel import load_all_data_sync
    from t3api_utils.main.utils import (get_authenticated_client_or_error,
                                        interactive_collection_handler,
                                        match_collection_from_csv, pick_license)
    from t3api_utils.openapi import pick_collection
    from t3api_utils.style import print_warning


    def main():
        # Get authenticated httpx-based client
        api_client = get_authenticated_client_or_error()

        # Pick a license interactively
        license = pick_license(api_client=api_client)

        # selected_collection = pick_collection()

        # Load all data for the selected collection and license
        collection: List[MetrcObject] = load_all_data_sync(
            client=api_client,
            path="/v2/items",
            license_number=license["licenseNumber"],
        )

        # interactive_collection_handler(data=collection)

        filtered_collection = match_collection_from_csv(
            data=collection, on_no_match="error"
        )

        for item in filtered_collection:
            send_api_request(
                client=api_client,
                path="/v2/items/discontinue",
                method="POST",
                params={
                    "licenseNumber": license["licenseNumber"],
                    "submit": True
                },
                json_body={
                    "id": item["id"]
                }
            )


    if __name__ == "__main__":
        main()
    ```

=== "2.0"

    ```python
    #!/usr/bin/env python3
    # /// script
    # requires-python = ">=3.12"
    # dependencies = ["t3api-utils>=2.0"]
    # ///
    """Discontinue every item named in input.csv.

    Every row is validated with a dry run first. Nothing is sent to Metrc unless
    all rows pass (or you choose to send only the valid ones).
    """

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

What changed:

- **Safer.** The 1.x loop submitted each item straight to Metrc, so a bad row
  halfway through left the job half done. `bulk()` validates every row with a
  dry run first and submits nothing if any fail (in a terminal it asks whether
  to send only the valid ones).
- **Never repeated.** 1.x could send the same failed POST three times. 2.0
  never resends a write after a server error or timeout.
- **A record of what happened.** `log_to=` writes each row's status and the
  server's message to a CSV.
- **Smaller download.** `mask=["id", "name"]` asks the server for only the two
  fields the script uses.
- **Matching on `name` only**, explicitly, so extra columns in `input.csv`
  don't change what matches.
