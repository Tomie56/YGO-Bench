from __future__ import annotations

import argparse
from pathlib import Path

from ygo_bench.visualization.public_site import build_public_site, validate_public_site


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the static YGO-Bench project site and review terminal."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "tmp" / "pilot-review-v0.2" / "manifest.json",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "site")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_public_site(args.manifest, args.output_dir)
    summary = validate_public_site(args.output_dir)
    print(manifest)
    print(f"files={summary['file_count']} bytes={summary['total_bytes']}")


if __name__ == "__main__":
    main()
