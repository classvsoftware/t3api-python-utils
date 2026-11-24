"""_http.py: retry transport, redaction, HTTP logging, proxies and build_client()."""

from __future__ import annotations

import email.utils
import logging
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from importlib import metadata
from pathlib import Path
from typing import Any

import httpx2
import pytest

from t3api_utils import _http
from t3api_utils._ratelimit import TokenBucket
from t3api_utils.auth.credentials import SecretKeyAuth

BASE = "https://api.test"

Outcome = int | httpx2.Response | type[httpx2.TransportError]


class Script:
    """A MockTransport handler that plays back one outcome per request.

    The last outcome repeats once the others are used up.
    """

    def __init__(self, *outcomes: Outcome) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, httpx2.Response):
            return outcome
        if isinstance(outcome, int):
            return httpx2.Response(outcome, json={"status": outcome})
        raise outcome("simulated failure", request=request)


class CountingBucket(TokenBucket):
    def __init__(self) -> None:
        super().__init__(None)
        self.acquired = 0

    def acquire(self) -> float:
        self.acquired += 1
        return 0.0


class TrackingStream(httpx2.SyncByteStream):
    def __init__(self) -> None:
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield b"{}"

    def close(self) -> None:
        self.closed = True


def make_client(script: Script, **kwargs: Any) -> httpx2.Client:
    return _http.build_client(base_url=BASE, transport=httpx2.MockTransport(script), **kwargs)


def retry_transport(script: Script, **kwargs: Any) -> _http.RetryTransport:
    return _http.RetryTransport(httpx2.MockTransport(script), **kwargs)


@pytest.fixture(autouse=True)
def reset_http_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start every test with HTTP logging off, and undo whatever a test turned on."""
    log = _http.http_logger
    saved_handlers = list(log.handlers)
    saved_level = log.level
    log.handlers[:] = []
    log.setLevel(logging.NOTSET)
    monkeypatch.setattr(_http, "_handler_installed", False)
    yield
    for handler in log.handlers:
        handler.close()
    log.handlers[:] = saved_handlers
    log.setLevel(saved_level)


@pytest.fixture
def proxy_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No proxy variables in the environment (the autouse fixture only clears T3_*)."""
    for name in list(os.environ):
        if name.lower().endswith("_proxy") or name.upper() == "REQUEST_METHOD":
            monkeypatch.delenv(name, raising=False)
    return monkeypatch


# --------------------------------------------------------------------------- GET retries


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_get_retries_retryable_status(status: int, sleeps: list[float]) -> None:
    script = Script(status, 200)
    with make_client(script) as client:
        response = client.get("/v2/items")
    assert response.status_code == 200
    assert len(script.requests) == 2
    assert len(sleeps) == 1


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS"])
def test_head_and_options_retry_like_get(method: str) -> None:
    script = Script(503, 200)
    with make_client(script) as client:
        assert client.request(method, "/v2/items").status_code == 200
    assert len(script.requests) == 2


def test_get_gives_up_after_three_attempts(sleeps: list[float]) -> None:
    script = Script(503)
    with make_client(script) as client:
        response = client.get("/v2/items")
    assert response.status_code == 503
    assert len(script.requests) == 3
    assert len(sleeps) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 500, 501])
def test_get_not_retried_on_other_errors(status: int, sleeps: list[float]) -> None:
    script = Script(status, 200)
    with make_client(script) as client:
        assert client.get("/v2/items").status_code == status
    assert len(script.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "error", [httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.ReadTimeout, httpx2.RemoteProtocolError]
)
def test_get_retries_any_connection_error(error: type[httpx2.TransportError]) -> None:
    script = Script(error, 200)
    with make_client(script) as client:
        assert client.get("/v2/items").status_code == 200
    assert len(script.requests) == 2


def test_get_connection_error_raised_after_three_attempts(sleeps: list[float]) -> None:
    script = Script(httpx2.ReadTimeout)
    with make_client(script) as client, pytest.raises(httpx2.ReadTimeout):
        client.get("/v2/items")
    assert len(script.requests) == 3
    assert len(sleeps) == 2


# --------------------------------------------------------------------------- write retries


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("status", [400, 409, 422, 500, 502, 503, 504])
def test_write_answered_with_error_is_sent_exactly_once(
    method: str, status: int, sleeps: list[float]
) -> None:
    script = Script(status, 200)
    with make_client(script) as client:
        response = client.request(method, "/v2/items/discontinue", json={"id": 1})
    assert response.status_code == status
    assert len(script.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_write_retried_on_429(method: str) -> None:
    script = Script(429, 200)
    with make_client(script) as client:
        response = client.request(method, "/v2/items/discontinue", json={"id": 1})
    assert response.status_code == 200
    assert len(script.requests) == 2
    assert [r.content for r in script.requests] == [b'{"id":1}', b'{"id":1}']


def test_write_429_returned_after_three_attempts() -> None:
    script = Script(429)
    with make_client(script) as client:
        assert client.post("/v2/x", json={}).status_code == 429
    assert len(script.requests) == 3


@pytest.mark.parametrize("error", [httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout])
def test_write_retried_on_pre_send_errors(error: type[httpx2.TransportError]) -> None:
    script = Script(error, 201)
    with make_client(script) as client:
        assert client.post("/v2/x", json={"a": 1}).status_code == 201
    assert len(script.requests) == 2


@pytest.mark.parametrize(
    "error",
    [httpx2.ReadTimeout, httpx2.RemoteProtocolError, httpx2.WriteTimeout, httpx2.ReadError],
)
def test_write_not_retried_after_send(error: type[httpx2.TransportError], sleeps: list[float]) -> None:
    script = Script(error, 200)
    with make_client(script) as client, pytest.raises(error):
        client.post("/v2/x", json={"a": 1})
    assert len(script.requests) == 1
    assert sleeps == []


def test_write_pre_send_error_raised_after_three_attempts() -> None:
    script = Script(httpx2.ConnectError)
    with make_client(script) as client, pytest.raises(httpx2.ConnectError):
        client.post("/v2/x", json={})
    assert len(script.requests) == 3


# --------------------------------------------------------------------------- backoff


def test_backoff_doubles_with_jitter_centered() -> None:
    script = Script(503, 503, 200)
    recorded: list[float] = []
    transport = retry_transport(script, sleep=recorded.append, jitter=lambda: 0.5)
    response = transport.handle_request(httpx2.Request("GET", BASE + "/v2/items"))
    assert response.status_code == 200
    assert recorded == [0.5, 1.0]


@pytest.mark.parametrize(("jitter", "expected"), [(0.0, 0.375), (1.0, 0.625)])
def test_jitter_bounds(jitter: float, expected: float) -> None:
    script = Script(503, 200)
    recorded: list[float] = []
    transport = retry_transport(script, sleep=recorded.append, jitter=lambda: jitter)
    transport.handle_request(httpx2.Request("GET", BASE + "/v2/items"))
    assert recorded == [pytest.approx(expected)]


def test_default_delays_are_within_jitter_range(sleeps: list[float]) -> None:
    script = Script(503, 503, 200)
    with make_client(script) as client:
        client.get("/v2/items")
    assert 0.375 <= sleeps[0] <= 0.625
    assert 0.75 <= sleeps[1] <= 1.25


def test_build_client_sleep_is_used_instead_of_time_sleep(sleeps: list[float]) -> None:
    recorded: list[float] = []
    script = Script(503, 200)
    with make_client(script, sleep=recorded.append) as client:
        client.get("/v2/items")
    assert len(recorded) == 1
    assert sleeps == []


def test_max_attempts_is_at_least_one() -> None:
    script = Script(503)
    transport = retry_transport(script, max_attempts=0)
    assert transport.max_attempts == 1
    assert transport.handle_request(httpx2.Request("GET", BASE + "/x")).status_code == 503
    assert len(script.requests) == 1


def test_retried_response_is_closed() -> None:
    stream = TrackingStream()
    first = httpx2.Response(503, stream=stream)
    script = Script(first, 200)
    retry_transport(script, sleep=lambda _: None).handle_request(httpx2.Request("GET", BASE + "/x"))
    assert stream.closed


def test_close_closes_wrapped_transport() -> None:
    class Closable(httpx2.MockTransport):
        closed = False

        def close(self) -> None:
            self.closed = True

    inner = Closable(Script(200))
    client = _http.build_client(base_url=BASE, transport=inner)
    client.close()
    assert inner.closed


# --------------------------------------------------------------------------- Retry-After


def test_retry_after_seconds_honored(sleeps: list[float]) -> None:
    script = Script(httpx2.Response(429, headers={"Retry-After": "2"}), 200)
    with make_client(script) as client:
        client.post("/v2/x", json={})
    assert sleeps == [2.0]


def test_retry_after_http_date_honored(sleeps: list[float]) -> None:
    when = email.utils.format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    script = Script(httpx2.Response(503, headers={"Retry-After": when}), 200)
    with make_client(script) as client:
        client.get("/v2/x")
    assert len(sleeps) == 1
    assert 28.0 < sleeps[0] <= 30.0


def test_retry_after_is_capped(sleeps: list[float]) -> None:
    script = Script(httpx2.Response(429, headers={"Retry-After": "3600"}), 200)
    with make_client(script) as client:
        client.get("/v2/x")
    assert sleeps == [_http.MAX_RETRY_AFTER]


def test_unparseable_retry_after_falls_back_to_backoff(sleeps: list[float]) -> None:
    script = Script(httpx2.Response(429, headers={"Retry-After": "soon"}), 200)
    with make_client(script) as client:
        client.get("/v2/x")
    assert 0.375 <= sleeps[0] <= 0.625


def test_retry_after_parsing() -> None:
    def parse(value: str | None, now: float = 0.0) -> float | None:
        headers = {} if value is None else {"Retry-After": value}
        return _http._retry_after(httpx2.Response(429, headers=headers), now=lambda: now)

    assert parse(None) is None
    assert parse("") is None
    assert parse("5") == 5.0
    assert parse("0.5") == 0.5
    assert parse("-3") == 0.0
    assert parse("120") == 60.0
    assert parse("not a date") is None
    date = "Wed, 21 Oct 2026 07:28:00 GMT"
    stamp = email.utils.parsedate_to_datetime(date).timestamp()
    assert parse(date, now=stamp - 10) == pytest.approx(10.0)
    assert parse(date, now=stamp + 10) == 0.0
    assert parse(date, now=stamp - 1000) == 60.0


# --------------------------------------------------------------------------- rate limiting


def test_limiter_acquired_once_per_attempt() -> None:
    bucket = CountingBucket()
    script = Script(503, httpx2.ConnectError, 200)
    transport = retry_transport(script, limiter=bucket, sleep=lambda _: None)
    transport.handle_request(httpx2.Request("GET", BASE + "/x"))
    assert bucket.acquired == 3
    assert len(script.requests) == 3


def test_build_client_rate_limit_creates_shared_limiter() -> None:
    with make_client(Script(200), rate_limit=10) as client:
        transport = client._transport
        assert isinstance(transport, _http.RetryTransport)
        assert transport.limiter is not None
        assert transport.limiter.rate == 10


@pytest.mark.parametrize("rate", [None, 0])
def test_build_client_without_rate_limit(rate: float | None) -> None:
    with make_client(Script(200), rate_limit=rate) as client:
        transport = client._transport
        assert isinstance(transport, _http.RetryTransport)
        assert transport.limiter is None


def test_build_client_rate_limit_spaces_requests(sleeps: list[float]) -> None:
    with make_client(Script(200), rate_limit=10) as client:
        for _ in range(3):
            client.get("/x")
    # One token: the 2nd and 3rd requests each wait for the next 100 ms slot.
    # (time.sleep is a recorder, so the clock barely moves between requests;
    # the bounds leave room for a slow machine.)
    assert len(sleeps) == 2
    assert 0.05 < sleeps[0] <= 0.1
    assert 0.15 < sleeps[1] <= 0.2


# --------------------------------------------------------------------------- retry warnings


def test_retry_warning_is_logged_with_redacted_url(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="t3api_utils")
    script = Script(503, httpx2.ConnectError, 200)
    with make_client(script) as client:
        client.get("/v2/items/report?licenseNumber=L&secretKey=sk-query-secret")
    messages = [r.getMessage() for r in caplog.records if r.name == "t3api_utils"]
    assert len(messages) == 2
    assert "returned 503; retrying" in messages[0]
    assert "attempt 2 of 3" in messages[0]
    assert "ConnectError" in messages[1] and "attempt 3 of 3" in messages[1]
    assert "sk-query-secret" not in caplog.text
    assert "secretKey=***" in caplog.text


# --------------------------------------------------------------------------- redaction helpers


def test_redact_url() -> None:
    assert _http.redact_url("https://h/v2/auth/secretkey/abc-123") == "https://h/v2/auth/secretkey/***"
    assert _http.redact_url("/v2/auth/SecretKey/abc?x=1") == "/v2/auth/SecretKey/***?x=1"
    assert _http.redact_url("/v2/auth/secretkey/abc/extra") == "/v2/auth/secretkey/***/extra"
    assert _http.redact_url("/r?secretKey=s1&a=1") == "/r?secretKey=***&a=1"
    assert _http.redact_url("/r?a=1&secretkey=s2#frag") == "/r?a=1&secretkey=***#frag"
    assert _http.redact_url("/v2/auth/secretkey") == "/v2/auth/secretkey"
    assert _http.redact_url("/v2/items?licenseNumber=L") == "/v2/items?licenseNumber=L"


def test_redact_headers() -> None:
    headers = {
        "Authorization": "Bearer t",
        "x-t3-api-key": "k",
        "Cookie": "c=1",
        "Set-Cookie": "s=2",
        "Accept": "application/json",
    }
    assert _http.redact_headers(headers) == {
        "Authorization": "***",
        "x-t3-api-key": "***",
        "Cookie": "***",
        "Set-Cookie": "***",
        "Accept": "application/json",
    }


def test_redact_json_at_any_depth() -> None:
    value = {
        "username": "jdoe",
        "Password": "p",
        "otp": "123456",
        "otpSeed": "SEED",
        "nested": {"secretKey": "sk", "list": [{"accessToken": "a"}, {"refreshToken": "r"}, 3]},
        1: "non-string key kept",
    }
    assert _http.redact_json(value) == {
        "username": "jdoe",
        "Password": "***",
        "otp": "***",
        "otpSeed": "***",
        "nested": {"secretKey": "***", "list": [{"accessToken": "***"}, {"refreshToken": "***"}, 3]},
        1: "non-string key kept",
    }
    assert _http.redact_json("plain") == "plain"


def test_redact_body() -> None:
    assert _http._redact_body(b"", "application/json") == ""
    assert _http._redact_body(b'{"password": "x", "a": 1}', "application/json") == '{"password": "***", "a": 1}'
    assert _http._redact_body(b"{not json", "application/json") == "<unparseable JSON body>"
    assert _http._redact_body(b"\xff\xfe", "application/json") == "<unparseable JSON body>"
    assert _http._redact_body(b"password=x", "application/x-www-form-urlencoded") == "<form body not logged>"
    assert _http._redact_body(b"--b\r\n", "multipart/form-data; boundary=b") == "<form body not logged>"
    assert _http._redact_body(b"hello", "text/plain") == "hello"
    assert _http._redact_body(b"\xff\xfe\x00", "application/octet-stream") == "<3 bytes>"
    long_text = _http._redact_body(b"z" * 5000, "text/plain")
    assert long_text == "z" * 4000 + "…"
    long_json = _http._redact_body(b'"' + b"q" * 5000 + b'"', "application/json")
    assert long_json.endswith("…") and len(long_json) == 4001


# --------------------------------------------------------------------------- DEBUG logging


def http_debug_text(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.name == "t3api_utils.http")


def test_debug_logs_never_contain_secrets(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="t3api_utils.http")
    response = httpx2.Response(
        200,
        json={"accessToken": "tok-SECRET-1", "refreshToken": "tok-SECRET-2", "user": {"secretKey": "sk-SECRET-3"}},
        headers={"Set-Cookie": "session=cookie-SECRET-4"},
    )
    script = Script(response)
    with make_client(script, auth=SecretKeyAuth("hdr-SECRET-5")) as client:
        client.post(
            "/v2/auth/secretkey/path-SECRET-6?secretKey=query-SECRET-7&licenseNumber=LIC-1",
            json={
                "username": "jdoe",
                "password": "pw-SECRET-8",
                "otp": "otp-SECRET-9",
                "otpSeed": "seed-SECRET-10",
                "deep": [{"secretKey": "deep-SECRET-11"}],
            },
            headers={"Authorization": "Bearer jwt-SECRET-12", "Cookie": "c=cookie-SECRET-13"},
        )
    text = http_debug_text(caplog)
    assert "→ POST" in text and "← 200 POST" in text
    assert "SECRET" not in text
    # Non-secret parts are still useful.
    assert "jdoe" in text and "licenseNumber=LIC-1" in text
    assert "/v2/auth/secretkey/***" in text
    # The request really carried the secrets; only the logs hide them.
    sent = script.requests[0]
    assert sent.headers["X-T3-API-Key"] == "hdr-SECRET-5"
    assert b"pw-SECRET-8" in sent.content


def test_debug_logs_form_and_streamed_bodies(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="t3api_utils.http")

    def chunks() -> Iterator[bytes]:
        yield b"password=streamed-SECRET"

    with make_client(Script(200)) as client:
        client.post("/v2/form", data={"password": "form-SECRET"})
        client.post("/v2/stream", content=chunks())
    text = http_debug_text(caplog)
    assert "<form body not logged>" in text
    assert "<streamed body>" in text
    assert "SECRET" not in text


def test_debug_logs_skip_non_json_response_bodies(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="t3api_utils.http")
    csv_response = httpx2.Response(200, content=b"a,b\n1,2\n", headers={"content-type": "text/csv"})
    with make_client(Script(csv_response, httpx2.Response(200, content=b"raw"))) as client:
        client.get("/v2/items/report")
        client.get("/v2/blob")
    text = http_debug_text(caplog)
    assert "<text/csv body not logged>" in text
    assert "<unknown body not logged>" in text
    assert "a,b" not in text


def test_nothing_logged_when_debug_is_off(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="t3api_utils.http")
    stream = TrackingStream()
    response = httpx2.Response(200, stream=stream, headers={"content-type": "application/json"})
    with make_client(Script(response, 200)) as client:
        with client.stream("GET", "/v2/items") as streamed:
            # The response hook didn't read the body when it had nothing to log.
            assert not streamed.is_stream_consumed
        client.post("/v2/x", json={"password": "p"})
    assert http_debug_text(caplog) == ""


# --------------------------------------------------------------------------- enable_http_logging


def test_enable_http_logging_to_file(tmp_path: Path) -> None:
    log_file = tmp_path / "http.log"
    _http.enable_http_logging(str(log_file))
    log = _http.http_logger
    assert log.level == logging.DEBUG
    assert _http._handler_installed is True
    [handler] = log.handlers
    assert isinstance(handler, logging.FileHandler)
    with make_client(Script(200)) as client:
        client.post("/v2/auth/credentials", json={"password": "file-SECRET"})
    handler.flush()
    text = log_file.read_text(encoding="utf-8")
    assert "→ POST https://api.test/v2/auth/credentials" in text
    assert "t3api_utils.http" in text
    assert "file-SECRET" not in text


def test_enable_http_logging_installs_only_once(tmp_path: Path) -> None:
    _http.enable_http_logging(str(tmp_path / "a.log"))
    _http.http_logger.setLevel(logging.WARNING)
    _http.enable_http_logging(str(tmp_path / "b.log"))
    assert len(_http.http_logger.handlers) == 1
    assert _http.http_logger.level == logging.DEBUG
    assert not (tmp_path / "b.log").exists()


def test_enable_http_logging_stderr_when_nothing_else_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    _http.enable_http_logging()
    [handler] = _http.http_logger.handlers
    assert type(handler) is logging.StreamHandler
    assert handler.stream is sys.stderr
    assert _http._handler_installed is True


def test_enable_http_logging_adds_nothing_when_root_has_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging.getLogger(), "handlers", [logging.NullHandler()])
    _http.enable_http_logging()
    assert _http.http_logger.handlers == []
    assert _http.http_logger.level == logging.DEBUG
    assert _http._handler_installed is False


def test_enable_http_logging_adds_nothing_when_logger_has_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    own = logging.NullHandler()
    _http.http_logger.addHandler(own)
    _http.enable_http_logging()
    assert _http.http_logger.handlers == [own]
    assert _http._handler_installed is False


def test_build_client_log_http_uses_t3_log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "from-env.log"
    monkeypatch.setenv("T3_LOG_FILE", str(log_file))
    with make_client(Script(200), log_http=True) as client:
        client.get("/v2/licenses")
    [handler] = _http.http_logger.handlers
    assert isinstance(handler, logging.FileHandler)
    assert handler.baseFilename == os.path.abspath(log_file)
    handler.flush()
    assert "→ GET https://api.test/v2/licenses" in log_file.read_text(encoding="utf-8")


def test_build_client_log_http_without_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging.getLogger(), "handlers", [logging.NullHandler()])
    with make_client(Script(200), log_http=True):
        pass
    assert _http.http_logger.level == logging.DEBUG
    assert _http.http_logger.handlers == []


def test_build_client_without_log_http_leaves_logging_alone() -> None:
    with make_client(Script(200)):
        pass
    assert _http.http_logger.level == logging.NOTSET
    assert _http._handler_installed is False


# --------------------------------------------------------------------------- env_flag


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("YES", True), (" on ", True), ("0", False), ("no", False), ("", False)],
)
def test_env_flag(value: str, expected: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T3_LOG_HTTP", value)
    assert _http.env_flag("T3_LOG_HTTP") is expected


def test_env_flag_unset() -> None:
    assert _http.env_flag("T3_LOG_HTTP") is False


# --------------------------------------------------------------------------- env_proxy


def test_env_proxy_none_without_variables(proxy_env: pytest.MonkeyPatch) -> None:
    assert _http.env_proxy(BASE) is None


def test_env_proxy_https(proxy_env: pytest.MonkeyPatch) -> None:
    proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    assert _http.env_proxy(BASE) == "http://proxy.corp:3128"


def test_env_proxy_http_only_applies_to_http_urls(proxy_env: pytest.MonkeyPatch) -> None:
    proxy_env.setenv("HTTP_PROXY", "http://plain.corp:80")
    assert _http.env_proxy("http://api.test") == "http://plain.corp:80"
    assert _http.env_proxy(BASE) is None


def test_env_proxy_all_proxy_fallback(proxy_env: pytest.MonkeyPatch) -> None:
    proxy_env.setenv("ALL_PROXY", "socks5://all.corp:1080")
    assert _http.env_proxy(BASE) == "socks5://all.corp:1080"
    proxy_env.setenv("HTTPS_PROXY", "http://https.corp:3128")
    assert _http.env_proxy(BASE) == "http://https.corp:3128"


def test_env_proxy_url_without_scheme_uses_https(proxy_env: pytest.MonkeyPatch) -> None:
    proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    assert _http.env_proxy("api.test") == "http://proxy.corp:3128"


@pytest.mark.parametrize(
    "no_proxy",
    [
        "*",
        "api.test",
        "API.TEST",
        "test",
        ".test",
        "other.org, api.test",
        "api.test:443",
        ",, ,api.test",
    ],
)
def test_env_proxy_no_proxy_matches(no_proxy: str, proxy_env: pytest.MonkeyPatch) -> None:
    proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    proxy_env.setenv("NO_PROXY", no_proxy)
    assert _http.env_proxy(BASE) is None


@pytest.mark.parametrize("no_proxy", ["other.org", "pi.test", "api.test.evil", "example.com,,"])
def test_env_proxy_no_proxy_does_not_match(no_proxy: str, proxy_env: pytest.MonkeyPatch) -> None:
    proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    proxy_env.setenv("NO_PROXY", no_proxy)
    assert _http.env_proxy(BASE) == "http://proxy.corp:3128"


def test_env_proxy_lowercase_no_proxy(proxy_env: pytest.MonkeyPatch) -> None:
    proxy_env.setenv("https_proxy", "http://proxy.corp:3128")
    proxy_env.setenv("no_proxy", "api.test")
    assert _http.env_proxy("https://API.test/v2") is None
    assert _http.env_proxy("https://elsewhere.org") == "http://proxy.corp:3128"


# --------------------------------------------------------------------------- build_client


class TransportRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> httpx2.BaseTransport:
        self.calls.append(kwargs)
        return httpx2.MockTransport(Script(200))


@pytest.fixture
def transport_recorder(monkeypatch: pytest.MonkeyPatch) -> TransportRecorder:
    recorder = TransportRecorder()
    # _http calls httpx2.HTTPTransport through the module, so patch it there.
    monkeypatch.setattr(httpx2, "HTTPTransport", recorder)
    return recorder


def test_build_client_uses_env_proxy(
    proxy_env: pytest.MonkeyPatch, transport_recorder: TransportRecorder
) -> None:
    proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    with _http.build_client(base_url=BASE) as client:
        assert client.get("/x").status_code == 200
    assert transport_recorder.calls == [{"verify": True, "proxy": "http://proxy.corp:3128"}]


def test_build_client_explicit_proxy_wins(
    proxy_env: pytest.MonkeyPatch, transport_recorder: TransportRecorder
) -> None:
    proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    with _http.build_client(base_url=BASE, proxy="http://mine:8080", verify="/ca.pem"):
        pass
    assert transport_recorder.calls == [{"verify": "/ca.pem", "proxy": "http://mine:8080"}]


def test_build_client_honors_no_proxy(
    proxy_env: pytest.MonkeyPatch, transport_recorder: TransportRecorder
) -> None:
    proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    proxy_env.setenv("NO_PROXY", "api.test")
    with _http.build_client(base_url=BASE):
        pass
    assert transport_recorder.calls == [{"verify": True, "proxy": None}]


def test_build_client_with_transport_builds_no_http_transport(transport_recorder: TransportRecorder) -> None:
    with make_client(Script(200)):
        pass
    assert transport_recorder.calls == []


def test_build_client_default_transport_is_wrapped(proxy_env: pytest.MonkeyPatch) -> None:
    with _http.build_client() as client:
        transport = client._transport
        assert isinstance(transport, _http.RetryTransport)
        assert isinstance(transport.wrapped, httpx2.HTTPTransport)
        assert str(client.base_url).rstrip("/") == _http.DEFAULT_HOST
        assert client.timeout.read == _http.DEFAULT_TIMEOUT


def test_build_client_headers_base_url_auth_and_timeout() -> None:
    script = Script(200)
    with make_client(
        script,
        auth=SecretKeyAuth("sk-1"),
        timeout=7.0,
        headers={"Accept": "text/csv", "X-Extra": "1"},
    ) as client:
        assert client.timeout.read == 7.0
        client.get("/v2/items")
    [sent] = script.requests
    assert str(sent.url) == BASE + "/v2/items"
    assert sent.headers["User-Agent"] == _http.user_agent()
    assert sent.headers["Accept"] == "text/csv"
    assert sent.headers["X-Extra"] == "1"
    assert sent.headers["X-T3-API-Key"] == "sk-1"


def test_build_client_strips_trailing_slash() -> None:
    script = Script(200)
    with _http.build_client(base_url=BASE + "/", transport=httpx2.MockTransport(script)) as client:
        client.get("/v2/items")
    assert str(script.requests[0].url) == BASE + "/v2/items"
    assert script.requests[0].headers["Accept"] == "application/json"


def test_user_agent() -> None:
    assert _http.user_agent() == f"t3api-utils/{metadata.version('t3api-utils')}"
