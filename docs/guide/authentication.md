# Authentication

## Secret keys first

T3 accepts two credentials:

| Credential | Sent as | Lasts | Role |
|---|---|---|---|
| Secret key | `X-T3-API-Key` header | Until it's deleted or disabled, or the Metrc login behind it changes | The default. Use it everywhere. |
| JWT | `Authorization: Bearer` header | 24 hours | Fallback for a short session |

A secret key is created once from your Metrc hostname, username and password
(plus email or OTP seed in states that need them). T3 keeps what it needs to
sign in to Metrc for you, so a script holding the key never needs your Metrc
password. The library never stores the password.

Requests always send the secret key in the header. The one deliberate
exception is [`client.report_url()`](reports-and-tag-lists.md#report-urls-for-spreadsheets),
which puts it in a URL for spreadsheets to pull.

There are three ways to get a key:

- `t3api login` (recommended): creates one and saves it to a profile.
- `t3api keys create`: creates one, prints it once, and offers to save it.
- In the browser at <https://api.trackandtrace.tools/v2/pages/secret-key>.
  Paste it into `t3api login` when it asks whether you already have one.

API-key auth (`/v2/auth/apikey`) from 1.x is gone.

## The login flow

`t3api login` runs it. So does `connect()`, when it finds no credential and a
person is there to answer.

1. **Existing key.** "Do you already have a T3 secret key?" Paste it; it's
   checked with `GET /v2/auth/whoami` and saved.
2. **Metrc login.** Hostname (a state abbreviation like `CA` works), username
   and password. The client reads `GET /v2/states` to find out whether your
   state needs an email (`requiresEmail`) or a one-time password
   (`requiresOtp`), and asks only for what's needed. If that endpoint can't be
   reached, it falls back to the 1.x rules: `mi.metrc.com` needs an OTP and
   `co.metrc.com` needs an email.
3. **The secret-key offer** (default yes): "Create a secret key so you don't
   have to log in again?"
    - **Yes:** calls `POST /v2/auth/secretkey` and saves the key. In OTP states
      it asks for the **OTP seed**, the base32 secret behind your authenticator
      app, not a 6-digit code: T3 signs in to Metrc on your behalf later and
      needs to make its own codes.
    - **No:** calls `POST /v2/auth/credentials` and saves only the JWT. In OTP
      states it takes a 6-digit code (or a seed, which it turns into a code).
      The JWT expires in 24 hours.
4. **Default license.** Optionally pick one for the profile.

When a saved JWT has expired, `connect()` in a terminal starts again at step 3,
so you're offered a secret key each time.

## How connect() finds a credential

```python
import t3api_utils as t3

client = t3.connect()
```

`connect()` stops at the first of these that supplies a credential:

| # | Source | Notes |
|---|---|---|
| 1 | `connect(secret_key=...)` or `connect(jwt=...)` | Wins over everything. |
| 2 | `T3_SECRET_KEY`, then `T3_JWT` | Best for CI and scheduled jobs. |
| 3 | The profile's saved secret key, or its JWT if it hasn't expired | See [which profile](#which-profile) below. |
| 4 | The login flow | Only when `interactive` allows it (below). |
| - | Otherwise | Raises `AuthRequired` with setup instructions. |

Then it validates the credential with one `GET /v2/auth/whoami` call. A
rejected credential raises `AuthError`, and the client is closed for you.
`connect(validate=False)` skips the check.

**Prompts.** By default `connect()` prompts only when someone can answer: a
terminal, or a Jupyter notebook. It never prompts when stdin isn't a terminal,
so a cron job or CI step without a credential fails at once instead of waiting
for input. `interactive=False` never prompts; `interactive=True` allows it.

### Which profile

The profile is `connect(profile=...)`, then `T3_PROFILE`, then the default
profile in the config file.

The profile also supplies the API host and default license. When the
credential comes from an argument or environment variable (steps 1 and 2), the
*default* profile is not consulted for those, so `T3_SECRET_KEY` on its own
always means the production host and no default license. Name a profile
(`profile=` or `T3_PROFILE`) to use its settings alongside a key from the
environment.

### Which API host

`connect(api_host=...)`, then `T3_API_HOST`, then the profile's `api_host`,
then `https://api.trackandtrace.tools`.

### Which default license

`connect(license=...)`, then `T3_LICENSE`, then the profile's `license`. It's
available as `client.license`, and it's used only by calls whose endpoint
requires a `licenseNumber`. A license passed to a call always wins.

In the [sandbox](#sandbox), only `connect(license=...)` counts: `T3_LICENSE`
and the profile's license are production licenses.

### Other connect() options

| Option | Default | What it does |
|---|---|---|
| `validate` | `True` | Check the credential with `/v2/auth/whoami`. |
| `sandbox` | `T3_SANDBOX`, then `False` | Swap the credential for a Metrc sandbox JWT. See [Sandbox](#sandbox). |
| `spec` | `T3_SPEC`, then `"auto"` | `"bundled"` pins the spec shipped with the package. See [Endpoints and the spec](endpoints-and-spec.md#where-the-spec-comes-from). |
| `rate_limit` | `10.0` | Requests per second across all threads. `None` turns it off. |
| `concurrency` | `10` | Threads used to fetch collection pages. |
| `timeout` | `30.0` | Request timeout in seconds. Reports always get 5 minutes. |
| `log_http` | `T3_LOG_HTTP` | Log every request and response, secrets masked. |
| `verify`, `proxy` | `True`, `None` | TLS verification and proxy URL, as in httpx2. |
| `transport` | `None` | An `httpx2` transport to use instead of the network (for tests). |

## Profiles and where secrets live

A profile is a saved login. Non-secret settings go in `config.toml` in the
user config folder:

| OS | Config folder |
|---|---|
| macOS | `~/Library/Application Support/t3api-utils/` |
| Linux | `~/.config/t3api-utils/` |
| Windows | `%LOCALAPPDATA%\t3api-utils\` |

```toml title="config.toml"
default_profile = "mo"

[profiles.mo]
api_host = "https://api.trackandtrace.tools"
metrc_hostname = "mo.metrc.com"
username = "jdoe"
license = "LIC-00001"        # optional default
credential = "secret_key"    # or "jwt"
```

Secrets are not in that file. They go in the OS keyring under the service name
`t3api-utils`, with the entry `<profile>:secret_key` or `<profile>:jwt`: macOS
Keychain, Windows Credential Manager, or Secret Service on Linux.

**No keyring?** On headless Linux or in a container there may be no keyring
backend. If a keyring write fails, the secret goes in `secrets.toml` next to
`config.toml`, created readable only by you, and a warning says so. For CI,
skip profiles and use `T3_SECRET_KEY`.

Manage profiles from the command line:

```bash
t3api login --profile mi-prod      # create or update a profile
t3api profiles list                # show them all; the default is ticked
t3api profiles use mi-prod         # make it the default
t3api profiles remove mi-prod      # delete it and its saved secret
t3api license set LIC-00001 -p mi-prod
t3api logout -p mi-prod            # forget the saved credential, keep the profile
```

The first profile you create becomes the default.

## Environment variables

These are the only environment variables the library reads. There's no
`.t3.env` file.

| Variable | What it does |
|---|---|
| `T3_SECRET_KEY` | Secret key to use. Wins over any saved profile. |
| `T3_JWT` | JWT to use, if `T3_SECRET_KEY` isn't set. |
| `T3_PROFILE` | Profile to use instead of the default. `t3api` commands that take `--profile` read it too. |
| `T3_LICENSE` | Default license number. Ignored in the sandbox. |
| `T3_SANDBOX` | `1`, `true`, `yes` or `on` makes `connect()` and the `t3api` data commands use the [Metrc sandbox](#sandbox). |
| `T3_API_HOST` | T3 API base URL, e.g. a staging host. |
| `T3_SPEC` | `bundled` pins the spec shipped with the package. |
| `T3_LOG_HTTP` | `1`, `true`, `yes` or `on` logs every request and response at DEBUG. |
| `T3_LOG_FILE` | With `T3_LOG_HTTP`, write that log to this file. |

## Scheduled jobs and CI

Set `T3_SECRET_KEY` from your CI system's secret store and call `connect()`
with no arguments:

```yaml title=".github/workflows/nightly.yml (excerpt)"
env:
  T3_SECRET_KEY: ${{ secrets.T3_SECRET_KEY }}
  T3_LICENSE: LIC-00001
steps:
  - run: uv run nightly_export.py
```

```python title="nightly_export.py"
import t3api_utils as t3

with t3.connect(interactive=False) as client:
    rows = client.collect("METRC_ACTIVE_PACKAGES")
    t3.to_csv(rows, "packages.csv")
```

`interactive=False` is the default behaviour without a terminal anyway; passing
it makes the intent clear. If the key is missing, the job fails with
`AuthRequired` and instructions instead of waiting for input.

## Managing secret keys

A secret key's ID is the key value itself, so `rotate` and `delete` take the
key.

| Python (`client.secret_keys`) | CLI | Endpoint |
|---|---|---|
| `list()` | `t3api keys list` (keys masked) | `GET /v2/auth/secretkey` |
| `create(hostname, username, password, email=None, otp_seed=None)` | `t3api keys create` | `POST /v2/auth/secretkey` |
| `rotate(key, password=..., username=None, hostname=None, email=None, otp_seed=None)` | `t3api keys rotate [KEY]` | `PUT /v2/auth/secretkey/{key}` |
| `delete(key)` | `t3api keys revoke KEY` | `DELETE /v2/auth/secretkey/{key}` |

```python
for key in client.secret_keys.list():
    print(key["isEnabled"], key["isManaged"], key["lastUsedAt"])
```

**After a Metrc password, email or OTP change**, the key stops working:
requests fail with `AuthError` and a hint to rotate. Rotating updates the Metrc
login stored behind the key. The key value stays the same, so nothing that
uses it needs changing:

```bash
t3api keys rotate
```

With no argument it rotates the profile's saved key. In Python,
`client.secret_keys.rotate(key, password="...")` fills in the username and
hostname from the profile, or from `whoami`.

**To cut a key off**, delete it. Anything using it stops working, including
report URLs that contain it. Managed keys can't be deleted (the server answers
403).

```bash
t3api keys revoke 1b2c3d4e-...
```

**Logging out.** `t3api logout` removes the profile's saved secret from this
machine; the key itself still works. `t3api logout --everywhere` also calls
`POST /v2/auth/logout`, which ends all of the account's Metrc sessions.

## Sandbox

`connect(sandbox=True)` exchanges your credential for a Metrc sandbox JWT
through `POST /v2/auth/sandbox`. Everything the client does after that,
including `submit=True` writes, goes to the Metrc sandbox instead of
production:

```python
with t3.connect(sandbox=True) as client:
    lic = client.pick_license()        # the sandbox's own licenses
    client.post("/v2/items/discontinue", license=lic, json={"id": 12345}, submit=True)
```

To point an existing script or scheduled job at the sandbox without editing
it, set `T3_SANDBOX=1`. The `t3api` command takes `--sandbox` before the
command name (`t3api --sandbox pull ...`); see [the CLI guide](cli.md#conventions).

**Licenses.** The sandbox has its own licenses (such as `SF-SBX-1-101`), and it
answers a request for any other license with an empty result, not an error. A
production license would quietly return nothing. So in the sandbox:

- `T3_LICENSE` and the profile's default license are ignored, and
  `client.license` is `None` unless you passed `connect(license=...)`. The
  common `license or client.license or client.pick_license()` pattern then
  asks you to pick a sandbox license.
- The first time a call names a license, the client lists the session's
  licenses (one request, cached) and logs a warning for any license that isn't
  one of them.

**Telling where you are.** `client.sandbox` is `True` in the sandbox, and
`client.hostname` is the Metrc hostname behind the credential, such as
`sandbox-me.metrc.com` (from `whoami`). Entering the sandbox logs
`Using the Metrc sandbox (sandbox-me.metrc.com).` at INFO, and
`bulk(submit="ask")` says "sandbox" when it asks.

The client's credential is a JWT from then on (`client.credential_kind ==
"jwt"`), so `report_url()`, which needs a secret key, isn't available. An
existing client can switch with `client.enter_sandbox()`, which also clears
`client.license`.

## Using a credential directly

`connect()` is the usual way in, but `T3Client` can be built by hand with one
of the two `httpx2.Auth` classes:

```python
client = t3.T3Client(auth=t3.SecretKeyAuth("..."), license="LIC-00001")
```

This skips profiles, environment variables and validation entirely.
