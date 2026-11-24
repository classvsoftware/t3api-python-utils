from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest

import t3api_utils
from t3api_utils import _console, _http
from t3api_utils._http import DEFAULT_HOST
from t3api_utils.auth import resolve
from t3api_utils.auth.credentials import SECRET_KEY_HEADER, BearerAuth, SecretKeyAuth
from t3api_utils.auth.login import LoginResult
from t3api_utils.auth.resolve import SETUP_HELP, connect
from t3api_utils.auth.store import KEYRING_SERVICE, Profile, Store
from t3api_utils.client import T3Client
from t3api_utils.errors import AuthError, AuthRequired, ServerError
from tests.conftest import MemoryKeyring, Router

WHOAMI = "/v2/auth/whoami"
SANDBOX = "/v2/auth/sandbox"


def make_jwt(exp: float | None) -> str:
    claims = {} if exp is None else {"exp": exp}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJub25lIn0.{payload}.sig"


LIVE_JWT = make_jwt(time.time() + 3600)
EXPIRED_JWT = make_jwt(time.time() - 3600)


@pytest.fixture
def made(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[T3Client, dict[str, Any]]]]:
    """Every T3Client connect() builds, with the keyword arguments it got. Closed at teardown."""
    clients: list[tuple[T3Client, dict[str, Any]]] = []

    class SpyClient(T3Client):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            clients.append((self, kwargs))

    monkeypatch.setattr(resolve, "T3Client", SpyClient)
    yield clients
    for c, _ in clients:
        c.close()


@pytest.fixture
def api(router: Router, made: list[tuple[T3Client, dict[str, Any]]]) -> Router:
    router.add("GET", WHOAMI, json={"username": "jdoe", "hostname": "mo.metrc.com"})
    return router


@pytest.fixture
def store() -> Store:
    return Store()


def go(router: Router, **kwargs: Any) -> T3Client:
    return connect(transport=router.transport, **kwargs)


def save(store: Store, name: str, kind: str | None = "secret_key", secret: str | None = None, **fields: Any) -> Profile:
    profile = Profile(name=name, credential=kind, **fields)  # type: ignore[arg-type]
    store.save_profile(profile)
    if kind is not None and secret is not None:
        store.set_secret(name, kind, secret)  # type: ignore[arg-type]
    return profile


def sent_key(router: Router) -> str | None:
    return router.requests("GET", WHOAMI)[-1].headers.get(SECRET_KEY_HEADER)


def sent_bearer(router: Router) -> str | None:
    return router.requests("GET", WHOAMI)[-1].headers.get("Authorization")


@pytest.fixture
def fake_login(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the login flow; record how connect() called it."""
    calls: list[dict[str, Any]] = []

    def run_login(**kwargs: Any) -> LoginResult:
        calls.append(kwargs)
        profile = Profile(name=kwargs["profile_name"], api_host=kwargs["api_host"], license="LIC-LOGIN", credential="secret_key")
        return LoginResult(auth=SecretKeyAuth("sk-from-login"), profile=profile, secret_location="keyring")

    monkeypatch.setattr(resolve, "run_login", run_login)
    return calls


def test_connect_is_exported() -> None:
    assert t3api_utils.connect is connect


# --------------------------------------------------------------------------- credential order


def test_secret_key_argument_wins_over_everything(
    api: Router, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    save(store, "mo", secret="sk-profile")
    monkeypatch.setenv("T3_SECRET_KEY", "sk-env")
    monkeypatch.setenv("T3_JWT", LIVE_JWT)

    client = go(api, secret_key="sk-arg", jwt=LIVE_JWT)

    assert client.secret_key == "sk-arg"
    assert sent_key(api) == "sk-arg"
    assert sent_bearer(api) is None
    # An unnamed default profile's settings don't apply to a credential passed in code.
    assert client.profile is None


def test_jwt_argument_beats_environment(api: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T3_SECRET_KEY", "sk-env")
    client = go(api, jwt=f"Bearer {LIVE_JWT}")
    assert client.credential_kind == "jwt"
    assert sent_bearer(api) == f"Bearer {LIVE_JWT}"
    assert sent_key(api) is None


def test_env_secret_key_beats_env_jwt_and_profile(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    save(store, "mo", secret="sk-profile")
    monkeypatch.setenv("T3_SECRET_KEY", " sk-env ")
    monkeypatch.setenv("T3_JWT", LIVE_JWT)
    assert go(api).secret_key == "sk-env"
    assert sent_key(api) == "sk-env"


def test_env_jwt_beats_profile(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    save(store, "mo", secret="sk-profile")
    monkeypatch.setenv("T3_JWT", LIVE_JWT)
    client = go(api)
    assert client.credential_kind == "jwt"
    assert sent_bearer(api) == f"Bearer {LIVE_JWT}"


def test_blank_env_values_are_ignored(api: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T3_SECRET_KEY", "   ")
    monkeypatch.setenv("T3_JWT", f" {LIVE_JWT} ")
    assert go(api).credential_kind == "jwt"


def test_profile_secret_key(api: Router, store: Store, memory_keyring: MemoryKeyring) -> None:
    profile = save(store, "mo", secret="sk-profile", api_host="https://mo.t3.test", license="LIC-MO", username="jdoe")
    assert memory_keyring.passwords[(KEYRING_SERVICE, "mo:secret_key")] == "sk-profile"

    client = go(api)

    assert client.secret_key == "sk-profile"
    assert client.profile == profile
    assert client.base_url == "https://mo.t3.test"
    assert client.license == "LIC-MO"
    assert str(api.calls[0].url) == "https://mo.t3.test" + WHOAMI


def test_profile_live_jwt(api: Router, store: Store) -> None:
    save(store, "mo", kind="jwt", secret=LIVE_JWT)
    client = go(api)
    assert isinstance(client.http.auth, BearerAuth)
    assert sent_bearer(api) == f"Bearer {LIVE_JWT}"
    assert client.profile is not None and client.profile.name == "mo"


def test_profile_jwt_without_readable_expiry_is_used(api: Router, store: Store) -> None:
    save(store, "mo", kind="jwt", secret="opaque-token")
    assert go(api).credential_kind == "jwt"
    assert sent_bearer(api) == "Bearer opaque-token"


# --------------------------------------------------------------------------- no credential


def test_no_credential_without_terminal_raises_setup_help(api: Router) -> None:
    with pytest.raises(AuthRequired) as info:
        go(api)
    assert str(info.value) == SETUP_HELP
    assert "t3api login" in SETUP_HELP and "T3_SECRET_KEY" in SETUP_HELP and "connect(secret_key=...)" in SETUP_HELP
    assert api.calls == []


def test_expired_profile_jwt_without_terminal(api: Router, store: Store) -> None:
    save(store, "mo", kind="jwt", secret=EXPIRED_JWT)
    with pytest.raises(AuthRequired) as info:
        go(api)
    message = str(info.value)
    assert message.startswith("The JWT saved in profile 'mo' has expired.\n")
    assert message.endswith(SETUP_HELP)
    assert api.calls == []


@pytest.mark.parametrize(
    ("kind", "secret"),
    [("secret_key", None), ("jwt", None), (None, None)],
    ids=["secret-key-missing", "jwt-missing", "no-credential-kind"],
)
def test_profile_without_usable_secret(api: Router, store: Store, kind: str | None, secret: str | None) -> None:
    save(store, "mo", kind=kind, secret=secret)
    with pytest.raises(AuthRequired) as info:
        go(api)
    assert str(info.value) == SETUP_HELP


def test_interactive_false_never_prompts(api: Router, monkeypatch: pytest.MonkeyPatch, fake_login: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    with pytest.raises(AuthRequired):
        go(api, interactive=False)
    assert fake_login == []


def test_unknown_default_profile(api: Router, store: Store) -> None:
    store.config_dir.mkdir(parents=True)
    store.config_path.write_text('default_profile = "ghost"\n', encoding="utf-8")
    with pytest.raises(AuthRequired):
        go(api)


# --------------------------------------------------------------------------- login


def test_login_in_terminal(
    api: Router, monkeypatch: pytest.MonkeyPatch, fake_login: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(_console, "is_interactive", lambda: True)

    client = go(api, verify=False)

    (call,) = fake_login
    assert call["profile_name"] == "default"
    assert call["api_host"] == DEFAULT_HOST
    assert call["start_at"] == "start"
    assert isinstance(call["store"], Store)
    assert call["http_options"] == {"transport": call["http_options"]["transport"], "verify": False, "proxy": None}
    assert isinstance(call["http_options"]["transport"], httpx2.MockTransport)
    # The login result is what the client uses, and it is validated.
    assert client.secret_key == "sk-from-login"
    assert client.profile is not None and client.profile.name == "default"
    assert client.license == "LIC-LOGIN"
    assert sent_key(api) == "sk-from-login"


def test_interactive_true_logs_in_without_terminal(api: Router, fake_login: list[dict[str, Any]]) -> None:
    client = go(api, interactive=True, profile="new", license="LIC-ARG")
    assert fake_login[0]["profile_name"] == "new"
    assert client.license == "LIC-ARG"


def test_expired_jwt_restarts_login_at_offer_with_profile_host(
    api: Router, store: Store, fake_login: list[dict[str, Any]]
) -> None:
    save(store, "sandbox", kind="jwt", secret=EXPIRED_JWT, api_host="https://sandbox.t3.test")

    client = go(api, interactive=True)

    (call,) = fake_login
    assert call["start_at"] == "offer"
    assert call["profile_name"] == "sandbox"
    # The login runs against, and saves back, the profile's own API host.
    assert call["api_host"] == "https://sandbox.t3.test"
    assert client.base_url == "https://sandbox.t3.test"


def test_missing_secret_logs_in_to_profile_host(api: Router, store: Store, fake_login: list[dict[str, Any]]) -> None:
    save(store, "mo", kind="secret_key", api_host="https://mo.t3.test")
    go(api, interactive=True)
    assert fake_login[0]["start_at"] == "start"
    assert fake_login[0]["profile_name"] == "mo"
    assert fake_login[0]["api_host"] == "https://mo.t3.test"


def test_login_end_to_end(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch, memory_keyring: MemoryKeyring) -> None:
    answers: list[object] = [True, "sk-pasted", False]  # have a key? / paste it / pick a license?

    def answer(text: str, **kwargs: Any) -> object:
        return answers.pop(0)

    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    monkeypatch.setattr(_console, "ask", answer)
    monkeypatch.setattr(_console, "confirm", answer)

    client = go(api)

    assert answers == []
    assert client.secret_key == "sk-pasted"
    assert memory_keyring.passwords == {(KEYRING_SERVICE, "default:secret_key"): "sk-pasted"}
    assert store.get_profile("default") == client.profile
    # One whoami from the login flow, one from connect()'s validation.
    assert [r.headers[SECRET_KEY_HEADER] for r in api.requests("GET", WHOAMI)] == ["sk-pasted", "sk-pasted"]


# --------------------------------------------------------------------------- which profile


def test_profile_choice_order(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    save(store, "a", secret="sk-a")
    save(store, "b", secret="sk-b")
    save(store, "c", secret="sk-c")
    assert store.default_profile_name() == "a"

    assert go(api).secret_key == "sk-a"
    monkeypatch.setenv("T3_PROFILE", "b")
    assert go(api).secret_key == "sk-b"
    assert go(api, profile="c").secret_key == "sk-c"


def test_named_profile_settings_apply_to_env_credential(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = save(store, "mo", secret="sk-profile", api_host="https://mo.t3.test", license="LIC-MO")
    monkeypatch.setenv("T3_SECRET_KEY", "sk-env")

    client = go(api, profile="mo")

    assert client.secret_key == "sk-env"
    assert client.profile == profile
    assert (client.base_url, client.license) == ("https://mo.t3.test", "LIC-MO")


def test_t3_profile_counts_as_named(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    save(store, "mo", secret="sk-profile", api_host="https://mo.t3.test")
    monkeypatch.setenv("T3_PROFILE", "mo")
    assert go(api, secret_key="sk-arg").base_url == "https://mo.t3.test"


def test_unnamed_default_profile_ignored_for_env_credential(
    api: Router, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    save(store, "mo", secret="sk-profile", api_host="https://mo.t3.test", license="LIC-MO")
    monkeypatch.setenv("T3_SECRET_KEY", "sk-env")
    client = go(api)
    assert (client.base_url, client.license, client.profile) == (DEFAULT_HOST, None, None)


# --------------------------------------------------------------------------- base URL and license


def test_base_url_order(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    save(store, "mo", secret="sk", api_host="https://profile.t3.test/")
    assert go(api).base_url == "https://profile.t3.test"
    monkeypatch.setenv("T3_API_HOST", "https://env.t3.test")
    assert go(api).base_url == "https://env.t3.test"
    client = go(api, api_host="https://arg.t3.test/")
    assert client.base_url == "https://arg.t3.test"
    assert str(api.calls[-1].url) == "https://arg.t3.test" + WHOAMI


def test_default_base_url(api: Router) -> None:
    client = go(api, secret_key="sk")
    assert client.base_url == DEFAULT_HOST
    assert str(api.calls[0].url) == DEFAULT_HOST + WHOAMI


def test_license_order(api: Router, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    save(store, "mo", secret="sk", license="LIC-PROFILE")
    assert go(api).license == "LIC-PROFILE"
    monkeypatch.setenv("T3_LICENSE", "LIC-ENV")
    assert go(api).license == "LIC-ENV"
    assert go(api, license="LIC-ARG").license == "LIC-ARG"


def test_no_license(api: Router) -> None:
    assert go(api, secret_key="sk").license is None


# --------------------------------------------------------------------------- validation and sandbox


def test_validate_false_makes_no_requests(api: Router) -> None:
    client = go(api, secret_key="sk", validate=False)
    assert api.calls == []
    assert client.secret_key == "sk"


def test_rejected_secret_key_raises_and_closes(api: Router, made: list[tuple[T3Client, dict[str, Any]]]) -> None:
    api.add("GET", WHOAMI, status=401, json={"detail": "Invalid secret key"})
    with pytest.raises(AuthError, match="t3api keys rotate") as info:
        go(api, secret_key="sk-revoked")
    assert info.value.status_code == 401
    assert made[0][0].http.is_closed


def test_rejected_jwt_raises_and_closes(api: Router, made: list[tuple[T3Client, dict[str, Any]]]) -> None:
    api.add("GET", WHOAMI, status=401, json={"detail": "expired"})
    with pytest.raises(AuthError, match="JWT has expired"):
        go(api, jwt=LIVE_JWT)
    assert made[0][0].http.is_closed


def test_sandbox_switches_to_sandbox_jwt(api: Router) -> None:
    api.add("POST", SANDBOX, json={"accessToken": "sandbox.jwt.token"})

    client = go(api, secret_key="sk-real", sandbox=True)

    assert client.credential_kind == "jwt"
    assert [(r.method, r.url.path) for r in api.calls] == [("POST", SANDBOX), ("GET", WHOAMI)]
    assert api.calls[0].headers[SECRET_KEY_HEADER] == "sk-real"
    assert api.calls[1].headers["Authorization"] == "Bearer sandbox.jwt.token"
    assert SECRET_KEY_HEADER not in api.calls[1].headers


def test_sandbox_without_validation(api: Router) -> None:
    api.add("POST", SANDBOX, json={"accessToken": "sandbox.jwt.token"})
    client = go(api, secret_key="sk-real", sandbox=True, validate=False)
    assert [r.url.path for r in api.calls] == [SANDBOX]
    assert client.credential_kind == "jwt"


def test_sandbox_failure_closes_client(api: Router, made: list[tuple[T3Client, dict[str, Any]]]) -> None:
    api.add("POST", SANDBOX, status=500, json={"detail": "sandbox down"})
    with pytest.raises(ServerError):
        go(api, secret_key="sk-real", sandbox=True)
    assert made[0][0].http.is_closed
    assert api.requests("GET", WHOAMI) == []


# --------------------------------------------------------------------------- client options


@pytest.mark.parametrize(
    ("env", "arg", "expected"),
    [(None, None, "auto"), ("bundled", None, "bundled"), (" BUNDLED ", None, "bundled"), ("live", None, "auto"), ("bundled", "auto", "auto")],
)
def test_spec_mode(
    api: Router,
    monkeypatch: pytest.MonkeyPatch,
    made: list[tuple[T3Client, dict[str, Any]]],
    env: str | None,
    arg: str | None,
    expected: str,
) -> None:
    if env is not None:
        monkeypatch.setenv("T3_SPEC", env)
    go(api, secret_key="sk", validate=False, spec=arg)
    assert made[0][1]["spec"] == expected


def test_t3_spec_bundled_uses_bundled_copy(api: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T3_SPEC", "bundled")
    client = go(api, secret_key="sk", validate=False)
    assert client.spec.source is not None and client.spec.source.kind == "bundled"
    assert api.calls == []


@pytest.mark.parametrize(
    ("env", "arg", "expected"),
    [(None, None, False), ("1", None, True), ("yes", None, True), ("0", None, False), ("1", False, False), (None, True, True)],
)
def test_log_http(
    api: Router,
    monkeypatch: pytest.MonkeyPatch,
    made: list[tuple[T3Client, dict[str, Any]]],
    env: str | None,
    arg: bool | None,
    expected: bool,
) -> None:
    enabled: list[str | None] = []
    monkeypatch.setattr(_http, "enable_http_logging", lambda log_file=None: enabled.append(log_file))
    monkeypatch.setenv("T3_LOG_FILE", "http.log")
    if env is not None:
        monkeypatch.setenv("T3_LOG_HTTP", env)

    go(api, secret_key="sk", validate=False, log_http=arg)

    assert made[0][1]["log_http"] is expected
    assert enabled == (["http.log"] if expected else [])


def test_options_are_passed_to_the_client(api: Router, made: list[tuple[T3Client, dict[str, Any]]]) -> None:
    transport = api.transport
    client = connect(
        secret_key="sk",
        rate_limit=None,
        concurrency=3,
        timeout=7.5,
        verify="/path/to/ca.pem",
        proxy="http://proxy.local:3128",
        transport=transport,
    )
    kwargs = made[0][1]
    assert kwargs["transport"] is transport
    assert (kwargs["rate_limit"], kwargs["concurrency"], kwargs["timeout"]) == (None, 3, 7.5)
    assert (kwargs["verify"], kwargs["proxy"]) == ("/path/to/ca.pem", "http://proxy.local:3128")
    assert client.concurrency == 3
    assert client.http.timeout.read == 7.5
    assert len(api.calls) == 1  # the transport really was used


def test_defaults_passed_to_the_client(api: Router, made: list[tuple[T3Client, dict[str, Any]]]) -> None:
    go(api, secret_key="sk")
    kwargs = made[0][1]
    assert (kwargs["rate_limit"], kwargs["concurrency"], kwargs["timeout"]) == (10.0, 10, 30.0)
    assert (kwargs["verify"], kwargs["proxy"], kwargs["log_http"]) == (True, None, False)


def test_context_manager_closes(api: Router) -> None:
    with go(api, secret_key="sk") as client:
        assert not client.http.is_closed
    assert client.http.is_closed


def test_named_profile_that_does_not_exist_says_so(api: Router) -> None:
    with pytest.raises(AuthRequired) as info:
        go(api, profile="typo")
    assert str(info.value).startswith("There is no saved profile named 'typo'.\n")
    assert str(info.value).endswith(SETUP_HELP)
