from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
YGO_AGENT = ROOT / "references" / "ygo-agent"
RESULT_DIR = ROOT / "results" / "cpu_pilot"


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", default="CyberDragon.ydk")
    parser.add_argument("--episodes", type=int, default=32)
    parser.add_argument("--num-envs", type=int, default=16)
    parser.add_argument("--seed", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    import numpy as np
    import ygoenv
    from ygoai.rl.env import RecordEpisodeStatistics
    from ygoai.utils import init_ygopro

    args = parse_args()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    num_episodes = args.episodes
    num_envs = args.num_envs
    requested_seed = args.seed
    random.seed(requested_seed + 100000)
    engine_seed = random.randint(0, int(1e8))
    random.seed(engine_seed)
    np.random.seed(engine_seed)

    started_at = datetime.now(timezone.utc)
    start = time.perf_counter()
    previous_cwd = Path.cwd()
    os.chdir(YGO_AGENT / "scripts")
    deck_path = YGO_AGENT / "assets" / "deck" / args.deck
    deck, deck_names = init_ygopro(
        "YGOPro-v1",
        "english",
        str(deck_path),
        str(YGO_AGENT / "scripts" / "code_list.txt"),
        return_deck_names=True,
    )
    envs = ygoenv.make(
        task_id="YGOPro-v1",
        env_type="gymnasium",
        num_envs=num_envs,
        num_threads=num_envs,
        seed=engine_seed,
        deck1=deck,
        deck2=deck,
        player=-1,
        max_options=24,
        n_history_actions=32,
        play_mode="random",
        async_reset=False,
        verbose=False,
        record=False,
    )
    envs.num_envs = num_envs
    envs = RecordEpisodeStatistics(envs)

    observation, infos = envs.reset()
    episode_lengths: list[int] = []
    episode_rewards: list[float] = []
    win_rates: list[int] = []
    win_reasons: list[int] = []
    episode_log: list[str] = []
    step = 0
    while len(episode_lengths) < num_episodes:
        actions = np.random.randint(infos["num_options"])
        observation, rewards, dones, infos = envs.step(actions)
        step += 1
        for idx, done in enumerate(dones):
            if not done or len(episode_lengths) >= num_episodes:
                continue
            episode_length = int(infos["l"][idx])
            episode_reward = float(infos["r"][idx])
            win_reason = int(infos["win_reason"][idx])
            win = int(episode_reward > 0)
            episode_lengths.append(episode_length)
            episode_rewards.append(episode_reward)
            win_rates.append(win)
            win_reasons.append(int(win_reason == 1))
            episode_log.append(
                f"Episode {len(episode_lengths)}: length={episode_length}, "
                f"reward={episode_reward}, win={win}, win_reason={win_reason}"
            )

    elapsed = time.perf_counter() - start
    total_steps = step * num_envs
    metrics = {
        "episodes": len(episode_lengths),
        "mean_length": float(np.mean(episode_lengths)),
        "mean_reward": float(np.mean(episode_rewards)),
        "win_rate": float(np.mean(win_rates)),
        "normal_win_reason_rate": float(np.mean(win_reasons)),
        "sps": total_steps / elapsed,
        "total_steps": total_steps,
    }
    summary = (
        f"len={metrics['mean_length']:.4f}, reward={metrics['mean_reward']:.4f}, "
        f"win_rate={metrics['win_rate']:.4f}, "
        f"win_reason={metrics['normal_win_reason_rate']:.4f}\n"
        f"SPS: {metrics['sps']:.0f}, total_steps: {total_steps}\n"
        f"total: {elapsed:.4f}, model: 0.0000, env: {elapsed:.4f}\n"
    )
    output = "\n".join(episode_log) + "\n" + summary
    result_stem = f"random_eval_{num_episodes}_{deck_path.stem}"
    (RESULT_DIR / f"{result_stem}.raw.log").write_text(output, encoding="utf-8")

    report = {
        "experiment": "ygo_agent_random_eval_cpu",
        "started_at": started_at.isoformat(),
        "elapsed_seconds": elapsed,
        "returncode": 0,
        "runner": str(Path(__file__).resolve()),
        "upstream_equivalent": "scripts/eval.py random branch",
        "cwd": str(YGO_AGENT / "scripts"),
        "cpu_only": True,
        "requested_seed": requested_seed,
        "engine_seed": engine_seed,
        "num_envs": num_envs,
        "deck_path": str(deck_path),
        "deck_selector": deck,
        "available_decks": sorted(deck_names),
        "observation_shapes": {
            key: list(value.shape) for key, value in observation.items()
        },
        "info_keys": sorted(infos),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "logical_cpu_count": os.cpu_count(),
            "packages": {
                name: package_version(name)
                for name in ("jax", "jaxlib", "numpy", "flax", "ygoenv", "ygoai")
            },
        },
        "metrics": metrics,
    }
    (RESULT_DIR / f"{result_stem}.metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if hasattr(envs, "close"):
        envs.close()
    os.chdir(previous_cwd)
    print(output, end="")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
