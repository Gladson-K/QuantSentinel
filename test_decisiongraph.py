import os, tempfile, unittest, importlib
os.environ["DG_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
dg = importlib.import_module("decisiongraph")
class T(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(len(dg.extract("We decided to use Redis for cache. Nice weather today.")), 1)
    def test_pipeline(self):
        dg.ingest("sample_notes")
        kinds = {f["kind"] for f in dg.conflicts()}
        self.assertIn("option_swap", kinds); self.assertIn("number_change", kinds)
        self.assertIn("polarity_flip", kinds)
    def test_incremental(self):
        dg.ingest("sample_notes"); self.assertEqual(len(dg.load()), 6)
unittest.main()
