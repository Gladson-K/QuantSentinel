import hashlib
from dataclasses import dataclass

import decisiongraph as dg

ALLOWED_SUFFIXES = (".onnx", ".safetensors")


@dataclass
class Verdict:
    label: str
    score: float
    explanation: str


class HeuristicNLI:
    name = "heuristic-nli"

    def classify(self, left, right):
        left_tokens, right_tokens = set(dg.tokens(left)), set(dg.tokens(right))
        union = left_tokens | right_tokens
        overlap = len(left_tokens & right_tokens) / len(union) if union else 0.0
        left_negated = bool(dg.NEG.search(left))
        right_negated = bool(dg.NEG.search(right))
        if overlap >= 0.3 and left_negated != right_negated:
            return Verdict("contradiction", round(0.5 + overlap / 2, 3), "negation differs with shared topic")
        if overlap >= 0.6 and left_negated == right_negated:
            return Verdict("entailment", round(overlap, 3), "high lexical overlap with matching polarity")
        return Verdict("unrelated", round(overlap, 3), "insufficient shared topic")


class OnnxNLI:
    name = "onnx-nli"

    def __init__(self, artefact_path, expected_sha256):
        if not artefact_path.lower().endswith(ALLOWED_SUFFIXES):
            raise ValueError("model artefact must be .onnx or .safetensors")
        self.artefact_path = artefact_path
        self.expected_sha256 = expected_sha256.lower()
        with open(artefact_path, "rb") as handle:
            actual = hashlib.sha256(handle.read()).hexdigest()
        if actual != self.expected_sha256:
            raise ValueError(f"model artefact hash mismatch: {actual}")

    def classify(self, left, right):
        raise RuntimeError("ONNX runtime is not enabled; provide a hash-pinned artefact and approved runtime")


def classify_pairs(pairs, classifier=None):
    classifier = classifier or HeuristicNLI()
    results = []
    for a, b in pairs:
        verdict = classifier.classify(a, b)
        results.append((a, b, verdict))
    return results
