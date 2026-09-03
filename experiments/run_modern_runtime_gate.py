from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ygo_bench.contracts import validate_path
from ygo_bench.runtime.modern import DEFAULT_CONFIG, ModernRuntime


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATE_PROTOCOL = ROOT / "configs" / "runtime-modern-gates-v0.1.json"
FOLLOWUP_STAGES = {
    "step",
    "hidden_information",
    "trace_replay",
    "lifecycle",
    "throughput",
    "random_eval",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def observation_hash(observation: dict[str, Any]) -> str:
    import numpy as np

    digest = hashlib.sha256()
    for name in sorted(observation):
        value = np.ascontiguousarray(observation[name])
        digest.update(name.encode("ascii"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()


def runtime_state_hash(
    observation: dict[str, Any],
    infos: dict[str, Any],
) -> str:
    import numpy as np

    digest = hashlib.sha256()
    digest.update(observation_hash(observation).encode("ascii"))
    for name in (
        "card_visibility_",
        "num_options",
        "to_play",
        "is_selfplay",
        "win_reason",
    ):
        if name not in infos:
            raise ValueError(f"Runtime state hash is missing info field: {name}")
        value = np.ascontiguousarray(infos[name])
        digest.update(name.encode("ascii"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()


def git_value(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True
    ).strip()


def validate_reset_output(
    observation: dict[str, Any],
    infos: dict[str, Any],
    environment_spec: dict[str, Any],
    card_count: int,
) -> dict[str, Any]:
    import numpy as np

    observation_metrics = validate_observation_output(
        observation,
        environment_spec,
        card_count,
    )
    info_metrics = validate_info_output(
        infos,
        environment_spec,
        minimum_options=1,
    )
    hidden_information = validate_reset_hidden_information(
        observation,
        environment_spec,
    )
    return {
        **observation_metrics,
        **info_metrics,
        "hidden_information_reset": hidden_information,
    }


def validate_observation_output(
    observation: dict[str, Any],
    environment_spec: dict[str, Any],
    card_count: int,
) -> dict[str, Any]:
    import numpy as np

    batch_size = environment_spec["batch_size"]
    action_features = 10 + 2 * environment_spec["max_multi_select"]
    expected = {
        "cards_": (batch_size, environment_spec["max_cards"] * 2, 40),
        "global_": (batch_size, 9),
        "actions_": (batch_size, environment_spec["max_options"], action_features),
        "h_actions_": (
            batch_size,
            environment_spec["n_history_actions"],
            action_features,
        ),
    }
    if set(observation) != set(expected):
        raise ValueError(
            f"Unexpected observation keys: {sorted(observation)}; "
            f"expected {sorted(expected)}"
        )

    observation_shapes = {}
    observation_dtypes = {}
    for name, expected_shape in expected.items():
        value = np.asarray(observation[name])
        if value.shape != expected_shape:
            raise ValueError(
                f"Observation '{name}' has shape {value.shape}; "
                f"expected {expected_shape}"
            )
        if value.dtype != np.uint8:
            raise ValueError(
                f"Observation '{name}' has dtype {value.dtype}; expected uint8"
            )
        observation_shapes[name] = list(value.shape)
        observation_dtypes[name] = str(value.dtype)

    cards = np.asarray(observation["cards_"], dtype=np.uint16)
    card_ids = (cards[..., 0] << 8) + cards[..., 1]
    visible_card_ids = card_ids[card_ids != 0]
    if visible_card_ids.size and int(visible_card_ids.max()) > card_count:
        raise ValueError(
            "Observation contains a card ID outside the frozen code list: "
            f"{int(visible_card_ids.max())} > {card_count}"
        )

    return {
        "observation_shapes": observation_shapes,
        "observation_dtypes": observation_dtypes,
        "visible_card_rows": int(visible_card_ids.size),
        "maximum_visible_card_id": (
            int(visible_card_ids.max()) if visible_card_ids.size else 0
        ),
    }


def validate_info_output(
    infos: dict[str, Any],
    environment_spec: dict[str, Any],
    minimum_options: int,
) -> dict[str, Any]:
    import numpy as np

    batch_size = environment_spec["batch_size"]
    required_info = {"num_options", "to_play", "is_selfplay", "win_reason"}
    missing_info = sorted(required_info.difference(infos))
    if missing_info:
        raise ValueError(f"Reset info is missing required fields: {missing_info}")

    def scalar_info(name: str) -> int:
        value = np.asarray(infos[name])
        if value.shape != (batch_size,):
            raise ValueError(
                f"Reset info '{name}' has shape {value.shape}; "
                f"expected {(batch_size,)}"
            )
        return int(value[0])

    num_options = scalar_info("num_options")
    if not minimum_options <= num_options <= environment_spec["max_options"]:
        raise ValueError(f"Runtime returned invalid num_options: {num_options}")
    to_play = scalar_info("to_play")
    if to_play not in (0, 1):
        raise ValueError(f"Reset returned invalid to_play: {to_play}")
    is_selfplay = scalar_info("is_selfplay")
    if is_selfplay not in (0, 1):
        raise ValueError(f"Reset returned invalid is_selfplay: {is_selfplay}")

    return {
        "info_keys": sorted(infos),
        "num_options": num_options,
        "to_play": to_play,
        "is_selfplay": is_selfplay,
    }


def validate_reset_hidden_information(
    observation: dict[str, Any],
    environment_spec: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    cards = np.asarray(observation["cards_"], dtype=np.uint16)
    batch_size = environment_spec["batch_size"]
    max_cards = environment_spec["max_cards"]
    if cards.shape[:2] != (batch_size, max_cards * 2):
        raise ValueError(
            f"Reset hidden-information audit received cards shape {cards.shape}; "
            f"expected first dimensions {(batch_size, max_cards * 2)}"
        )

    totals = {
        "own_deck_rows": 0,
        "own_deck_identity_leaks": 0,
        "own_deck_detail_leaks": 0,
        "opponent_private_rows": 0,
        "opponent_private_identity_leaks": 0,
        "opponent_private_detail_leaks": 0,
        "opponent_private_sequence_leaks": 0,
        "opponent_facedown_rows": 0,
        "opponent_facedown_identity_leaks": 0,
        "opponent_facedown_detail_leaks": 0,
        "own_hand_rows": 0,
        "own_hand_identity_missing": 0,
    }
    private_locations = {1, 2, 7}
    field_locations = {3, 4}
    facedown_positions = {2, 6, 7}
    for batch_index in range(batch_size):
        own = cards[batch_index, :max_cards]
        opponent = cards[batch_index, max_cards:]

        own_deck = own[own[:, 2] == 1]
        totals["own_deck_rows"] += len(own_deck)
        totals["own_deck_identity_leaks"] += int(
            np.count_nonzero(own_deck[:, :2])
        )
        totals["own_deck_detail_leaks"] += int(
            np.count_nonzero(own_deck[:, 7:])
        )

        own_hand = own[own[:, 2] == 2]
        own_hand_ids = (own_hand[:, 0] << 8) + own_hand[:, 1]
        totals["own_hand_rows"] += len(own_hand)
        totals["own_hand_identity_missing"] += int(
            np.count_nonzero(own_hand_ids == 0)
        )

        opponent_private = opponent[
            np.isin(opponent[:, 2], tuple(private_locations))
        ]
        opponent_private_ids = (
            opponent_private[:, 0] << 8
        ) + opponent_private[:, 1]
        totals["opponent_private_rows"] += len(opponent_private)
        totals["opponent_private_identity_leaks"] += int(
            np.count_nonzero(opponent_private_ids)
        )
        totals["opponent_private_detail_leaks"] += int(
            np.count_nonzero(opponent_private[:, 7:])
        )
        totals["opponent_private_sequence_leaks"] += int(
            np.count_nonzero(opponent_private[:, 3])
        )

        opponent_facedown = opponent[
            np.isin(opponent[:, 2], tuple(field_locations))
            & np.isin(opponent[:, 5], tuple(facedown_positions))
        ]
        opponent_facedown_ids = (
            opponent_facedown[:, 0] << 8
        ) + opponent_facedown[:, 1]
        totals["opponent_facedown_rows"] += len(opponent_facedown)
        totals["opponent_facedown_identity_leaks"] += int(
            np.count_nonzero(opponent_facedown_ids)
        )
        totals["opponent_facedown_detail_leaks"] += int(
            np.count_nonzero(opponent_facedown[:, 7:])
        )

    failures = {
        name: value
        for name, value in totals.items()
        if name.endswith(("_leaks", "_missing")) and value != 0
    }
    if totals["own_deck_rows"] == 0:
        failures["own_deck_rows"] = 0
    if totals["opponent_private_rows"] == 0:
        failures["opponent_private_rows"] = 0
    if totals["own_hand_rows"] == 0:
        failures["own_hand_rows"] = 0
    if failures:
        raise ValueError(f"Reset hidden-information audit failed: {failures}")
    return {
        **totals,
        "scope": "reset_observation",
        "identity_grounding_pass": True,
        "hidden_information_pass": True,
    }


def validate_dynamic_hidden_information(
    observation: dict[str, Any],
    infos: dict[str, Any],
    environment_spec: dict[str, Any],
    visibility_codes: dict[str, int],
) -> dict[str, Any]:
    import numpy as np

    cards = np.asarray(observation["cards_"], dtype=np.uint16)
    visibility = np.asarray(infos.get("card_visibility_"))
    batch_size = environment_spec["batch_size"]
    max_cards = environment_spec["max_cards"]
    expected_shape = (batch_size, max_cards * 2)
    if cards.shape[:2] != expected_shape:
        raise ValueError(
            f"Dynamic hidden-information audit received cards shape {cards.shape}; "
            f"expected first dimensions {expected_shape}"
        )
    if visibility.shape != expected_shape:
        raise ValueError(
            "Dynamic hidden-information audit requires info "
            f"'card_visibility_' with shape {expected_shape}; got {visibility.shape}"
        )
    if not np.issubdtype(visibility.dtype, np.integer):
        raise ValueError("card_visibility_ must have an integer dtype")

    expected_codes = set(visibility_codes.values())
    actual_codes = set(np.unique(visibility).astype(int).tolist())
    unknown_codes = sorted(actual_codes.difference(expected_codes))
    if unknown_codes:
        raise ValueError(f"Unknown card visibility provenance codes: {unknown_codes}")

    locations = cards[..., 2]
    positions = cards[..., 5]
    card_ids = (cards[..., 0] << 8) + cards[..., 1]
    active = locations != 0
    padding = ~active
    visible_codes = {
        visibility_codes["owner_visible"],
        visibility_codes["public_field"],
        visibility_codes["confirmed_reveal"],
        visibility_codes["selectable_own_deck"],
    }
    hidden_codes = {
        visibility_codes["hidden_private"],
        visibility_codes["opponent_facedown"],
    }
    visible = np.isin(visibility, tuple(visible_codes))
    hidden = np.isin(visibility, tuple(hidden_codes))
    hidden_details = np.any(cards[..., 7:] != 0, axis=-1)

    own = np.zeros(expected_shape, dtype=bool)
    own[:, :max_cards] = True
    opponent = ~own
    own_deck = own & (locations == 1)
    opponent_private = opponent & np.isin(locations, (1, 2, 7))
    opponent_facedown = (
        opponent & np.isin(locations, (3, 4)) & np.isin(positions, (2, 6, 7))
    )
    confirmed = visibility == visibility_codes["confirmed_reveal"]
    selectable_own_deck = (
        visibility == visibility_codes["selectable_own_deck"]
    )

    failures = {
        "active_rows_without_provenance": int(np.count_nonzero(active & (visibility == 0))),
        "padding_rows_with_provenance": int(np.count_nonzero(padding & (visibility != 0))),
        "hidden_identity_leaks": int(np.count_nonzero(hidden & (card_ids != 0))),
        "hidden_detail_leaks": int(np.count_nonzero(hidden & hidden_details)),
        "hidden_private_sequence_leaks": int(
            np.count_nonzero(
                (visibility == visibility_codes["hidden_private"])
                & (cards[..., 3] != 0)
            )
        ),
        "visible_identity_missing": int(np.count_nonzero(visible & (card_ids == 0))),
        "own_deck_invalid_provenance": int(
            np.count_nonzero(
                own_deck
                & ~np.isin(
                    visibility,
                    (
                        visibility_codes["hidden_private"],
                        visibility_codes["confirmed_reveal"],
                        visibility_codes["selectable_own_deck"],
                    ),
                )
            )
        ),
        "opponent_private_invalid_provenance": int(
            np.count_nonzero(
                opponent_private
                & ~np.isin(
                    visibility,
                    (
                        visibility_codes["hidden_private"],
                        visibility_codes["confirmed_reveal"],
                    ),
                )
            )
        ),
        "opponent_facedown_invalid_provenance": int(
            np.count_nonzero(
                opponent_facedown
                & ~np.isin(
                    visibility,
                    (
                        visibility_codes["opponent_facedown"],
                        visibility_codes["confirmed_reveal"],
                    ),
                )
            )
        ),
    }
    failures = {name: value for name, value in failures.items() if value}
    if failures:
        raise ValueError(f"Dynamic hidden-information audit failed: {failures}")

    return {
        "active_rows": int(np.count_nonzero(active)),
        "private_rows": int(
            np.count_nonzero(own_deck | opponent_private | opponent_facedown)
        ),
        "hidden_rows": int(np.count_nonzero(hidden)),
        "visible_rows": int(np.count_nonzero(visible)),
        "confirmed_reveal_rows": int(np.count_nonzero(confirmed)),
        "selectable_own_deck_rows": int(np.count_nonzero(selectable_own_deck)),
        "identity_grounding_pass": True,
        "hidden_information_pass": True,
    }


def validate_hidden_information_coverage(
    totals: dict[str, int],
    gate_spec: dict[str, Any],
) -> dict[str, Any]:
    requirements = {
        "states_audited": gate_spec["minimum_steps_audited"],
        "private_rows": gate_spec["minimum_private_rows"],
        "confirmed_reveal_rows": gate_spec["minimum_confirmed_reveal_rows"],
    }
    missing = {
        name: {"actual": int(totals.get(name, 0)), "required": required}
        for name, required in requirements.items()
        if int(totals.get(name, 0)) < required
    }
    if missing:
        raise ValueError(f"Dynamic hidden-information coverage is insufficient: {missing}")
    return {
        "coverage_pass": True,
        "coverage_requirements": requirements,
    }


def validate_step_output(
    observation: dict[str, Any],
    rewards: Any,
    terminated: Any,
    truncated: Any,
    infos: dict[str, Any],
    environment_spec: dict[str, Any],
    card_count: int,
) -> dict[str, Any]:
    import numpy as np

    batch_size = environment_spec["batch_size"]
    arrays = {
        "rewards": np.asarray(rewards),
        "terminated": np.asarray(terminated),
        "truncated": np.asarray(truncated),
    }
    for name, value in arrays.items():
        if value.shape != (batch_size,):
            raise ValueError(
                f"Step output '{name}' has shape {value.shape}; "
                f"expected {(batch_size,)}"
            )
    if not np.issubdtype(arrays["rewards"].dtype, np.number):
        raise ValueError("Step rewards must have a numeric dtype")
    if not np.all(np.isfinite(arrays["rewards"])):
        raise ValueError("Step rewards must be finite")

    done = np.logical_or(arrays["terminated"], arrays["truncated"])
    observation_metrics = validate_observation_output(
        observation,
        environment_spec,
        card_count,
    )
    info_metrics = validate_info_output(
        infos,
        environment_spec,
        minimum_options=0 if bool(np.any(done)) else 1,
    )
    return {
        **observation_metrics,
        **info_metrics,
        "reward": float(arrays["rewards"][0]),
        "terminated": bool(arrays["terminated"][0]),
        "truncated": bool(arrays["truncated"][0]),
    }


def validate_legal_action_selection(
    observation: dict[str, Any],
    infos: dict[str, Any],
    action: Any,
    environment_spec: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    batch_size = environment_spec["batch_size"]
    actions = np.asarray(action)
    num_options = np.asarray(infos["num_options"])
    action_features = np.asarray(observation["actions_"])
    if actions.shape != (batch_size,):
        raise ValueError(
            f"Action selection has shape {actions.shape}; expected {(batch_size,)}"
        )
    if num_options.shape != (batch_size,):
        raise ValueError(
            f"num_options has shape {num_options.shape}; expected {(batch_size,)}"
        )

    selected_features = []
    for index in range(batch_size):
        selected = int(actions[index])
        option_count = int(num_options[index])
        if not 0 <= selected < option_count:
            raise ValueError(
                f"Action {selected} is outside {option_count} legal options "
                f"for batch index {index}"
            )
        features = action_features[index, selected]
        if not np.any(features):
            raise ValueError(
                f"Legal action features are empty for batch index {index}, "
                f"action {selected}"
            )
        selected_features.append(features.tolist())
    return {
        "legal_action_verified": True,
        "pre_num_options": num_options.astype(int).tolist(),
        "action_indices": actions.astype(int).tolist(),
        "selected_action_features": selected_features,
    }


def load_gate_protocol(path: Path, runtime_snapshot_id: str) -> dict[str, Any]:
    path = path.resolve()
    validate_path("runtime-gate-protocol", path)
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol["runtime_snapshot_id"] != runtime_snapshot_id:
        raise ValueError(
            "Gate protocol and runtime snapshot IDs do not match: "
            f"{protocol['runtime_snapshot_id']} != {runtime_snapshot_id}"
        )
    return protocol


def select_uniform_legal_actions(
    infos: dict[str, Any],
    environment_spec: dict[str, Any],
    rng: Any,
) -> Any:
    import numpy as np

    batch_size = environment_spec["batch_size"]
    num_options = np.asarray(infos["num_options"])
    if num_options.shape != (batch_size,):
        raise ValueError(
            f"num_options has shape {num_options.shape}; expected {(batch_size,)}"
        )
    if np.any(num_options <= 0):
        raise ValueError(f"Cannot sample from non-positive num_options: {num_options}")
    return np.asarray(
        [rng.integers(int(count)) for count in num_options],
        dtype=np.int32,
    )


def done_flags(
    terminated: Any,
    truncated: Any,
    environment_spec: dict[str, Any],
) -> Any:
    import numpy as np

    expected_shape = (environment_spec["batch_size"],)
    terminated_array = np.asarray(terminated, dtype=bool)
    truncated_array = np.asarray(truncated, dtype=bool)
    if terminated_array.shape != expected_shape:
        raise ValueError(
            f"terminated has shape {terminated_array.shape}; expected {expected_shape}"
        )
    if truncated_array.shape != expected_shape:
        raise ValueError(
            f"truncated has shape {truncated_array.shape}; expected {expected_shape}"
        )
    return np.logical_or(terminated_array, truncated_array)


def close_pool(pool: Any) -> None:
    if hasattr(pool, "close"):
        pool.close()


def require_single_environment(
    environment_spec: dict[str, Any],
    gate_kind: str,
) -> None:
    cardinality = {
        name: environment_spec[name]
        for name in ("num_envs", "batch_size", "num_threads")
    }
    if set(cardinality.values()) != {1}:
        raise ValueError(
            f"{gate_kind} requires num_envs=batch_size=num_threads=1; "
            f"got {cardinality}"
        )


def run_hidden_information_gate(
    runtime: ModernRuntime,
    profile_name: str,
    gate_spec: dict[str, Any],
    visibility_codes: dict[str, int],
) -> dict[str, Any]:
    import numpy as np

    profile = runtime.profile(profile_name)
    environment_spec = profile["spec"]
    require_single_environment(environment_spec, "hidden_information")
    action_seed = environment_spec["seed"] + gate_spec["action_seed_offset"]
    rng = np.random.default_rng(action_seed)
    pool = runtime.construct_gymnasium_pool(profile_name)
    observation, infos = pool.reset()
    totals: dict[str, int] = {"states_audited": 0, "transitions": 0, "episodes": 0}
    for _ in range(gate_spec["max_steps"]):
        audit = validate_dynamic_hidden_information(
            observation,
            infos,
            environment_spec,
            visibility_codes,
        )
        totals["states_audited"] += environment_spec["batch_size"]
        for name, value in audit.items():
            if isinstance(value, int) and not isinstance(value, bool):
                totals[name] = totals.get(name, 0) + value
        requirements_met = (
            totals["states_audited"] >= gate_spec["minimum_steps_audited"]
            and totals.get("private_rows", 0) >= gate_spec["minimum_private_rows"]
            and totals.get("confirmed_reveal_rows", 0)
            >= gate_spec["minimum_confirmed_reveal_rows"]
        )
        if requirements_met and totals["transitions"] > 0:
            break
        action = select_uniform_legal_actions(infos, environment_spec, rng)
        observation, _, terminated, truncated, infos = pool.step(action)
        totals["transitions"] += environment_spec["batch_size"]
        done = done_flags(terminated, truncated, environment_spec)
        if bool(np.any(done)):
            totals["episodes"] += int(np.count_nonzero(done))
            observation, infos = pool.reset()
    close_pool(pool)
    del pool
    gc.collect()
    coverage = validate_hidden_information_coverage(totals, gate_spec)
    return {
        "gate_kind": "hidden_information",
        "pool_constructed": True,
        "pool_reset": True,
        "pool_destroyed": True,
        "action_seed": action_seed,
        **totals,
        **coverage,
        "identity_grounding_pass": True,
        "hidden_information_pass": True,
    }


def run_trace(
    runtime: ModernRuntime,
    profile_name: str,
    max_steps: int,
    rng: Any | None = None,
    fixed_actions: list[list[int]] | None = None,
) -> dict[str, Any]:
    import numpy as np

    profile = runtime.profile(profile_name)
    environment_spec = profile["spec"]
    require_single_environment(environment_spec, "trace_replay")
    pool = runtime.construct_gymnasium_pool(profile_name)
    observation, infos = pool.reset()
    actions: list[list[int]] = []
    pre_hashes: list[str] = []
    post_hashes: list[str] = []
    done_history: list[list[bool]] = []
    for step_index in range(max_steps):
        if fixed_actions is None:
            if rng is None:
                raise ValueError("Trace collection requires an action RNG")
            action = select_uniform_legal_actions(infos, environment_spec, rng)
        else:
            if step_index >= len(fixed_actions):
                break
            action = np.asarray(fixed_actions[step_index], dtype=np.int32)
        validate_legal_action_selection(
            observation,
            infos,
            action,
            environment_spec,
        )
        pre_hashes.append(runtime_state_hash(observation, infos))
        actions.append(action.astype(int).tolist())
        observation, _, terminated, truncated, infos = pool.step(action)
        post_hashes.append(runtime_state_hash(observation, infos))
        done = done_flags(terminated, truncated, environment_spec)
        done_history.append(done.astype(bool).tolist())
        if bool(np.any(done)):
            break
    close_pool(pool)
    del pool
    gc.collect()
    return {
        "actions": actions,
        "pre_observation_hashes": pre_hashes,
        "post_observation_hashes": post_hashes,
        "done": done_history,
    }


def compare_traces(original: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    actions_match = original["actions"] == replay["actions"]
    pre_hashes_match = (
        original["pre_observation_hashes"]
        == replay["pre_observation_hashes"]
    )
    post_hashes_match = (
        original["post_observation_hashes"]
        == replay["post_observation_hashes"]
    )
    terminal_match = original["done"] == replay["done"]
    if not actions_match:
        raise ValueError("Trace replay actions do not match")
    if not pre_hashes_match or not post_hashes_match:
        raise ValueError("Trace replay observation state hashes do not match")
    if not terminal_match:
        raise ValueError("Trace replay terminal flags do not match")
    return {
        "actions_match": True,
        "all_state_hashes_match": True,
        "terminal_flags_match": True,
        "steps": len(original["actions"]),
        "original": original,
        "replay": replay,
    }


def run_trace_replay_gate(
    runtime: ModernRuntime,
    profile_name: str,
    gate_spec: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    environment_spec = runtime.profile(profile_name)["spec"]
    action_seed = environment_spec["seed"] + gate_spec["action_seed_offset"]
    rng = np.random.default_rng(action_seed)
    original = run_trace(
        runtime,
        profile_name,
        gate_spec["max_steps"],
        rng=rng,
    )
    replay = run_trace(
        runtime,
        profile_name,
        len(original["actions"]),
        fixed_actions=original["actions"],
    )
    return {
        "gate_kind": "trace_replay",
        "pool_constructed": True,
        "pool_reset": True,
        "pool_destroyed": True,
        "action_seed": action_seed,
        **compare_traces(original, replay),
    }


def run_lifecycle_gate(
    runtime: ModernRuntime,
    profile_name: str,
    gate_spec: dict[str, Any],
) -> dict[str, Any]:
    require_single_environment(
        runtime.profile(profile_name)["spec"],
        "lifecycle",
    )
    completed_cycles = 0
    for _ in range(gate_spec["completed_cycles_target"]):
        pool = runtime.construct_gymnasium_pool(profile_name)
        pool.reset()
        close_pool(pool)
        del pool
        gc.collect()
        completed_cycles += 1
    return {
        "gate_kind": "lifecycle",
        "completed_cycles": completed_cycles,
        "crashes": 0,
        "pool_destroyed": True,
    }


def run_transition_loop(
    pool: Any,
    environment_spec: dict[str, Any],
    rng: Any,
    transitions: int,
    observation: dict[str, Any],
    infos: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    import numpy as np

    completed = 0
    episodes = 0
    while completed < transitions:
        action = select_uniform_legal_actions(infos, environment_spec, rng)
        observation, _, terminated, truncated, infos = pool.step(action)
        completed += environment_spec["batch_size"]
        done = done_flags(terminated, truncated, environment_spec)
        if bool(np.any(done)):
            episodes += int(np.count_nonzero(done))
            observation, infos = pool.reset()
    return observation, infos, completed, episodes


def run_throughput_gate(
    runtime: ModernRuntime,
    profile_name: str,
    gate_spec: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    overrides = gate_spec["environment_overrides"]
    environment_spec = runtime.environment_spec(profile_name, overrides)
    action_seed = environment_spec["seed"] + gate_spec["action_seed_offset"]
    rng = np.random.default_rng(action_seed)
    pool = runtime.construct_gymnasium_pool(profile_name, overrides)
    observation, infos = pool.reset()
    observation, infos, _, _ = run_transition_loop(
        pool,
        environment_spec,
        rng,
        gate_spec["warmup_steps"],
        observation,
        infos,
    )
    started = time.perf_counter()
    _, _, measured_steps, episodes = run_transition_loop(
        pool,
        environment_spec,
        rng,
        gate_spec["measured_steps"],
        observation,
        infos,
    )
    elapsed = time.perf_counter() - started
    steps_per_second = measured_steps / elapsed
    close_pool(pool)
    del pool
    gc.collect()
    if steps_per_second < gate_spec["minimum_steps_per_second"]:
        raise ValueError(
            f"Throughput {steps_per_second:.3f} steps/s is below "
            f"{gate_spec['minimum_steps_per_second']} steps/s"
        )
    return {
        "gate_kind": "throughput",
        "warmup_steps": gate_spec["warmup_steps"],
        "measured_steps": measured_steps,
        "measured_episodes": episodes,
        "elapsed_seconds": elapsed,
        "steps_per_second": steps_per_second,
        "minimum_steps_per_second": gate_spec["minimum_steps_per_second"],
        "action_seed": action_seed,
        "environment_spec": environment_spec,
        "pool_destroyed": True,
    }


def run_random_eval_gate(
    runtime: ModernRuntime,
    profile_name: str,
    gate_spec: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    environment_spec = runtime.profile(profile_name)["spec"]
    require_single_environment(environment_spec, "random_eval")
    action_seed = environment_spec["seed"] + gate_spec["action_seed_offset"]
    rng = np.random.default_rng(action_seed)
    pool = runtime.construct_gymnasium_pool(profile_name)
    observation, infos = pool.reset()
    episodes = 0
    total_steps = 0
    episode_steps = np.zeros(environment_spec["batch_size"], dtype=np.int64)
    episode_lengths: list[int] = []
    rewards: list[float] = []
    while episodes < gate_spec["episodes"]:
        action = select_uniform_legal_actions(infos, environment_spec, rng)
        observation, step_rewards, terminated, truncated, infos = pool.step(action)
        total_steps += environment_spec["batch_size"]
        episode_steps += 1
        done = done_flags(terminated, truncated, environment_spec)
        for index in np.flatnonzero(done):
            if episodes >= gate_spec["episodes"]:
                break
            length = int(episode_steps[index])
            if length > gate_spec["max_steps_per_episode"]:
                raise ValueError(
                    f"Episode length {length} exceeds "
                    f"{gate_spec['max_steps_per_episode']}"
                )
            episode_lengths.append(length)
            rewards.append(float(np.asarray(step_rewards)[index]))
            episode_steps[index] = 0
            episodes += 1
        if bool(np.any(done)):
            observation, infos = pool.reset()
    close_pool(pool)
    del pool
    gc.collect()
    return {
        "gate_kind": "random_eval",
        "episodes": episodes,
        "total_steps": total_steps,
        "mean_episode_length": float(np.mean(episode_lengths)),
        "mean_terminal_reward": float(np.mean(rewards)),
        "crashes": 0,
        "action_seed": action_seed,
        "pool_destroyed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=(
            "init",
            "construct",
            "reset",
            "step",
            "hidden_information",
            "trace_replay",
            "lifecycle",
            "throughput",
            "random_eval",
        ),
        required=True,
    )
    parser.add_argument("--profile", choices=("tcg", "ocg"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--gate-protocol",
        type=Path,
        default=DEFAULT_GATE_PROTOCOL,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.stage != "init" and args.profile is None:
        parser.error(f"--profile is required for the {args.stage} stage")
    if args.stage == "init" and args.profile is not None:
        parser.error("--profile is not valid for the init stage")

    runtime = ModernRuntime(args.config)
    gate_protocol = None
    gate_spec = None
    gate_id = None
    if args.stage in FOLLOWUP_STAGES:
        gate_protocol = load_gate_protocol(
            args.gate_protocol,
            runtime.config["runtime_snapshot_id"],
        )
        gate_spec = gate_protocol["gates"][args.stage]
        gate_id = f"{gate_spec['result_stem']}_{args.profile}"
    suffix = f"_{args.profile}" if args.profile else ""
    output_stem = gate_spec["result_stem"] if gate_spec else args.stage
    output = args.output or (
        ROOT / "results" / "runtime_modern_v1" / f"gate_{output_stem}{suffix}.json"
    )
    output = output.resolve()
    git_commit = git_value("rev-parse", "HEAD")
    result_directory = "results/runtime_modern_v1"
    git_dirty = bool(
        git_value(
            "status",
            "--porcelain",
            "--",
            ".",
            f":(exclude){result_directory}",
        )
    )
    started = time.perf_counter()
    runtime.initialize()
    profile = runtime.profile(args.profile) if args.profile else None
    metrics: dict[str, Any] = {
        "stage": args.stage,
        "init_completed": True,
        "pool_constructed": False,
        "pool_reset": False,
        "pool_stepped": False,
        "pool_destroyed": False,
    }
    if args.stage in {"construct", "reset", "step"}:
        pool = runtime.construct_gymnasium_pool(args.profile)
        metrics["pool_constructed"] = True
        if args.stage in {"reset", "step"}:
            observation, infos = pool.reset()
            metrics["pool_reset"] = True
            reset_metrics = validate_reset_output(
                observation,
                infos,
                profile["spec"],
                runtime.asset_manifest["code_list"]["card_count"],
            )
            metrics["reset"] = reset_metrics
            if args.stage == "reset":
                metrics.update(reset_metrics)
        if args.stage == "step":
            import numpy as np

            metrics["gate_kind"] = "step"
            action = np.full(
                profile["spec"]["batch_size"],
                gate_spec["action_index"],
                dtype=np.int32,
            )
            action_metrics = validate_legal_action_selection(
                observation,
                infos,
                action,
                profile["spec"],
            )
            pre_observation_hash = observation_hash(observation)
            observation, rewards, terminated, truncated, infos = pool.step(action)
            post_observation_hash = observation_hash(observation)
            if pre_observation_hash == post_observation_hash:
                raise ValueError("Legal action did not change the observation state")
            metrics["pool_stepped"] = True
            metrics.update(action_metrics)
            metrics["pre_observation_sha256"] = pre_observation_hash
            metrics["post_observation_sha256"] = post_observation_hash
            metrics["state_changed"] = True
            metrics["step"] = validate_step_output(
                observation,
                rewards,
                terminated,
                truncated,
                infos,
                profile["spec"],
                runtime.asset_manifest["code_list"]["card_count"],
            )
            metrics["dynamic_hidden_information"] = (
                validate_dynamic_hidden_information(
                    observation,
                    infos,
                    profile["spec"],
                    gate_protocol["visibility_codes"],
                )
            )
        close_pool(pool)
        del pool
        gc.collect()
        metrics["pool_destroyed"] = True
    elif args.stage == "hidden_information":
        metrics = run_hidden_information_gate(
            runtime,
            args.profile,
            gate_spec,
            gate_protocol["visibility_codes"],
        )
    elif args.stage == "trace_replay":
        metrics = run_trace_replay_gate(runtime, args.profile, gate_spec)
    elif args.stage == "lifecycle":
        metrics = run_lifecycle_gate(runtime, args.profile, gate_spec)
    elif args.stage == "throughput":
        metrics = run_throughput_gate(runtime, args.profile, gate_spec)
    elif args.stage == "random_eval":
        metrics = run_random_eval_gate(runtime, args.profile, gate_spec)
    metrics.setdefault("stage", args.stage)
    metrics.setdefault("init_completed", True)
    execution_spec = metrics.get(
        "environment_spec",
        profile["spec"] if profile else None,
    )

    result = {
        "status": "passed",
        "runtime_snapshot_id": runtime.config["runtime_snapshot_id"],
        "profile": args.profile,
        "environment_snapshot_id": (
            profile["snapshot_id"] if profile else None
        ),
        "environment_spec": execution_spec,
        "command": " ".join(sys.argv),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "git_dirty_excludes": [result_directory],
        "config": str(args.config.resolve().relative_to(ROOT)),
        "config_sha256": sha256_file(args.config.resolve()),
        "extension_sha256": sha256_file(runtime.extension),
        "asset_manifest_sha256": sha256_file(runtime.asset_manifest_path),
        "runtime_snapshot_sha256": sha256_file(runtime.runtime_snapshot_path),
        "duration_seconds": time.perf_counter() - started,
        "metrics": metrics,
    }
    if gate_protocol is not None:
        result.update(
            {
                "gate_id": gate_id,
                "gate_protocol_id": gate_protocol["gate_protocol_id"],
                "gate_protocol": str(
                    args.gate_protocol.resolve().relative_to(ROOT)
                ),
                "gate_protocol_sha256": sha256_file(
                    args.gate_protocol.resolve()
                ),
                "gate_configuration": gate_spec,
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
