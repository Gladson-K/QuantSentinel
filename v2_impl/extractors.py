import hashlib
import json
import os
from urllib.parse import urlparse

import decisiongraph as dg

from schemas import Decision, validate_evidence

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def chunk_text(text, max_chars=800):
    chunks = []
    current = []
    size = 0
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if size + len(paragraph) > max_chars and current:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


class RegexExtractor:
    name = "regex"

    def extract(self, text, source, date):
        result = []
        for sentence, confidence in dg.extract(text):
            decision = Decision(
                statement=sentence,
                source=source,
                date=date,
                confidence=confidence,
                evidence_span=sentence,
                negated=bool(dg.NEG.search(sentence)),
            )
            validate_evidence(decision, text)
            result.append(decision)
        return result


class FakeLLMExtractor:
    name = "fake-llm"

    def __init__(self, enrichments=None):
        self.enrichments = enrichments or {}

    def extract(self, text, source, date):
        result = []
        for sentence, confidence in dg.extract(text):
            payload = self.enrichments.get(sentence, {})
            decision = Decision(
                statement=payload.get("statement", sentence),
                source=source,
                date=date,
                title=payload.get("title", ""),
                owner=payload.get("owner"),
                scope=payload.get("scope"),
                rationale=payload.get("rationale"),
                alternatives=payload.get("alternatives", []),
                status=payload.get("status", "accepted"),
                evidence_span=payload.get("evidence_span", sentence),
                confidence=payload.get("confidence", max(confidence, 0.9)),
                negated=payload.get("negated", bool(dg.NEG.search(sentence))),
            )
            validate_evidence(decision, text)
            result.append(decision)
        return result


class LLMExtractor:
    name = "llm"

    def __init__(self, endpoint=None, timeout=5):
        self.endpoint = endpoint or os.environ.get("DG_LLM_ENDPOINT")
        self.timeout = timeout
        if self.endpoint:
            parsed = urlparse(self.endpoint)
            if parsed.scheme not in ("http", "https") or parsed.hostname not in LOOPBACK_HOSTS:
                raise ValueError("only loopback LLM endpoints are allowed")

    def extract(self, text, source, date):
        if not self.endpoint:
            raise RuntimeError("offline: no local LLM endpoint configured")
        from urllib.request import Request, urlopen

        payload = json.dumps(
            {"text": text, "source": source, "date": date, "schema": "decision-v2"}
        ).encode("utf-8")
        request = Request(self.endpoint, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        result = []
        for item in body.get("decisions", []):
            decision = Decision(
                statement=item["statement"], source=source, date=date,
                title=item.get("title", ""), owner=item.get("owner"),
                scope=item.get("scope"), rationale=item.get("rationale"),
                alternatives=item.get("alternatives", []), status=item.get("status", "accepted"),
                evidence_span=item["evidence_span"], confidence=float(item.get("confidence", 0.9)),
                negated=bool(item.get("negated", False)),
            )
            validate_evidence(decision, text)
            result.append(decision)
        return result


class HybridExtractor:
    def __init__(self, recall=None, parser=None, cache=None):
        self.recall = recall or RegexExtractor()
        self.parser = parser
        self.cache = cache if cache is not None else {}

    def extract(self, text, source, date):
        result = []
        for chunk in chunk_text(text):
            key = hashlib.sha1((self.parser_name + "|" + chunk).encode()).hexdigest()
            if key in self.cache:
                result.extend(self.cache[key])
                continue
            candidates = self.recall.extract(chunk, source, date)
            if not candidates:
                self.cache[key] = []
                continue
            decisions = candidates
            if self.parser is not None:
                try:
                    decisions = self.parser.extract(chunk, source, date)
                except Exception:
                    decisions = candidates
            validated = []
            for decision in decisions:
                try:
                    validate_evidence(decision, chunk)
                    validated.append(decision)
                except ValueError:
                    continue
            self.cache[key] = validated
            result.extend(validated)
        return result

    @property
    def parser_name(self):
        return getattr(self.parser, "name", "none")
