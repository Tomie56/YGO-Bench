from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CDB_PATH = REPO_ROOT / "references" / "babelcdb" / "cards.cdb"
SCRIPT_ROOT = REPO_ROOT / "references" / "cardscripts" / "official"
DECK_ROOT = REPO_ROOT / "references" / "ygo-agent" / "assets" / "deck"
SNAPSHOT_ROOT = REPO_ROOT / "snapshots"
RESULT_ROOT = REPO_ROOT / "results" / "local_pilot"
REPORT_PATH = REPO_ROOT / "docs" / "local-pilot-results.md"
DEFAULT_SNAPSHOT_IDS = ["tcg-kde-e-2026-05-18", "ocg-jp-2026-07-01"]


def load_cards() -> dict[int, dict[str, object]]:
    connection = sqlite3.connect(CDB_PATH)
    try:
        rows = connection.execute(
            """
            SELECT d.id, d.type, d.ot, t.name, t.desc
            FROM datas d JOIN texts t USING(id)
            """
        ).fetchall()
    finally:
        connection.close()
    return {
        int(card_id): {
            "type": int(card_type),
            "ot": int(ot),
            "name": name or "",
            "desc": desc or "",
        }
        for card_id, card_type, ot, name, desc in rows
    }


def parse_ydk(path: Path) -> dict[str, list[int]]:
    zones: dict[str, list[int]] = {"main": [], "extra": [], "side": []}
    zone = "main"
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line == "#main":
            zone = "main"
        elif line == "#extra":
            zone = "extra"
        elif line == "!side":
            zone = "side"
        elif line.isdigit():
            zones[zone].append(int(line))
    return zones


def load_decks() -> dict[str, dict[str, list[int]]]:
    return {path.stem: parse_ydk(path) for path in sorted(DECK_ROOT.glob("*.ydk"))}


def load_snapshot(snapshot_id: str) -> dict[str, object]:
    path = SNAPSHOT_ROOT / f"{snapshot_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Snapshot not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_banlist(path: Path) -> tuple[str, dict[int, int]]:
    name = ""
    limits: dict[int, int] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("!") and not name:
            name = line[1:].strip()
        match = re.match(r"^(\d+)\s+([0-3])\s+--", line)
        if match:
            limits[int(match.group(1))] = int(match.group(2))
    return name, limits


def binary_metrics(labels: list[bool], predictions: list[bool]) -> dict[str, float | int]:
    tp = sum(label and prediction for label, prediction in zip(labels, predictions))
    fp = sum(not label and prediction for label, prediction in zip(labels, predictions))
    fn = sum(label and not prediction for label, prediction in zip(labels, predictions))
    tn = sum(not label and not prediction for label, prediction in zip(labels, predictions))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(labels) if labels else 0.0
    return {
        "n": len(labels),
        "prevalence": round((tp + fn) / len(labels), 4) if labels else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def run_u1(cards: dict[int, dict[str, object]]) -> dict[str, object]:
    callback_patterns = {
        "count_limit_callback": re.compile(r"[:.]SetCountLimit\s*\("),
        "cost_callback": re.compile(r"[:.]SetCost\s*\("),
        "target_callback": re.compile(r"[:.]SetTarget\s*\("),
        "condition_callback": re.compile(r"[:.]SetCondition\s*\("),
    }
    lexical_patterns = {
        "count_limit_callback": re.compile(
            r"once per turn|you can only use (?:each|this) effect|you can only activate",
            re.IGNORECASE,
        ),
        "cost_callback": re.compile(
            r"discard|pay \d+ lp|banish .{0,60} from your|send .{0,60} to the gy|tribute",
            re.IGNORECASE,
        ),
        "target_callback": re.compile(r"\btarget\b", re.IGNORECASE),
        "condition_callback": re.compile(r"\bif\b|\bwhen\b|\bduring\b", re.IGNORECASE),
    }

    rows: list[dict[str, object]] = []
    for script_path in sorted(SCRIPT_ROOT.glob("c*.lua")):
        card_id_text = script_path.stem[1:]
        if not card_id_text.isdigit():
            continue
        card_id = int(card_id_text)
        card = cards.get(card_id)
        if not card or not card["desc"]:
            continue
        script = script_path.read_text(encoding="utf-8", errors="replace")
        description = str(card["desc"])
        row: dict[str, object] = {
            "card_id": card_id,
            "name": card["name"],
            "description": description,
        }
        for label_name, pattern in callback_patterns.items():
            row[f"label_{label_name}"] = bool(pattern.search(script))
            row[f"pred_{label_name}"] = bool(lexical_patterns[label_name].search(description))
        rows.append(row)

    metrics: dict[str, object] = {}
    disagreements: dict[str, object] = {}
    for label_name in callback_patterns:
        labels = [bool(row[f"label_{label_name}"]) for row in rows]
        predictions = [bool(row[f"pred_{label_name}"]) for row in rows]
        metrics[label_name] = binary_metrics(labels, predictions)
        false_positives = [
            row for row in rows if row[f"pred_{label_name}"] and not row[f"label_{label_name}"]
        ][:5]
        false_negatives = [
            row for row in rows if row[f"label_{label_name}"] and not row[f"pred_{label_name}"]
        ][:5]
        disagreements[label_name] = {
            "false_positives": [
                {"card_id": row["card_id"], "name": row["name"]} for row in false_positives
            ],
            "false_negatives": [
                {"card_id": row["card_id"], "name": row["name"]} for row in false_negatives
            ],
        }

    output_fields = ["card_id", "name"]
    for label_name in callback_patterns:
        output_fields.extend([f"label_{label_name}", f"pred_{label_name}"])
    with (RESULT_ROOT / "u1_text_script_proxy.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in output_fields})

    return {
        "experiment": "U1 text-to-script-callback lexical proxy",
        "records": len(rows),
        "metrics": metrics,
        "disagreement_examples": disagreements,
        "interpretation_limit": (
            "Lua callbacks are implementation structure, not direct semantic gold. In particular, "
            "SetTarget may be used by effects that do not use PSCT targeting."
        ),
    }


def validate_deck(
    zones: dict[str, list[int]],
    cards: dict[int, dict[str, object]],
    limits: dict[int, int],
    deck_rules: dict[str, dict[str, int]],
    card_pool_flag: int,
) -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    for zone, bounds in deck_rules.items():
        minimum, maximum = int(bounds["min"]), int(bounds["max"])
        size = len(zones[zone])
        if size < minimum or size > maximum:
            violations.append(
                {"type": f"{zone}_size", "zone": zone, "actual": size, "allowed": [minimum, maximum]}
            )

    combined = Counter(zones["main"] + zones["extra"] + zones["side"])
    for card_id, count in combined.items():
        if card_id not in cards:
            violations.append({"type": "missing_card_id", "card_id": card_id, "copies": count})
            continue
        if int(cards[card_id]["ot"]) & card_pool_flag == 0:
            violations.append(
                {
                    "type": "card_pool",
                    "card_id": card_id,
                    "name": cards[card_id]["name"],
                    "copies": count,
                    "cdb_ot": cards[card_id]["ot"],
                    "required_flag": card_pool_flag,
                }
            )
        allowed = limits.get(card_id, 3)
        if count > allowed:
            violations.append(
                {
                    "type": "copy_limit",
                    "card_id": card_id,
                    "name": cards.get(card_id, {}).get("name", ""),
                    "actual": count,
                    "allowed": allowed,
                }
            )
    return violations


def run_d1(
    decks: dict[str, dict[str, list[int]]],
    cards: dict[int, dict[str, object]],
    snapshot: dict[str, object],
    limits: dict[int, int],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    violation_counts: Counter[str] = Counter()
    for deck_name, zones in decks.items():
        violations = validate_deck(
            zones,
            cards,
            limits,
            snapshot["deck_rules"],
            int(snapshot["card_pool_flag"]),
        )
        violation_counts.update(str(item["type"]) for item in violations)
        rows.append(
            {
                "snapshot_id": snapshot["snapshot_id"],
                "regulation": snapshot["regulation"],
                "deck": deck_name,
                "main": len(zones["main"]),
                "extra": len(zones["extra"]),
                "side": len(zones["side"]),
                "valid": not violations,
                "violation_count": len(violations),
                "violations": json.dumps(violations, ensure_ascii=False),
            }
        )

    result = {
        "experiment": "D1 snapshot-specific deck legality audit",
        "snapshot_id": snapshot["snapshot_id"],
        "regulation": snapshot["regulation"],
        "banlist": snapshot["banlist"],
        "decks": len(rows),
        "valid_decks": sum(bool(row["valid"]) for row in rows),
        "invalid_decks": sum(not bool(row["valid"]) for row in rows),
        "violation_counts": dict(sorted(violation_counts.items())),
        "invalid_examples": [
            {"deck": row["deck"], "violations": json.loads(str(row["violations"]))}
            for row in rows
            if not row["valid"]
        ][:8],
        "interpretation_limit": (
            "The ygo-agent decks predate the selected snapshot, so invalidity measures regulation, "
            "card-pool, and temporal mismatch plus importer requirements, not deck-author quality."
        ),
    }
    return result, rows


def reciprocal_rank(ranking: list[int], target: int) -> float:
    try:
        return 1.0 / (ranking.index(target) + 1)
    except ValueError:
        return 0.0


def ranking_metrics(rows: list[dict[str, object]], baseline: str, retrievable_only: bool) -> dict[str, float | int]:
    selected = [row for row in rows if row["retrievable"] or not retrievable_only]
    ranks = [int(row[f"{baseline}_rank"]) for row in selected]
    if not ranks:
        return {"n": 0, "hit_at_1": 0.0, "hit_at_5": 0.0, "hit_at_10": 0.0, "mrr": 0.0}
    return {
        "n": len(ranks),
        "hit_at_1": round(sum(0 < rank <= 1 for rank in ranks) / len(ranks), 4),
        "hit_at_5": round(sum(0 < rank <= 5 for rank in ranks) / len(ranks), 4),
        "hit_at_10": round(sum(0 < rank <= 10 for rank in ranks) / len(ranks), 4),
        "mrr": round(sum(1.0 / rank if rank > 0 else 0.0 for rank in ranks) / len(ranks), 4),
    }


def run_d2(decks: dict[str, dict[str, list[int]]], cards: dict[int, dict[str, object]]) -> dict[str, object]:
    main_decks = {
        name: Counter(card_id for card_id in zones["main"] if card_id in cards)
        for name, zones in decks.items()
    }
    result_rows: list[dict[str, object]] = []

    for test_name, test_counts in main_decks.items():
        train = {name: counts for name, counts in main_decks.items() if name != test_name}
        popularity: Counter[int] = Counter()
        presence: Counter[int] = Counter()
        pair_counts: Counter[tuple[int, int]] = Counter()
        for counts in train.values():
            popularity.update(counts)
            card_set = sorted(counts)
            presence.update(card_set)
            for left in card_set:
                for right in card_set:
                    if left != right:
                        pair_counts[(left, right)] += 1
        candidates = set(popularity)

        for target, target_quantity in sorted(test_counts.items()):
            visible = test_counts.copy()
            del visible[target]
            visible_set = set(visible)
            eligible = [candidate for candidate in candidates if visible.get(candidate, 0) < 3]

            popularity_ranking = sorted(
                eligible,
                key=lambda candidate: (-popularity[candidate], candidate),
            )

            cooccurrence_scores: dict[int, float] = {}
            for candidate in eligible:
                score = 0.0
                for visible_card in visible_set:
                    denominator = presence[visible_card]
                    if denominator:
                        score += pair_counts[(candidate, visible_card)] / denominator
                score += 0.001 * math.log1p(popularity[candidate])
                cooccurrence_scores[candidate] = score
            cooccurrence_ranking = sorted(
                eligible,
                key=lambda candidate: (-cooccurrence_scores[candidate], -popularity[candidate], candidate),
            )

            nearest_name = ""
            nearest_score = -1.0
            for train_name, train_counts in train.items():
                train_set = set(train_counts)
                union = visible_set | train_set
                score = len(visible_set & train_set) / len(union) if union else 0.0
                if score > nearest_score or (score == nearest_score and train_name < nearest_name):
                    nearest_name = train_name
                    nearest_score = score
            nearest_counts = train[nearest_name]
            nearest_ranking = sorted(
                eligible,
                key=lambda candidate: (
                    -nearest_counts[candidate],
                    -popularity[candidate],
                    candidate,
                ),
            )

            rankings = {
                "popularity": popularity_ranking,
                "cooccurrence": cooccurrence_ranking,
                "nearest": nearest_ranking,
            }
            row: dict[str, object] = {
                "deck": test_name,
                "target_card_id": target,
                "target_name": cards[target]["name"],
                "target_quantity": target_quantity,
                "visible_unique_cards": len(visible_set),
                "retrievable": target in candidates,
                "nearest_deck": nearest_name,
                "nearest_jaccard": round(nearest_score, 4),
            }
            for baseline, ranking in rankings.items():
                rank = ranking.index(target) + 1 if target in ranking else 0
                row[f"{baseline}_rank"] = rank
                row[f"{baseline}_top10"] = "|".join(
                    str(cards[card_id]["name"]) for card_id in ranking[:10]
                )
            result_rows.append(row)

    fieldnames = list(result_rows[0])
    with (RESULT_ROOT / "d2_leave_one_deck_out.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result_rows)

    baselines = ["popularity", "cooccurrence", "nearest"]
    return {
        "experiment": "D2 leave-one-deck-out masked card-type completion",
        "decks": len(main_decks),
        "queries": len(result_rows),
        "retrievable_queries": sum(bool(row["retrievable"]) for row in result_rows),
        "train_candidate_coverage": round(
            sum(bool(row["retrievable"]) for row in result_rows) / len(result_rows), 4
        ),
        "metrics_all": {
            baseline: ranking_metrics(result_rows, baseline, retrievable_only=False)
            for baseline in baselines
        },
        "metrics_retrievable": {
            baseline: ranking_metrics(result_rows, baseline, retrievable_only=True)
            for baseline in baselines
        },
        "interpretation_limit": (
            "The 31 decks are a small engineering sample, not tournament data. Leave-one-deck-out "
            "candidate coverage quantifies how often a target card appears in any other deck."
        ),
    }


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def write_report(results: dict[str, object]) -> None:
    u1 = results["u1"]
    d1_by_snapshot = results["d1_by_snapshot"]
    d2 = results["d2"]
    d1_compatibility = results["d1_cross_snapshot_compatibility"]

    u1_rows = []
    for label_name, metrics in u1["metrics"].items():
        u1_rows.append(
            [
                label_name,
                metrics["prevalence"],
                metrics["precision"],
                metrics["recall"],
                metrics["f1"],
                metrics["accuracy"],
            ]
        )

    d2_rows = []
    for baseline, metrics in d2["metrics_all"].items():
        retrievable = d2["metrics_retrievable"][baseline]
        d2_rows.append(
            [
                baseline,
                metrics["hit_at_1"],
                metrics["hit_at_5"],
                metrics["mrr"],
                retrievable["hit_at_1"],
                retrievable["hit_at_5"],
                retrievable["mrr"],
            ]
        )

    d1_rows = [
        [
            item["snapshot_id"],
            item["regulation"],
            item["decks"],
            item["valid_decks"],
            item["invalid_decks"],
            json.dumps(item["violation_counts"], ensure_ascii=False),
        ]
        for item in d1_by_snapshot
    ]

    report = f"""# 本地可运行实验：首轮 Pilot 结果

运行时间：{results['generated_at']}

运行环境：Windows + CPU；本轮未下载模型权重，也未运行 ygopro engine。

## 结论

1. U1 的词法基线表现高度不均衡：count-limit 与 condition callback 可被表面措辞较好预测，cost 居中，target callback 的 recall 很低。单纯的 once-per-turn/if/when 识别可能过于简单，而 Lua callback 也不能直接当作完整语义 gold。
2. D1 现在按 TCG/OCG snapshot 分开审计。历史 ygo-agent 牌组在两个当前环境都存在明显的 regulation、card-pool 或时间错配，不能合并成一个“YGO 合法率”。
3. D2 的 leave-one-deck-out 训练候选覆盖率为 {d2['train_candidate_coverage']:.2%}。这意味着小牌组池中的大量主题卡在其他牌组从未出现，masked completion 首先受数据覆盖限制。
4. 当前本地 CPU pipeline 已经能复现数据加载、snapshot legality、leave-one-deck-out 和结构代理评分；下一步需要 WSL/engine 才能生成真正的 LegalSet、ResolveDelta 与策略 rollout 标签。

## U1：卡片文本到脚本 Callback 词法基线

样本：{u1['records']} 张同时具有英文文本和 official Lua script 的卡。

{markdown_table(['标签', '正例率', 'Precision', 'Recall', 'F1', 'Accuracy'], u1_rows)}

注意：`SetTarget` 是引擎 target callback，不等于 PSCT 中一定存在语义上的“取对象”；该实验用于评估自动标签可行性，不是最终 Card Understanding benchmark。

## D1：TCG/OCG 牌组合法性审计

{markdown_table(['Snapshot', 'Regulation', '牌组数', '通过', '未通过', '违规类型'], d1_rows)}

逐牌组兼容模式：`{json.dumps(d1_compatibility['patterns'], ensure_ascii=False)}`。这里的 `none` 表示牌组不通过任一所选 snapshot，环境名组合表示通过对应 snapshot。

这些牌组来自较早版本的 ygo-agent。结果测量的是 regulation/card-pool/temporal mismatch 和 importer 需求，而不是原作者构筑质量。BabelCDB 的 `datas.ot` 只提供聚合的 OCG/TCG availability bit；在 `card_pool_cutoff` 尚未固定时，它不能证明某张卡在历史赛事日期已经发售。

## D2：Leave-One-Deck-Out 卡片补全

- 牌组数：{d2['decks']}
- 查询数：{d2['queries']}
- 目标卡在其他牌组出现的查询：{d2['retrievable_queries']}
- 训练候选覆盖率：{d2['train_candidate_coverage']:.2%}

{markdown_table(['Baseline', 'All H@1', 'All H@5', 'All MRR', 'Seen H@1', 'Seen H@5', 'Seen MRR'], d2_rows)}

`All` 包含训练牌组中完全没出现过的目标卡；`Seen` 只评估候选池中出现过的目标。正式 DeckMeta 数据必须使用更大的同环境赛事牌组池，并按赛事和近重复牌组分组切分。

## 生成文件

- `results/local_pilot/metrics.json`
- `results/local_pilot/u1_text_script_proxy.csv`
- `results/local_pilot/d1_deck_legality.csv`
- `results/local_pilot/d2_leave_one_deck_out.csv`

## 下一步

1. 安装 WSL2/Ubuntu，跑 E0 双 bot 固定 seed 对局。
2. 从首条 trace 生成 20 个 decision points 和 10 个 counterfactual groups。
3. 分别收集至少 50 副同一 TCG snapshot 与 50 副同一 OCG snapshot 的 tournament decks，重跑 D1/D2，再加入本地 7B/14B 或 API LLM baseline。
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local YGO-Bench proxy pilots.")
    parser.add_argument(
        "--snapshot",
        action="append",
        dest="snapshot_ids",
        help="Snapshot ID to audit. Repeat for multiple snapshots; defaults to TCG and OCG v1.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    cards = load_cards()
    decks = load_decks()
    snapshot_ids = args.snapshot_ids or DEFAULT_SNAPSHOT_IDS
    snapshots = [load_snapshot(snapshot_id) for snapshot_id in snapshot_ids]
    d1_by_snapshot: list[dict[str, object]] = []
    d1_rows: list[dict[str, object]] = []
    for snapshot in snapshots:
        lflist_path = REPO_ROOT / snapshot["artifacts"]["lflist"]["path"]
        banlist_name, limits = load_banlist(lflist_path)
        if banlist_name != snapshot["banlist"]:
            raise ValueError(
                f"Banlist mismatch for {snapshot['snapshot_id']}: "
                f"snapshot={snapshot['banlist']!r}, file={banlist_name!r}"
            )
        d1_result, rows = run_d1(decks, cards, snapshot, limits)
        d1_by_snapshot.append(d1_result)
        d1_rows.extend(rows)

    deck_compatibility: dict[str, list[str]] = defaultdict(list)
    for row in d1_rows:
        if row["valid"]:
            deck_compatibility[str(row["deck"])].append(str(row["regulation"]))
        else:
            deck_compatibility.setdefault(str(row["deck"]), [])
    compatibility_patterns = Counter(
        "+".join(sorted(regulations)) if regulations else "none"
        for regulations in deck_compatibility.values()
    )

    with (RESULT_ROOT / "d1_deck_legality.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(d1_rows[0]))
        writer.writeheader()
        writer.writerows(d1_rows)

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": snapshots,
        "shared_artifacts": {
            "cdb": str(CDB_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "card_scripts": str(SCRIPT_ROOT.relative_to(REPO_ROOT)).replace("\\", "/"),
        },
        "u1": run_u1(cards),
        "d1_by_snapshot": d1_by_snapshot,
        "d1_cross_snapshot_compatibility": {
            "decks": len(deck_compatibility),
            "patterns": dict(sorted(compatibility_patterns.items())),
            "interpretation_limit": (
                "Compatibility is evaluated only against the selected current snapshots; it does not "
                "recover the historical snapshot under which each source deck was authored."
            ),
        },
        "d2": run_d2(decks, cards),
        "local_model": {
            "run": False,
            "reason": "No local Hugging Face, ModelScope, LM Studio, or D:/models weights were found.",
        },
    }
    (RESULT_ROOT / "metrics.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
