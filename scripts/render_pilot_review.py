from __future__ import annotations

import argparse
from pathlib import Path

from ygo_bench.visualization import render_pilot_review_bundle


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render static YGO-Bench pilot questions for human review."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "tmp" / "pilot-review-v0.2",
    )
    parser.add_argument(
        "--edge",
        type=Path,
        help="Optional Microsoft Edge executable. When omitted, only HTML is generated.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = render_pilot_review_bundle(
        understanding_path=ROOT
        / "data"
        / "benchmark"
        / "understanding"
        / "pilot-candidates-v0.1.jsonl",
        construction_path=ROOT
        / "data"
        / "benchmark"
        / "deck"
        / "pilot-candidates-v0.1.jsonl",
        puzzle_root=ROOT / "tmp" / "projectignis-puzzles-audit",
        card_image_dir=ROOT
        / "data"
        / "card_images"
        / "runtime-modern-v1-2026-07-20"
        / "full",
        cdb_paths=(
            ROOT / "references" / "babelcdb" / "cards.cdb",
            ROOT / "references" / "babelcdb" / "release-cori.cdb",
        ),
        card_script_dir=ROOT / "references" / "cardscripts" / "official",
        output_dir=args.output_dir,
        edge_executable=args.edge,
    )
    print(manifest)


if __name__ == "__main__":
    main()
