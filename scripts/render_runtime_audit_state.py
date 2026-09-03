from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ygo_bench.runtime.modern import DEFAULT_CONFIG
from ygo_bench.visualization import render_audit_board


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a captured agent-visible runtime state as an SVG audit board."
    )
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--title", default="YGO-Bench Runtime Audit")
    args = parser.parse_args()

    capture_path = args.capture.resolve()
    if capture_path.suffix != ".npz":
        parser.error("--capture must end in .npz")
    if not capture_path.is_file():
        raise FileNotFoundError(f"Capture not found: {capture_path}")
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    with np.load(capture_path, allow_pickle=False) as archive:
        observation = {
            name.removeprefix("obs_"): archive[name]
            for name in archive.files
            if name.startswith("obs_")
        }
        required_info = ("card_visibility_", "num_options", "to_play")
        infos = {}
        for name in required_info:
            archive_name = f"info_{name}"
            if archive_name not in archive.files:
                raise ValueError(f"Capture is missing required info field: {name}")
            infos[name] = archive[archive_name]
    outputs = render_audit_board(
        observation,
        infos,
        ROOT / config["code_list"],
        ROOT / config["cdb"],
        args.output,
        args.title,
    )
    print(json.dumps({name: str(path) for name, path in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
