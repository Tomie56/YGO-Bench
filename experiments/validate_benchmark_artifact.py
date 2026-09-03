from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ygo_bench.contracts import SCHEMA_PATHS, validate_path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate YGO-Bench records against a frozen contract"
    )
    parser.add_argument("--kind", choices=sorted(SCHEMA_PATHS), required=True)
    parser.add_argument("paths", type=Path, nargs="+")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = []
    total_records = 0
    for path in args.paths:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Contract input does not exist: {resolved}")
        record_count = validate_path(args.kind, resolved)
        total_records += record_count
        artifacts.append(
            {
                "path": str(resolved),
                "sha256": sha256_file(resolved),
                "records": record_count,
            }
        )
    print(
        json.dumps(
            {
                "status": "passed",
                "kind": args.kind,
                "schema": str(SCHEMA_PATHS[args.kind]),
                "records": total_records,
                "artifacts": artifacts,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
