import json
import tempfile
import unittest
from pathlib import Path

from code_graph_export.d3_code_graph_html import graph_to_d3_graphdata, write_d3_force_html


class TestD3CodeGraphHtml(unittest.TestCase):
    def test_graph_to_d3_and_cross_file(self):
        graph = {
            "nodes": [
                {
                    "id": "a",
                    "labels": ["FUNCTION"],
                    "properties": {"name": "foo", "qualified_name": "foo", "path": "x/a.c"},
                },
                {
                    "id": "b",
                    "labels": ["FUNCTION"],
                    "properties": {"name": "bar", "qualified_name": "bar", "path": "y/b.c"},
                },
            ],
            "edges": [{"type": "CALLS", "src": "a", "dst": "b", "properties": {}}],
        }
        d = graph_to_d3_graphdata(graph, edge_types={"CALLS"})
        self.assertEqual(d["mode"], "full")
        self.assertEqual(len(d["nodes"]), 2)
        self.assertEqual(len(d["edges"]), 1)
        self.assertTrue(d["edges"][0].get("cross_file"))

    def test_write_html(self):
        graph = {
            "nodes": [
                {"id": "n1", "labels": ["FILE"], "properties": {"path": "f.c", "name": "f.c"}},
            ],
            "edges": [],
        }
        td = Path(tempfile.mkdtemp())
        try:
            outp = td / "g.html"
            write_d3_force_html(graph, str(outp), title="t")
            text = outp.read_text(encoding="utf-8")
            self.assertIn("var graphData =", text)
            self.assertIn("d3.forceSimulation", text)
            self.assertIn("<title>t</title>", text)
            # valid JSON embedded
            i = text.index("var graphData = ") + len("var graphData = ")
            j = text.index(";\nconst EDGE_COLOR", i)
            json.loads(text[i:j])
        finally:
            import shutil

            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
