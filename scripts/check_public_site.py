from __future__ import annotations

import argparse
from pathlib import Path

from ygo_bench.visualization.public_site import validate_public_site


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a generated public Pages tree.")
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    summary = validate_public_site(args.site)
    print(f"public site valid: files={summary['file_count']} bytes={summary['total_bytes']}")


if __name__ == "__main__":
    main()
