from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "0.1.0"
SCHEMA_PATHS = {
    "benchmark-record": ROOT / "schemas" / "benchmark-record.schema.json",
    "environment-snapshot": ROOT / "schemas" / "environment-snapshot.schema.json",
    "fixed-scenario": ROOT / "schemas" / "fixed-scenario.schema.json",
    "model-output": ROOT / "schemas" / "model-output.schema.json",
    "evaluation-result": ROOT / "schemas" / "evaluation-result.schema.json",
    "runtime-gate-protocol": (
        ROOT / "schemas" / "runtime-gate-protocol.schema.json"
    ),
    "runtime-snapshot": ROOT / "schemas" / "runtime-snapshot.schema.json",
    "understanding-annotation": (
        ROOT / "schemas" / "understanding-annotation.schema.json"
    ),
}


class ContractValidationError(ValueError):
    pass


@lru_cache(maxsize=None)
def load_schema(kind: str) -> dict[str, Any]:
    try:
        path = SCHEMA_PATHS[kind]
    except KeyError as error:
        raise ValueError(
            f"Unknown contract kind '{kind}'; expected one of {sorted(SCHEMA_PATHS)}"
        ) from error
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validate_document(kind: str, document: Any) -> None:
    validator = Draft202012Validator(
        load_schema(kind),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    messages = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        messages.append(f"{location}: {error.message}")
    raise ContractValidationError("; ".join(messages))


def read_documents(path: Path) -> Iterable[Any]:
    if path.suffix == ".jsonl":
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON at {path}:{line_number}: {error}"
                ) from error
        return
    if path.suffix != ".json":
        raise ValueError(f"Contract input must be .json or .jsonl: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        yield from value
    else:
        yield value


def validate_path(kind: str, path: Path) -> int:
    count = 0
    for index, document in enumerate(read_documents(path)):
        try:
            validate_document(kind, document)
        except ContractValidationError as error:
            raise ContractValidationError(f"{path}[{index}]: {error}") from error
        count += 1
    if count == 0:
        raise ValueError(f"Contract input contains no documents: {path}")
    return count
