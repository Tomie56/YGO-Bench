from __future__ import annotations

import unittest

from ygo_bench.models.base import (
    HarnessConfig,
    InferenceRequest,
    ModelAdapter,
    ModelIdentity,
    ProviderResponse,
    TokenUsage,
)


ZERO_HASH = "0" * 64


class FakeAdapter(ModelAdapter):
    def complete_batch(self, requests):
        return [
            ProviderResponse(
                record_id=request.record_id,
                status="ok",
                answer={"legal": True},
                confidence=0.75,
                latency_ms=1.5,
                usage=TokenUsage(10, 2, 12),
                raw_response='{"legal":true}',
                actors=({"actor": "model", "operation": "predict"},),
            )
            for request in requests
        ]


class ShortAdapter(FakeAdapter):
    def complete_batch(self, requests):
        return []


class ModelAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        identity = ModelIdentity("local", "fake", "revision-1", "local", "Q4")
        harness = HarnessConfig("C1", "hidden", False, False, False, ZERO_HASH)
        self.adapter = FakeAdapter(identity, harness)
        self.request = InferenceRequest(
            run_id="run-1",
            record_id="record-1",
            messages=({"role": "user", "content": "answer"},),
            response_schema={"type": "object"},
            max_output_tokens=32,
            temperature=0.0,
            seed=1,
        )

    def test_batch_output_matches_contract(self) -> None:
        output = self.adapter.run_batch([self.request])[0]
        self.assertEqual(output["record_id"], "record-1")
        self.assertEqual(output["answer"], {"legal": True})
        self.assertFalse(output["audit"]["fallback_used"])
        self.assertEqual(len(output["raw_response_sha256"]), 64)

    def test_batch_cardinality_mismatch_fails(self) -> None:
        adapter = ShortAdapter(self.adapter.identity, self.adapter.harness)
        with self.assertRaisesRegex(RuntimeError, "0 responses"):
            adapter.run_batch([self.request])

    def test_empty_batch_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.adapter.run_batch([])


if __name__ == "__main__":
    unittest.main()
