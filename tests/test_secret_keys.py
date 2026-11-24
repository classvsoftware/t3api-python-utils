from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest

from t3api_utils._http import build_client
from t3api_utils.auth.credentials import SECRET_KEY_HEADER
from t3api_utils.auth.secret_keys import SECRET_KEY_PATH, SecretKeys, create_secret_key
from t3api_utils.auth.store import Profile
from t3api_utils.client import T3Client
from t3api_utils.errors import AuthError, NotFound, RateLimited, ServerError, T3Error, ValidationError
from tests.conftest import Router

KEY = "sk-live-0123456789"
WHOAMI = "/v2/auth/whoami"


@pytest.fixture
def anon_http(router: Router) -> Iterator[httpx2.Client]:
    """An httpx2 client with no credential, like the login flow uses."""
    http = build_client(base_url="https://api.t3.test", transport=router.transport)
    yield http
    http.close()


def _body(request: httpx2.Request) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(request.content)
    return body


# --------------------------------------------------------------------------- create


def test_create_needs_no_auth_and_sends_only_given_fields(router: Router, anon_http: httpx2.Client) -> None:
    router.add("POST", SECRET_KEY_PATH, json={"secretKey": KEY})

    key = create_secret_key(anon_http, hostname="mo.metrc.com", username="jdoe", password="pw")

    assert key == KEY
    (request,) = router.requests("POST", SECRET_KEY_PATH)
    assert _body(request) == {"hostname": "mo.metrc.com", "username": "jdoe", "password": "pw"}
    assert "Authorization" not in request.headers
    assert SECRET_KEY_HEADER not in request.headers


def test_create_sends_email_and_normalized_otp_seed(router: Router, anon_http: httpx2.Client) -> None:
    router.add("POST", SECRET_KEY_PATH, json={"secretKey": KEY})

    create_secret_key(
        anon_http,
        hostname="nv.metrc.com",
        username="jdoe",
        password="pw",
        email="jdoe@example.com",
        otp_seed="jbsw y3dp-ehpk 3pxp",
    )

    assert _body(router.calls[0]) == {
        "hostname": "nv.metrc.com",
        "username": "jdoe",
        "password": "pw",
        "email": "jdoe@example.com",
        "otpSeed": "JBSWY3DPEHPK3PXP",
    }


def test_create_skips_empty_email_and_seed(router: Router, anon_http: httpx2.Client) -> None:
    router.add("POST", SECRET_KEY_PATH, json={"secretKey": KEY})
    create_secret_key(anon_http, hostname="h", username="u", password="p", email="", otp_seed="")
    assert set(_body(router.calls[0])) == {"hostname", "username", "password"}


def test_create_rejects_bad_seed_before_sending(router: Router, anon_http: httpx2.Client) -> None:
    with pytest.raises(ValueError, match="isn't a valid OTP seed"):
        create_secret_key(anon_http, hostname="mi.metrc.com", username="u", password="p", otp_seed="123456")
    assert router.calls == []


def test_client_create_uses_client_http(router: Router, client: T3Client) -> None:
    router.add("POST", SECRET_KEY_PATH, json={"secretKey": KEY})
    assert client.secret_keys.create("co.metrc.com", "jdoe", "pw", email="j@example.com") == KEY
    assert _body(router.calls[0])["email"] == "j@example.com"
    assert str(router.calls[0].url) == "https://api.trackandtrace.tools" + SECRET_KEY_PATH


@pytest.mark.parametrize(
    ("status", "error"),
    [(400, ValidationError), (401, AuthError), (422, ValidationError), (500, ServerError)],
)
def test_create_errors(router: Router, anon_http: httpx2.Client, status: int, error: type[Exception]) -> None:
    router.add("POST", SECRET_KEY_PATH, status=status, json={"detail": "Metrc login failed"})
    with pytest.raises(error, match="Metrc login failed") as info:
        create_secret_key(anon_http, hostname="h", username="u", password="hunter2-pw")
    assert "hunter2-pw" not in str(info.value)
    assert len(router.calls) == 1  # writes never retry on 4xx/5xx


# --------------------------------------------------------------------------- list


def test_list_returns_data_rows(router: Router, client: T3Client) -> None:
    rows = [
        {"secretKey": "sk-1", "isEnabled": True, "isManaged": False, "lastUsedAt": None},
        {"secretKey": "sk-2", "isEnabled": False, "isManaged": True, "extra": "field"},
    ]
    router.add("GET", SECRET_KEY_PATH, json={"data": rows})
    assert client.secret_keys.list() == rows
    assert router.calls[0].headers[SECRET_KEY_HEADER] == "test-secret-key"


@pytest.mark.parametrize("payload", [{}, [{"secretKey": "sk-1"}]])
def test_list_tolerates_other_shapes(router: Router, client: T3Client, payload: Any) -> None:
    router.add("GET", SECRET_KEY_PATH, json=payload)
    assert client.secret_keys.list() == []


def test_list_rejected_key(router: Router, client: T3Client) -> None:
    router.add("GET", SECRET_KEY_PATH, status=401, json={"detail": "bad key"})
    with pytest.raises(AuthError, match="t3api keys rotate") as info:
        client.secret_keys.list()
    assert info.value.status_code == 401


def test_list_rate_limited_after_retries(router: Router, client: T3Client, sleeps: list[float]) -> None:
    router.add("GET", SECRET_KEY_PATH, status=429, json={}, headers={"Retry-After": "2"})
    with pytest.raises(RateLimited):
        client.secret_keys.list()
    assert len(router.calls) == 3
    assert sleeps == [2.0, 2.0]


# --------------------------------------------------------------------------- rotate


def test_rotate_with_explicit_args(router: Router, client: T3Client) -> None:
    client.profile = Profile(name="p", metrc_hostname="profile.metrc.com", username="profile-user")
    router.add("PUT", f"{SECRET_KEY_PATH}/{{key}}", json={"secretKey": KEY, "isEnabled": True})

    result = client.secret_keys.rotate(
        f"  {KEY}  ",
        password="new-pw",
        username="arg-user",
        hostname="arg.metrc.com",
        email="e@example.com",
        otp_seed="jbswy3dpehpk3pxp",
    )

    assert result == {"secretKey": KEY, "isEnabled": True}
    (request,) = router.requests("PUT")
    assert request.url.path == f"{SECRET_KEY_PATH}/{KEY}"
    assert _body(request) == {
        "hostname": "arg.metrc.com",
        "username": "arg-user",
        "password": "new-pw",
        "email": "e@example.com",
        "otpSeed": "JBSWY3DPEHPK3PXP",
    }
    assert router.requests("GET", WHOAMI) == []


def test_rotate_uses_profile(router: Router, client: T3Client) -> None:
    client.profile = Profile(name="p", metrc_hostname="mo.metrc.com", username="jdoe")
    router.add("PUT", f"{SECRET_KEY_PATH}/{{key}}", json={})
    client.secret_keys.rotate(KEY, password="pw")
    assert _body(router.calls[0]) == {"hostname": "mo.metrc.com", "username": "jdoe", "password": "pw"}
    assert router.requests("GET", WHOAMI) == []


def test_rotate_falls_back_to_whoami(router: Router, client: T3Client) -> None:
    router.add("GET", WHOAMI, json={"username": "who-user", "hostname": "who.metrc.com"})
    router.add("PUT", f"{SECRET_KEY_PATH}/{{key}}", json={"ok": True})
    assert client.secret_keys.rotate(KEY, password="pw") == {"ok": True}
    assert _body(router.requests("PUT")[0]) == {"hostname": "who.metrc.com", "username": "who-user", "password": "pw"}


def test_rotate_mixes_profile_and_whoami(router: Router, client: T3Client) -> None:
    client.profile = Profile(name="p", username="profile-user")
    router.add("GET", WHOAMI, json={"username": "who-user", "hostname": "who.metrc.com"})
    router.add("PUT", f"{SECRET_KEY_PATH}/{{key}}", json={})
    client.secret_keys.rotate(KEY, password="pw")
    body = _body(router.requests("PUT")[0])
    assert (body["username"], body["hostname"]) == ("profile-user", "who.metrc.com")


def test_rotate_without_username_or_hostname_anywhere(router: Router, client: T3Client) -> None:
    router.add("GET", WHOAMI, json={"username": "who-user"})
    with pytest.raises(ValueError, match="needs username= and hostname="):
        client.secret_keys.rotate(KEY, password="pw")
    assert router.requests("PUT") == []


def test_rotate_url_encodes_the_key(router: Router, client: T3Client) -> None:
    key = "ab/cd+ef=?#"
    router.add("PUT", f"{SECRET_KEY_PATH}/{key}", json={})
    client.secret_keys.rotate(key, password="pw", username="u", hostname="h")
    assert router.calls[0].url.raw_path == f"{SECRET_KEY_PATH}/ab%2Fcd%2Bef%3D%3F%23".encode()


def test_rotate_non_dict_response(router: Router, client: T3Client) -> None:
    router.add("PUT", f"{SECRET_KEY_PATH}/{{key}}", status=204, content=b"")
    assert client.secret_keys.rotate(KEY, password="pw", username="u", hostname="h") == {}


@pytest.mark.parametrize(
    ("status", "error"),
    [(400, ValidationError), (401, AuthError), (404, NotFound), (502, ServerError)],
)
def test_rotate_errors(router: Router, client: T3Client, status: int, error: type[Exception]) -> None:
    router.add("PUT", f"{SECRET_KEY_PATH}/{{key}}", status=status, json={"detail": "nope"})
    with pytest.raises(error):
        client.secret_keys.rotate(KEY, password="pw", username="u", hostname="h")
    assert len(router.calls) == 1  # a PUT is never retried on 5xx


# --------------------------------------------------------------------------- delete


def test_delete(router: Router, client: T3Client) -> None:
    router.add("DELETE", f"{SECRET_KEY_PATH}/{{key}}", json={"deleted": True})
    assert client.secret_keys.delete(f" {KEY}\n") == {"deleted": True}
    assert router.calls[0].method == "DELETE"
    assert router.calls[0].url.path == f"{SECRET_KEY_PATH}/{KEY}"


def test_delete_url_encodes_the_key(router: Router, client: T3Client) -> None:
    router.add("DELETE", f"{SECRET_KEY_PATH}/a b/c", status=204, content=b"")
    assert client.secret_keys.delete("a b/c") == {}
    assert router.calls[0].url.raw_path == f"{SECRET_KEY_PATH}/a%20b%2Fc".encode()


def test_delete_managed_key_is_forbidden(router: Router, client: T3Client) -> None:
    router.add("DELETE", f"{SECRET_KEY_PATH}/{{key}}", status=403, json={"detail": "Managed keys can't be deleted"})
    with pytest.raises(AuthError, match="Managed keys") as info:
        client.secret_keys.delete(KEY)
    assert info.value.status_code == 403
    assert KEY not in info.value.url


def test_delete_unknown_key(router: Router, client: T3Client) -> None:
    router.add("DELETE", f"{SECRET_KEY_PATH}/{{key}}", status=404, json={"detail": "no such key"})
    with pytest.raises(NotFound):
        client.secret_keys.delete(KEY)


def test_secret_keys_namespace(client: T3Client) -> None:
    assert isinstance(client.secret_keys, SecretKeys)


def test_create_with_unexpected_body_raises_t3error(router: Router, anon_http: httpx2.Client) -> None:
    router.add("POST", SECRET_KEY_PATH, json={"data": {}})
    with pytest.raises(T3Error, match="no 'secretKey'"):
        create_secret_key(anon_http, hostname="mo.metrc.com", username="jdoe", password="pw")
