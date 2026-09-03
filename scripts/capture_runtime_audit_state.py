from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np

from ygo_bench.runtime.modern import DEFAULT_CONFIG, ModernRuntime


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close_pool(pool: Any) -> None:
    if hasattr(pool, "close"):
        pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture one agent-visible modern runtime state for audit rendering."
    )
    parser.add_argument("--profile", choices=("tcg", "ocg"), required=True)
    parser.add_argument("--stage", choices=("reset", "step"), default="reset")
    parser.add_argument("--action-index", type=int, default=0)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output_path = args.output.resolve()
    if output_path.suffix != ".npz":
        parser.error("--output must end in .npz")
    if args.stage == "reset" and args.action_index != 0:
        parser.error("--action-index is only valid for --stage step")

    runtime = ModernRuntime(args.config)
    profile = runtime.profile(args.profile)
    started = time.perf_counter()
    pool = None
    try:
        runtime.initialize()
        pool = runtime.construct_gymnasium_pool(args.profile)
        observation, infos = pool.reset()
        if args.stage == "step":
            num_options = int(np.asarray(infos["num_options"])[0])
            if not 0 <= args.action_index < num_options:
                raise ValueError(
                    f"Action index {args.action_index} is outside {num_options} legal options"
                )
            action = np.asarray([args.action_index], dtype=np.int32)
            observation, rewards, terminated, truncated, infos = pool.step(action)
        else:
            rewards = np.asarray([], dtype=np.float32)
            terminated = np.asarray([], dtype=bool)
            truncated = np.asarray([], dtype=bool)
    finally:
        if pool is not None:
            close_pool(pool)

    arrays = {f"obs_{name}": np.asarray(value) for name, value in observation.items()}
    skipped_info_fields = []
    for name, value in infos.items():
        array = np.asarray(value)
        if array.dtype.hasobject:
            skipped_info_fields.append(name)
            continue
        arrays[f"info_{name}"] = array
    arrays["rewards"] = rewards
    arrays["terminated"] = terminated
    arrays["truncated"] = truncated
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path, **arrays)

    metadata = {
        "status": "captured",
        "profile": args.profile,
        "stage": args.stage,
        "action_index": args.action_index if args.stage == "step" else None,
        "environment_snapshot_id": profile["snapshot_id"],
        "environment_spec": profile["spec"],
        "config": str(args.config.resolve().relative_to(ROOT)),
        "config_sha256": sha256_file(args.config.resolve()),
        "extension_sha256": sha256_file(runtime.extension),
        "asset_manifest_sha256": sha256_file(runtime.asset_manifest_path),
        "runtime_snapshot_sha256": sha256_file(runtime.runtime_snapshot_path),
        "python": platform.python_version(),
        "duration_seconds": time.perf_counter() - started,
        "pool_destroyed": True,
        "skipped_object_info_fields": skipped_info_fields,
        "capture": str(output_path),
    }
    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
