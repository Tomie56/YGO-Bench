from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from ygo_bench.contracts import SCHEMA_VERSION, validate_document


ADAPTER_PROTOCOL_VERSION = "0.1.0"
OUTPUT_STATUSES = {
    "ok",
    "parser_error",
    "timeout",
    "refusal",
    "provider_error",
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model_id: str
    revision: str
    inference_mode: str
    quantization: str | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "model_id", "revision"):
            if not getattr(self, name):
                raise ValueError(f"Model identity field '{name}' must be non-empty")
        if self.inference_mode not in {"local", "api", "non_llm"}:
            raise ValueError(f"Invalid inference_mode: {self.inference_mode}")


@dataclass(frozen=True)
class HarnessConfig:
    condition: str
    legal_actions: str
    snapshot_rag: bool
    checker: bool
    memory_planner: bool
    config_sha256: str

    def __post_init__(self) -> None:
        if self.condition not in {"C1", "C2", "C3", "custom"}:
            raise ValueError(f"Invalid harness condition: {self.condition}")
        if self.legal_actions not in {"hidden", "shown"}:
            raise ValueError(f"Invalid legal_actions mode: {self.legal_actions}")
        if len(self.config_sha256) != 64:
            raise ValueError("Harness config_sha256 must contain 64 hex characters")
        try:
            int(self.config_sha256, 16)
        except ValueError as error:
            raise ValueError("Harness config_sha256 must be hexadecimal") from error


@dataclass(frozen=True)
class InferenceRequest:
    run_id: str
    record_id: str
    messages: tuple[dict[str, str], ...]
    response_schema: dict[str, Any]
    max_output_tokens: int
    temperature: float
    seed: int | None
    attempt: int = 1

    def __post_init__(self) -> None:
        if not self.run_id or not self.record_id:
            raise ValueError("Inference request IDs must be non-empty")
        if not self.messages:
            raise ValueError("Inference request must contain at least one message")
        for message in self.messages:
            if set(message) != {"role", "content"}:
                raise ValueError("Each message must contain only role and content")
            if not message["role"] or not message["content"]:
                raise ValueError("Message role and content must be non-empty")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.temperature < 0:
            raise ValueError("temperature must be non-negative")
        if self.attempt <= 0:
            raise ValueError("attempt must be positive")


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None

    def __post_init__(self) -> None:
        values = (self.input_tokens, self.output_tokens, self.total_tokens)
        if any(value is not None and value < 0 for value in values):
            raise ValueError("Token usage values must be non-negative")
        if all(value is not None for value in values):
            if self.total_tokens != self.input_tokens + self.output_tokens:
                raise ValueError("total_tokens must equal input_tokens + output_tokens")


@dataclass(frozen=True)
class ProviderResponse:
    record_id: str
    status: str
    latency_ms: float
    usage: TokenUsage
    answer: dict[str, Any] | None = None
    confidence: float | None = None
    raw_response: str | None = None
    provider_request_id: str | None = None
    error: str | None = None
    retry_count: int = 0
    repair_count: int = 0
    fallback_used: bool = False
    actors: tuple[dict[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.status not in OUTPUT_STATUSES:
            raise ValueError(f"Invalid provider response status: {self.status}")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        if self.status == "ok" and self.answer is None:
            raise ValueError("Successful provider response must include answer")
        if self.status != "ok" and not self.error:
            raise ValueError("Failed provider response must include error")
        if self.retry_count < 0 or self.repair_count < 0:
            raise ValueError("Retry and repair counts must be non-negative")
        if not self.actors:
            raise ValueError("Provider response must identify at least one actor")
        for actor in self.actors:
            if set(actor) != {"actor", "operation"}:
                raise ValueError("Actor records must contain only actor and operation")


class ModelAdapter(ABC):
    def __init__(self, identity: ModelIdentity, harness: HarnessConfig) -> None:
        self.identity = identity
        self.harness = harness

    @abstractmethod
    def complete_batch(
        self,
        requests: Sequence[InferenceRequest],
    ) -> Sequence[ProviderResponse]:
        """Return exactly one response for each request, in request order."""

    def run_batch(self, requests: Sequence[InferenceRequest]) -> list[dict[str, Any]]:
        if not requests:
            raise ValueError("Model batch must contain at least one request")
        responses = list(self.complete_batch(requests))
        if len(responses) != len(requests):
            raise RuntimeError(
                f"Provider returned {len(responses)} responses for "
                f"{len(requests)} requests"
            )
        outputs = []
        for request, response in zip(requests, responses):
            if response.record_id != request.record_id:
                raise RuntimeError(
                    "Provider response order mismatch: "
                    f"expected {request.record_id}, got {response.record_id}"
                )
            output: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "run_id": request.run_id,
                "record_id": request.record_id,
                "attempt": request.attempt,
                "status": response.status,
                "model": asdict(self.identity),
                "harness": asdict(self.harness),
                "latency_ms": response.latency_ms,
                "usage": asdict(response.usage),
                "audit": {
                    "retry_count": response.retry_count,
                    "repair_count": response.repair_count,
                    "fallback_used": response.fallback_used,
                    "actors": list(response.actors),
                },
                "provider_request_id": response.provider_request_id,
                "error": response.error,
            }
            if response.answer is not None:
                output["answer"] = response.answer
            if response.confidence is not None:
                output["confidence"] = response.confidence
            if response.raw_response is not None:
                output["raw_response_sha256"] = hashlib.sha256(
                    response.raw_response.encode("utf-8")
                ).hexdigest()
            validate_document("model-output", output)
            outputs.append(output)
        return outputs
