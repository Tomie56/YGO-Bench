from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from run_local_pilot import binary_metrics, load_cards, load_decks, run_d2


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_RESULT_ROOT = REPO_ROOT / "results" / "local_pilot"
CPU_RESULT_ROOT = REPO_ROOT / "results" / "cpu_pilot"


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def summarize_u1() -> dict[str, object]:
    path = LOCAL_RESULT_ROOT / "u1_text_script_proxy.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    metrics: dict[str, object] = {}
    for name in ("count_limit_callback", "cost_callback", "target_callback", "condition_callback"):
        labels = [as_bool(row[f"label_{name}"]) for row in rows]
        predictions = [as_bool(row[f"pred_{name}"]) for row in rows]
        metrics[name] = binary_metrics(labels, predictions)
    return {
        "experiment": "U1 text-to-script-callback lexical proxy",
        "records": len(rows),
        "metrics": metrics,
        "source": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "interpretation_limit": (
            "Lua callbacks are implementation structure, not direct semantic gold. "
            "SetTarget is not equivalent to PSCT semantic targeting."
        ),
    }


def summarize_d1() -> dict[str, object]:
    path = LOCAL_RESULT_ROOT / "d1_deck_legality.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["snapshot_id"], row["regulation"])].append(row)

    snapshots: list[dict[str, object]] = []
    deck_passes: dict[str, list[str]] = defaultdict(list)
    for (snapshot_id, regulation), group in sorted(grouped.items()):
        violation_counts: Counter[str] = Counter()
        for row in group:
            if as_bool(row["valid"]):
                deck_passes[row["deck"]].append(regulation)
            else:
                deck_passes.setdefault(row["deck"], [])
            for item in json.loads(row["violations"]):
                violation_counts[str(item["type"])] += 1
        valid = sum(as_bool(row["valid"]) for row in group)
        snapshots.append(
            {
                "snapshot_id": snapshot_id,
                "regulation": regulation,
                "decks": len(group),
                "valid_decks": valid,
                "invalid_decks": len(group) - valid,
                "violation_counts": dict(sorted(violation_counts.items())),
            }
        )

    compatibility = Counter(
        "+".join(sorted(regulations)) if regulations else "none"
        for regulations in deck_passes.values()
    )
    return {
        "experiment": "D1 TCG/OCG snapshot deck-legality audit",
        "snapshots": snapshots,
        "cross_snapshot_patterns": dict(sorted(compatibility.items())),
        "source": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "interpretation_limit": (
            "The 31 bundled decks are an engineering sample and predate the selected snapshots; "
            "this is an importer/regulation audit, not a tournament deck-quality estimate."
        ),
    }


def main() -> None:
    CPU_RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    cards = load_cards()
    decks = load_decks()
    print("Running D2 leave-one-deck-out baseline...", flush=True)
    d2 = run_d2(decks, cards)
    result = {
        "experiment": "cpu_non_llm_baselines",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cpu_only": True,
        "u1_rule_understanding_proxy": summarize_u1(),
        "d1_deck_legality": summarize_d1(),
        "d2_deck_completion": d2,
    }
    output = CPU_RESULT_ROOT / "non_llm_baselines.metrics.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    print(f"Wrote {output}", flush=True)


if __name__ == "__main__":
    main()
