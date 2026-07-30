#!/usr/bin/env python3
"""Export or verify the deterministic current-release OpenAPI contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = APP_ROOT / "openapi" / "current-release.json"


def normalized_openapi() -> dict:
    os.environ.setdefault("CODEAWARE_TESTING", "1")
    sys.path.insert(0, str(APP_ROOT))
    from app.main import app

    schema = app.openapi()
    schema.pop("servers", None)
    return schema


def encoded(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    output = encoded(normalized_openapi())
    if args.write:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(output, encoding="utf-8")
        print(f"wrote {SNAPSHOT.relative_to(APP_ROOT)}")
        return 0
    if not SNAPSHOT.is_file():
        print("OpenAPI snapshot missing; run scripts/export_openapi.py --write", file=sys.stderr)
        return 1
    if SNAPSHOT.read_text(encoding="utf-8") != output:
        print("OpenAPI snapshot is stale; run scripts/export_openapi.py --write", file=sys.stderr)
        return 1
    print("OpenAPI snapshot matches current app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
