from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ygo_bench.contracts import (
    ContractValidationError,
    SCHEMA_PATHS,
    load_schema,
    validate_document,
    validate_path,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "schemas" / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class ContractTest(unittest.TestCase):
    def test_schemas_and_examples_are_valid(self) -> None:
        examples = {
            "benchmark-record": "benchmark-record.json",
            "model-output": "model-output.json",
            "evaluation-result": "evaluation-result.json",
            "understanding-annotation": "understanding-annotation.json",
        }
        for kind, filename in examples.items():
            self.assertEqual(load_schema(kind)["$schema"].split("/")[-2], "2020-12")
            self.assertEqual(validate_path(kind, EXAMPLES / filename), 1)

    def test_unknown_contract_kind_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown contract kind"):
            load_schema("unknown")

    def test_schema_can_validate_many_records_in_one_process(self) -> None:
        record = load_example("understanding-annotation.json")
        for _ in range(50):
            validate_document("understanding-annotation", record)

    def test_layer_and_task_must_match(self) -> None:
        record = load_example("benchmark-record.json")
        record["layer"] = "deck"
        with self.assertRaisesRegex(ContractValidationError, "task"):
            validate_document("benchmark-record", record)

    def test_model_revision_is_required(self) -> None:
        output = load_example("model-output.json")
        del output["model"]["revision"]
        with self.assertRaisesRegex(ContractValidationError, "revision"):
            validate_document("model-output", output)

    def test_failure_output_requires_error(self) -> None:
        output = load_example("model-output.json")
        output["status"] = "timeout"
        output.pop("answer")
        output.pop("error")
        with self.assertRaisesRegex(ContractValidationError, "error"):
            validate_document("model-output", output)

    def test_scored_result_requires_primary_metric(self) -> None:
        result = load_example("evaluation-result.json")
        del result["primary"]
        with self.assertRaisesRegex(ContractValidationError, "primary"):
            validate_document("evaluation-result", result)

    def test_unknown_fields_fail_instead_of_being_ignored(self) -> None:
        output = copy.deepcopy(load_example("model-output.json"))
        output["silent_fallback"] = True
        with self.assertRaisesRegex(ContractValidationError, "silent_fallback"):
            validate_document("model-output", output)

    def test_all_contract_files_exist(self) -> None:
        self.assertEqual(
            set(SCHEMA_PATHS),
            {
                "benchmark-record",
                "environment-snapshot",
                "fixed-scenario",
                "model-output",
                "evaluation-result",
                "runtime-gate-protocol",
                "runtime-snapshot",
                "understanding-annotation",
            },
        )
        self.assertTrue(all(path.is_file() for path in SCHEMA_PATHS.values()))

    def test_frozen_snapshots_and_scenarios_match_contracts(self) -> None:
        validate_path(
            "runtime-snapshot",
            ROOT / "snapshots" / "runtime-modern-v1-2026-07-20.json",
        )
        validate_path(
            "runtime-gate-protocol",
            ROOT / "configs" / "runtime-modern-gates-v0.1.json",
        )
        for snapshot_id in ("tcg-kde-e-2026-05-18", "ocg-jp-2026-07-01"):
            validate_path(
                "environment-snapshot",
                ROOT / "snapshots" / f"{snapshot_id}.json",
            )
            validate_path(
                "fixed-scenario",
                ROOT / "data" / "fixed_snapshots" / snapshot_id / "scenarios.json",
            )


if __name__ == "__main__":
    unittest.main()
