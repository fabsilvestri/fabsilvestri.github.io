#!/usr/bin/env python3
"""Tests for the manual publication overlay in fetch_publications.py.

Hermetic — no DBLP fetch, no repo files touched. Each test seeds a fake
DBLP result list and a temporary data/manual_publications.yml, then
checks what apply_manual_overlay() merges, what it prunes, and what it
leaves behind in the YAML.

Run:  python3 scripts/test_manual_overlay.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_publications as fp  # noqa: E402

# Minimal stand-ins for the vendored ranking data, so the test doesn't
# move when CORE or Scimago is refreshed.
VENUES = {
    "conference_core_acronym": {},
    "journal_issn": {"tois": ["10468188"]},
    "journal_q1_override": set(),
}
CORE = {"SIGIR": {"rank": "A*", "title": "Int. ACM SIGIR Conf. on Research and Development in IR"}}
SCIMAGO = {"10468188": {"categories": [("Information Systems", 1)], "title": "ACM TOIS"}}
TOPICS = [
    {"slug": "ir", "name": "Information Retrieval",
     "compiled_patterns": [re.compile("retrieval|ranking", re.IGNORECASE)]},
    {"slug": "llm", "name": "LLMs",
     "compiled_patterns": [re.compile("language model", re.IGNORECASE)]},
    {"slug": fp.MISC_SLUG, "name": "Other", "compiled_patterns": []},
]

HEADER = "# overlay header comment — must survive a prune\n"

ADDITION_KEPT = """\
  # a comment on the kept entry
  - key:           manual/sigir/kept-2027
    title:         Neural Ranking Without DBLP
    authors:       ["A. Coauthor", "Fabrizio Silvestri"]
    year:          2027
    venue:         SIGIR
    venue_short:   SIGIR
    url_publisher: https://doi.org/10.1145/1111111.1111111
"""

ADDITION_STALE = """\
  - key:           manual/sigir/stale-2026
    title:         A Paper DBLP Has Just Indexed
    authors:       ["F. Silvestri"]
    year:          2026
    venue:         SIGIR
    venue_short:   SIGIR
    type:          a_star_conf
"""


def dblp_pub(key, title, ptype, **extra):
    """A record shaped like parse_record() + main() produce."""
    rec = {
        "key": key, "title": title, "authors": ["F. Silvestri"], "year": 2026,
        "venue": "CoRR" if ptype == fp.TYPE_PREPRINT else "SIGIR",
        "venue_short": "arXiv" if ptype == fp.TYPE_PREPRINT else "SIGIR",
        "url": None, "url_publisher": None, "url_arxiv": None,
        "type": ptype, "topics": ["ir"], "citations": 0,
    }
    rec.update(extra)
    if rec["url"] is None:
        rec["url"] = rec["url_publisher"] or rec["url_arxiv"]
    return rec


class OverlayTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "manual_publications.yml"

    def write_overlay(self, additions="[]", overrides="{}"):
        self.path.write_text(
            HEADER + "additions:" + ("\n" + additions if additions != "[]" else " []\n")
            + "overrides:" + ("\n" + overrides if overrides != "{}" else " {}\n"),
            encoding="utf-8",
        )

    def run_overlay(self, pubs, prune=True, citations=None):
        err = io.StringIO()
        with redirect_stderr(err):
            merged = fp.apply_manual_overlay(
                pubs, self.path, VENUES, CORE, SCIMAGO, TOPICS, {},
                citations or {}, prune=prune,
            )
        return merged, err.getvalue()

    def titles(self, pubs):
        return [p["title"] for p in pubs]

    # -- additions ------------------------------------------------------

    def test_addition_is_merged_and_classified(self):
        self.write_overlay(additions=ADDITION_KEPT)
        merged, err = self.run_overlay([], citations={"manual/sigir/kept-2027": 7})
        self.assertEqual(len(merged), 1)
        rec = merged[0]
        self.assertEqual(list(rec), fp.RECORD_FIELDS)  # same shape as a DBLP record
        # Type came from CORE via the key's venue abbreviation, topics
        # from data/topics.yml patterns — the DBLP classification path.
        self.assertEqual(rec["type"], fp.TYPE_A_STAR)
        self.assertEqual(rec["topics"], ["ir"])
        self.assertEqual(rec["authors"], ["A. Coauthor", "F. Silvestri"])
        self.assertEqual(rec["url"], "https://doi.org/10.1145/1111111.1111111")
        self.assertEqual(rec["citations"], 7)  # citations.json wins
        self.assertNotIn("pruned", err)
        self.assertIn(HEADER, self.path.read_text())

    def test_addition_pruned_when_dblp_indexes_it(self):
        self.write_overlay(additions=ADDITION_KEPT + ADDITION_STALE)
        dblp = [dblp_pub("conf/sigir/Silvestri26",
                         "A paper DBLP has, just indexed.", fp.TYPE_A_STAR)]
        merged, err = self.run_overlay(dblp)

        self.assertIn(
            '[manual] pruned addition "A Paper DBLP Has Just Indexed", '
            'DBLP now has it as conf/sigir/Silvestri26', err)
        # Gone from the output …
        self.assertEqual(self.titles(merged),
                         ["A paper DBLP has, just indexed.", "Neural Ranking Without DBLP"])
        blob = json.dumps({"publications": merged}, ensure_ascii=False)
        self.assertNotIn("A Paper DBLP Has Just Indexed", blob)
        self.assertNotIn("manual/sigir/stale-2026", blob)
        # … and gone from the YAML, with comments and the other entry intact.
        text = self.path.read_text()
        self.assertNotIn("manual/sigir/stale-2026", text)
        self.assertIn("manual/sigir/kept-2027", text)
        self.assertIn(HEADER, text)
        self.assertIn("# a comment on the kept entry", text)

    def test_prune_keeps_the_prose_that_follows_the_last_entry(self):
        # ruamel parks a trailing comment block on the entry above it, so
        # a naive delete of the last addition takes the next section's
        # documentation with it.
        self.path.write_text(
            HEADER + "additions:\n" + ADDITION_KEPT + ADDITION_STALE
            + "\n# ==== a documentation block between the two sections ====\n"
            + "# second line\n" + "overrides: {}\n",
            encoding="utf-8",
        )
        dblp = [dblp_pub("conf/sigir/Silvestri26",
                         "A Paper DBLP Has Just Indexed", fp.TYPE_A_STAR)]
        self.run_overlay(dblp)
        text = self.path.read_text()
        self.assertIn("# ==== a documentation block between the two sections ====", text)
        self.assertIn("# second line", text)
        self.assertIn("# a comment on the kept entry", text)
        self.assertIn(HEADER, text)
        self.assertNotIn("manual/sigir/stale-2026", text)

    def test_pruning_the_first_entry_keeps_the_next_ones_comment(self):
        self.write_overlay(additions=ADDITION_STALE + ADDITION_KEPT)
        dblp = [dblp_pub("conf/sigir/Silvestri26",
                         "A Paper DBLP Has Just Indexed", fp.TYPE_A_STAR)]
        self.run_overlay(dblp)
        text = self.path.read_text()
        self.assertIn("# a comment on the kept entry", text)
        self.assertIn("manual/sigir/kept-2027", text)
        self.assertNotIn("manual/sigir/stale-2026", text)

    def test_unparseable_yaml_is_skipped_not_fatal(self):
        self.path.write_text("additions:\n  - title: Broken: Title\n", encoding="utf-8")
        merged, err = self.run_overlay([dblp_pub("conf/sigir/X26", "Untouched", fp.TYPE_A_STAR)])
        self.assertIn("could not be parsed", err)
        self.assertEqual(self.titles(merged), ["Untouched"])

    def test_no_prune_leaves_the_yaml_alone(self):
        self.write_overlay(additions=ADDITION_STALE)
        before = self.path.read_text()
        dblp = [dblp_pub("conf/sigir/Silvestri26",
                         "A Paper DBLP Has Just Indexed", fp.TYPE_A_STAR)]
        merged, err = self.run_overlay(dblp, prune=False)
        self.assertIn("--no-prune", err)
        self.assertEqual(len(merged), 1)  # still kept out of the output
        self.assertEqual(self.path.read_text(), before)

    def test_bad_addition_is_skipped_not_fatal(self):
        self.write_overlay(additions="  - key: conf/sigir/NotSynthetic\n    title: Nope\n")
        merged, err = self.run_overlay([])
        self.assertEqual(merged, [])
        self.assertIn("must start with 'manual/'", err)

    # -- overrides ------------------------------------------------------

    OVERRIDE = """\
  journals/corr/abs-2501-01234:
    title:         Retrieval With Language Models
    venue:         SIGIR
    venue_short:   SIGIR
    type:          a_star_conf
    year:          2026
    url_publisher: https://doi.org/10.1145/2222222.2222222
"""

    def corr_pub(self):
        return dblp_pub(
            "journals/corr/abs-2501-01234", "Retrieval With Language Models",
            fp.TYPE_PREPRINT, year=2025,
            url_arxiv="https://arxiv.org/abs/2501.01234",
            url="https://arxiv.org/abs/2501.01234", topics=["ir"],
        )

    def test_override_patches_fields_and_keeps_arxiv(self):
        self.write_overlay(overrides=self.OVERRIDE)
        pubs = [self.corr_pub()]
        merged, err = self.run_overlay(pubs)
        rec = merged[0]
        self.assertEqual(rec["type"], fp.TYPE_A_STAR)
        self.assertEqual((rec["venue"], rec["venue_short"], rec["year"]),
                         ("SIGIR", "SIGIR", 2026))
        self.assertEqual(rec["url_arxiv"], "https://arxiv.org/abs/2501.01234")
        self.assertEqual(rec["url"], "https://doi.org/10.1145/2222222.2222222")
        self.assertEqual(sorted(rec["topics"]), ["ir", "llm"])  # re-derived
        self.assertNotIn("pruned", err)  # kept, silently
        self.assertIn("journals/corr/abs-2501-01234", self.path.read_text())

    def test_override_pruned_when_dblp_publishes_the_paper(self):
        self.write_overlay(overrides=self.OVERRIDE)
        pubs = [self.corr_pub(),
                dblp_pub("conf/sigir/Silvestri26",
                         "Retrieval with language models!", fp.TYPE_A_STAR)]
        merged, err = self.run_overlay(pubs)
        self.assertIn("[manual] pruned override journals/corr/abs-2501-01234, "
                      "superseded by conf/sigir/Silvestri26", err)
        self.assertNotIn("journals/corr/abs-2501-01234", self.path.read_text())
        self.assertIn(HEADER, self.path.read_text())
        # The CoRR record is left exactly as DBLP reported it.
        self.assertEqual(merged[0]["type"], fp.TYPE_PREPRINT)
        self.assertEqual(merged[0]["venue"], "CoRR")

    def test_override_pruned_when_corr_key_disappears(self):
        self.write_overlay(overrides=self.OVERRIDE)
        pubs = [dblp_pub("conf/sigir/Silvestri26",
                         "Retrieval With Language Models", fp.TYPE_A_STAR)]
        _, err = self.run_overlay(pubs)
        self.assertIn("[manual] pruned override journals/corr/abs-2501-01234, "
                      "superseded by conf/sigir/Silvestri26", err)
        self.assertNotIn("journals/corr/abs-2501-01234", self.path.read_text())

    def test_override_on_unknown_key_warns_and_carries_on(self):
        self.write_overlay(overrides=self.OVERRIDE)
        merged, err = self.run_overlay([])  # DBLP knows nothing at all
        self.assertEqual(merged, [])
        self.assertIn("targets a DBLP key that is not in the current results", err)
        self.assertIn("journals/corr/abs-2501-01234", self.path.read_text())

    def test_override_pruned_when_dblp_retypes_the_key(self):
        self.write_overlay(overrides=self.OVERRIDE)
        pubs = [dblp_pub("journals/corr/abs-2501-01234",
                         "Retrieval With Language Models", fp.TYPE_A_STAR)]
        _, err = self.run_overlay(pubs)
        self.assertIn("[manual] pruned override journals/corr/abs-2501-01234, "
                      "superseded by journals/corr/abs-2501-01234", err)
        self.assertNotIn("journals/corr/abs-2501-01234", self.path.read_text())

    # -- idempotence ----------------------------------------------------

    def test_second_run_prunes_nothing_and_is_stable(self):
        self.write_overlay(additions=ADDITION_KEPT + ADDITION_STALE,
                           overrides=self.OVERRIDE)
        pubs = [dblp_pub("conf/sigir/Silvestri26",
                         "A Paper DBLP Has Just Indexed", fp.TYPE_A_STAR),
                self.corr_pub()]
        first, _ = self.run_overlay([dict(p) for p in pubs])
        after_first = self.path.read_text()
        second, err = self.run_overlay([dict(p) for p in pubs])
        self.assertEqual(self.path.read_text(), after_first)  # byte-identical
        self.assertNotIn("pruned", err)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
