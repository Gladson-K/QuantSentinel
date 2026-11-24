import os
import socket
import tempfile
import unittest

from acl import filter_decisions, visible_documents
from connectors import Document, github_connector, slack_connector
from pipeline import Pipeline
from sync import SyncState, sync_once
from threads import ThreadAssembler


class V3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.v2_path = os.path.join(self.tmp.name, "v2.db")
        self.v3_path = os.path.join(self.tmp.name, "v3.db")

    def test_connector_contract(self):
        connector = github_connector()
        self.assertTrue(connector.authorize())
        items, cursor = connector.list_changes(0)
        self.assertEqual(len(items), 3)
        self.assertEqual(cursor, 3)
        raw = connector.fetch(items[0])
        document = connector.to_document(raw)
        self.assertIsInstance(document, Document)
        self.assertEqual(document.source, "github")
        self.assertEqual(document.acl, ("engineering",))
        self.assertTrue(document.url.startswith("https://github.example/"))
        self.assertEqual(document.thread_id, "gh-thread-1")

    def test_sync_incremental_and_idempotent(self):
        state = SyncState(self.v3_path)
        connector = github_connector()
        self.assertEqual(len(sync_once(connector, state, state.save_document)), 3)
        self.assertEqual(state.get_cursor("github"), 3)
        self.assertEqual(len(sync_once(connector, state, state.save_document)), 0)
        self.assertEqual(len(state.list_documents()), 3)
        sync_once(connector, state, state.save_document, backfill=True)
        self.assertEqual(len(state.list_documents()), 3)

    def test_dead_letter(self):
        state = SyncState(self.v3_path)

        def failing(document):
            raise ValueError("handler failed")

        sync_once(github_connector(), state, handler=failing)
        self.assertEqual(len(state.list_dead()), 3)
        self.assertEqual(state.get_cursor("github"), 3)

    def test_thread_assembly(self):
        state = SyncState(self.v3_path)
        sync_once(slack_connector(), state, state.save_document)
        threads = {thread.thread_id: thread for thread in ThreadAssembler().group(state.list_documents())}
        thread = threads["slack:sl-thread-2"]
        self.assertEqual(len(thread.documents), 2)
        self.assertEqual(thread.participants, ["erin", "frank"])
        self.assertIn("thumbsup", thread.reactions)

    def test_pipeline_end_to_end(self):
        result = Pipeline(self.v2_path, self.v3_path).run()
        self.assertGreater(len(result["documents"]), 0)
        self.assertGreater(len(result["decisions"]), 0)
        self.assertGreater(len(result["merged"]), 0)
        for decision in result["decisions"]:
            self.assertTrue(decision.evidence_span)

    def test_dedup_merge_and_undo(self):
        pipeline = Pipeline(self.v2_path, self.v3_path)
        result = pipeline.run()
        merge_id = result["merged"][0][2]
        self.assertTrue(any(row[0] == merge_id and not row[5] for row in pipeline.state.list_merges()))
        pipeline.state.undo_merge(merge_id)
        self.assertTrue(all(row[5] for row in pipeline.state.list_merges() if row[0] == merge_id))

    def test_acl_no_leak(self):
        pipeline = Pipeline(self.v2_path, self.v3_path)
        result = pipeline.run()
        leadership_urls = {doc.url for doc in result["documents"] if "leadership" in doc.acl}
        engineering = visible_documents(result["documents"], ["engineering"])
        self.assertTrue(leadership_urls.isdisjoint({doc.url for doc in engineering}))
        visible = pipeline.query(["engineering"])
        statements = {decision.statement for decision in visible}
        self.assertNotIn("Decision: API rate limit is 300 requests per minute.", statements)
        self.assertEqual(len(filter_decisions(result["decisions"], pipeline.state, ["leadership"])), 2)

    def test_no_network_egress(self):
        original = socket.socket

        def blocked(*args, **kwargs):
            raise OSError("network disabled in tests")

        socket.socket = blocked
        self.addCleanup(setattr, socket, "socket", original)
        result = Pipeline(self.v2_path, self.v3_path).run()
        self.assertGreater(len(result["decisions"]), 0)


if __name__ == "__main__":
    unittest.main()
