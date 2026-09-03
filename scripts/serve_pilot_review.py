from __future__ import annotations

import argparse
from pathlib import Path

from ygo_bench.visualization.review_app import serve_review_app


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the local YGO-Bench review terminal.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "tmp" / "pilot-review-v0.1" / "manifest.json",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    serve_review_app(args.manifest, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
