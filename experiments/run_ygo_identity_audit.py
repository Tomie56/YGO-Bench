from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from run_ygo_trace_pilot import YGO_AGENT, run_episode
from ygoai.utils import init_ygopro


ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "results" / "cpu_pilot"
BINARY_PATH = YGO_AGENT / "ygoenv" / "ygoenv" / "ygopro" / "ygopro_ygoenv.so"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", default="CyberDragon.ydk")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=400)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed + 100000)
    engine_seed = random.randint(0, int(1e8))
    action_seed = args.seed + 200000
    deck_path = YGO_AGENT / "assets" / "deck" / args.deck

    previous_cwd = Path.cwd()
    os.chdir(YGO_AGENT / "scripts")
    try:
        deck = init_ygopro(
            "YGOPro-v1",
            "english",
            str(deck_path),
            str(YGO_AGENT / "scripts" / "code_list.txt"),
        )
        episode = run_episode(engine_seed, deck, action_seed, args.max_steps)
    finally:
        os.chdir(previous_cwd)

    totals: dict[str, int] = {}
    for state in episode.states:
        for key, value in state["hidden_information"].items():
            totals[key] = totals.get(key, 0) + int(value)

    report = {
        "experiment": "ygo_identity_grounding_audit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deck": str(deck_path),
        "requested_seed": args.seed,
        "engine_seed": engine_seed,
        "action_seed": action_seed,
        "binary": {
            "path": str(BINARY_PATH),
            "sha256": sha256(BINARY_PATH),
        },
        "steps_audited": len(episode.states),
        "terminal": episode.terminal,
        "totals": totals,
        "opponent_private_identity_pass": (
            totals.get("opponent_private_identity_leaks", 0) == 0
            and totals.get("opponent_private_identity_mask_leaks", 0) == 0
        ),
        "opponent_private_detail_pass": totals.get(
            "opponent_private_detail_leaks", 0
        )
        == 0,
        "opponent_private_sequence_pass": totals.get(
            "opponent_private_sequence_leaks", 0
        )
        == 0,
        "facedown_field_identity_pass": (
            totals.get("facedown_opponent_field_identity_leaks", 0) == 0
            and totals.get("facedown_opponent_field_identity_mask_leaks", 0) == 0
        ),
        "potential_own_deck_order_leak": totals.get(
            "my_deck_identity_exposed", 0
        )
        > 0,
        "own_hand_identity_available": (
            totals.get("my_hand_rows", 0) > 0
            and totals.get("my_hand_identity_missing", 0) == 0
        ),
    }
    mask_applicable = totals.get("mask_nonzero_values", 0) > 0
    report["identity_mask_applicable"] = mask_applicable
    report["identity_mask_consistency_pass"] = (
        totals.get("visible_identity_mask_missing", 0) == 0
        and totals.get("hidden_identity_mask_exposed", 0) == 0
        if mask_applicable
        else None
    )
    report["identity_grounding_pass"] = (
        report["own_hand_identity_available"]
        and report["identity_mask_consistency_pass"] is not False
    )
    report["hidden_information_pass"] = (
        report["opponent_private_identity_pass"]
        and report["opponent_private_detail_pass"]
        and report["opponent_private_sequence_pass"]
        and report["facedown_field_identity_pass"]
        and not report["potential_own_deck_order_leak"]
    )

    output = RESULT_DIR / "identity_audit_post_card_id_fix.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
