"""`t3api login/logout/whoami/profiles/license/keys`."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from t3api_utils._http import DEFAULT_HOST
from t3api_utils.auth.credentials import BearerAuth, CredentialKind, SecretKeyAuth
from t3api_utils.auth.login import LoginResult
from t3api_utils.auth.store import Profile, Store
from tests._cli_helpers import Prompts, cli_app, invoke, save_profile
from tests._cli_helpers import api, cli_env, prompts  # noqa: F401  (fixtures)
from tests.conftest import Router

CA_STATE = {
    "abbreviation": "CA",
    "name": "California",
    "hostname": "ca.metrc.com",
    "requiresEmail": False,
    "requiresOtp": False,
}
MI_STATE = {
    "abbreviation": "MI",
    "name": "Michigan",
    "hostname": "mi.metrc.com",
    "requiresEmail": True,
    "requiresOtp": True,
}
OTP_SEED = "JBSWY3DPEHPK3PXP"


def body(request: Any) -> Any:
    return json.loads(request.content)


# --------------------------------------------------------------------------- login


class FakeLogin:
    """Stands in for auth.login.run_login and records how it was called."""

    def __init__(self, credential: CredentialKind = "secret_key") -> None:
        self.credential = credential
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, store: Store, profile_name: str, api_host: str) -> LoginResult:
        self.calls.append({"profile_name": profile_name, "api_host": api_host})
        profile = Profile(name=profile_name, api_host=api_host, credential=self.credential)
        store.save_profile(profile)
        auth = SecretKeyAuth("sk-new") if self.credential == "secret_key" else BearerAuth("a.b.c")
        return LoginResult(auth=auth, profile=profile, secret_location="keyring")


def test_login_first_profile_suggests_plain_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLogin()
    monkeypatch.setattr(cli_app, "run_login", fake)
    result = invoke("login")
    assert result.exit_code == 0
    assert fake.calls == [{"profile_name": "default", "api_host": DEFAULT_HOST}]
    assert "Scripts can now call t3.connect()." in result.stderr
    assert "switch to a secret key" not in result.stderr


def test_login_named_profile_with_host_and_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    save_profile("main")
    fake = FakeLogin(credential="jwt")
    monkeypatch.setattr(cli_app, "run_login", fake)
    result = invoke("login", "--profile", "other", "--host", "https://sandbox.example")
    assert result.exit_code == 0
    assert fake.calls == [{"profile_name": "other", "api_host": "https://sandbox.example"}]
    assert 'Scripts can now call t3.connect(profile="other").' in result.stderr
    assert "Run `t3api login` again any time to switch to a secret key." in result.stderr
    assert Store().default_profile_name() == "main"


def test_login_reuses_the_saved_api_host(monkeypatch: pytest.MonkeyPatch) -> None:
    save_profile("default", api_host="https://saved.example")
    fake = FakeLogin()
    monkeypatch.setattr(cli_app, "run_login", fake)
    invoke("login")
    assert fake.calls[0]["api_host"] == "https://saved.example"


def test_login_api_host_env_wins_over_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    save_profile("default", api_host="https://saved.example")
    monkeypatch.setenv("T3_API_HOST", "https://env.example")
    fake = FakeLogin()
    monkeypatch.setattr(cli_app, "run_login", fake)
    invoke("login")
    assert fake.calls[0]["api_host"] == "https://env.example"


def test_login_profile_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T3_PROFILE", "ci")
    fake = FakeLogin()
    monkeypatch.setattr(cli_app, "run_login", fake)
    invoke("login")
    assert fake.calls[0]["profile_name"] == "ci"


def test_login_cancelled_with_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    def cancelled(**kwargs: Any) -> LoginResult:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_app, "run_login", cancelled)
    result = invoke("login")
    assert result.exit_code == 130
    assert "Cancelled." in result.stderr


# --------------------------------------------------------------------------- logout


def test_logout_without_a_profile_fails() -> None:
    result = invoke("logout")
    assert result.exit_code == 1
    assert "No profile named 'default'. Run `t3api login --profile default`." in result.stderr


def test_logout_secret_key_profile_reminds_about_revoking() -> None:
    save_profile("default", secret="sk-default-0001")
    result = invoke("logout")
    assert result.exit_code == 0
    store = Store()
    saved = store.get_profile("default")
    assert saved is not None and saved.credential is None
    assert store.get_secret("default", "secret_key") is None
    assert "Removed the saved credential from profile default." in result.stderr
    assert "The secret key itself still works" in result.stderr
    assert "t3api keys revoke" in result.stderr


def test_logout_jwt_profile_has_no_secret_key_reminder() -> None:
    save_profile("main")
    save_profile("work", credential="jwt", secret="a.b.c")
    result = invoke("logout", "--profile", "work")
    assert result.exit_code == 0
    store = Store()
    assert store.get_secret("work", "jwt") is None
    assert store.get_secret("main", "secret_key") == "sk-default-0001"
    assert store.default_profile_name() == "main"
    assert "still works" not in result.stderr


def test_logout_everywhere_posts_logout_first(api: Router) -> None:
    api.add("POST", "/v2/auth/logout", json={"message": "ok"})
    save_profile("default", secret="sk-default-0001")
    result = invoke("logout", "--everywhere")
    assert result.exit_code == 0
    [request] = api.requests("POST", "/v2/auth/logout")
    assert request.headers["X-T3-API-Key"] == "sk-default-0001"
    assert "Logged out of all Metrc sessions." in result.stderr
    assert Store().get_secret("default", "secret_key") is None


def test_logout_everywhere_rejected_keeps_the_credential(api: Router) -> None:
    api.add("POST", "/v2/auth/logout", json={"detail": "nope"}, status=401)
    save_profile("default", secret="sk-default-0001")
    result = invoke("logout", "--everywhere")
    assert result.exit_code == 1
    assert "401" in result.stderr
    assert Store().get_secret("default", "secret_key") == "sk-default-0001"


# --------------------------------------------------------------------------- whoami


def test_whoami_with_a_profile(api: Router) -> None:
    api.add(
        "GET",
        "/v2/auth/whoami",
        json={"username": "jane", "hostname": "ca.metrc.com", "hasT3plus": False, "unlisted": "hidden"},
    )
    save_profile("default", license="LIC-1")
    result = invoke("whoami")
    assert result.exit_code == 0
    out = result.stdout
    for text in ("profile", "default", "secret_key", DEFAULT_HOST, "LIC-1", "jane", "ca.metrc.com", "hasT3plus", "False"):
        assert text in out
    assert "authMode" not in out
    assert "unlisted" not in out and "hidden" not in out


def test_whoami_with_an_environment_key_has_no_profile_row(
    api: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    api.add("GET", "/v2/auth/whoami", json={"username": "ci-bot", "authMode": "SECRET_KEY"})
    monkeypatch.setenv("T3_SECRET_KEY", "sk-env-5555")
    result = invoke("whoami")
    assert result.exit_code == 0
    assert "profile" not in result.stdout
    assert "ci-bot" in result.stdout and "SECRET_KEY" in result.stdout
    [request] = api.requests("GET", "/v2/auth/whoami")
    assert request.headers["X-T3-API-Key"] == "sk-env-5555"


def test_whoami_without_any_credential_explains_setup() -> None:
    result = invoke("whoami")
    assert result.exit_code == 1
    assert "No T3 credential found" in result.stderr


# --------------------------------------------------------------------------- profiles


def test_profiles_list_empty() -> None:
    result = invoke("profiles", "list")
    assert result.exit_code == 0
    assert "No profiles yet. Run `t3api login`." in result.stderr
    assert result.stdout == ""


def test_profiles_list_shows_every_profile() -> None:
    save_profile("zeta", license="LIC-Z", metrc_hostname="ca.metrc.com", username="jane")
    save_profile("alpha", credential=None, api_host="https://other.example")
    result = invoke("profiles", "list")
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    alpha = next(line for line in lines if "alpha" in line)
    zeta = next(line for line in lines if "zeta" in line)
    assert lines.index(alpha) < lines.index(zeta)
    assert "none" in alpha and "https://other.example" in alpha and "✓" not in alpha
    for text in ("✓", "secret_key", "ca.metrc.com", "jane", "LIC-Z", DEFAULT_HOST):
        assert text in zeta


def test_profiles_use() -> None:
    save_profile("a")
    save_profile("b")
    result = invoke("profiles", "use", "b")
    assert result.exit_code == 0
    assert "Default profile: b" in result.stderr
    assert Store().default_profile_name() == "b"


def test_profiles_use_unknown() -> None:
    result = invoke("profiles", "use", "nope")
    assert result.exit_code == 1
    assert "✗ No profile named 'nope'." in result.stderr


def test_profiles_remove() -> None:
    save_profile("a", secret="sk-a")
    result = invoke("profiles", "remove", "a")
    assert result.exit_code == 0
    assert "Removed profile a." in result.stderr
    assert Store().get_profile("a") is None
    assert Store().get_secret("a", "secret_key") is None


def test_profiles_remove_unknown() -> None:
    result = invoke("profiles", "remove", "nope")
    assert result.exit_code == 1
    assert "No profile named 'nope'." in result.stderr


# --------------------------------------------------------------------------- license


def test_license_show() -> None:
    save_profile("default", license="LIC-1")
    result = invoke("license")
    assert result.exit_code == 0
    assert result.stdout == "LIC-1\n"


def test_license_show_for_another_profile() -> None:
    save_profile("default", license="LIC-1")
    save_profile("work", license="LIC-[2]")
    result = invoke("license", "--profile", "work")
    assert result.stdout == "LIC-[2]\n"


def test_license_show_when_unset() -> None:
    save_profile("default")
    result = invoke("license")
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Profile default has no default license. Set one with `t3api license pick`." in result.stderr


def test_license_show_without_profile() -> None:
    result = invoke("license")
    assert result.exit_code == 1
    assert "No profile named 'default'" in result.stderr


def test_license_set_strips_and_keeps_the_default_profile() -> None:
    save_profile("main")
    save_profile("work")
    result = invoke("license", "set", "  LIC-9 ", "--profile", "work")
    assert result.exit_code == 0
    assert "Default license for work: LIC-9" in result.stderr
    store = Store()
    work = store.get_profile("work")
    assert work is not None and work.license == "LIC-9"
    assert store.default_profile_name() == "main"


def test_license_group_profile_reaches_subcommands() -> None:
    save_profile("main")
    save_profile("work")
    result = invoke("license", "--profile", "work", "set", "LIC-7")
    assert result.exit_code == 0
    work = Store().get_profile("work")
    main = Store().get_profile("main")
    assert work is not None and work.license == "LIC-7"
    assert main is not None and main.license is None


def test_license_set_without_profile() -> None:
    result = invoke("license", "set", "LIC-1")
    assert result.exit_code == 1


LICENSES = [
    {"licenseNumber": "LIC-1", "licenseName": "North"},
    {"licenseNumber": "LIC-2", "licenseName": "South"},
]


def test_license_pick_from_several(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/licenses", json=LICENSES)
    save_profile("default")
    prompts.answer("Number", "2")
    result = invoke("license", "pick")
    assert result.exit_code == 0
    saved = Store().get_profile("default")
    assert saved is not None and saved.license == "LIC-2"
    assert "Default license for default: LIC-2" in result.stderr
    assert "North" in result.stderr and "South" in result.stderr
    # The callback ran first and printed nothing of its own.
    assert result.stdout == ""


def test_license_pick_single_license_needs_no_terminal(api: Router) -> None:
    api.add("GET", "/v2/licenses", json=LICENSES[:1])
    save_profile("default")
    result = invoke("license", "pick")
    assert result.exit_code == 0
    assert "Using the only license available: LIC-1" in result.stderr
    saved = Store().get_profile("default")
    assert saved is not None and saved.license == "LIC-1"


def test_license_pick_without_terminal(api: Router) -> None:
    api.add("GET", "/v2/licenses", json=LICENSES)
    save_profile("default")
    result = invoke("license", "pick")
    assert result.exit_code == 1
    assert "Licenses needs a terminal to ask in." in result.stderr


def test_license_pick_without_profile() -> None:
    result = invoke("license", "pick")
    assert result.exit_code == 1
    assert "No profile named 'default'" in result.stderr


# --------------------------------------------------------------------------- keys list


def test_keys_list_masks_keys_and_marks_the_one_in_use(api: Router) -> None:
    api.add(
        "GET",
        "/v2/auth/secretkey",
        json={
            "data": [
                {
                    "secretKey": "sk-default-0001",
                    "isEnabled": True,
                    "isManaged": False,
                    "createdAt": "2026-01-01",
                    "lastUsedAt": None,
                },
                {
                    "secretKey": "sk-other-9999",
                    "isEnabled": False,
                    "isManaged": True,
                    "createdAt": None,
                    "lastUsedAt": "2026-02-02",
                },
                {},
            ]
        },
    )
    save_profile("default", secret="sk-default-0001")
    result = invoke("keys", "list")
    assert result.exit_code == 0
    out = result.stdout
    assert "sk-default-0001" not in out and "sk-other-9999" not in out
    lines = out.splitlines()
    mine = next(line for line in lines if "********0001" in line)
    other = next(line for line in lines if "********9999" in line)
    assert "✓" in mine and "yes" in mine and "never" in mine and "2026-01-01" in mine
    assert "✓" not in other and "2026-02-02" in other
    assert out.count("✓") == 1


# --------------------------------------------------------------------------- keys create


def test_keys_create_and_save_to_a_new_profile(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/states", json=[CA_STATE, MI_STATE])
    api.add("POST", "/v2/auth/secretkey", json={"secretKey": "sk-created-4321"})
    prompts.answer("Metrc hostname", "CA")
    prompts.answer("Metrc username", "jane")
    prompts.answer("Metrc password", "hunter2")
    prompts.confirm("Save it to profile default?", True)

    result = invoke("keys", "create")

    assert result.exit_code == 0, result.output
    assert "sk-created-4321" in result.stdout
    assert prompts.texts() == ["Metrc hostname", "Metrc username", "Metrc password"]
    assert [a["default"] for a in prompts.asked[:2]] == [None, None]
    assert prompts.asked[2]["password"] is True
    [request] = api.requests("POST", "/v2/auth/secretkey")
    assert body(request) == {"hostname": "ca.metrc.com", "username": "jane", "password": "hunter2"}
    store = Store()
    saved = store.get_profile("default")
    assert saved is not None
    assert (saved.credential, saved.metrc_hostname, saved.username) == ("secret_key", "ca.metrc.com", "jane")
    assert store.get_secret("default", "secret_key") == "sk-created-4321"
    assert store.default_profile_name() == "default"
    assert "Saved to profile default." in result.stderr


def test_keys_create_with_email_and_otp_replaces_a_jwt(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/states", json=[CA_STATE, MI_STATE])
    api.add("POST", "/v2/auth/secretkey", json={"secretKey": "sk-mi-7777"})
    save_profile("mi", credential="jwt", secret="a.b.c", metrc_hostname="mi.metrc.com", username="old")
    prompts.answer("Metrc hostname", "mi.metrc.com")
    prompts.answer("Metrc username", "jane")
    prompts.answer("Metrc password", "pw")
    prompts.answer("Metrc login email", "jane@example.com")
    prompts.answer("OTP seed (base32, not a 6-digit code)", OTP_SEED.lower())
    prompts.confirm("Save it to profile mi?", True)

    result = invoke("keys", "create", "--profile", "mi")

    assert result.exit_code == 0, result.output
    assert [a["default"] for a in prompts.asked[:2]] == ["mi.metrc.com", "old"]
    assert prompts.asked[4]["password"] is True
    [request] = api.requests("POST", "/v2/auth/secretkey")
    assert body(request) == {
        "hostname": "mi.metrc.com",
        "username": "jane",
        "password": "pw",
        "email": "jane@example.com",
        "otpSeed": OTP_SEED,
    }
    store = Store()
    assert store.get_secret("mi", "jwt") is None
    assert store.get_secret("mi", "secret_key") == "sk-mi-7777"
    saved = store.get_profile("mi")
    assert saved is not None and saved.credential == "secret_key" and saved.username == "jane"


def test_keys_create_declining_to_save(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/states", json=[CA_STATE])
    api.add("POST", "/v2/auth/secretkey", json={"secretKey": "sk-unsaved-1111"})
    prompts.answer("Metrc hostname", "ca.metrc.com")
    prompts.answer("Metrc username", "jane")
    prompts.answer("Metrc password", "pw")
    prompts.confirm("Save it to profile default?", False)

    result = invoke("keys", "create")

    assert result.exit_code == 0
    assert "sk-unsaved-1111" in result.stdout
    assert Store().profiles() == []
    assert prompts.confirmed == [{"text": "Save it to profile default?", "default": True}]


def test_keys_create_without_terminal(api: Router) -> None:
    api.add("GET", "/v2/states", json=[CA_STATE])
    result = invoke("keys", "create")
    assert result.exit_code == 1
    assert "needs a terminal" in result.stderr
    assert api.requests("POST") == []


def test_keys_create_rejected_credentials(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/states", json=[CA_STATE])
    api.add("POST", "/v2/auth/secretkey", json={"detail": "Metrc login failed"}, status=401)
    prompts.answer("Metrc hostname", "ca")
    prompts.answer("Metrc username", "jane")
    prompts.answer("Metrc password", "wrong")
    result = invoke("keys", "create")
    assert result.exit_code == 1
    assert "Metrc login failed" in result.stderr
    assert Store().profiles() == []


# --------------------------------------------------------------------------- keys rotate


def test_keys_rotate_an_explicit_key(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/states", json=[CA_STATE])
    api.add("PUT", "/v2/auth/secretkey/{key}", json={"ok": True})
    prompts.answer("Metrc hostname", "CA")
    prompts.answer("Metrc username", "jane")
    prompts.answer("New Metrc password", "new-pw")

    result = invoke("keys", "rotate", " sk-explicit-2468 ")

    assert result.exit_code == 0, result.output
    [request] = api.requests("PUT")
    assert request.url.path == "/v2/auth/secretkey/sk-explicit-2468"
    assert request.headers["X-T3-API-Key"] == "sk-explicit-2468"
    assert body(request) == {"hostname": "ca.metrc.com", "username": "jane", "password": "new-pw"}
    assert api.requests("GET", "/v2/auth/whoami") == []
    assert "Updated the credentials behind ********2468. The key value is unchanged." in result.stderr
    assert "sk-explicit-2468" not in result.output


def test_keys_rotate_defaults_to_the_profile_key_with_email_and_otp(api: Router, prompts: Prompts) -> None:
    api.add("GET", "/v2/states", json=[MI_STATE])
    api.add("PUT", "/v2/auth/secretkey/{key}", json={})
    save_profile("default", secret="sk-saved-1357", metrc_hostname="mi.metrc.com", username="jane")
    prompts.answer("Metrc hostname", "mi.metrc.com")
    prompts.answer("Metrc username", "jane")
    prompts.answer("New Metrc password", "pw2")
    prompts.answer("Metrc login email", "jane@example.com")
    prompts.answer("OTP seed (base32)", OTP_SEED)

    result = invoke("keys", "rotate")

    assert result.exit_code == 0, result.output
    [request] = api.requests("PUT")
    assert request.url.path == "/v2/auth/secretkey/sk-saved-1357"
    assert body(request)["email"] == "jane@example.com"
    assert body(request)["otpSeed"] == OTP_SEED
    assert prompts.asked[4]["password"] is True


@pytest.mark.parametrize("setup", ["no profile", "jwt profile"])
def test_keys_rotate_needs_a_key(setup: str) -> None:
    if setup == "jwt profile":
        save_profile("default", credential="jwt", secret="a.b.c")
    result = invoke("keys", "rotate")
    assert result.exit_code == 1
    assert "No secret key given and none saved in the profile." in result.stderr


# --------------------------------------------------------------------------- keys revoke


def _revoke_setup(api: Router) -> None:
    api.add("DELETE", "/v2/auth/secretkey/{key}", json={})
    save_profile("a", secret="sk-shared-0042")
    save_profile("b", secret="sk-shared-0042")
    save_profile("c", secret="sk-different-0001")


def _secret_keys() -> Mapping[str, str | None]:
    store = Store()
    return {name: store.get_secret(name, "secret_key") for name in ("a", "b", "c")}


def test_keys_revoke_with_yes_removes_it_from_profiles(api: Router) -> None:
    _revoke_setup(api)
    result = invoke("keys", "revoke", " sk-shared-0042 ", "--yes")
    assert result.exit_code == 0, result.output
    [request] = api.requests("DELETE")
    assert request.url.path == "/v2/auth/secretkey/sk-shared-0042"
    assert _secret_keys() == {"a": None, "b": None, "c": "sk-different-0001"}
    store = Store()
    assert [p.credential for p in sorted(store.profiles(), key=lambda p: p.name)] == [None, None, "secret_key"]
    assert "Deleted ********0042." in result.stderr
    assert "Removed it from profile a." in result.stderr
    assert "Removed it from profile b." in result.stderr
    assert "profile c" not in result.stderr


def test_keys_revoke_declined(api: Router, prompts: Prompts) -> None:
    _revoke_setup(api)
    prompts.confirm("Delete secret key ********0042? Anything using it stops working.", False)
    result = invoke("keys", "revoke", "sk-shared-0042")
    assert result.exit_code == 1
    assert api.requests("DELETE") == []
    assert prompts.confirmed[0]["default"] is False
    assert _secret_keys()["a"] == "sk-shared-0042"


def test_keys_revoke_confirmed(api: Router, prompts: Prompts) -> None:
    _revoke_setup(api)
    prompts.confirm("Delete secret key ********0001? Anything using it stops working.", True)
    result = invoke("keys", "revoke", "sk-different-0001")
    assert result.exit_code == 0
    assert _secret_keys() == {"a": "sk-shared-0042", "b": "sk-shared-0042", "c": None}


def test_keys_revoke_without_terminal_or_yes(api: Router) -> None:
    _revoke_setup(api)
    result = invoke("keys", "revoke", "sk-shared-0042")
    assert result.exit_code == 1
    assert "needs a terminal" in result.stderr
    assert api.requests("DELETE") == []


def test_keys_revoke_managed_key_is_refused(api: Router) -> None:
    _revoke_setup(api)
    api.add("DELETE", "/v2/auth/secretkey/{key}", json={"detail": "Managed keys can't be deleted"}, status=403)
    result = invoke("keys", "revoke", "sk-shared-0042", "-y")
    assert result.exit_code == 1
    assert "Managed keys can't be deleted" in result.stderr
    assert _secret_keys()["a"] == "sk-shared-0042"


# --------------------------------------------------------------------------- --sandbox


def sandbox_routes(api: Router) -> None:
    api.add("POST", "/v2/auth/sandbox", json={"accessToken": "sandbox.jwt.token"})
    api.add("GET", "/v2/auth/whoami", json={"username": "jane", "hostname": "sandbox-me.metrc.com"})
    api.add("GET", "/v2/auth/secretkey", json=[])
    api.add("POST", "/v2/auth/logout", json={})
    api.add("GET", "/v2/licenses", json=[{"licenseNumber": "LIC-1", "licenseName": "Only"}])


def test_whoami_with_sandbox_shows_it(api: Router) -> None:
    sandbox_routes(api)
    save_profile("default", license="AR1769")
    result = invoke("--sandbox", "whoami")
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert any("sandbox" in line and "yes" in line for line in lines)
    assert "sandbox-me.metrc.com" in result.stdout
    assert not any("default license" in line and "AR1769" in line for line in lines)
    whoami = api.requests("GET", "/v2/auth/whoami")[-1]
    assert whoami.headers["Authorization"] == "Bearer sandbox.jwt.token"


def test_t3_sandbox_applies_to_data_commands(api: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox_routes(api)
    save_profile("default")
    monkeypatch.setenv("T3_SANDBOX", "1")
    result = invoke("whoami")
    assert result.exit_code == 0
    assert api.requests("POST", "/v2/auth/sandbox")


def test_whoami_without_sandbox_has_no_sandbox_row(api: Router) -> None:
    sandbox_routes(api)
    save_profile("default")
    result = invoke("whoami")
    assert result.exit_code == 0
    assert not any(line.split("│")[1:2] == [" sandbox "] for line in result.stdout.splitlines())
    assert api.requests("POST", "/v2/auth/sandbox") == []


@pytest.mark.parametrize(
    "args",
    [["--sandbox", "keys", "list"], ["--sandbox", "logout", "--everywhere"], ["--sandbox", "license", "pick"]],
)
def test_credential_commands_never_use_the_sandbox(
    api: Router, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    sandbox_routes(api)
    save_profile("default")
    monkeypatch.setenv("T3_SANDBOX", "1")
    result = invoke(*args)
    assert result.exit_code == 0
    assert api.requests("POST", "/v2/auth/sandbox") == []
    assert all(r.headers.get("X-T3-API-Key") == "sk-default-0001" for r in api.calls)


def test_keys_revoke_never_uses_the_sandbox(api: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox_routes(api)
    api.add("DELETE", "/v2/auth/secretkey/{key}", json={})
    save_profile("default")
    monkeypatch.setenv("T3_SANDBOX", "1")
    result = invoke("keys", "revoke", "sk-old-key", "--yes")
    assert result.exit_code == 0
    assert api.requests("POST", "/v2/auth/sandbox") == []


def test_the_sandbox_flag_does_not_stick_between_runs(api: Router) -> None:
    sandbox_routes(api)
    save_profile("default")
    assert invoke("--sandbox", "whoami").exit_code == 0
    api.calls.clear()
    assert invoke("whoami").exit_code == 0
    assert api.requests("POST", "/v2/auth/sandbox") == []
