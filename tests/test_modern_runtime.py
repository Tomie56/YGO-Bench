from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np

from experiments.run_modern_runtime_gate import (
    compare_traces,
    observation_hash,
    runtime_state_hash,
    validate_dynamic_hidden_information,
    validate_hidden_information_coverage,
    validate_legal_action_selection,
    validate_reset_hidden_information,
    validate_reset_output,
    validate_step_output,
)
from scripts.patch_edopro_adapter import (
    BLOCK_REPLACEMENTS,
    REPLACEMENTS,
    apply_replacements,
)
from ygo_bench.runtime.modern import ModernRuntime


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "runtime-modern-v1-2026-07-20.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModernRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.snapshot = json.loads(
            (ROOT / cls.config["runtime_snapshot"]).read_text(encoding="utf-8")
        )
        cls.manifest = json.loads(
            (ROOT / cls.config["asset_manifest"]).read_text(encoding="utf-8")
        )

    def test_runtime_identifiers_match(self) -> None:
        expected = self.config["runtime_snapshot_id"]
        self.assertEqual(self.snapshot["runtime_snapshot_id"], expected)
        self.assertEqual(self.manifest["runtime_snapshot_id"], expected)
        self.assertEqual(
            self.snapshot["compatibility"]["card_data_loading"],
            "full_babelcdb_at_init",
        )

    def test_tcg_and_ocg_profiles_are_separate(self) -> None:
        profiles = self.config["environments"]
        self.assertEqual(set(profiles), {"tcg", "ocg"})
        self.assertNotEqual(
            profiles["tcg"]["snapshot_id"], profiles["ocg"]["snapshot_id"]
        )
        for name, profile in profiles.items():
            spec = profile["spec"]
            self.assertEqual(spec["deck1"], spec["deck2"])
            self.assertTrue(spec["deck1"].startswith(f"{name}_"))
            self.assertIn(spec["deck1"], self.config["decks"])

    def test_throughput_overrides_are_explicit_and_cardinality_safe(self) -> None:
        runtime = ModernRuntime(CONFIG_PATH)
        spec = runtime.environment_spec(
            "tcg",
            {"num_envs": 16, "batch_size": 16, "num_threads": 16},
        )
        self.assertEqual(spec["num_envs"], 16)
        self.assertEqual(runtime.profile("tcg")["spec"]["num_envs"], 1)
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            runtime.environment_spec("tcg", {"silent_fallback": 1})
        with self.assertRaisesRegex(ValueError, "num_envs and batch_size"):
            runtime.environment_spec("tcg", {"num_envs": 2})

    def test_code_list_matches_manifest(self) -> None:
        record = self.manifest["code_list"]
        path = ROOT / record["path"]
        codes = [int(line) for line in path.read_text(encoding="ascii").splitlines()]
        self.assertEqual(len(codes), record["card_count"])
        self.assertEqual(codes, sorted(set(codes)))
        self.assertGreater(codes[0], 0)
        self.assertLessEqual(len(codes), 65535)
        self.assertEqual(sha256_file(path), record["sha256"])

    def test_deck_hashes_and_effective_scripts(self) -> None:
        records = {record["name"]: record for record in self.manifest["decks"]}
        self.assertEqual(set(records), set(self.config["decks"]))
        for name, relative_path in self.config["decks"].items():
            record = records[name]
            self.assertEqual(sha256_file(ROOT / relative_path), record["sha256"])
            self.assertEqual(record["missing_script_card_ids"], [])

    def test_cardscript_dependency_closure(self) -> None:
        audit = self.manifest["cardscripts"]["dependency_audit"]
        self.assertGreater(audit["entrypoint_count"], 2)
        self.assertGreaterEqual(
            audit["resolved_script_count"], audit["entrypoint_count"]
        )
        self.assertEqual(
            audit["special_layout_routes"]["proc_unofficial.lua"],
            "unofficial/proc_unofficial.lua",
        )
        resolved = {
            item["request"]: item["path"] for item in audit["resolved_scripts"]
        }
        self.assertEqual(
            resolved["proc_unofficial.lua"], "unofficial/proc_unofficial.lua"
        )

    def test_adapter_transform_matches_frozen_source_once(self) -> None:
        source = (
            ROOT / "references/ygo-agent/ygoenv/ygoenv/edopro/edopro.h"
        ).read_text(encoding="utf-8")
        patched = apply_replacements(source)
        self.assertEqual(len(REPLACEMENTS) + len(BLOCK_REPLACEMENTS), 33)
        self.assertIn("const std::string &script_dir", patched)
        self.assertIn('scripts_dir_ / "official" / path', patched)
        self.assertIn('scripts_dir_ / "unofficial" / path', patched)
        self.assertIn("preload_all_cards(db, all_codes);", patched)
        self.assertIn("pduel_{nullptr}", patched)
        self.assertIn("OCG_DuelOptions opts{};", patched)
        self.assertIn("Failed to create duel, status=", patched)
        self.assertIn("Card metadata missing for code:", patched)
        self.assertIn("Observation card ID missing for code:", patched)
        self.assertIn("Main deck not initialized:", patched)
        self.assertIn("parse_query_record", patched)
        self.assertIn("Location query size header does not match buffer", patched)
        self.assertIn('if (path == "c0.lua")', patched)
        self.assertIn("normal_monster || (type & TYPE_TOKEN)", patched)
        self.assertIn("selectable_specs", patched)
        self.assertIn("selectable_own_deck_card", patched)
        self.assertIn("!confirmed_visible && !selectable_own_deck_card", patched)
        self.assertIn('"info:card_visibility_"_.Bind', patched)
        self.assertIn("opponent && hidden_for_opponent && revealed_.empty()", patched)
        self.assertIn("f_visibility(offset) = kHiddenPrivate", patched)
        self.assertIn("visibility = kConfirmedReveal", patched)
        self.assertIn("fclose(fp_);\n        fp_ = nullptr;", patched)
        with self.assertRaises(RuntimeError):
            apply_replacements(patched)

    def test_build_uses_stable_gcc_12_optimization_profile(self) -> None:
        build_script = (ROOT / "scripts/build_edopro_ygoenv.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("-std=c++17 -O2 -DNDEBUG -march=native", build_script)
        self.assertIn('CXX="${CXX:-g++-12}"', build_script)
        self.assertIn("modern runtime builds require GCC 12.x", build_script)
        self.assertNotIn("-O3", build_script)
        self.assertNotIn("-flto", build_script)
        self.assertIn('"${COMPILE_FLAGS[@]}" -c "$source"', build_script)
        self.assertIn('"$CXX" -shared "${OBJECTS[@]}"', build_script)

    def test_reset_output_validation(self) -> None:
        spec = self.config["environments"]["tcg"]["spec"]
        action_features = 10 + 2 * spec["max_multi_select"]
        observation = {
            "cards_": np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8),
            "global_": np.zeros((1, 9), dtype=np.uint8),
            "actions_": np.zeros(
                (1, spec["max_options"], action_features), dtype=np.uint8
            ),
            "h_actions_": np.zeros(
                (1, spec["n_history_actions"], action_features), dtype=np.uint8
            ),
        }
        observation["cards_"][0, 0, 2] = 1
        observation["cards_"][0, 1, 1] = 1
        observation["cards_"][0, 1, 2] = 2
        observation["cards_"][0, spec["max_cards"], 2] = 1
        observation["cards_"][0, spec["max_cards"], 4] = 1
        infos = {
            "num_options": np.array([2], dtype=np.int32),
            "to_play": np.array([0], dtype=np.int32),
            "is_selfplay": np.array([0], dtype=np.int32),
            "win_reason": np.array([0], dtype=np.int32),
        }
        metrics = validate_reset_output(observation, infos, spec, 14605)
        self.assertEqual(metrics["num_options"], 2)
        self.assertEqual(metrics["visible_card_rows"], 1)
        self.assertEqual(metrics["maximum_visible_card_id"], 1)
        self.assertTrue(
            metrics["hidden_information_reset"]["hidden_information_pass"]
        )

    def test_reset_output_rejects_unknown_card_id(self) -> None:
        spec = self.config["environments"]["ocg"]["spec"]
        action_features = 10 + 2 * spec["max_multi_select"]
        observation = {
            "cards_": np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8),
            "global_": np.zeros((1, 9), dtype=np.uint8),
            "actions_": np.zeros(
                (1, spec["max_options"], action_features), dtype=np.uint8
            ),
            "h_actions_": np.zeros(
                (1, spec["n_history_actions"], action_features), dtype=np.uint8
            ),
        }
        observation["cards_"][0, 0, 0] = 255
        observation["cards_"][0, 0, 1] = 255
        infos = {
            "num_options": np.array([1], dtype=np.int32),
            "to_play": np.array([1], dtype=np.int32),
            "is_selfplay": np.array([0], dtype=np.int32),
            "win_reason": np.array([0], dtype=np.int32),
        }
        with self.assertRaisesRegex(ValueError, "outside the frozen code list"):
            validate_reset_output(observation, infos, spec, 14605)

    def test_step_output_validation(self) -> None:
        spec = self.config["environments"]["tcg"]["spec"]
        action_features = 10 + 2 * spec["max_multi_select"]
        observation = {
            "cards_": np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8),
            "global_": np.zeros((1, 9), dtype=np.uint8),
            "actions_": np.zeros(
                (1, spec["max_options"], action_features), dtype=np.uint8
            ),
            "h_actions_": np.zeros(
                (1, spec["n_history_actions"], action_features), dtype=np.uint8
            ),
        }
        infos = {
            "num_options": np.array([3], dtype=np.int32),
            "to_play": np.array([1], dtype=np.int32),
            "is_selfplay": np.array([0], dtype=np.int32),
            "win_reason": np.array([0], dtype=np.int32),
        }
        metrics = validate_step_output(
            observation,
            np.array([0.0], dtype=np.float32),
            np.array([False]),
            np.array([False]),
            infos,
            spec,
            14605,
        )
        self.assertEqual(metrics["num_options"], 3)
        self.assertEqual(metrics["reward"], 0.0)
        self.assertFalse(metrics["terminated"])
        self.assertFalse(metrics["truncated"])

    def test_step_output_rejects_non_finite_reward(self) -> None:
        spec = self.config["environments"]["ocg"]["spec"]
        action_features = 10 + 2 * spec["max_multi_select"]
        observation = {
            "cards_": np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8),
            "global_": np.zeros((1, 9), dtype=np.uint8),
            "actions_": np.zeros(
                (1, spec["max_options"], action_features), dtype=np.uint8
            ),
            "h_actions_": np.zeros(
                (1, spec["n_history_actions"], action_features), dtype=np.uint8
            ),
        }
        infos = {
            "num_options": np.array([1], dtype=np.int32),
            "to_play": np.array([0], dtype=np.int32),
            "is_selfplay": np.array([0], dtype=np.int32),
            "win_reason": np.array([0], dtype=np.int32),
        }
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_step_output(
                observation,
                np.array([np.nan], dtype=np.float32),
                np.array([False]),
                np.array([False]),
                infos,
                spec,
                14605,
            )

    def test_legal_action_selection_and_state_hash(self) -> None:
        spec = self.config["environments"]["tcg"]["spec"]
        action_features = 10 + 2 * spec["max_multi_select"]
        actions = np.zeros(
            (1, spec["max_options"], action_features), dtype=np.uint8
        )
        actions[0, 0, -1] = 3
        observation = {"actions_": actions}
        infos = {"num_options": np.array([2], dtype=np.int32)}
        metrics = validate_legal_action_selection(
            observation,
            infos,
            np.array([0], dtype=np.int32),
            spec,
        )
        self.assertTrue(metrics["legal_action_verified"])
        self.assertEqual(metrics["pre_num_options"], [2])
        first_hash = observation_hash(observation)
        observation["actions_"][0, 0, -1] = 4
        self.assertNotEqual(observation_hash(observation), first_hash)

    def test_runtime_state_hash_includes_visibility_and_info(self) -> None:
        observation = {"cards_": np.zeros((1, 2, 40), dtype=np.uint8)}
        infos = {
            "card_visibility_": np.zeros((1, 2), dtype=np.uint8),
            "num_options": np.array([1], dtype=np.int32),
            "to_play": np.array([0], dtype=np.int32),
            "is_selfplay": np.array([0], dtype=np.int32),
            "win_reason": np.array([0], dtype=np.int32),
        }
        first_hash = runtime_state_hash(observation, infos)
        infos["card_visibility_"][0, 0] = 1
        self.assertNotEqual(runtime_state_hash(observation, infos), first_hash)

    def test_legal_action_selection_rejects_out_of_range_index(self) -> None:
        spec = self.config["environments"]["ocg"]["spec"]
        action_features = 10 + 2 * spec["max_multi_select"]
        observation = {
            "actions_": np.ones(
                (1, spec["max_options"], action_features), dtype=np.uint8
            )
        }
        infos = {"num_options": np.array([1], dtype=np.int32)}
        with self.assertRaisesRegex(ValueError, "outside 1 legal options"):
            validate_legal_action_selection(
                observation,
                infos,
                np.array([1], dtype=np.int32),
                spec,
            )

    def test_hidden_information_validation(self) -> None:
        spec = self.config["environments"]["tcg"]["spec"]
        cards = np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8)
        cards[0, 0, 2] = 1
        cards[0, 1, :3] = (0, 1, 2)
        opponent_offset = spec["max_cards"]
        cards[0, opponent_offset, 2] = 1
        cards[0, opponent_offset, 4] = 1
        observation = {"cards_": cards}
        metrics = validate_reset_hidden_information(observation, spec)
        self.assertTrue(metrics["hidden_information_pass"])
        self.assertEqual(metrics["own_deck_rows"], 1)
        self.assertEqual(metrics["opponent_private_rows"], 1)

    def test_hidden_information_rejects_own_deck_identity(self) -> None:
        spec = self.config["environments"]["ocg"]["spec"]
        cards = np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8)
        cards[0, 0, :3] = (0, 9, 1)
        cards[0, 1, :3] = (0, 1, 2)
        opponent_offset = spec["max_cards"]
        cards[0, opponent_offset, 2] = 2
        cards[0, opponent_offset, 4] = 1
        with self.assertRaisesRegex(ValueError, "own_deck_identity_leaks"):
            validate_reset_hidden_information({"cards_": cards}, spec)

    def test_dynamic_hidden_information_uses_visibility_provenance(self) -> None:
        spec = self.config["environments"]["tcg"]["spec"]
        codes = {
            "padding": 0,
            "hidden_private": 1,
            "owner_visible": 2,
            "public_field": 3,
            "confirmed_reveal": 4,
            "selectable_own_deck": 5,
            "opponent_facedown": 6,
        }
        cards = np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8)
        visibility = np.zeros((1, spec["max_cards"] * 2), dtype=np.uint8)
        cards[0, 0, 2] = 1
        visibility[0, 0] = codes["hidden_private"]
        cards[0, 1, :3] = (0, 1, 2)
        visibility[0, 1] = codes["owner_visible"]
        opponent = spec["max_cards"]
        cards[0, opponent, 2] = 1
        cards[0, opponent, 4] = 1
        visibility[0, opponent] = codes["hidden_private"]
        cards[0, opponent + 1, :3] = (0, 2, 2)
        cards[0, opponent + 1, 4] = 1
        visibility[0, opponent + 1] = codes["confirmed_reveal"]
        cards[0, opponent + 2, 2] = 4
        cards[0, opponent + 2, 4] = 1
        cards[0, opponent + 2, 5] = 2
        visibility[0, opponent + 2] = codes["opponent_facedown"]
        metrics = validate_dynamic_hidden_information(
            {"cards_": cards},
            {"card_visibility_": visibility},
            spec,
            codes,
        )
        self.assertEqual(metrics["confirmed_reveal_rows"], 1)
        self.assertEqual(metrics["hidden_rows"], 3)
        self.assertTrue(metrics["hidden_information_pass"])

    def test_dynamic_hidden_information_rejects_unproven_private_id(self) -> None:
        spec = self.config["environments"]["ocg"]["spec"]
        codes = {
            "padding": 0,
            "hidden_private": 1,
            "owner_visible": 2,
            "public_field": 3,
            "confirmed_reveal": 4,
            "selectable_own_deck": 5,
            "opponent_facedown": 6,
        }
        cards = np.zeros((1, spec["max_cards"] * 2, 40), dtype=np.uint8)
        visibility = np.zeros((1, spec["max_cards"] * 2), dtype=np.uint8)
        opponent = spec["max_cards"]
        cards[0, opponent, :3] = (0, 7, 2)
        cards[0, opponent, 4] = 1
        visibility[0, opponent] = codes["hidden_private"]
        with self.assertRaisesRegex(ValueError, "hidden_identity_leaks"):
            validate_dynamic_hidden_information(
                {"cards_": cards},
                {"card_visibility_": visibility},
                spec,
                codes,
            )

    def test_hidden_information_coverage_is_explicit(self) -> None:
        gate_spec = {
            "minimum_steps_audited": 10,
            "minimum_private_rows": 100,
            "minimum_confirmed_reveal_rows": 1,
        }
        with self.assertRaisesRegex(ValueError, "coverage is insufficient"):
            validate_hidden_information_coverage(
                {"states_audited": 10, "private_rows": 100}, gate_spec
            )
        result = validate_hidden_information_coverage(
            {
                "states_audited": 10,
                "private_rows": 100,
                "confirmed_reveal_rows": 1,
            },
            gate_spec,
        )
        self.assertTrue(result["coverage_pass"])

    def test_trace_comparison_requires_actions_hashes_and_terminal_flags(self) -> None:
        trace = {
            "actions": [[0], [1]],
            "pre_observation_hashes": ["a", "b"],
            "post_observation_hashes": ["b", "c"],
            "done": [[False], [True]],
        }
        result = compare_traces(trace, dict(trace))
        self.assertTrue(result["all_state_hashes_match"])
        changed = dict(trace)
        changed["post_observation_hashes"] = ["b", "d"]
        with self.assertRaisesRegex(ValueError, "state hashes"):
            compare_traces(trace, changed)


if __name__ == "__main__":
    unittest.main()
