import os
import tempfile
import unittest

import decisiongraph as dg

SAMPLE_NOTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_notes")


class V1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        dg.set_db(os.path.join(self.tmp.name, "v1.db"))

    def test_extract(self):
        found = dg.extract("We decided to use Redis for cache. Nice weather today.")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][1], 0.9)

    def test_pipeline(self):
        dg.ingest(SAMPLE_NOTES)
        kinds = {finding["kind"] for finding in dg.conflicts()}
        self.assertIn("option_swap", kinds)
        self.assertIn("number_change", kinds)
        self.assertIn("polarity_flip", kinds)

    def test_incremental(self):
        dg.ingest(SAMPLE_NOTES)
        self.assertEqual(len(dg.load()), 6)
        dg.ingest(SAMPLE_NOTES)
        self.assertEqual(len(dg.load()), 6)

    def test_report(self):
        dg.ingest(SAMPLE_NOTES)
        out = os.path.join(self.tmp.name, "report.md")
        dg.main(["report", "--out", out])
        with open(out, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("option_swap", body)
        self.assertIn("number_change", body)
        self.assertIn("polarity_flip", body)


if __name__ == "__main__":
    unittest.main()
