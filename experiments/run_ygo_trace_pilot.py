from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import ygoenv
from ygoai.utils import init_ygopro


ROOT = Path(__file__).resolve().parents[1]
YGO_AGENT = ROOT / "references" / "ygo-agent"
RESULT_DIR = ROOT / "results" / "cpu_pilot" / "trace"
OBSERVATION_KEYS = ("cards_", "global_", "actions_", "h_actions_", "mask_")


@dataclass
class EpisodeRun:
    actions: list[int]
    states: list[dict[str, Any]]
    observations: dict[str, list[np.ndarray]]
    terminal: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", default="CyberDragon.ydk")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=400)
    parser.add_argument("--counterfactual-groups", type=int, default=10)
    return parser.parse_args()


def observation_hash(observation: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for key in sorted(observation):
        value = np.ascontiguousarray(observation[key])
        digest.update(key.encode("ascii"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()


def row_card_id(row: np.ndarray) -> int:
    return (int(row[0]) << 8) + int(row[1])


def info_value(infos: dict[str, Any], key: str, index: int = 0) -> Any:
    value = infos[key]
    if isinstance(value, np.ndarray):
        value = value[index]
    if isinstance(value, np.generic):
        return value.item()
    return value


def private_information_audit(observation: dict[str, np.ndarray]) -> dict[str, int]:
    cards = observation["cards_"][0]
    masks = observation["mask_"][0]
    global_features = observation["global_"][0]
    my_counts = [int(value) for value in global_features[8:15]]
    opponent_counts = [int(value) for value in global_features[15:22]]

    offsets: list[tuple[str, int, int]] = []
    cursor = 0
    locations = ("deck", "hand", "monster", "spell_trap", "grave", "banished", "extra")
    for owner, counts in (("me", my_counts), ("opponent", opponent_counts)):
        for location, count in zip(locations, counts):
            offsets.append((f"{owner}_{location}", cursor, cursor + count))
            cursor += count

    result = {
        "opponent_private_rows": 0,
        "opponent_private_identity_leaks": 0,
        "opponent_private_identity_mask_leaks": 0,
        "opponent_private_detail_leaks": 0,
        "opponent_private_sequence_leaks": 0,
        "my_deck_rows": 0,
        "my_deck_identity_exposed": 0,
        "my_hand_rows": 0,
        "my_hand_identity_missing": 0,
        "my_hand_identity_mask_missing": 0,
        "facedown_opponent_field_rows": 0,
        "facedown_opponent_field_identity_leaks": 0,
        "facedown_opponent_field_identity_mask_leaks": 0,
        "visible_identity_rows": 0,
        "visible_identity_mask_missing": 0,
        "hidden_identity_rows": 0,
        "hidden_identity_mask_exposed": 0,
        "mask_nonzero_values": int(np.count_nonzero(masks[:cursor])),
    }
    for label, start, end in offsets:
        rows = cards[start:end]
        row_masks = masks[start:end]
        if label in {"opponent_deck", "opponent_hand", "opponent_extra"}:
            result["opponent_private_rows"] += len(rows)
            result["opponent_private_identity_leaks"] += sum(
                row_card_id(row) != 0 for row in rows
            )
            result["opponent_private_identity_mask_leaks"] += sum(
                int(row_mask[0]) != 0 for row_mask in row_masks
            )
            result["opponent_private_detail_leaks"] += sum(
                bool(np.any(row[7:])) for row in rows
            )
            result["opponent_private_sequence_leaks"] += sum(
                int(row[3]) != 0 for row in rows
            )
        elif label == "me_deck":
            result["my_deck_rows"] += len(rows)
            result["my_deck_identity_exposed"] += sum(
                row_card_id(row) != 0 for row in rows
            )
        elif label == "me_hand":
            result["my_hand_rows"] += len(rows)
            result["my_hand_identity_missing"] += sum(
                row_card_id(row) == 0 for row in rows
            )
            result["my_hand_identity_mask_missing"] += sum(
                int(row_mask[0]) == 0 for row_mask in row_masks
            )
        elif label in {"opponent_monster", "opponent_spell_trap"}:
            for row, row_mask in zip(rows, row_masks):
                position_id = int(row[5])
                if position_id in {2, 6, 7}:
                    result["facedown_opponent_field_rows"] += 1
                    result["facedown_opponent_field_identity_leaks"] += int(
                        row_card_id(row) != 0
                    )
                    result["facedown_opponent_field_identity_mask_leaks"] += int(
                        row_mask[0] != 0
                    )

    active_cards = cards[:cursor]
    active_masks = masks[:cursor]
    for row, row_mask in zip(active_cards, active_masks):
        identity_visible = row_card_id(row) != 0
        identity_masked_visible = int(row_mask[0]) != 0
        if identity_visible:
            result["visible_identity_rows"] += 1
            result["visible_identity_mask_missing"] += int(not identity_masked_visible)
        else:
            result["hidden_identity_rows"] += 1
            result["hidden_identity_mask_exposed"] += int(identity_masked_visible)
    return result


def make_env(engine_seed: int, deck: str, record: bool = False):
    return ygoenv.make(
        task_id="YGOPro-v1",
        env_type="gymnasium",
        num_envs=1,
        num_threads=1,
        seed=engine_seed,
        deck1=deck,
        deck2=deck,
        player=-1,
        max_options=24,
        n_history_actions=32,
        play_mode="random",
        async_reset=False,
        verbose=False,
        record=record,
    )


def close_env(env: Any) -> None:
    if hasattr(env, "close"):
        env.close()
    del env
    gc.collect()


def run_episode(
    engine_seed: int,
    deck: str,
    action_seed: int,
    max_steps: int,
    fixed_actions: list[int] | None = None,
    record: bool = False,
) -> EpisodeRun:
    env = make_env(engine_seed, deck, record=record)
    observation, infos = env.reset()
    rng = np.random.default_rng(action_seed)
    actions: list[int] = []
    states: list[dict[str, Any]] = []
    observations: dict[str, list[np.ndarray]] = {key: [] for key in OBSERVATION_KEYS}
    terminal: dict[str, Any] = {"done": False, "max_steps_reached": False}

    for step in range(max_steps):
        for key in OBSERVATION_KEYS:
            observations[key].append(np.array(observation[key][0], copy=True))
        num_options = int(info_value(infos, "num_options"))
        if fixed_actions is None:
            action = int(rng.integers(num_options))
        else:
            if step >= len(fixed_actions):
                terminal = {"done": False, "prefix_complete": True, "steps": step}
                break
            action = fixed_actions[step]
            if action >= num_options:
                raise AssertionError(
                    f"Replay action {action} is invalid for {num_options} options at step {step}"
                )
        actions.append(action)
        states.append(
            {
                "step": step,
                "observation_hash": observation_hash(observation),
                "num_options": num_options,
                "to_play": int(info_value(infos, "to_play")),
                "global": observation["global_"][0].tolist(),
                "legal_actions": observation["actions_"][0, :num_options].tolist(),
                "action": action,
                "action_features": observation["actions_"][0, action].tolist(),
                "hidden_information": private_information_audit(observation),
            }
        )
        next_observation, rewards, terminated, truncated, next_infos = env.step(
            np.asarray([action], dtype=np.int32)
        )
        done = bool(terminated[0] or truncated[0])
        states[-1].update(
            reward=float(rewards[0]),
            done=done,
            next_observation_hash=observation_hash(next_observation),
        )
        observation, infos = next_observation, next_infos
        if done:
            terminal = {
                "done": True,
                "steps": step + 1,
                "reward": float(rewards[0]),
                "win_reason": int(info_value(infos, "win_reason")),
            }
            break
    else:
        terminal = {"done": False, "max_steps_reached": True, "steps": max_steps}

    close_env(env)
    return EpisodeRun(actions, states, observations, terminal)


def replay_prefix(
    engine_seed: int,
    deck: str,
    prefix: list[int],
    branch_action: int,
) -> dict[str, Any]:
    env = make_env(engine_seed, deck)
    observation, infos = env.reset()
    prefix_hashes: list[str] = []
    for step, action in enumerate(prefix):
        prefix_hashes.append(observation_hash(observation))
        num_options = int(info_value(infos, "num_options"))
        if action >= num_options:
            raise AssertionError(f"Invalid prefix action at step {step}")
        observation, rewards, terminated, truncated, infos = env.step(
            np.asarray([action], dtype=np.int32)
        )
        if bool(terminated[0] or truncated[0]):
            raise AssertionError(f"Prefix terminated at step {step}")

    pre_hash = observation_hash(observation)
    num_options = int(info_value(infos, "num_options"))
    if branch_action >= num_options:
        raise AssertionError("Branch action is not legal")
    pre_global = observation["global_"][0].astype(int)
    action_features = observation["actions_"][0, branch_action].tolist()
    next_observation, rewards, terminated, truncated, infos = env.step(
        np.asarray([branch_action], dtype=np.int32)
    )
    post_global = next_observation["global_"][0].astype(int)
    result = {
        "prefix_hashes": prefix_hashes,
        "pre_hash": pre_hash,
        "post_hash": observation_hash(next_observation),
        "num_options": num_options,
        "action": branch_action,
        "action_features": action_features,
        "reward": float(rewards[0]),
        "done": bool(terminated[0] or truncated[0]),
        "global_delta": (post_global - pre_global).tolist(),
    }
    close_env(env)
    return result


def main() -> None:
    args = parse_args()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    replay_dir = YGO_AGENT / "scripts" / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    existing_replays = set(replay_dir.glob("*.yrp"))

    random.seed(args.seed + 100000)
    engine_seed = random.randint(0, int(1e8))
    action_seed = args.seed + 200000
    deck_path = YGO_AGENT / "assets" / "deck" / args.deck

    previous_cwd = Path.cwd()
    os.chdir(YGO_AGENT / "scripts")
    deck = init_ygopro(
        "YGOPro-v1",
        "english",
        str(deck_path),
        str(YGO_AGENT / "scripts" / "code_list.txt"),
    )

    original = run_episode(
        engine_seed, deck, action_seed, args.max_steps, record=True
    )
    replay = run_episode(
        engine_seed,
        deck,
        action_seed,
        args.max_steps,
        fixed_actions=original.actions,
    )

    original_hashes = [state["observation_hash"] for state in original.states]
    replay_hashes = [state["observation_hash"] for state in replay.states]
    matched = sum(a == b for a, b in zip(original_hashes, replay_hashes))
    replay_report = {
        "engine_seed": engine_seed,
        "action_seed": action_seed,
        "original_steps": len(original_hashes),
        "replay_steps": len(replay_hashes),
        "matched_state_hashes": matched,
        "all_state_hashes_match": original_hashes == replay_hashes,
        "actions_match": original.actions == replay.actions,
        "original_terminal": original.terminal,
        "replay_terminal": replay.terminal,
    }

    audit_totals: dict[str, int] = {}
    for state in original.states:
        for key, value in state["hidden_information"].items():
            audit_totals[key] = audit_totals.get(key, 0) + value
    hidden_report = {
        "steps_audited": len(original.states),
        "totals": audit_totals,
        "opponent_private_identity_pass": (
            audit_totals.get("opponent_private_identity_leaks", 0) == 0
            and audit_totals.get("opponent_private_identity_mask_leaks", 0) == 0
        ),
        "opponent_private_detail_pass": audit_totals.get(
            "opponent_private_detail_leaks", 0
        )
        == 0,
        "opponent_private_sequence_pass": audit_totals.get(
            "opponent_private_sequence_leaks", 0
        )
        == 0,
        "facedown_field_identity_pass": (
            audit_totals.get("facedown_opponent_field_identity_leaks", 0) == 0
            and audit_totals.get("facedown_opponent_field_identity_mask_leaks", 0) == 0
        ),
        "potential_own_deck_order_leak": audit_totals.get(
            "my_deck_identity_exposed", 0
        )
        > 0,
        "own_hand_identity_available": (
            audit_totals.get("my_hand_rows", 0) > 0
            and audit_totals.get("my_hand_identity_missing", 0) == 0
        ),
    }
    mask_applicable = audit_totals.get("mask_nonzero_values", 0) > 0
    hidden_report["identity_mask_applicable"] = mask_applicable
    hidden_report["identity_mask_consistency_pass"] = (
        audit_totals.get("visible_identity_mask_missing", 0) == 0
        and audit_totals.get("hidden_identity_mask_exposed", 0) == 0
        if mask_applicable
        else None
    )
    hidden_report["identity_grounding_pass"] = (
        hidden_report["own_hand_identity_available"]
        and hidden_report["identity_mask_consistency_pass"] is not False
    )
    hidden_report["hidden_information_pass"] = (
        hidden_report["opponent_private_identity_pass"]
        and hidden_report["opponent_private_detail_pass"]
        and hidden_report["opponent_private_sequence_pass"]
        and hidden_report["facedown_field_identity_pass"]
        and not hidden_report["potential_own_deck_order_leak"]
    )

    candidates = [state for state in original.states if state["num_options"] >= 2]
    if len(candidates) > args.counterfactual_groups:
        positions = np.linspace(
            0, len(candidates) - 1, args.counterfactual_groups, dtype=int
        )
        candidates = [candidates[index] for index in positions]
    counterfactuals: list[dict[str, Any]] = []
    for group_index, state in enumerate(candidates):
        step = int(state["step"])
        original_action = int(state["action"])
        alternative_action = (original_action + 1) % int(state["num_options"])
        prefix = original.actions[:step]
        branch_a = replay_prefix(engine_seed, deck, prefix, original_action)
        branch_b = replay_prefix(engine_seed, deck, prefix, alternative_action)
        counterfactuals.append(
            {
                "group_id": f"cyberdragon-action-cf-{group_index:03d}",
                "label_kind": "L1_engine_action_counterfactual",
                "source_step": step,
                "source_observation_hash": state["observation_hash"],
                "same_pre_state": (
                    branch_a["pre_hash"]
                    == branch_b["pre_hash"]
                    == state["observation_hash"]
                ),
                "branch_a": branch_a,
                "branch_b": branch_b,
                "outcome_flipped": branch_a["post_hash"] != branch_b["post_hash"],
                "limitation": (
                    "This varies the legal action at a fixed engine state; it is not "
                    "a minimal state-variable counterfactual."
                ),
            }
        )

    with (RESULT_DIR / "canonical_trace.jsonl").open("w", encoding="utf-8") as handle:
        for state in original.states:
            handle.write(json.dumps(state, separators=(",", ":")) + "\n")
    np.savez_compressed(
        RESULT_DIR / "canonical_observations.npz",
        **{
            key: np.stack(original.observations[key])
            for key in OBSERVATION_KEYS
        },
    )
    (RESULT_DIR / "replay_report.json").write_text(
        json.dumps(replay_report, indent=2), encoding="utf-8"
    )
    (RESULT_DIR / "hidden_information_audit.json").write_text(
        json.dumps(hidden_report, indent=2), encoding="utf-8"
    )
    with (RESULT_DIR / "action_counterfactual_gold.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for record in counterfactuals:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    new_replays = sorted(set(replay_dir.glob("*.yrp")) - existing_replays)
    copied_replays: list[str] = []
    for source in new_replays:
        destination = RESULT_DIR / source.name
        shutil.copy2(source, destination)
        copied_replays.append(str(destination))

    manifest = {
        "experiment": "ygo_cpu_trace_pilot",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deck": str(deck_path),
        "engine_seed": engine_seed,
        "action_seed": action_seed,
        "trace_steps": len(original.states),
        "counterfactual_groups": len(counterfactuals),
        "replay": replay_report,
        "hidden_information": hidden_report,
        "yrp_files": copied_replays,
    }
    (RESULT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    os.chdir(previous_cwd)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
