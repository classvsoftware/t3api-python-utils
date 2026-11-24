"""T3Client.collect() and iter_rows(): parallel paging, ordering, dedupe, failures."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx2
import pytest

from t3api_utils import _console
from t3api_utils.auth.credentials import SecretKeyAuth
from t3api_utils.client import T3Client
from t3api_utils.errors import NotFound, ServerError, SpecError
from tests.conftest import Router, paginated

Handler = Callable[[httpx2.Request], httpx2.Response]


def make_client(router: Router, **kwargs: Any) -> T3Client:
    options: dict[str, Any] = {
        "auth": SecretKeyAuth("test-secret-key"),
        "transport": router.transport,
        "spec": "bundled",
        "rate_limit": None,
    }
    options.update(kwargs)
    return T3Client(**options)


def pages_handler(pages: list[list[dict[str, Any]]]) -> Handler:
    """Serve fixed pages (page 1 is pages[0]), whatever the page size."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx2.Response(
            200, json={"page": page, "totalPages": len(pages), "data": pages[page - 1]}
        )

    return handler


def page_numbers(router: Router) -> list[int]:
    return [int(r.url.params.get("page", "1")) for r in router.calls]


ROWS = [{"id": i, "name": f"item {i}"} for i in range(1, 8)]


# --------------------------------------------------------------------------- basics


def test_collect_reads_every_page_in_order(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS, page_size=2))
    assert client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=False) == ROWS
    # Page 1 first (with no page parameter), then pages 2-4.
    assert "page" not in router.calls[0].url.params
    assert sorted(page_numbers(router)) == [1, 2, 3, 4]
    assert page_numbers(router)[0] == 1
    assert all(r.url.params["licenseNumber"] == "LIC-1" for r in router.calls)


def test_collect_by_path(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS, page_size=3))
    assert client.collect("/v2/items", license="LIC-1", progress=False) == ROWS


def test_collect_single_page(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", json={"data": [{"id": 1}]})  # no totalPages: one page
    assert client.collect("METRC_ACTIVE_ITEMS", license="LIC-1") == [{"id": 1}]
    assert len(router.calls) == 1


def test_collect_empty(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated([]))
    assert client.collect("METRC_ACTIVE_ITEMS", license="LIC-1") == []


def test_rest_of_pages_load_in_parallel_and_keep_page_order(client: T3Client, router: Router) -> None:
    """Page 2 waits until page 3 has been served, so page 3 finishes first.

    That only works if pages 2 and 3 are in flight together; the rows still
    come back in page order."""
    page3_served = threading.Event()
    finished: list[int] = []
    threads: set[str] = set()
    pages = [[{"id": 1}], [{"id": 2}], [{"id": 3}]]
    serve = pages_handler(pages)

    def handler(request: httpx2.Request) -> httpx2.Response:
        page = int(request.url.params.get("page", "1"))
        if page > 1:
            threads.add(threading.current_thread().name)
        if page == 2:
            assert page3_served.wait(timeout=5), "page 3 was never requested in parallel"
        response = serve(request)
        if page == 3:
            page3_served.set()
        finished.append(page)
        return response

    router.add("GET", "/v2/items", handler=handler)
    rows = client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=False)
    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert finished == [1, 3, 2]
    assert all(name.startswith("t3api-page") for name in threads)


def test_concurrency_one_loads_pages_sequentially(router: Router) -> None:
    threads: set[str] = set()
    serve = paginated(ROWS, page_size=2)

    def handler(request: httpx2.Request) -> httpx2.Response:
        if "page" in request.url.params:
            threads.add(threading.current_thread().name)
        return serve(request)

    router.add("GET", "/v2/items", handler=handler)
    with make_client(router, concurrency=1) as c:
        assert c.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=False) == ROWS
    assert len(threads) == 1
    assert page_numbers(router) == [1, 2, 3, 4]


def test_concurrency_below_one_raises(router: Router) -> None:
    with pytest.raises(ValueError, match="concurrency"):
        make_client(router, concurrency=-1)


# --------------------------------------------------------------------------- dedupe


def test_duplicate_ids_across_pages_are_dropped_and_logged(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    pages = [
        [{"id": 1}, {"id": 2}],
        [{"id": 2}, {"id": 3}],  # id 2 moved onto page 2 while loading
        [{"id": 3}, {"id": 4}],
    ]
    router.add("GET", "/v2/items", handler=pages_handler(pages))
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        rows = client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=False)
    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]
    assert "Dropped 2 duplicate row(s) from /v2/items" in caplog.text


def test_rows_without_usable_ids_are_kept(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    pages: list[list[Any]] = [
        [{"name": "no id"}, {"name": "no id"}, "not a dict"],
        [{"id": ["unhashable"]}, {"id": ["unhashable"]}, "not a dict"],
    ]
    router.add("GET", "/v2/items", handler=pages_handler(pages))
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        rows = client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=False)
    assert rows == pages[0] + pages[1]
    assert "Dropped" not in caplog.text


# --------------------------------------------------------------------------- parameters


def test_collection_parameters_map_to_query(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS, page_size=4))
    client.collect(
        "METRC_ACTIVE_ITEMS",
        license="LIC-1",
        filter=["name__contains:flower", "id__gt:3"],
        filter_logic="or",
        sort="name:asc",
        mask=["id", "name"],
        page_size=4,
        progress=False,
    )
    for request in router.calls:
        params = request.url.params
        assert params.get_list("filter") == ["name__contains:flower", "id__gt:3"]
        assert params["filterLogic"] == "or"
        assert params["sort"] == "name:asc"
        assert params["collectionMask"] == "id,name"
        assert params["pageSize"] == "4"
        assert params["licenseNumber"] == "LIC-1"
    assert sorted(page_numbers(router)) == [1, 2]


def test_string_filter_and_mask(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS))
    client.collect(
        "METRC_ACTIVE_ITEMS", license="LIC-1", filter="name__eq:x", mask="id,name", progress=False
    )
    params = router.calls[0].url.params
    assert params.get_list("filter") == ["name__eq:x"]
    assert params["collectionMask"] == "id,name"


def test_defaults_leave_optional_parameters_out(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS))
    client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", page_size=None, progress=False)
    params = router.calls[0].url.params
    assert set(params.keys()) == {"licenseNumber"}


def test_default_page_size_is_100(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS))
    client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=False)
    assert router.calls[0].url.params["pageSize"] == "100"


def test_page_size_skipped_when_endpoint_has_none(client: T3Client, router: Router) -> None:
    # /v2/tag-lists/{tag_list_id}/resolve has no pageSize parameter (and no license).
    router.add("GET", "/v2/tag-lists/{tag_list_id}/resolve", handler=paginated(ROWS))
    rows = client.collect("/v2/tag-lists/{tag_list_id}/resolve", tag_list_id="tl-1", progress=False)
    assert rows == ROWS
    assert router.calls[0].url.path == "/v2/tag-lists/tl-1/resolve"
    assert "pageSize" not in router.calls[0].url.params
    assert "licenseNumber" not in router.calls[0].url.params


def test_collect_concrete_path_with_path_parameter(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/tag-lists/{tag_list_id}/entries", handler=paginated(ROWS))
    assert client.collect("/v2/tag-lists/tl-9/entries", progress=False) == ROWS
    assert {r.url.path for r in router.calls} == {"/v2/tag-lists/tl-9/entries"}


def test_params_passthrough(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS))
    client.collect(
        "METRC_ACTIVE_ITEMS", license="LIC-1", params={"strictPagination": "true"}, progress=False
    )
    assert all(r.url.params["strictPagination"] == "true" for r in router.calls)


def test_default_license_from_client(router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS))
    with make_client(router, license="LIC-7") as c:
        c.collect("METRC_ACTIVE_ITEMS", progress=False)
    assert {r.url.params["licenseNumber"] for r in router.calls} == {"LIC-7"}


def test_missing_license_raises_before_sending(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError, match="license="):
        client.collect("METRC_ACTIVE_ITEMS")
    with pytest.raises(SpecError, match="license="):
        list(client.iter_rows("METRC_ACTIVE_ITEMS"))
    assert router.calls == []


def test_non_collection_endpoint_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(SpecError):
        client.collect("/v2/auth/whoami")
    assert router.calls == []


def test_unknown_path_keyword_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(TypeError, match="no path parameter"):
        client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", bogus="x")
    assert router.calls == []


# --------------------------------------------------------------------------- licenses


def license_rows_handler(per_license: int = 3, page_size: int = 2) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        lic = request.url.params["licenseNumber"]
        rows = [{"id": f"{lic}-{i}", "licenseNumber": lic} for i in range(per_license)]
        return paginated(rows, page_size)(request)

    return handler


def test_multi_license_runs_one_load_per_license_in_order(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=license_rows_handler())
    rows = client.collect("METRC_ACTIVE_ITEMS", license=["A", "B"], progress=False)
    assert [r["id"] for r in rows] == ["A-0", "A-1", "A-2", "B-0", "B-1", "B-2"]
    licenses = [r.url.params["licenseNumber"] for r in router.calls]
    assert licenses == ["A", "A", "B", "B"]


def test_empty_license_list_raises(client: T3Client, router: Router) -> None:
    with pytest.raises(ValueError, match="empty"):
        client.collect("METRC_ACTIVE_ITEMS", license=[])
    assert router.calls == []


# --------------------------------------------------------------------------- failures


def test_failed_page_fails_the_whole_call_and_names_the_page(
    client: T3Client, router: Router, sleeps: list[float]
) -> None:
    serve = paginated(ROWS, page_size=3)

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.params.get("page") == "2":
            return httpx2.Response(503, json={"detail": "busy"})
        return serve(request)

    router.add("GET", "/v2/items", handler=handler)
    with pytest.raises(ServerError) as info:
        client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=False)
    assert info.value.__notes__ == ["Failed loading page 2 of 3 from /v2/items."]
    # The page was retried (3 attempts, 2 backoff sleeps) before giving up.
    assert page_numbers(router).count(2) == 3
    assert len(sleeps) == 2


def test_failed_first_page_raises(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", status=404, json={"detail": "missing"})
    with pytest.raises(NotFound):
        client.collect("METRC_ACTIVE_ITEMS", license="LIC-1")


@pytest.mark.parametrize("body", [[{"id": 1}], {"data": "nope"}, {"rows": []}])
def test_non_paginated_body_raises(client: T3Client, router: Router, body: Any) -> None:
    router.add("GET", "/v2/items", json=body)
    with pytest.raises(SpecError, match="paginated"):
        client.collect("METRC_ACTIVE_ITEMS", license="LIC-1")


def test_non_paginated_body_raises_in_iter_rows(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", content=b"plain", headers={"content-type": "text/plain"})
    with pytest.raises(SpecError, match="paginated"):
        list(client.iter_rows("METRC_ACTIVE_ITEMS", license="LIC-1"))


# --------------------------------------------------------------------------- progress


def test_progress_bar_on_does_not_crash(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS, page_size=2))
    assert client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=True) == ROWS


@pytest.mark.parametrize(
    ("progress", "terminal", "expected"),
    [(None, True, True), (None, False, False), (True, False, True), (False, True, False)],
)
def test_progress_default_follows_stderr_terminal(
    client: T3Client,
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    progress: bool | None,
    terminal: bool,
    expected: bool,
) -> None:
    shown: list[tuple[str, int | None, bool]] = []
    advanced: list[int] = []

    @contextmanager
    def fake_bar(label: str, total: int | None, enabled: bool) -> Iterator[Callable[[int], None]]:
        shown.append((label, total, enabled))
        yield advanced.append

    monkeypatch.setattr(_console, "stderr_is_terminal", lambda: terminal)
    monkeypatch.setattr(_console, "progress_bar", fake_bar)
    router.add("GET", "/v2/items", handler=paginated(ROWS, page_size=2))
    client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=progress)
    assert shown == [("METRC_ACTIVE_ITEMS · LIC-1", 4, expected)]
    assert sum(advanced) == 4


def test_no_progress_bar_for_one_page(
    client: T3Client, router: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("no progress bar expected")

    monkeypatch.setattr(_console, "progress_bar", fail)
    router.add("GET", "/v2/items", handler=paginated(ROWS[:1]))
    client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", progress=True)


def test_progress_label_without_license(
    client: T3Client, router: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels: list[str] = []

    @contextmanager
    def fake_bar(label: str, total: int | None, enabled: bool) -> Iterator[Callable[[int], None]]:
        labels.append(label)
        yield lambda n: None

    monkeypatch.setattr(_console, "progress_bar", fake_bar)
    router.add("GET", "/v2/tag-lists/{tag_list_id}/entries", handler=paginated(ROWS))
    client.collect("/v2/tag-lists/{tag_list_id}/entries", tag_list_id="x", progress=True)
    assert labels == ["/v2/tag-lists/{tag_list_id}/entries"]


# --------------------------------------------------------------------------- iter_rows


def test_iter_rows_is_lazy(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS, page_size=3))
    rows = client.iter_rows("METRC_ACTIVE_ITEMS", license="LIC-1")
    assert router.calls == []
    assert next(rows) == ROWS[0]
    assert page_numbers(router) == [1]
    assert [next(rows), next(rows)] == ROWS[1:3]
    assert page_numbers(router) == [1]
    assert next(rows) == ROWS[3]
    assert page_numbers(router) == [1, 2]
    assert list(rows) == ROWS[4:]
    assert page_numbers(router) == [1, 2, 3]


def test_iter_rows_dedupes_across_pages(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    pages = [[{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 3}]]
    router.add("GET", "/v2/items", handler=pages_handler(pages))
    with caplog.at_level(logging.INFO, logger="t3api_utils"):
        rows = list(client.iter_rows("METRC_ACTIVE_ITEMS", license="LIC-1"))
    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert "Dropped 1 duplicate row(s)" in caplog.text


def test_iter_rows_maps_parameters_and_licenses(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/items", handler=license_rows_handler(per_license=2, page_size=1))
    rows = list(
        client.iter_rows(
            "METRC_ACTIVE_ITEMS",
            license=["A", "B"],
            filter="name__eq:x",
            filter_logic="and",
            sort="id:desc",
            mask=["id"],
            page_size=1,
            params={"strictPagination": "true"},
        )
    )
    assert [r["id"] for r in rows] == ["A-0", "A-1", "B-0", "B-1"]
    assert [r.url.params["licenseNumber"] for r in router.calls] == ["A", "A", "B", "B"]
    assert page_numbers(router) == [1, 2, 1, 2]
    params = router.calls[0].url.params
    assert params["filter"] == "name__eq:x"
    assert params["filterLogic"] == "and"
    assert params["sort"] == "id:desc"
    assert params["collectionMask"] == "id"
    assert params["pageSize"] == "1"
    assert params["strictPagination"] == "true"


def test_iter_rows_failure_propagates(client: T3Client, router: Router) -> None:
    serve = paginated(ROWS, page_size=4)

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.params.get("page") == "2":
            return httpx2.Response(404, json={"detail": "gone"})
        return serve(request)

    router.add("GET", "/v2/items", handler=handler)
    rows = client.iter_rows("METRC_ACTIVE_ITEMS", license="LIC-1")
    first_page = [next(rows) for _ in range(4)]
    assert first_page == ROWS[:4]
    with pytest.raises(NotFound):
        next(rows)


# --------------------------------------------------------------------------- include=


def test_include_is_sent_repeated(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/packages/active/super", handler=paginated(ROWS, page_size=4))
    rows = client.collect(
        "METRC_ACTIVE_SUPERPACKAGES", license="LIC-1", include=["labResults", "sourceHarvests"], progress=False
    )
    assert rows == ROWS
    for request in router.calls:
        assert request.url.params.get_list("include") == ["labResults", "sourceHarvests"]


def test_include_string_is_split_on_commas(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/packages/active/super", handler=paginated(ROWS[:1]))
    list(client.iter_rows("METRC_ACTIVE_SUPERPACKAGES", license="LIC-1", include="labResults, history,"))
    assert router.calls[0].url.params.get_list("include") == ["labResults", "history"]


def test_unknown_include_values_warn_and_are_sent(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("GET", "/v2/packages/active/super", handler=paginated(ROWS[:1]))
    client.collect("METRC_ACTIVE_SUPERPACKAGES", license="LIC-1", include=["history", "bogus"], progress=False)
    assert router.calls[0].url.params.get_list("include") == ["history", "bogus"]
    assert "doesn't list include value(s) bogus in the spec (it lists labResults," in caplog.text


def test_include_on_an_endpoint_without_it_warns_as_unknown(
    client: T3Client, router: Router, caplog: pytest.LogCaptureFixture
) -> None:
    router.add("GET", "/v2/items", handler=paginated(ROWS[:1]))
    client.collect("METRC_ACTIVE_ITEMS", license="LIC-1", include=["history"], progress=False)
    assert router.calls[0].url.params.get_list("include") == ["history"]
    assert "doesn't list query parameter(s) include" in caplog.text
    assert "include value" not in caplog.text


def test_empty_include_sends_nothing(client: T3Client, router: Router) -> None:
    router.add("GET", "/v2/packages/active/super", handler=paginated(ROWS[:1]))
    client.collect("METRC_ACTIVE_SUPERPACKAGES", license="LIC-1", include=[], progress=False)
    assert "include" not in router.calls[0].url.params
