import hashlib
import os
import socket
import tempfile
import unittest

from evaluate import evaluate, load_golden
from extractors import FakeLLMExtractor, HybridExtractor, LLMExtractor, RegexExtractor
from nli import HeuristicNLI, OnnxNLI
from review import ReviewQueue
from schemas import Decision, validate_evidence
from store import Store
from vectors import (
    HashingEmbedder,
    IVFIndex,
    cosine,
    dequantize_int8,
    pack_int8,
    quantize_int8,
    unpack_int8,
)


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "v2.db"))

    def test_schema_and_span_validation(self):
        source = "We decided to use Redis for the cache."
        decision = Decision(statement=source, source="a.md", date="2026-01-10", evidence_span=source)
        self.assertTrue(validate_evidence(decision, source))
        with self.assertRaises(ValueError):
            validate_evidence(decision, "unrelated text")

    def test_store_migrations_and_entities(self):
        self.assertEqual(self.store.version(), "2")
        self.store.add_entity("PostgreSQL", ["Postgres", "PG"])
        self.assertEqual(self.store.resolve_entity("postgres"), "PostgreSQL")

    def test_hybrid_offline_fallback(self):
        text = "We decided to use PostgreSQL for the orders store. Nice weather today."
        extractor = HybridExtractor(recall=RegexExtractor(), parser=LLMExtractor(endpoint=None))
        decisions = extractor.extract(text, "a.md", "2026-01-10")
        self.assertEqual(len(decisions), 1)
        self.assertGreaterEqual(decisions[0].confidence, 0.9)
        self.assertTrue(validate_evidence(decisions[0], text))

    def test_fake_llm_enrichment(self):
        statement = "We decided to use PostgreSQL for the orders store."
        parser = FakeLLMExtractor({statement: {"owner": "alice", "rationale": "ACID needs"}})
        text = statement + " Nice weather today."
        decisions = HybridExtractor(parser=parser).extract(text, "a.md", "2026-01-10")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].owner, "alice")
        self.assertEqual(decisions[0].rationale, "ACID needs")

    def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            LLMExtractor("https://remote.example.com/v1/extract")

    def test_no_network_egress_in_fallback(self):
        original = socket.socket

        def blocked(*args, **kwargs):
            raise OSError("network disabled in tests")

        socket.socket = blocked
        self.addCleanup(setattr, socket, "socket", original)
        text = "We decided to use Redis for the cache."
        extractor = HybridExtractor(parser=LLMExtractor("http://127.0.0.1:9/extract"))
        decisions = extractor.extract(text, "a.md", "2026-01-10")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].statement, text)

    def test_quantization_roundtrip(self):
        embedder = HashingEmbedder(dim=32)
        vector = embedder.embed("rate limit 100 requests per minute")
        quantized, scale = quantize_int8(vector)
        restored = dequantize_int8(quantized, scale)
        self.assertEqual(len(quantized), 32)
        self.assertLessEqual(max(abs(a - b) for a, b in zip(vector, restored)), scale)
        self.assertEqual(unpack_int8(pack_int8(quantized)), quantized)

    def test_ivf_index_recall(self):
        embedder = HashingEmbedder(dim=32)
        texts = [
            "We decided to use PostgreSQL for orders",
            "We decided to use MongoDB for orders",
            "API rate limit is 100 per minute",
            "Deploy the service every Friday",
        ]
        items = [(str(i), embedder.embed(text)) for i, text in enumerate(texts)]
        index = IVFIndex(embedder, nlist=2, probes=2)
        index.build(items)
        self.assertEqual(index.query(items[0][1], k=1)[0][0], "0")
        restored = IVFIndex.from_rows(index.to_rows(), embedder, nlist=2, probes=2)
        self.assertEqual(restored.query(items[0][1], k=1)[0][0], "0")
        self.assertGreater(cosine(items[0][1], items[0][1]), 0.99)

    def test_nli_heuristic(self):
        classifier = HeuristicNLI()
        contradiction = classifier.classify(
            "We decided to deploy the orders service on Fridays.",
            "We agreed to stop deploying the orders service on Fridays.",
        )
        self.assertEqual(contradiction.label, "contradiction")
        unrelated = classifier.classify("We decided to use Redis for cache.", "The weather is nice today.")
        self.assertEqual(unrelated.label, "unrelated")

    def test_hash_pinned_artefact(self):
        artefact = os.path.join(self.tmp.name, "model.onnx")
        with open(artefact, "wb") as handle:
            handle.write(b"fake-model-bytes")
        digest = hashlib.sha256(b"fake-model-bytes").hexdigest()
        with self.assertRaises(ValueError):
            OnnxNLI(artefact, "0" * 64)
        model = OnnxNLI(artefact, digest)
        with self.assertRaises(RuntimeError):
            model.classify("a", "b")

    def test_review_queue(self):
        decision = Decision(statement="We decided to use Redis.", source="a.md", date="2026-01-10", confidence=0.5)
        self.store.upsert_decision(decision)
        queue = ReviewQueue(self.store)
        self.assertEqual(len(queue.pending()["decisions"]), 1)
        queue.accept(decision.id)
        self.assertEqual(self.store.labels_for(decision.id)[0][1], "accept")
        conflict = queue.record_conflict("a", "b", "option_swap", 0.7, "different options")
        self.assertEqual(len(queue.pending()["conflicts"]), 1)
        queue.resolve_conflict(conflict.id)
        self.assertEqual(len(queue.pending()["conflicts"]), 0)

    def test_evaluation_harness(self):
        report = evaluate(HybridExtractor(parser=None), load_golden())
        self.assertEqual(report["f1"], 1.0)
        self.assertEqual(report["fp"], 0)


if __name__ == "__main__":
    unittest.main()
