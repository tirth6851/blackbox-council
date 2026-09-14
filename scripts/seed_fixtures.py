#!/usr/bin/env python3
"""Regenerate apps/api/app/fixtures/retention-v1.json from the declarative
source file, computing real byte counts and SHA-256 hashes from the actual
files under demo-repo/uploads.

Never invent or hardcode a hash or byte count here: both are measured from
the file on disk so the same fixture always yields the same values, and the
seeded byte counts are never presented as real storage savings.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_REPO = REPO_ROOT / "demo-repo"
SOURCE_PATH = REPO_ROOT / "apps" / "api" / "app" / "fixtures" / "retention-v1.source.json"
OUTPUT_PATH = REPO_ROOT / "apps" / "api" / "app" / "fixtures" / "retention-v1.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    files = []
    for entry in source["files"]:
        file_path = DEMO_REPO / entry["path"]
        if not file_path.is_file():
            print(f"error: missing fixture file {file_path}", file=sys.stderr)
            return 1
        real_path = file_path.resolve()
        if DEMO_REPO.resolve() not in real_path.parents:
            print(f"error: refusing path outside demo-repo: {file_path}", file=sys.stderr)
            return 1
        files.append(
            {
                "id": entry["id"],
                "path": entry["path"],
                "owner_id": entry["owner_id"],
                "inactive_days": entry["inactive_days"],
                "modified_days": entry["modified_days"],
                "legal_hold": entry["legal_hold"],
                "synthetic": True,
                "content_sha256": sha256_of(file_path),
                "byte_count": file_path.stat().st_size,
            }
        )

    output = {"fixture_id": source["fixture_id"], "files": files}
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
