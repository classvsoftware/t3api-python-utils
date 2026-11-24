from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx2
import keyring
import pytest
from keyring.backends import fail

from t3api_utils import _console, _paths
from t3api_utils._http import build_client
from t3api_utils.auth import login as login_module
from t3api_utils.auth.credentials import SECRET_KEY_HEADER, BearerAuth, SecretKeyAuth, otp_code
from t3api_utils.auth.login import (
    CREDENTIALS_PATH,
    LICENSES_PATH,
    WHOAMI_PATH,
    LoginResult,
    StartAt,
    credentials_login,
    run_login,
)
from t3api_utils.auth.secret_keys import SECRET_KEY_PATH
from t3api_utils.auth.states import STATES_PATH
from t3api_utils.auth.store import KEYRING_SERVICE, Profile, Store
from t3api_utils.errors import AuthError, ValidationError
from tests.conftest import MemoryKeyring, Router

API = "https://api.t3.test"
PASSWORD = "Hunter2-Metrc-Password!"
NEW_KEY = "sk-created-by-t3-0001"
GOOD_KEY = "sk-pasted-good-0002"
JWT = "header.payload.jwt-from-credentials"
SEED = "JBSWY3DPEHPK3PXP"
DEFAULT = object()  # answer a prompt with its default

STATES: list[dict[str, Any]] = [
    {"abbreviation": "CA", "name": "California", "hostname": "ca.metrc.com", "requiresEmail": False, "requiresOtp": False},
    {"abbreviation": "MI", "name": "Michigan", "hostname": "mi.metrc.com", "requiresEmail": False, "requiresOtp": True},
    {"abbreviation": "CO", "name": "Colorado", "hostname": "co.metrc.com", "requiresEmail": True, "requiresOtp": False},
]
LICENSES: list[dict[str, Any]] = [
    {"licenseNumber": "LIC-1", "licenseName": "First"},
    {"licenseNumber": "LIC-2", "licenseName": "Second"},
]


# --------------------------------------------------------------------------- scripted prompts


@dataclass
class Prompt:
    kind: str  # "ask" or "confirm"
    expect: str  # a substring of the prompt text
    answer: object


def Ask(expect: str, answer: object) -> Prompt:  # noqa: N802 - reads like a step
    return Prompt("ask", expect, answer)


def Confirm(expect: str, answer: bool) -> Prompt:  # noqa: N802 - reads like a step
    return Prompt("confirm", expect, answer)


@dataclass
class Asked:
    kind: str
    text: str
    default: object
    password: bool


@dataclass
class Prompts:
    """Stands in for ``_console.ask`` / ``_console.confirm`` with scripted answers, in order."""

    script: list[Prompt] = field(default_factory=list)
    asked: list[Asked] = field(default_factory=list)

    def expect(self, *steps: Prompt) -> None:
        self.script.extend(steps)

    def _next(self, kind: str, text: str) -> Prompt:
        assert self.script, f"unexpected prompt {text!r}"
        step = self.script.pop(0)
        assert step.kind == kind and step.expect in text, f"expected {step.kind} {step.expect!r}, got {kind} {text!r}"
        return step

    def ask(self, text: str, *, default: str | None = None, password: bool = False, allow_empty: bool = False) -> str:
        step = self._next("ask", text)
        self.asked.append(Asked("ask", text, default, password))
        if step.answer is DEFAULT:
            assert default is not None
            return default
        assert isinstance(step.answer, str)
        return step.answer

    def confirm(self, text: str, *, default: bool = True) -> bool:
        step = self._next("confirm", text)
        self.asked.append(Asked("confirm", text, default, False))
        assert isinstance(step.answer, bool)
        return step.answer

    def find(self, expect: str) -> Asked:
        return next(a for a in self.asked if expect in a.text)


@pytest.fixture
def prompts(monkeypatch: pytest.MonkeyPatch) -> Iterator[Prompts]:
    p = Prompts()
    monkeypatch.setattr(_console, "is_interactive", lambda: True)
    monkeypatch.setattr(_console, "ask", p.ask)
    monkeypatch.setattr(_console, "confirm", p.confirm)
    yield p
    assert p.script == [], f"prompts never asked: {p.script}"


@pytest.fixture
def messages(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Every success/error/warning/info/header message, as (level, text)."""
    recorded: list[tuple[str, str]] = []
    for level in ("success", "error", "warning", "info", "header"):
        monkeypatch.setattr(_console, level, lambda text, level=level: recorded.append((level, text)))
    return recorded


def _said(messages: list[tuple[str, str]], level: str, text: str) -> bool:
    return any(lvl == level and text in msg for lvl, msg in messages)


# --------------------------------------------------------------------------- fake API


def _whoami(request: httpx2.Request) -> httpx2.Response:
    """Accepts GOOD_KEY and NEW_KEY; rejects any other key."""
    if request.headers.get(SECRET_KEY_HEADER) in (GOOD_KEY, NEW_KEY):
        return httpx2.Response(200, json={"username": "jdoe", "hostname": "mo.metrc.com"})
    return httpx2.Response(401, json={"detail": "Invalid secret key"})


@pytest.fixture
def api(router: Router) -> Router:
    router.add("GET", STATES_PATH, json=STATES)
    router.add("GET", WHOAMI_PATH, handler=_whoami)
    router.add("POST", SECRET_KEY_PATH, json={"secretKey": NEW_KEY})
    router.add("POST", CREDENTIALS_PATH, json={"accessToken": JWT})
    router.add("GET", LICENSES_PATH, json=LICENSES[:1])
    return router


@pytest.fixture
def store() -> Store:
    return Store()


def login(router: Router, store: Store, *, profile: str = "default", start_at: StartAt = "start") -> LoginResult:
    return run_login(
        store=store,
        profile_name=profile,
        api_host=API,
        start_at=start_at,
        http_options={"transport": router.transport},
    )


def _body(request: httpx2.Request) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(request.content)
    return body


def assert_password_never_stored(store: Store, memory_keyring: MemoryKeyring) -> None:
    for folder in (store.config_dir, _paths.cache_dir()):
        for path in folder.rglob("*") if folder.exists() else []:
            if path.is_file():
                assert PASSWORD.encode() not in path.read_bytes(), path
    assert all(PASSWORD not in value for value in memory_keyring.passwords.values())


# --------------------------------------------------------------------------- credentials_login


def test_credentials_login_minimal(router: Router) -> None:
    router.add("POST", CREDENTIALS_PATH, json={"accessToken": JWT})
    with httpx2.Client(base_url=API, transport=router.transport) as http:
        assert credentials_login(http, hostname="ca.metrc.com", username="u", password=PASSWORD) == JWT
    assert _body(router.calls[0]) == {"hostname": "ca.metrc.com", "username": "u", "password": PASSWORD}


def test_credentials_login_with_email_and_code(router: Router) -> None:
    router.add("POST", CREDENTIALS_PATH, json={"accessToken": JWT})
    with httpx2.Client(base_url=API, transport=router.transport) as http:
        credentials_login(http, hostname="h", username="u", password="p", email="e@x.com", otp=" 123456 ")
    assert _body(router.calls[0]) == {"hostname": "h", "username": "u", "password": "p", "email": "e@x.com", "otp": "123456"}


def test_credentials_login_turns_seed_into_code(router: Router) -> None:
    router.add("POST", CREDENTIALS_PATH, json={"accessToken": JWT})
    before = otp_code(SEED)
    with httpx2.Client(base_url=API, transport=router.transport) as http:
        credentials_login(http, hostname="mi.metrc.com", username="u", password="p", otp=SEED.lower())
    after = otp_code(SEED)
    assert _body(router.calls[0])["otp"] in {before, after}


def test_credentials_login_rejected(router: Router) -> None:
    router.add("POST", CREDENTIALS_PATH, status=401, json={"detail": "Metrc rejected the login"})
    with httpx2.Client(base_url=API, transport=router.transport) as http, pytest.raises(AuthError, match="Metrc rejected"):
        credentials_login(http, hostname="h", username="u", password="p")


# --------------------------------------------------------------------------- existing key


def test_paste_existing_key_rejected_then_accepted(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], memory_keyring: MemoryKeyring
) -> None:
    prompts.expect(
        Confirm("already have a T3 secret key", True),
        Ask("Paste your secret key", "sk-wrong"),
        Ask("Paste your secret key", f"  {GOOD_KEY}  "),
        Confirm("Pick a default license", True),
    )

    result = login(api, store)

    assert isinstance(result.auth, SecretKeyAuth)
    assert result.auth.key == GOOD_KEY
    assert result.secret_location == "keyring"
    assert result.profile == Profile(
        name="default",
        api_host=API,
        metrc_hostname="mo.metrc.com",
        username="jdoe",
        license="LIC-1",
        credential="secret_key",
    )
    assert store.get_profile("default") == result.profile
    assert store.default_profile_name() == "default"
    assert memory_keyring.passwords == {(KEYRING_SERVICE, "default:secret_key"): GOOD_KEY}
    assert prompts.find("already have").default is False
    assert prompts.find("Paste").password is True
    # Both pasted keys went to whoami; the Metrc login routes were never touched.
    assert [r.headers[SECRET_KEY_HEADER] for r in api.requests("GET", WHOAMI_PATH)] == ["sk-wrong", GOOD_KEY]
    assert api.requests("POST", SECRET_KEY_PATH) == []
    assert api.requests("POST", CREDENTIALS_PATH) == []
    assert api.requests("GET", STATES_PATH) == []
    assert _said(messages, "header", "T3 login · profile default")
    assert _said(messages, "error", "T3 rejected that secret key")
    assert _said(messages, "success", "Saved your secret key to profile default")
    assert _said(messages, "info", "Using the only license available: LIC-1")
    assert _said(messages, "success", "Default license: LIC-1")
    # The licenses call used the new key.
    assert api.requests("GET", LICENSES_PATH)[0].headers[SECRET_KEY_HEADER] == GOOD_KEY


def test_paste_key_keeps_profile_fields_whoami_lacks(api: Router, store: Store, prompts: Prompts) -> None:
    store.save_profile(
        Profile(name="mo", api_host="https://old.example", metrc_hostname="old.metrc.com", username="old", license="LIC-9")
    )
    api.add("GET", WHOAMI_PATH, json={})
    prompts.expect(Confirm("already have", True), Ask("Paste your secret key", GOOD_KEY))

    result = login(api, store, profile="mo")

    # whoami had nothing to say, so the saved fields stay; the license is already set (no prompt).
    assert result.profile == Profile(
        name="mo", api_host=API, metrc_hostname="old.metrc.com", username="old", license="LIC-9", credential="secret_key"
    )
    assert store.get_profile("mo") == result.profile


def test_paste_key_whoami_not_a_dict(api: Router, store: Store, prompts: Prompts) -> None:
    api.add("GET", WHOAMI_PATH, json=["unexpected"])
    prompts.expect(Confirm("already have", True), Ask("Paste", GOOD_KEY), Confirm("default license", False))
    result = login(api, store)
    assert (result.profile.username, result.profile.metrc_hostname) == (None, None)
    assert result.profile.credential == "secret_key"


# --------------------------------------------------------------------------- credentials + secret key


def test_credentials_then_secret_key_in_otp_state(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], memory_keyring: MemoryKeyring
) -> None:
    memory_keyring.passwords[(KEYRING_SERVICE, "default:jwt")] = "old-jwt"
    prompts.expect(
        Confirm("already have a T3 secret key", False),
        Ask("Metrc hostname", "MI"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Ask("OTP seed", "123456"),  # a code, not a seed: rejected with help
        Ask("OTP seed", "jbsw y3dp-ehpk 3pxp"),
        Confirm("Pick a default license", False),
    )

    result = login(api, store)

    assert isinstance(result.auth, SecretKeyAuth)
    assert result.auth.key == NEW_KEY
    (create,) = api.requests("POST", SECRET_KEY_PATH)
    assert _body(create) == {"hostname": "mi.metrc.com", "username": "jdoe", "password": PASSWORD, "otpSeed": SEED}
    assert SECRET_KEY_HEADER not in create.headers and "Authorization" not in create.headers
    assert api.requests("POST", CREDENTIALS_PATH) == []
    assert memory_keyring.passwords == {(KEYRING_SERVICE, "default:secret_key"): NEW_KEY}
    assert store.get_profile("default") == Profile(
        name="default", api_host=API, metrc_hostname="mi.metrc.com", username="jdoe", credential="secret_key"
    )
    assert prompts.find("Metrc password").password is True
    assert prompts.find("OTP seed").password is True
    assert prompts.find("Create a secret key").default is True
    assert prompts.find("Metrc hostname").default is None
    assert _said(messages, "info", "state abbreviation")
    assert _said(messages, "info", "OTP seed")
    assert _said(messages, "error", "isn't a valid OTP seed")
    assert _said(messages, "success", "Created a secret key (********0001)")
    assert _said(messages, "success", "Your Metrc password was not stored")
    assert not any(NEW_KEY in text for _, text in messages)
    assert_password_never_stored(store, memory_keyring)


def test_credentials_then_secret_key_in_email_state(
    api: Router, store: Store, prompts: Prompts, memory_keyring: MemoryKeyring
) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "https://co.metrc.com/"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Ask("Metrc login email", "jdoe@example.com"),
        Confirm("Create a secret key", True),
        Confirm("Pick a default license", False),
    )

    login(api, store)

    assert _body(api.requests("POST", SECRET_KEY_PATH)[0]) == {
        "hostname": "co.metrc.com",
        "username": "jdoe",
        "password": PASSWORD,
        "email": "jdoe@example.com",
    }
    assert_password_never_stored(store, memory_keyring)


def test_existing_profile_values_are_prompt_defaults(api: Router, store: Store, prompts: Prompts) -> None:
    store.save_profile(Profile(name="ca", metrc_hostname="ca.metrc.com", username="saved-user"))
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", DEFAULT),
        Ask("Metrc username", DEFAULT),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Confirm("Pick a default license", False),
    )

    result = login(api, store, profile="ca")

    assert prompts.find("Metrc hostname").default == "ca.metrc.com"
    assert prompts.find("Metrc username").default == "saved-user"
    assert (result.profile.metrc_hostname, result.profile.username) == ("ca.metrc.com", "saved-user")
    assert _body(api.requests("POST", SECRET_KEY_PATH)[0])["hostname"] == "ca.metrc.com"


def test_unknown_hostname_is_asked_again(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]]
) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "zz.metrc.com"),
        Confirm("isn't in T3's list", False),
        Ask("Metrc hostname", "California"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Confirm("Pick a default license", False),
    )

    result = login(api, store)

    assert result.profile.metrc_hostname == "ca.metrc.com"


def test_unlisted_hostname_can_be_used_anyway(api: Router, store: Store, prompts: Prompts) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "sandbox-xx.metrc.com"),
        Confirm("isn't in T3's list", True),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Confirm("Pick a default license", False),
    )

    result = login(api, store)

    assert result.profile.metrc_hostname == "sandbox-xx.metrc.com"


def test_states_unavailable_uses_fallback_lists(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]]
) -> None:
    api.add("GET", STATES_PATH, status=503, json={})
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "anything.example"),  # not checked without a states list
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Confirm("Pick a default license", False),
    )
    login(api, store)
    assert _body(api.requests("POST", SECRET_KEY_PATH)[0])["hostname"] == "anything.example"
    assert not _said(messages, "info", "state abbreviation")


def test_states_unavailable_mi_still_needs_otp(api: Router, store: Store, prompts: Prompts) -> None:
    api.add("GET", STATES_PATH, status=503, json={})
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "mi"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Ask("OTP seed", SEED),
        Confirm("Pick a default license", False),
    )
    login(api, store)
    assert _body(api.requests("POST", SECRET_KEY_PATH)[0])["otpSeed"] == SEED


def test_secret_key_creation_rejected(
    api: Router, store: Store, prompts: Prompts, memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[httpx2.Client] = []

    def spy_build(**kwargs: Any) -> httpx2.Client:
        built.append(build_client(**kwargs))
        return built[-1]

    monkeypatch.setattr(login_module, "build_client", spy_build)
    api.add("POST", SECRET_KEY_PATH, status=400, json={"detail": "Metrc login failed"})
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "CA"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
    )

    with pytest.raises(ValidationError, match="Metrc login failed"):
        login(api, store)

    assert store.profiles() == []
    assert memory_keyring.passwords == {}
    assert built[0].is_closed
    assert str(built[0].base_url) == API


# --------------------------------------------------------------------------- credentials + JWT


def test_decline_secret_key_logs_in_for_jwt(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], memory_keyring: MemoryKeyring
) -> None:
    memory_keyring.passwords[(KEYRING_SERVICE, "work:secret_key")] = "old-secret-key"
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "ca.metrc.com"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", False),
        Confirm("Pick a default license", False),
    )

    result = login(api, store, profile="work")

    assert isinstance(result.auth, BearerAuth)
    assert result.auth.token == JWT
    assert _body(api.requests("POST", CREDENTIALS_PATH)[0]) == {
        "hostname": "ca.metrc.com",
        "username": "jdoe",
        "password": PASSWORD,
    }
    assert api.requests("POST", SECRET_KEY_PATH) == []
    # Only the JWT is kept; the other kind's secret is gone.
    assert memory_keyring.passwords == {(KEYRING_SERVICE, "work:jwt"): JWT}
    assert store.get_profile("work") == Profile(
        name="work", api_host=API, metrc_hostname="ca.metrc.com", username="jdoe", credential="jwt"
    )
    assert _said(messages, "success", "Saved the JWT to profile work")
    assert _said(messages, "warning", "JWTs expire after 24 hours")
    assert_password_never_stored(store, memory_keyring)


def test_decline_in_otp_state_takes_a_code(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], memory_keyring: MemoryKeyring
) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "MI"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", False),
        Ask("6-digit code", "12345"),  # neither a code nor a seed
        Ask("6-digit code", "654321"),
        Confirm("Pick a default license", False),
    )

    login(api, store)

    body = _body(api.requests("POST", CREDENTIALS_PATH)[0])
    assert body["otp"] == "654321"
    assert "otpSeed" not in body
    assert prompts.find("6-digit code").password is True
    assert _said(messages, "error", "isn't a valid OTP seed")
    assert_password_never_stored(store, memory_keyring)


def test_decline_in_otp_state_turns_seed_into_code(api: Router, store: Store, prompts: Prompts) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "MI"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", False),
        Ask("6-digit code", "jbsw-y3dp-ehpk-3pxp"),
        Confirm("Pick a default license", False),
    )
    before = otp_code(SEED)
    login(api, store)
    after = otp_code(SEED)

    body = _body(api.requests("POST", CREDENTIALS_PATH)[0])
    assert body["otp"] in {before, after}
    assert SEED not in json.dumps(body)


def test_decline_in_email_state(api: Router, store: Store, prompts: Prompts) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "CO"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Ask("Metrc login email", "jdoe@example.com"),
        Confirm("Create a secret key", False),
        Confirm("Pick a default license", False),
    )
    login(api, store)
    assert _body(api.requests("POST", CREDENTIALS_PATH)[0])["email"] == "jdoe@example.com"


# --------------------------------------------------------------------------- restart at the offer


def test_start_at_offer_skips_existing_key_question(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], memory_keyring: MemoryKeyring
) -> None:
    store.save_profile(Profile(name="default", metrc_hostname="ca.metrc.com", username="jdoe", credential="jwt"))
    memory_keyring.passwords[(KEYRING_SERVICE, "default:jwt")] = "expired.jwt.token"
    prompts.expect(
        Ask("Metrc hostname", DEFAULT),
        Ask("Metrc username", DEFAULT),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Confirm("Pick a default license", False),
    )

    result = login(api, store, start_at="offer")

    assert result.profile.credential == "secret_key"
    assert memory_keyring.passwords == {(KEYRING_SERVICE, "default:secret_key"): NEW_KEY}
    assert _said(messages, "warning", "Your saved login has expired")
    assert not any("already have" in a.text for a in prompts.asked)


# --------------------------------------------------------------------------- default license


def test_pick_default_license_from_several(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]]
) -> None:
    api.add("GET", LICENSES_PATH, json=LICENSES)
    prompts.expect(
        Confirm("already have", True),
        Ask("Paste", GOOD_KEY),
        Confirm("Pick a default license", True),
        Ask("Number", "2"),
    )
    result = login(api, store)
    assert result.profile.license == "LIC-2"
    assert store.get_profile("default") == result.profile
    assert _said(messages, "success", "Default license: LIC-2")


@pytest.mark.parametrize("payload", [[], {"data": LICENSES}])
def test_no_licenses_available(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], payload: Any
) -> None:
    api.add("GET", LICENSES_PATH, json=payload)
    prompts.expect(Confirm("already have", True), Ask("Paste", GOOD_KEY), Confirm("Pick a default license", True))
    result = login(api, store)
    assert result.profile.license is None
    assert _said(messages, "warning", "No licenses are available")
    assert not _said(messages, "success", "Default license")


def test_licenses_error_is_survived(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], memory_keyring: MemoryKeyring
) -> None:
    api.add("GET", LICENSES_PATH, status=403, json={"detail": "no access"})
    prompts.expect(Confirm("already have", True), Ask("Paste", GOOD_KEY), Confirm("Pick a default license", True))

    result = login(api, store)

    assert result.profile.license is None
    assert _said(messages, "warning", "Couldn't load licenses")
    # The login itself still succeeded and was saved.
    assert store.get_profile("default") == result.profile
    assert memory_keyring.passwords == {(KEYRING_SERVICE, "default:secret_key"): GOOD_KEY}


def test_jwt_login_picks_license_with_bearer(api: Router, store: Store, prompts: Prompts) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "CA"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", False),
        Confirm("Pick a default license", True),
    )
    result = login(api, store)
    assert result.profile.license == "LIC-1"
    (request,) = api.requests("GET", LICENSES_PATH)
    assert request.headers["Authorization"] == f"Bearer {JWT}"
    assert SECRET_KEY_HEADER not in request.headers


# --------------------------------------------------------------------------- no keyring


@pytest.fixture
def no_keyring(memory_keyring: MemoryKeyring) -> Iterator[None]:
    keyring.set_keyring(fail.Keyring())  # type: ignore[no-untyped-call]
    yield
    keyring.set_keyring(memory_keyring)


def test_keyring_unavailable_saves_to_file_with_warning(
    api: Router, store: Store, prompts: Prompts, messages: list[tuple[str, str]], no_keyring: None,
    memory_keyring: MemoryKeyring,
) -> None:
    prompts.expect(
        Confirm("already have", False),
        Ask("Metrc hostname", "CA"),
        Ask("Metrc username", "jdoe"),
        Ask("Metrc password", PASSWORD),
        Confirm("Create a secret key", True),
        Confirm("Pick a default license", False),
    )

    result = login(api, store)

    assert result.secret_location == "file"
    assert _said(messages, "warning", "No OS keyring is available")
    assert _said(messages, "warning", str(store.secrets_path))
    assert store.get_secret("default", "secret_key") == NEW_KEY
    assert store.secrets_path.is_file()
    assert_password_never_stored(store, memory_keyring)
