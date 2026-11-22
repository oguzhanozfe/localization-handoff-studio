import json
from pathlib import Path
import unittest

from pipeline import prepare, export


def fixture():
    return json.loads(
        Path(__file__).with_name("example.json").read_text(encoding="utf-8")
    )


class PipelineTests(unittest.TestCase):
    def test_apply_forms_and_queue_glossary(self):
        d = fixture()
        r = prepare(d)
        out = export(d, r, r["candidates"])
        de = json.loads(out["de-DE.json"])
        queue = json.loads(out["repair-queue.json"])
        self.assertEqual(de["hud.gems"]["one"], "{count} Kristall")
        self.assertIn("legacy.tip", de)
        self.assertEqual([i["key"] for i in queue["tasks"]], ["hud.exit"])

    def test_deselection_keeps_source_translation(self):
        d = fixture()
        r = prepare(d)
        self.assertEqual(json.loads(export(d, r, [])["de-DE.json"]), d["target"])
        self.assertFalse(any(c["key"] == "hud.sync" for c in r["candidates"]))

    def test_bad_proposed_fix_queued_and_positional_order_matters(self):
        d = fixture()
        d["source"]["hud.cost"] = "%d paid for %s"
        d["target"]["hud.cost"] = "%s kostet %d"
        d["repairs"]["hud.greeting"] = "Hallo, {owner}."
        r = prepare(d)
        cs = {c["key"]: c for c in r["candidates"]}
        self.assertEqual(cs["hud.greeting"]["kind"], "queue")
        self.assertEqual(cs["hud.cost"]["kind"], "queue")

    def test_reject_invalid_source_syntax_or_locale(self):
        d = fixture()
        d["source"]["hud.greeting"] = "Hello {name"
        with self.assertRaises(ValueError):
            prepare(d)
        d = fixture()
        d["locale"] = "../de"
        with self.assertRaises(ValueError):
            prepare(d)


if __name__ == "__main__":
    unittest.main()
