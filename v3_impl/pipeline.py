from acl import filter_decisions
from connectors import github_connector, slack_connector
from dedup import merge_duplicates
from extractors import FakeLLMExtractor, HybridExtractor
from store import Store
from sync import SyncState, sync_once
from threads import ThreadAssembler
from vectors import HashingEmbedder


class Pipeline:
    def __init__(self, v2_path=None, v3_path=None):
        self.store = Store(v2_path)
        self.state = SyncState(v3_path)
        self.embedder = HashingEmbedder()
        self.extractor = HybridExtractor(parser=FakeLLMExtractor())
        self.assembler = ThreadAssembler()

    def run(self, connectors=None):
        connectors = connectors if connectors is not None else [github_connector(), slack_connector()]
        for connector in connectors:
            sync_once(connector, self.state, handler=self.state.save_document)
        decisions = []
        for thread in self.assembler.group(self.state.list_documents()):
            for decision in self.extractor.extract(thread.text, thread.source, thread.first_ts):
                self.store.upsert_decision(decision)
                for document in thread.documents:
                    self.state.add_evidence(
                        decision.id, document.url, document.source, document.thread_id, decision.evidence_span[:80]
                    )
                decisions.append(decision)
        merged = merge_duplicates(self.store, self.state, decisions, self.embedder)
        return {
            "decisions": decisions,
            "merged": merged,
            "documents": self.state.list_documents(),
            "dead_letters": self.state.list_dead(),
        }

    def query(self, groups):
        return filter_decisions(self.store.list_decisions(), self.state, groups)
