from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ygo_bench.contracts import validate_path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "pre-experiment-readiness-v0.1.json"
DEFAULT_OUTPUT = ROOT / "results" / "readiness" / "pre_experiment_v0.1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def audit_environment(expected: dict[str, Any]) -> dict[str, Any]:
    conda_env = os.environ.get("CONDA_DEFAULT_ENV")
    if conda_env is None and Path(sys.prefix).parent.name == "envs":
        conda_env = Path(sys.prefix).name
    packages = {
        name: package_version(name) for name in expected["packages"]
    }
    errors = []
    if conda_env != expected["conda_env"]:
        errors.append("conda_env_mismatch")
    if platform.python_version() != expected["python"]:
        errors.append("python_version_mismatch")
    if "microsoft-standard-WSL2" not in platform.release():
        errors.append("not_running_in_wsl2")
    for name, version in expected["packages"].items():
        if packages[name] != version:
            errors.append(f"package_version_mismatch:{name}")
    return {
        "ready": not errors,
        "distro": expected["distro"],
        "conda_env": conda_env,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_dirty": bool(git_value("status", "--porcelain")),
        "errors": errors,
    }


def resolve(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"Readiness path escapes the repository: {path}") from error
    return path


def current_runtime_hashes(
    runtime_config_path: Path,
    runtime_config: dict[str, Any],
) -> dict[str, str]:
    paths = {
        "config_sha256": runtime_config_path,
        "extension_sha256": resolve(runtime_config["extension"]),
        "asset_manifest_sha256": resolve(runtime_config["asset_manifest"]),
        "runtime_snapshot_sha256": resolve(runtime_config["runtime_snapshot"]),
    }
    return {name: sha256_file(path) for name, path in paths.items()}


def audit_foundation_gate(
    gate: dict[str, Any],
    runtime_hashes: dict[str, str],
) -> dict[str, Any]:
    path = resolve(gate["path"])
    if not path.is_file():
        return {**gate, "status": "pending", "errors": ["result_missing"]}
    record = load_json(path)
    errors = []
    expected = {
        "status": "passed",
        "profile": gate["profile"],
        "git_dirty": False,
    }
    for key, value in expected.items():
        if record.get(key) != value:
            errors.append(f"{key}_mismatch")
    if record.get("metrics", {}).get("stage") != gate["stage"]:
        errors.append("stage_mismatch")
    for key, value in runtime_hashes.items():
        if record.get(key) != value:
            errors.append(f"{key}_mismatch")
    return {
        **gate,
        "status": "passed" if not errors else "invalid",
        "result_sha256": sha256_file(path),
        "result_git_commit": record.get("git_commit"),
        "errors": errors,
    }


def audit_required_gate(
    gate: dict[str, Any],
    runtime_hashes: dict[str, str],
    gate_protocol: dict[str, str] | None = None,
) -> dict[str, Any]:
    path = resolve(gate["path"])
    if not path.is_file():
        return {**gate, "status": "pending"}
    record = load_json(path)
    errors = []
    if record.get("status") != "passed":
        errors.append("status_mismatch")
    if record.get("git_dirty") is not False:
        errors.append("git_dirty")
    if record.get("profile") != gate["profile"]:
        errors.append("profile_mismatch")
    if record.get("gate_id") != gate["gate_id"]:
        errors.append("gate_id_mismatch")
    if gate_protocol is not None:
        if record.get("gate_protocol_id") != gate_protocol["gate_protocol_id"]:
            errors.append("gate_protocol_id_mismatch")
        if record.get("gate_protocol_sha256") != gate_protocol["sha256"]:
            errors.append("gate_protocol_sha256_mismatch")
        expected_gate_configuration = gate_protocol["configuration"]["gates"][
            gate["kind"]
        ]
        if record.get("gate_configuration") != expected_gate_configuration:
            errors.append("gate_configuration_mismatch")
    else:
        expected_gate_configuration = None
    for key, value in runtime_hashes.items():
        if record.get(key) != value:
            errors.append(f"{key}_mismatch")

    metrics = record.get("metrics", {})
    kind = gate["kind"]
    if metrics.get("gate_kind") != kind:
        errors.append("gate_kind_mismatch")
    if metrics.get("init_completed") is not True:
        errors.append("runtime_not_initialized")
    if metrics.get("pool_destroyed") is not True:
        errors.append("pool_not_destroyed")
    if kind == "step":
        if metrics.get("stage") != "step" or metrics.get("pool_stepped") is not True:
            errors.append("step_not_verified")
        if metrics.get("legal_action_verified") is not True:
            errors.append("legal_action_not_verified")
        if metrics.get("state_changed") is not True:
            errors.append("step_state_unchanged")
        dynamic = metrics.get("dynamic_hidden_information", {})
        if dynamic.get("hidden_information_pass") is not True:
            errors.append("step_hidden_information_not_verified")
        if dynamic.get("identity_grounding_pass") is not True:
            errors.append("step_identity_grounding_not_verified")
    elif kind == "hidden_information":
        if metrics.get("hidden_information_pass") is not True:
            errors.append("hidden_information_not_verified")
        if metrics.get("identity_grounding_pass") is not True:
            errors.append("identity_grounding_not_verified")
        if metrics.get("coverage_pass") is not True:
            errors.append("hidden_information_coverage_not_verified")
        requirements = {
            "states_audited": expected_gate_configuration[
                "minimum_steps_audited"
            ],
            "private_rows": expected_gate_configuration["minimum_private_rows"],
            "confirmed_reveal_rows": expected_gate_configuration[
                "minimum_confirmed_reveal_rows"
            ],
        }
        for name, minimum in requirements.items():
            if int(metrics.get(name, 0)) < minimum:
                errors.append(f"{name}_below_protocol_minimum")
    elif kind == "trace_replay":
        if metrics.get("all_state_hashes_match") is not True:
            errors.append("state_hash_mismatch")
        if metrics.get("actions_match") is not True:
            errors.append("action_replay_mismatch")
        if metrics.get("terminal_flags_match") is not True:
            errors.append("terminal_replay_mismatch")
        if int(metrics.get("steps", 0)) < 1:
            errors.append("trace_is_empty")
    elif kind == "lifecycle":
        if int(metrics.get("completed_cycles", 0)) < expected_gate_configuration[
            "completed_cycles_target"
        ]:
            errors.append("lifecycle_cycles_below_100")
        if int(metrics.get("crashes", 1)) != 0:
            errors.append("lifecycle_crash")
    elif kind == "throughput":
        if float(metrics.get("steps_per_second", 0.0)) < expected_gate_configuration[
            "minimum_steps_per_second"
        ]:
            errors.append("throughput_below_1000")
        if int(metrics.get("measured_steps", 0)) < expected_gate_configuration[
            "measured_steps"
        ]:
            errors.append("throughput_measurement_too_short")
    elif kind == "random_eval":
        if int(metrics.get("episodes", 0)) < expected_gate_configuration["episodes"]:
            errors.append("episodes_below_32")
        if int(metrics.get("crashes", 1)) != 0:
            errors.append("random_eval_crash")
    else:
        raise ValueError(f"Unknown required runtime gate kind: {kind}")
    return {
        **gate,
        "status": "passed" if not errors else "invalid",
        "result_sha256": sha256_file(path),
        "errors": errors,
    }


def audit_gate_protocol(
    config: dict[str, Any],
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    path = resolve(config["runtime_gate_protocol"])
    validate_path("runtime-gate-protocol", path)
    protocol = load_json(path)
    errors = []
    if protocol["runtime_snapshot_id"] != runtime_config["runtime_snapshot_id"]:
        errors.append("runtime_snapshot_id_mismatch")
    expected_gate_ids = {
        f"{spec['result_stem']}_{profile}": kind
        for kind, spec in protocol["gates"].items()
        for profile in ("tcg", "ocg")
    }
    configured_gate_ids = {
        gate["gate_id"]: gate["kind"]
        for gate in config["required_runtime_gates"]
    }
    if configured_gate_ids != expected_gate_ids:
        errors.append("required_gate_set_mismatch")
    return {
        "status": "passed" if not errors else "invalid",
        "path": config["runtime_gate_protocol"],
        "gate_protocol_id": protocol["gate_protocol_id"],
        "sha256": sha256_file(path),
        "errors": errors,
        "configuration": protocol,
    }


def audit_contracts(config: dict[str, Any]) -> dict[str, Any]:
    records = []
    for item in config["contract_examples"]:
        path = resolve(item["path"])
        count = validate_path(item["kind"], path)
        records.append(
            {
                **item,
                "status": "passed",
                "records": count,
                "sha256": sha256_file(path),
            }
        )
    return {"status": "passed", "artifacts": records}


def audit_data_result(config: dict[str, Any]) -> dict[str, Any]:
    path = resolve(config["data_qualification_result"])
    if not path.is_file():
        return {
            "status": "pending",
            "path": config["data_qualification_result"],
            "input_validation_errors": ["result_missing"],
            "understanding": None,
            "deck_data": None,
            "gate_passed": False,
        }
    record = load_json(path)
    input_errors = []
    for artifact in record.get("configuration", {}).get("input_artifacts", []):
        artifact_path = resolve(artifact["path"])
        if not artifact_path.is_file():
            input_errors.append(f"missing:{artifact['path']}")
        elif sha256_file(artifact_path) != artifact["sha256"]:
            input_errors.append(f"hash_mismatch:{artifact['path']}")
    if record.get("environment", {}).get("script_sha256") != sha256_file(
        ROOT / "experiments" / "run_e0_data_qualification.py"
    ):
        input_errors.append("qualification_script_hash_mismatch")
    return {
        "status": "passed" if record.get("gate_passed") else "not_ready",
        "path": config["data_qualification_result"],
        "sha256": sha256_file(path),
        "input_validation_errors": input_errors,
        "understanding": record.get("understanding"),
        "deck_data": record.get("deck_data", {}).get("by_snapshot"),
        "gate_passed": bool(record.get("gate_passed") and not input_errors),
    }


def audit_snapshots(config: dict[str, Any]) -> dict[str, Any]:
    records = []
    for snapshot_id in config["snapshot_ids"]:
        path = ROOT / "snapshots" / f"{snapshot_id}.json"
        snapshot = load_json(path)
        open_fields = snapshot.get("open_fields", [])
        records.append(
            {
                "snapshot_id": snapshot_id,
                "sha256": sha256_file(path),
                "open_fields": open_fields,
                "publication_ready": not open_fields,
            }
        )
    return {
        "publication_ready": all(item["publication_ready"] for item in records),
        "snapshots": records,
    }


def audit_files(paths: list[str]) -> dict[str, Any]:
    records = []
    for relative_path in paths:
        path = resolve(relative_path)
        records.append(
            {
                "path": relative_path,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return {
        "ready": all(item["exists"] for item in records),
        "artifacts": records,
    }


def audit_implementation(specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    records = []
    for name, spec in specs.items():
        path = resolve(spec["path"])
        errors = []
        module = None
        if not path.is_file():
            errors.append("file_missing")
        else:
            try:
                module = importlib.import_module(spec["module"])
            except Exception as error:
                errors.append(f"import_failed:{type(error).__name__}")
        if module is not None:
            actual_version = getattr(module, spec["version_symbol"], None)
            if actual_version != spec["version"]:
                errors.append("version_mismatch")
            for symbol in spec["required_symbols"]:
                if not hasattr(module, symbol):
                    errors.append(f"symbol_missing:{symbol}")
        else:
            actual_version = None
        records.append(
            {
                "name": name,
                "path": spec["path"],
                "module": spec["module"],
                "version": actual_version,
                "sha256": sha256_file(path) if path.is_file() else None,
                "status": "passed" if not errors else "not_ready",
                "errors": errors,
            }
        )
    return {
        "ready": all(item["status"] == "passed" for item in records),
        "artifacts": records,
    }


def build_report(config_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    runtime_config_path = resolve(config["runtime_config"])
    runtime_config = load_json(runtime_config_path)
    runtime_hashes = current_runtime_hashes(runtime_config_path, runtime_config)
    gate_protocol = audit_gate_protocol(config, runtime_config)
    foundation = [
        audit_foundation_gate(gate, runtime_hashes)
        for gate in config["foundation_gates"]
    ]
    required_runtime = [
        audit_required_gate(gate, runtime_hashes, gate_protocol)
        for gate in config["required_runtime_gates"]
    ]
    runtime_foundation_ready = all(item["status"] == "passed" for item in foundation)
    runtime_engine_ready = (
        runtime_foundation_ready
        and gate_protocol["status"] == "passed"
        and all(
            item["status"] == "passed" for item in required_runtime
        )
    )
    contracts = audit_contracts(config)
    data = audit_data_result(config)
    snapshots = audit_snapshots(config)
    paper = audit_files(config["paper_documents"])
    implementation = audit_implementation(config["required_implementation"])
    environment = audit_environment(config["environment"])
    blockers = []
    if not runtime_engine_ready:
        blockers.append("runtime_followup_gates_pending")
    if gate_protocol["status"] != "passed":
        blockers.append("runtime_gate_protocol_invalid")
    if not data["gate_passed"]:
        blockers.append("e0_data_qualification_not_passed")
    if not snapshots["publication_ready"]:
        blockers.append("snapshot_open_fields_pending")
    if not implementation["ready"]:
        blockers.append("scorer_or_model_adapter_missing")
    if not environment["ready"]:
        blockers.append("environment_mismatch")

    static_model_ready = bool(
        contracts["status"] == "passed"
        and data["gate_passed"]
        and snapshots["publication_ready"]
        and implementation["ready"]
        and environment["ready"]
    )
    strategy_model_ready = static_model_ready and runtime_engine_ready
    return {
        "readiness_id": config["readiness_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if strategy_model_ready else "not_ready",
        "protocol": config["protocol"],
        "environment": environment,
        "configuration": {
            "path": config_path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(config_path),
            "script_sha256": sha256_file(Path(__file__)),
        },
        "contracts": contracts,
        "runtime": {
            "foundation_ready": runtime_foundation_ready,
            "engine_ready": runtime_engine_ready,
            "hashes": runtime_hashes,
            "gate_protocol": gate_protocol,
            "foundation_gates": foundation,
            "required_gates": required_runtime,
        },
        "data_qualification": data,
        "snapshots": snapshots,
        "paper_protocol": paper,
        "implementation": implementation,
        "tracks": {
            "static_model_experiment_ready": static_model_ready,
            "strategy_model_experiment_ready": strategy_model_ready,
            "paper_main_experiment_ready": strategy_model_ready and paper["ready"],
        },
        "blockers": blockers,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit YGO-Bench experiment readiness")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    output = args.output.resolve()
    report = build_report(config_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
