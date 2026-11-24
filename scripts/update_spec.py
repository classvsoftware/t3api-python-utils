"""Refresh the bundled OpenAPI spec (t3api_utils/spec/openapi.json.gz).

Run before each release:

    uv run python scripts/update_spec.py

It prints how the endpoint kinds changed so the release notes can mention it.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import httpx2

from t3api_utils.spec.registry import Registry

TARGET = Path(__file__).resolve().parent.parent / "t3api_utils" / "spec" / "openapi.json.gz"
DEFAULT_URL = "https://api.trackandtrace.tools/v2/spec/openapi.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args(argv)

    response = httpx2.get(args.url, timeout=60.0)
    response.raise_for_status()
    spec = response.json()
    if "paths" not in spec:
        print("The response isn't an OpenAPI document.", file=sys.stderr)
        return 1

    before: Counter[str] = Counter()
    if args.target.exists():
        old = json.loads(gzip.decompress(args.target.read_bytes()))
        before = Counter(str(ep.kind) for ep in Registry(old).endpoints)
    after: Counter[str] = Counter(ep.kind for ep in Registry(spec).endpoints)

    raw = json.dumps(spec, separators=(",", ":"), ensure_ascii=False).encode()
    args.target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    print(f"Wrote {args.target} ({len(raw):,} bytes raw, {args.target.stat().st_size:,} gzipped)")
    for kind in sorted(set(before) | set(after)):
        change = after[kind] - before[kind]
        sign = f" ({change:+d})" if before and change else ""
        print(f"  {kind:16} {after[kind]}{sign}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
