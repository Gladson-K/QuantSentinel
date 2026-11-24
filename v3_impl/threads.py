from dataclasses import dataclass, field
from datetime import date


@dataclass
class Thread:
    thread_id: str
    text: str
    source: str = ""
    participants: list = field(default_factory=list)
    reactions: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    first_ts: str = ""
    last_ts: str = ""


class ThreadAssembler:
    def __init__(self, window_days=7):
        self.window_days = window_days

    def group(self, documents):
        groups = {}
        for document in documents:
            groups.setdefault((document.source, document.thread_id), []).append(document)
        threads = []
        for (source, thread_id), items in sorted(groups.items()):
            items.sort(key=lambda item: (item.ts, item.item_id))
            buckets = [[items[0]]]
            for item in items[1:]:
                gap = (date.fromisoformat(item.ts) - date.fromisoformat(buckets[-1][-1].ts)).days
                if gap > self.window_days:
                    buckets.append([item])
                else:
                    buckets[-1].append(item)
            for bucket in buckets:
                threads.append(
                    Thread(
                        thread_id=f"{source}:{thread_id}",
                        source=source,
                        text="\n\n".join(item.text for item in bucket),
                        participants=sorted({item.author for item in bucket}),
                        reactions=sorted({reaction for item in bucket for reaction in item.reactions}),
                        documents=bucket,
                        first_ts=bucket[0].ts,
                        last_ts=bucket[-1].ts,
                    )
                )
        return threads
