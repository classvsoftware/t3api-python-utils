"""Live smoke tests against the Metrc sandbox, through the real T3 API.

Skipped unless T3_SMOKE_SECRET_KEY is set. Run before each release:

    T3_SMOKE_SECRET_KEY=... uv run pytest -m sandbox

The key is exchanged for a sandbox JWT (POST /v2/auth/sandbox), so every write
goes to the Metrc sandbox, and writes here are dry runs anyway.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from itertools import islice
from pathlib import Path

import pytest

import t3api_utils as t3

# Read at import: the autouse `isolated` fixture clears T3_* variables.
SMOKE_KEY = os.environ.get("T3_SMOKE_SECRET_KEY")
SMOKE_HOST = os.environ.get("T3_SMOKE_API_HOST")

pytestmark = [
    pytest.mark.sandbox,
    pytest.mark.skipif(not SMOKE_KEY, reason="set T3_SMOKE_SECRET_KEY to run sandbox tests"),
]


@pytest.fixture(autouse=True)
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Live tests really wait between retries (overrides the conftest recorder)."""
    monkeypatch.setattr(time, "sleep", time.sleep)
    return []


@pytest.fixture(scope="module")
def sandbox() -> Iterator[t3.T3Client]:
    assert SMOKE_KEY is not None
    client = t3.connect(secret_key=SMOKE_KEY, api_host=SMOKE_HOST, sandbox=True, interactive=False)
    yield client
    client.close()


@pytest.fixture(scope="module")
def license_number(sandbox: t3.T3Client) -> str:
    licenses = sandbox.licenses()
    assert licenses, "the sandbox account has no licenses"
    return str(licenses[0]["licenseNumber"])


def test_whoami(sandbox: t3.T3Client) -> None:
    who = sandbox.whoami()
    assert who.get("username")
    assert sandbox.credential_kind == "jwt"


def test_collect_and_iter_rows(sandbox: t3.T3Client, license_number: str) -> None:
    first = list(islice(sandbox.iter_rows("METRC_ACTIVE_ITEMS", license=license_number, page_size=5), 5))
    rows = sandbox.collect("METRC_ACTIVE_ITEMS", license=license_number, page_size=50, progress=False)
    assert all(r.get("licenseNumber") == license_number for r in rows)
    assert {r["id"] for r in first} <= {r["id"] for r in rows}


def test_dry_run_write(sandbox: t3.T3Client, license_number: str) -> None:
    items = sandbox.collect("METRC_ACTIVE_ITEMS", license=license_number, mask=["id"], progress=False)
    if not items:
        pytest.skip("no active items to dry-run against")
    result = sandbox.post("/v2/items/discontinue", license=license_number, json={"id": items[0]["id"]})
    assert result.dry_run is True
    assert result.message == "Dry run"


def test_report_download(sandbox: t3.T3Client, license_number: str, tmp_path: Path) -> None:
    path = sandbox.report("ITEMS_REPORT", licenses=[license_number], to=tmp_path / "items.csv")
    assert path.read_bytes().strip()


def test_tag_list_round_trip(sandbox: t3.T3Client, license_number: str) -> None:
    packages = sandbox.collect(
        "METRC_ACTIVE_PACKAGES", license=license_number, mask=["id", "label"], progress=False
    )
    if not packages:
        pytest.skip("no active packages to put in a tag list")
    labels = [p["label"] for p in packages[:3]]
    tag_list = sandbox.tag_lists.create(
        "t3api-utils smoke test", license=license_number, endpoint="METRC_ACTIVE_PACKAGES", handles=labels
    )
    try:
        resolved = tag_list.resolve()
        assert [r["label"] for r in resolved] == labels
    finally:
        tag_list.update(archived=True)
