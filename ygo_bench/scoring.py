from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from ygo_bench.contracts import SCHEMA_VERSION, validate_document


SCORER_VERSION = "0.1.0"
SEMANTIC_FIELDS = (
    "activation_condition",
    "cost",
    "target",
    "once_per_turn_scope",
    "resolution_operation",
    "restriction",
)


def canonical_item(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def set_metrics(target: list[Any], answer: list[Any]) -> dict[str, float]:
    target_set = {canonical_item(item) for item in target}
    answer_set = {canonical_item(item) for item in answer}
    overlap = len(target_set & answer_set)
    precision = overlap / len(answer_set) if answer_set else float(not target_set)
    recall = overlap / len(target_set) if target_set else float(not answer_set)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "set_precision": precision,
        "set_recall": recall,
        "set_f1": f1,
        "exact_set": float(target_set == answer_set),
    }


def score_exact(target: dict[str, Any], answer: dict[str, Any]) -> dict[str, float]:
    return {"exact_accuracy": float(target == answer)}


def score_set(target: dict[str, Any], answer: dict[str, Any]) -> dict[str, float]:
    if not isinstance(target.get("items"), list):
        raise ValueError("Set scorer target must contain an items array")
    if not isinstance(answer.get("items"), list):
        raise ValueError("Set scorer answer must contain an items array")
    return set_metrics(target["items"], answer["items"])


def field_score(target: Any, answer: Any) -> float:
    if isinstance(target, list) and isinstance(answer, list):
        return set_metrics(target, answer)["set_f1"]
    return float(target == answer)


def score_semantic_fields(
    target: dict[str, Any],
    answer: dict[str, Any],
) -> dict[str, float]:
    missing = [field for field in SEMANTIC_FIELDS if field not in target]
    if missing:
        raise ValueError(f"Semantic target is missing fields: {missing}")
    scores = {
        f"field_f1:{field}": field_score(target[field], answer.get(field))
        for field in SEMANTIC_FIELDS
    }
    scores["field_macro_f1"] = sum(scores.values()) / len(SEMANTIC_FIELDS)
    return scores


def score_ranking(target: dict[str, Any], answer: dict[str, Any]) -> dict[str, float]:
    acceptable = target.get("acceptable_items")
    ranked = answer.get("ranked_items")
    if not isinstance(acceptable, list) or not acceptable:
        raise ValueError("Ranking target must contain non-empty acceptable_items")
    if not isinstance(ranked, list):
        raise ValueError("Ranking answer must contain ranked_items")
    acceptable_set = {canonical_item(item) for item in acceptable}
    ranked_keys = [canonical_item(item) for item in ranked]
    first_rank = next(
        (index for index, item in enumerate(ranked_keys, start=1) if item in acceptable_set),
        None,
    )
    top_five = set(ranked_keys[:5])
    return {
        "recall_at_5": len(acceptable_set & top_five) / len(acceptable_set),
        "mrr": 1.0 / first_rank if first_rank is not None else 0.0,
        "candidate_coverage": float(bool(acceptable_set & set(ranked_keys))),
    }


@dataclass(frozen=True)
class Scorer:
    function: Callable[[dict[str, Any], dict[str, Any]], dict[str, float]]
    primary_metric: str


SCORERS = {
    "exact": Scorer(score_exact, "exact_accuracy"),
    "set": Scorer(score_set, "set_f1"),
    "semantic_fields": Scorer(score_semantic_fields, "field_macro_f1"),
    "ranking": Scorer(score_ranking, "mrr"),
}

TASK_SCORERS = {
    "CardSemantics": "semantic_fields",
    "RuleAndTiming": "exact",
    "CardPoolGrounding": "exact",
    "LegalSet": "set",
    "ResolveDelta": "exact",
    "CounterfactualRule": "exact",
    "LegalityAudit": "set",
    "MaskedCompletion": "ranking",
}


def scorer_config_sha256(name: str) -> str:
    payload = json.dumps(
        {"name": name, "version": SCORER_VERSION},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def score_record(
    record: dict[str, Any],
    output: dict[str, Any],
    scorer_name: str | None = None,
) -> dict[str, Any]:
    validate_document("benchmark-record", record)
    validate_document("model-output", output)
    if record["record_id"] != output["record_id"]:
        raise ValueError("Benchmark record and model output IDs do not match")

    if output["status"] != "ok":
        result = {
            "schema_version": SCHEMA_VERSION,
            "evaluation_id": f"{output['run_id']}:{record['record_id']}:unscorable",
            "run_id": output["run_id"],
            "record_id": record["record_id"],
            "status": "unscorable",
            "scorer": {
                "name": "unscorable",
                "version": SCORER_VERSION,
                "config_sha256": scorer_config_sha256("unscorable"),
            },
            "metrics": {},
            "errors": [output["status"]],
            "attribution": {
                "invalid_action": False,
                "parser_error": output["status"] == "parser_error",
                "retry_count": output["audit"]["retry_count"],
                "repair_count": output["audit"]["repair_count"],
                "fallback_used": output["audit"]["fallback_used"],
            },
        }
        validate_document("evaluation-result", result)
        return result

    selected_name = scorer_name or TASK_SCORERS.get(record["task"])
    if selected_name is None:
        raise ValueError(f"No deterministic scorer registered for task {record['task']}")
    try:
        scorer = SCORERS[selected_name]
    except KeyError as error:
        raise ValueError(f"Unknown scorer: {selected_name}") from error
    metrics = scorer.function(record["target"], output["answer"])
    primary_value = metrics[scorer.primary_metric]
    result = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": (
            f"{output['run_id']}:{record['record_id']}:{selected_name}:{SCORER_VERSION}"
        ),
        "run_id": output["run_id"],
        "record_id": record["record_id"],
        "status": "scored",
        "scorer": {
            "name": selected_name,
            "version": SCORER_VERSION,
            "config_sha256": scorer_config_sha256(selected_name),
        },
        "primary": {
            "name": scorer.primary_metric,
            "value": primary_value,
            "minimum": 0.0,
            "maximum": 1.0,
            "higher_is_better": True,
        },
        "metrics": metrics,
        "errors": [],
        "attribution": {
            "invalid_action": False,
            "parser_error": False,
            "retry_count": output["audit"]["retry_count"],
            "repair_count": output["audit"]["repair_count"],
            "fallback_used": output["audit"]["fallback_used"],
        },
        "cost": {
            "latency_ms": output["latency_ms"],
            "input_tokens": output["usage"]["input_tokens"],
            "output_tokens": output["usage"]["output_tokens"],
            "currency": None,
            "amount": None,
        },
    }
    validate_document("evaluation-result", result)
    return result
