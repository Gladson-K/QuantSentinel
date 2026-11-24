import json
import os


def load_golden(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "golden.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def evaluate(extractor, cases):
    true_positive = false_positive = false_negative = 0
    for case in cases:
        decisions = extractor.extract(case["text"], case.get("source", "golden"), case.get("date", "2026-01-01"))
        predicted = {d.statement for d in decisions}
        expected = set(case["expected"])
        true_positive += len(predicted & expected)
        false_positive += len(predicted - expected)
        false_negative += len(expected - predicted)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": true_positive, "fp": false_positive, "fn": false_negative}
