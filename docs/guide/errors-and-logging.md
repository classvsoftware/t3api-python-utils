# Errors and logging

## Exceptions

Every exception the library raises on purpose derives from `t3.T3Error`, and
all of them can be imported from the top-level package.

```text
T3Error
├── AuthRequired         no credential found, and no terminal to ask in
├── NotInteractive       a picker or prompt was called without a terminal
├── SpecError            missing required parameter, wrong endpoint kind
│   └── UnknownEndpoint  ID or path not in the spec
└── APIError             any non-2xx response
    ├── AuthError        401, 403
    ├── NotFound         404
    ├── ValidationError  400, 422
    │   └── TagListResolveError
    ├── RateLimited      429, after retries
    └── ServerError      5xx
```

`SpecError` and its subclass are raised **before** any request is sent, so
fixing them never risks a duplicate write.

### What an APIError carries

| Attribute | What it holds |
|---|---|
| `status_code` | The HTTP status, e.g. `422`. |
| `detail` | The server's explanation, from its error body. Falls back to the body text, truncated. |
| `errors` | Per-item problems from the error body, if any (for example one per failing tag-list handle). |
| `code` | The server's machine-readable error code, if any. |
| `hint` | What to do about it, when the library knows (auth and rate-limit errors). |
| `method`, `url` | The request, with any secret key in the URL masked. |
| `response` | The full `httpx2.Response`. |

The message reads like
`422 Unprocessable Entity from POST /v2/items/discontinue: <detail>`, with the
hint on the next line when there is one.

```python
import t3api_utils as t3

try:
    client.post("/v2/items/discontinue", license="LIC-00001", json={"id": 12345}, submit=True)
except t3.ValidationError as exc:
    print("Rejected:", exc.detail)
    for problem in exc.errors:
        print("  ", problem)
except t3.AuthError as exc:
    print(exc.hint)
    raise
```

### Auth errors and their hints

| Situation | Hint |
|---|---|
| 401 with a secret key, server code `METRC_LOGIN_FAILURE` | The Metrc login behind the key changed. Run `t3api keys rotate` (the key value stays the same). |
| Other 401 with a secret key | The key was deleted or disabled, or the Metrc login behind it changed. Run `t3api keys rotate`, or `t3api login` to save a new one. |
| 401 with a JWT | It expired (JWTs last 24 hours). Run `t3api login`. |
| 403 | The credential works but can't access this. Check the license number and the account's permissions. |

### Other exceptions you may see

| Exception | When |
|---|---|
| `ValueError` | Misuse that the library can spot locally: `submit=` on a route with no dry run, `dynamic=True` on a route without dynamic validation, more than 20 licenses on a report, an empty license list, a bad `submit`, `on_error`, `batch_size` or `on_unmatched` value, an unknown column in `filter_rows()`, an empty list given to `t3.choose()`. |
| `TypeError` | A path parameter the endpoint doesn't have. Query parameters go in `params=`. |
| `ImportError` | `t3.inspect()` without the `[tui]` extra. The message names the install command. |
| `NotInteractive` | A picker, prompt or `bulk(submit="ask")` with no terminal to ask in. See [Prompts and pickers](prompts.md#without-a-terminal). |
| `KeyboardInterrupt` | Ctrl-C at a picker or prompt. The library never calls `sys.exit()`; it's up to your script. |
| `httpx2` transport errors | The network failed for good after retries (DNS, connection refused, timeouts). |

## Retries

Retries are built into the client's transport, so they apply to every call,
including those made through `client.http`.

| Method | Retried on | Never retried |
|---|---|---|
| GET, HEAD, OPTIONS | Connection errors and timeouts; 429, 502, 503, 504 | Other 4xx and 5xx |
| POST, PUT, PATCH, DELETE | 429; connection failures before the request was sent | 5xx, timeouts after sending, every other 4xx |

- **At most 3 attempts**, with exponential backoff and jitter: about 0.5
  seconds before the second attempt and 1 second before the third. A
  `Retry-After` header from the server is honoured instead, up to 60 seconds.
- **Why writes are different.** A 429 means T3 rejected the request outright,
  so sending it again is safe. A 5xx, or a timeout after the request went out,
  may mean the write already reached Metrc, so it's raised to you instead of
  being repeated. A write that gets a 400 is sent exactly once.
- Each retry logs a warning on the `t3api_utils` logger.

## Rate limiting

Each client has one rate limiter, shared by every request it makes, including
the threads that fetch collection pages. The defaults are 10 requests per
second and 10 paging threads. Change them on `connect()`:

```python
client = t3.connect(rate_limit=5, concurrency=4)    # gentler
client = t3.connect(rate_limit=None)                # no client-side limit
```

If T3 still answers 429 after the retries, the call raises `RateLimited`, with
a hint to lower `rate_limit` or `concurrency`.

## Timeouts

| Request | Timeout |
|---|---|
| Normal requests | 30 seconds (`connect(timeout=...)` changes it) |
| Report downloads | 5 minutes |
| Spec and `/v2/states` fetches | 5 seconds (falls back to a cached or bundled copy) |

Single calls take `timeout=` too: `client.get(..., timeout=120)`.

## Logging

The library logs to `logging.getLogger("t3api_utils")` and never configures
handlers or the root logger itself. If your script doesn't set up logging,
Python's fallback handler still prints warnings to stderr, but INFO messages
such as dry-run notices stay hidden. To see everything:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

| Level | Examples |
|---|---|
| WARNING | Retries; a query parameter, or an `include` value, the spec doesn't list; a JSON body whose shape (list or object) doesn't match the route's; a license that isn't one of the sandbox session's; rows that failed validation in `bulk()`; a stale spec cache; no OS keyring; every `report_url()` call. |
| INFO | Dry-run notices (`dry run: pass submit=True to send ... to Metrc`); entering the sandbox (`Using the Metrc sandbox (sandbox-me.metrc.com).`) and the default license it ignores; duplicate rows dropped by `collect()`; the `bulk()` summary; falling back to the bundled spec. |

The `t3api` command sets up its own Rich log output; `-v` shows INFO messages.

## HTTP logging

To see every request and response, turn on HTTP logging:

```bash
T3_LOG_HTTP=1 uv run my_script.py                         # to stderr
T3_LOG_HTTP=1 T3_LOG_FILE=t3_http.log uv run my_script.py  # to a file
```

or in code:

```python
client = t3.connect(log_http=True)
```

Each request and response is logged at DEBUG on the `t3api_utils.http`
logger, with method, URL, headers and body:

```text
2026-11-23 14:05:09,112 t3api_utils.http → GET https://api.trackandtrace.tools/v2/items?pageSize=100&licenseNumber=LIC-00001 headers={..., 'x-t3-api-key': '***'} body=
2026-11-23 14:05:09,431 t3api_utils.http ← 200 GET https://api.trackandtrace.tools/v2/items?pageSize=100&licenseNumber=LIC-00001 headers={...} body={"data": [...], ...}
```

`T3_LOG_FILE` adds a file handler. Without it, a stderr handler is added only
if nothing else would print the messages; if your script already configured
logging, the messages go through your handlers.

**What's masked.** HTTP logs are meant to be safe to share with support:

- The `Authorization`, `X-T3-API-Key`, `Cookie` and `Set-Cookie` headers.
- The key in `/v2/auth/secretkey/{key}` paths and in any `secretKey=` query
  parameter.
- These JSON body fields, at any depth: `password`, `otp`, `otpSeed`,
  `secretKey`, `accessToken`, `refreshToken`.
- Form bodies aren't logged at all, and neither are non-JSON response bodies
  (CSV, XLSX, PDF). Logged bodies are cut off at 4,000 characters.

The rest of each body is logged as is, so HTTP logs still contain your Metrc
data. Treat them like any other export.
