import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass
class Decision:
    statement: str
    source: str
    date: str
    title: str = ""
    owner: str | None = None
    scope: str | None = None
    rationale: str | None = None
    alternatives: list = field(default_factory=list)
    status: str = "accepted"
    evidence_span: str = ""
    confidence: float = 0.0
    negated: bool = False
    id: str = ""
    embedding_id: str | None = None

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha1((self.source + "|" + self.statement).encode()).hexdigest()[:12]
        if not self.title:
            self.title = self.statement[:80]
        if not self.evidence_span:
            self.evidence_span = self.statement

    def to_row(self):
        return (
            self.id, self.source, self.date, self.title, self.statement, self.owner,
            self.scope, self.rationale, json.dumps(self.alternatives), self.status,
            self.evidence_span, self.confidence, int(self.negated), self.embedding_id,
        )

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row[0], source=row[1], date=row[2], title=row[3], statement=row[4],
            owner=row[5], scope=row[6], rationale=row[7],
            alternatives=json.loads(row[8]) if row[8] else [],
            status=row[9], evidence_span=row[10], confidence=row[11],
            negated=bool(row[12]), embedding_id=row[13],
        )

    def to_dict(self):
        return asdict(self)


@dataclass
class Conflict:
    id: str
    a: str
    b: str
    kind: str
    score: float
    explanation: str
    state: str = "proposed"


@dataclass
class Label:
    decision_id: str
    verdict: str
    reviewer: str
    ts: str


def validate_evidence(decision, source_text):
    if not decision.evidence_span or decision.evidence_span not in source_text:
        raise ValueError(f"evidence span not found in source for decision {decision.id}")
    return True
