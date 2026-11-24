import hashlib
from datetime import date

from vectors import cosine


def _date(value):
    return date.fromisoformat(value[:10])


def find_duplicates(decisions, embedder, threshold=0.85, window_days=7):
    pairs = []
    for i in range(len(decisions)):
        for j in range(i + 1, len(decisions)):
            left, right = decisions[i], decisions[j]
            if abs((_date(left.date) - _date(right.date)).days) > window_days:
                continue
            similarity = cosine(embedder.embed(left.statement), embedder.embed(right.statement))
            if left.statement.strip() == right.statement.strip() or similarity >= threshold:
                pairs.append((left, right, similarity))
    return pairs


def merge_duplicates(store, state, decisions, embedder, threshold=0.85):
    merged = []
    for left, right, similarity in find_duplicates(decisions, embedder, threshold):
        canonical, duplicate = (left, right) if left.date <= right.date else (right, left)
        merge_id = hashlib.sha1((canonical.id + "|" + duplicate.id).encode()).hexdigest()[:12]
        reason = f"duplicate across sources ({duplicate.source}), similarity {similarity:.3f}"
        state.record_merge(merge_id, canonical.id, duplicate.id, reason)
        store.add_merge(merge_id, canonical.id, duplicate.id, reason)
        for item in state.evidence_for(duplicate.id):
            state.add_evidence(canonical.id, item["url"], item["source"], item["thread_id"], item["span"])
        merged.append((canonical, duplicate, merge_id))
    return merged
