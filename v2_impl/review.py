import datetime
import hashlib

from schemas import Conflict


class ReviewQueue:
    def __init__(self, store):
        self.store = store

    def pending(self):
        low_confidence = [d for d in self.store.list_decisions() if d.confidence < 0.8]
        proposed = self.store.list_conflicts(state="proposed")
        return {"decisions": low_confidence, "conflicts": proposed}

    def accept(self, decision_id, reviewer="local"):
        self.store.add_label(decision_id, "accept", reviewer)
        return self.store.get_decision(decision_id)

    def reject(self, decision_id, reviewer="local"):
        self.store.add_label(decision_id, "reject", reviewer)
        return self.store.get_decision(decision_id)

    def edit(self, decision_id, statement, reviewer="local"):
        self.store.update_statement(decision_id, statement)
        self.store.add_label(decision_id, "edit", reviewer)
        return self.store.get_decision(decision_id)

    def record_conflict(self, a, b, kind, score, explanation):
        conflict_id = hashlib.sha1((a + "|" + b + "|" + kind).encode()).hexdigest()[:12]
        conflict = Conflict(conflict_id, a, b, kind, score, explanation)
        self.store.add_conflict(conflict)
        return conflict

    def resolve_conflict(self, conflict_id, state="resolved"):
        self.store.set_conflict_state(conflict_id, state)


def now_utc():
    return datetime.datetime.now(datetime.UTC).isoformat()
