from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pyotp
import pytest

from t3api_utils.auth.credentials import (
    SECRET_KEY_HEADER,
    BearerAuth,
    SecretKeyAuth,
    credential_kind,
    is_otp_code,
    jwt_expired,
    jwt_expiry,
    normalize_otp_seed,
    otp_code,
)
from tests.conftest import Router

SEED = "JBSWY3DPEHPK3PXP"  # 80 bits, the common 16-character authenticator seed
LONG_SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # 160 bits


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(claims: Any) -> str:
    """An unsigned JWT with the given claims."""
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps(claims).encode())
    return f"{header}.{payload}.sig"


def _send(auth: httpx2.Auth, router: Router) -> httpx2.Request:
    router.add("GET", "/ping", json={})
    with httpx2.Client(base_url="https://t3.test", auth=auth, transport=router.transport) as http:
        http.get("/ping")
    return router.calls[-1]


# --------------------------------------------------------------------------- SecretKeyAuth


def test_secret_key_auth_sends_header_and_never_authorization(router: Router) -> None:
    request = _send(SecretKeyAuth("  sk-abcdef123456  "), router)
    assert request.headers[SECRET_KEY_HEADER] == "sk-abcdef123456"
    assert "Authorization" not in request.headers
    assert "secretKey" not in str(request.url)


def test_secret_key_auth_strips_and_has_kind() -> None:
    auth = SecretKeyAuth("\tsk-1\n")
    assert auth.key == "sk-1"
    assert auth.kind == "secret_key"


@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_secret_key_auth_rejects_empty(value: str) -> None:
    with pytest.raises(ValueError, match="secret key is empty"):
        SecretKeyAuth(value)


def test_secret_key_auth_repr_masks_key() -> None:
    text = repr(SecretKeyAuth("sk-very-secret-value-9876"))
    assert "very-secret" not in text
    assert text == "SecretKeyAuth('********9876')"


# --------------------------------------------------------------------------- BearerAuth


@pytest.mark.parametrize(
    "value", ["tok.en.value", "Bearer tok.en.value", "bearer   tok.en.value", "  BEARER tok.en.value "]
)
def test_bearer_auth_strips_prefix(value: str) -> None:
    auth = BearerAuth(value)
    assert auth.token == "tok.en.value"
    assert auth.kind == "jwt"


def test_bearer_auth_sends_authorization_only(router: Router) -> None:
    request = _send(BearerAuth("Bearer abc.def.ghi"), router)
    assert request.headers["Authorization"] == "Bearer abc.def.ghi"
    assert SECRET_KEY_HEADER not in request.headers


@pytest.mark.parametrize("value", ["", "  ", "Bearer ", "bearer    "])
def test_bearer_auth_rejects_empty(value: str) -> None:
    with pytest.raises(ValueError, match="JWT is empty"):
        BearerAuth(value)


def test_bearer_auth_repr_masks_token() -> None:
    text = repr(BearerAuth("header.payload.signatureXYZW"))
    assert "payload" not in text
    assert text == "BearerAuth('********XYZW')"


def test_bearer_auth_expires_at() -> None:
    exp = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert BearerAuth(make_jwt({"exp": exp.timestamp()})).expires_at == exp
    assert BearerAuth("opaque-token").expires_at is None


# --------------------------------------------------------------------------- credential_kind


def test_credential_kind() -> None:
    assert credential_kind(SecretKeyAuth("k")) == "secret_key"
    assert credential_kind(BearerAuth("t")) == "jwt"
    assert credential_kind(None) is None
    assert credential_kind(httpx2.BasicAuth("u", "p")) is None


# --------------------------------------------------------------------------- JWT expiry


def test_jwt_expiry_reads_exp_without_verifying() -> None:
    assert jwt_expiry(make_jwt({"exp": 1_900_000_000})) == datetime.fromtimestamp(1_900_000_000, tz=UTC)
    # A string exp still parses; the signature is never checked.
    assert jwt_expiry(make_jwt({"exp": "1900000000"})) == datetime.fromtimestamp(1_900_000_000, tz=UTC)


@pytest.mark.parametrize(
    "token",
    [
        "no-dots-at-all",
        "header.abcde.sig",  # binascii.Error (5 base64 characters can't decode)
        f"header.{_b64(b'not json')}.sig",  # ValueError (JSON)
        make_jwt({"sub": "no exp"}),  # KeyError
        make_jwt(["a", "list"]),  # TypeError
        make_jwt({"exp": None}),  # TypeError
        make_jwt({"exp": "soon"}),  # ValueError (float)
        make_jwt({"exp": 1e300}),  # OverflowError / OSError / ValueError
    ],
)
def test_jwt_expiry_unreadable_is_none(token: str) -> None:
    assert jwt_expiry(token) is None


def test_jwt_expired_past_and_future() -> None:
    now = datetime.now(UTC)
    assert jwt_expired(make_jwt({"exp": (now - timedelta(hours=1)).timestamp()})) is True
    assert jwt_expired(make_jwt({"exp": (now + timedelta(hours=1)).timestamp()})) is False


def test_jwt_expired_unreadable_counts_as_live() -> None:
    assert jwt_expired("opaque-token") is False
    assert jwt_expired(make_jwt({"sub": "x"})) is False


def test_jwt_expired_leeway_and_now() -> None:
    exp = datetime(2030, 1, 1, tzinfo=UTC)
    token = make_jwt({"exp": exp.timestamp()})
    # Default leeway is one minute.
    assert jwt_expired(token, now=exp - timedelta(seconds=30)) is True
    assert jwt_expired(token, now=exp - timedelta(minutes=2)) is False
    assert jwt_expired(token, now=exp - timedelta(seconds=30), leeway=timedelta(0)) is False
    assert jwt_expired(token, now=exp, leeway=timedelta(0)) is True


# --------------------------------------------------------------------------- OTP


@pytest.mark.parametrize(
    ("value", "expected"),
    [("123456", True), (" 123456 ", True), ("12345", False), ("1234567", False), ("12a456", False), ("", False)],
)
def test_is_otp_code(value: str, expected: bool) -> None:
    assert is_otp_code(value) is expected


@pytest.mark.parametrize(
    "raw",
    [SEED, SEED.lower(), "jbsw y3dp ehpk 3pxp", "JBSW-Y3DP-EHPK-3PXP", " jbsw\ty3dp-EHPK 3pxp\n"],
)
def test_normalize_otp_seed_accepts_spaces_dashes_lowercase(raw: str) -> None:
    assert normalize_otp_seed(raw) == SEED


@pytest.mark.parametrize("raw", ["", "  ", "- -"])
def test_normalize_otp_seed_rejects_empty(raw: str) -> None:
    with pytest.raises(ValueError, match="OTP seed is empty"):
        normalize_otp_seed(raw)


@pytest.mark.parametrize("raw", ["123456", "JBSWY3DPEHPK3PX1", "not a seed!"])
def test_normalize_otp_seed_rejects_invalid_with_help(raw: str) -> None:
    with pytest.raises(ValueError, match="isn't a valid OTP seed") as info:
        normalize_otp_seed(raw)
    assert "not a 6-digit code" in str(info.value)
    assert "A-Z and digits 2-7" in str(info.value)


def _reference_totp(seed: str, at: float) -> str:
    """RFC 6238 with SHA-1, 30-second steps and 6 digits."""
    key = base64.b32decode(seed + "=" * (-len(seed) % 8))
    digest = hmac.new(key, int(at // 30).to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def test_otp_code_matches_pyotp() -> None:
    before = pyotp.TOTP(LONG_SEED).now()
    code = otp_code(LONG_SEED.lower())
    after = pyotp.TOTP(LONG_SEED).now()
    assert code in {before, after}
    assert is_otp_code(code)


def test_otp_code_accepts_80_bit_seed() -> None:
    # pyotp >= 2.12 refuses seeds under 112 bits on its own; otp_code must not.
    before = _reference_totp(SEED, time.time())
    code = otp_code("jbsw-y3dp-ehpk-3pxp")
    after = _reference_totp(SEED, time.time())
    assert code in {before, after}


def test_otp_code_rejects_invalid_seed() -> None:
    with pytest.raises(ValueError, match="isn't a valid OTP seed"):
        otp_code("999999")
