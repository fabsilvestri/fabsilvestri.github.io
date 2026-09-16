#!/usr/bin/env python3
"""Fetch Fabrizio Silvestri's publications from OpenAlex and classify them.

Records come from the OpenAlex works API, filtered to the author's
OpenAlex id and ORCID. Conferences are ranked against CORE
(data/core_rankings.csv); journals are ranked against Scimago
(data/scimago_journal_rank.csv), joined on the ISSN OpenAlex reports.
The venue→CORE acronym and venue→ISSN mappings live in data/venues.yml,
together with the patterns that recover a venue abbreviation from the
prose venue names OpenAlex uses. Topic tagging lives in data/topics.yml.
data/manual_publications.yml is a manual overlay merged in after the
fetch, for papers OpenAlex has not indexed yet; it prunes itself once
OpenAlex catches up. Outputs are written to data/publications.json
(fetched at runtime by assets/js/publications.js with cache: 'no-store'
so counters and the publication list always reflect the latest run).

This script previously read DBLP, which now serves an interstitial bot
check to every automated client and has no machine-readable route round
it. OpenAlex is an open API with no such gate, and a run this small sits
well inside its anonymous polite pool, so there is no key to configure;
$OPENALEX_API_KEY is honoured if one is ever needed.

Dependencies: PyYAML + ruamel.yaml (pip install -r scripts/requirements.txt).
Run locally:  python3 scripts/fetch_publications.py
              python3 scripts/fetch_publications.py --no-prune   # dry run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import os
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
import yaml

# OpenAlex author identity. The id and the ORCID are queried as two
# separate filters and unioned: OpenAlex splits an author across several
# ids as it disambiguates, and the ORCID catches records that landed on
# a split profile before it was merged back.
OPENALEX_AUTHOR_ID = "A5044165871"
OPENALEX_ORCID = "0000-0001-7669-9055"
OPENALEX_AUTHOR_NAME = "Fabrizio Silvestri"
# How the author's name is spelled across the records that carry it.
# Compared against a name stripped to lowercase ASCII letters, so
# "Silvestri, Fabrizio" and "F. Silvestri" both land in this set.
AUTHOR_NAME_FORMS = {
    "fabrizio silvestri", "silvestri fabrizio", "f silvestri", "silvestri f",
}
# Co-authors a work must share with the confirmed set before a record
# found only by name is accepted as his. Two is enough to be decisive —
# there are several other researchers named F. Silvestri, and none of
# them co-publish with two of his collaborators at once — while staying
# loose enough for a three-author paper.
MIN_SHARED_COAUTHORS = 2
OPENALEX_API = "https://api.openalex.org/works"
CROSSREF_API = "https://api.crossref.org/works/"
CONTACT_EMAIL = "fabrizio.silvestri@uniroma1.it"  # OpenAlex/Crossref polite pool
OPENALEX_PAGE_SIZE = 200  # the API maximum
USER_AGENT = "fabsilvestri-homepage/1.0 (+https://fabsilvestri.github.io)"

ROOT = Path(__file__).resolve().parent.parent
VENUES_FILE = ROOT / "data" / "venues.yml"
TOPICS_FILE = ROOT / "data" / "topics.yml"
CORE_FILE = ROOT / "data" / "core_rankings.csv"
SCIMAGO_FILE = ROOT / "data" / "scimago_journal_rank.csv"
CITATIONS_FILE = ROOT / "data" / "citations.json"
AWARDS_FILE = ROOT / "data" / "awards.yml"
TALKS_FILE = ROOT / "data" / "talks.yml"
MANUAL_FILE = ROOT / "data" / "manual_publications.yml"
OUT_JSON = ROOT / "data" / "publications.json"
OUT_SITEMAP = ROOT / "sitemap.xml"
OUT_SITEMAP_INDEX = ROOT / "sitemap_index.xml"
INDEX_HTML = ROOT / "index.html"
SITE_URL = "https://fabsilvestri.github.io/"

# Assets whose `?v=...` query string is set to a content hash of the file
# itself. Browsers cache them aggressively (max-age=600 on GH Pages, then
# revalidated by ETag); changing the URL forces a refetch the moment the
# file actually changes — whether by this script, a manual edit, or any
# other workflow. publications.json is intentionally NOT versioned: it's
# fetched at runtime with cache: 'no-store' by publications.js.
CACHE_BUSTED_ASSETS = [
    "assets/js/publications.js",
    "assets/js/analytics.js",
    "assets/css/style.css",
]

# Length of the truncated content-hash suffix. 10 hex chars = 40 bits =
# collision-resistant for the four-file scope here; short enough that the
# bumped index.html diff is one byte-stable line per asset.
CACHE_BUSTER_HASH_LEN = 10


def content_hash(path: Path) -> str:
    """SHA-256 of the file truncated to CACHE_BUSTER_HASH_LEN hex chars."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:CACHE_BUSTER_HASH_LEN]


def bump_cache_busters(root: Path, index_html: Path, assets: list[str]) -> bool:
    """Rewrite each `<asset>?v=...` reference in index_html to use the
    asset's current content hash. Returns True if index.html changed.

    The query string accepts either an old date stamp (YYYY-MM-DD) or a
    hex hash — both formats coexist during the migration. Missing assets
    are skipped with a warning rather than raising; the script is safe to
    run from a partial checkout."""
    if not index_html.exists():
        return False
    html = index_html.read_text(encoding="utf-8")
    new_html = html
    for asset in assets:
        asset_path = root / asset
        if not asset_path.exists():
            print(f"[warn] cache-buster: {asset} not found, skipping", file=sys.stderr)
            continue
        digest = content_hash(asset_path)
        # Match the asset path optionally followed by ?v=<anything-not-
        # whitespace-or-quote-or-amp>. This deliberately tolerates the
        # legacy YYYY-MM-DD format so the first run after migration
        # rewrites every reference to a hash without manual prep.
        new_html = re.sub(
            re.escape(asset) + r"(\?v=[^\s\"'&<>]*)?",
            f"{asset}?v={digest}",
            new_html,
        )
    if new_html != html:
        index_html.write_text(new_html, encoding="utf-8")
        return True
    return False

TYPE_A_STAR = "a_star_conf"
TYPE_Q1 = "q1_journal"
TYPE_OTHER_CONF = "other_conf"
TYPE_OTHER_JOURNAL = "other_journal"
TYPE_WORKSHOP = "workshop"
TYPE_PREPRINT = "preprint"

# Display-name overrides for venue abbreviations. Anything not in this map
# is uppercased (e.g. "sigir" -> "SIGIR", "eacl" -> "EACL").
VENUE_DISPLAY = {
    "corr":    "arXiv",
    "nips":    "NeurIPS",
    "neurips": "NeurIPS",
    "iclr":    "ICLR",
    "pvldb":   "VLDB",
    "tweb":    "TWEB",
    "tois":    "TOIS",
    "tkde":    "TKDE",
    "tors":    "TORS",
    "tist":    "TIST",
    "tkdd":    "TKDD",
    "jmlr":    "JMLR",
    "tacl":    "TACL",
    "jair":    "JAIR",
    "cacm":    "CACM",
    "ipm":     "IP&M",
    "jasis":   "JASIST",
    "access":  "IEEE Access",
    "tai":     "IEEE T-AI",
    "cmig":    "CMIG",
    "concurrency": "Concurrency",
    "fgcs":    "FGCS",
    "sigirforum": "SIGIR Forum",
    "la-web":  "LA-WEB",
}


# Scimago subject categories that count as "Computer Science". A
# journal is Q1 iff at least one of these categories is rated Q1 for
# it — per the user's preference that "Q1" means Scimago Q1 in a CS
# category, not any subject area.
CS_CATEGORIES: set[str] = {
    "Artificial Intelligence",
    "Computational Theory and Mathematics",
    "Computer Graphics and Computer-Aided Design",
    "Computer Networks and Communications",
    "Computer Science Applications",
    "Computer Science (miscellaneous)",
    "Computer Vision and Pattern Recognition",
    "Hardware and Architecture",
    "Human-Computer Interaction",
    "Information Systems",
    "Signal Processing",
    "Software",
}

# CORE rank precedence for collision resolution — when the same acronym
# appears in CORE under multiple conference names, we keep the best rank.
CORE_RANK_ORDER = {"A*": 0, "A": 1, "B": 2, "C": 3}

# Scimago category string format:  "Artificial Intelligence (Q1)".
# "-" quartile (no score) is also possible; we ignore those.
CATEGORY_RE = re.compile(r"^(?P<name>.+?)\s*\(Q(?P<q>[1-4])\)\s*$")


def load_venues(path: Path) -> dict:
    """Load venues.yml. Abbrevs are lowercased; acronyms uppercased;
    ISSNs normalized (no hyphen, uppercase X). Skip lists verbatim."""
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    conf = raw.get("conference_core_acronym") or {}
    raw["conference_core_acronym"] = {
        k.lower(): (v or "").strip().upper() for k, v in conf.items()
    }
    journals = raw.get("journal_issn") or {}
    raw["journal_issn"] = {
        k.lower(): [normalize_issn(i) for i in (v or []) if i]
        for k, v in journals.items()
    }
    raw["journal_q1_override"] = {
        k.lower() for k in (raw.get("journal_q1_override") or [])
    }
    for key in ("skip_title_patterns", "skip_keys"):
        raw[key] = list(raw.get(key, []) or [])
    raw["type_overrides"] = {
        str(k): str(v) for k, v in (raw.get("type_overrides") or {}).items()
    }
    unknown = {k: v for k, v in raw["type_overrides"].items() if v not in VALID_TYPES}
    for key, value in unknown.items():
        print(f"[warn] venues.yml: type_overrides[{key}] = {value!r} is not a known "
              f"type, ignoring (allowed: {', '.join(sorted(VALID_TYPES))})",
              file=sys.stderr)
        raw["type_overrides"].pop(key)
    # The venue-recovery tables are compiled once, under underscore keys
    # so they never collide with anything the YAML itself declares. All
    # three are first-match-wins, so list order is preserved.
    # ISSN → abbrev, the reverse of journal_issn. OpenAlex identifies a
    # journal by ISSN rather than by name, so this is what puts the
    # record back on the abbreviation the display names and the CORE
    # table are keyed on: without it "ACM Transactions on Information
    # Systems" resolves to an ISSN and then to no abbrev at all, and the
    # page loses "TOIS". First declaration wins, so a shared ISSN keeps
    # the abbrev listed first in the file.
    raw["_issn_abbrev"] = {}
    for abbrev, issns in raw["journal_issn"].items():
        for issn in issns:
            raw["_issn_abbrev"].setdefault(issn, abbrev)
    raw["_venue_patterns"] = compile_pattern_table(raw.get("venue_patterns"))
    raw["_doi_patterns"] = compile_pattern_table(raw.get("venue_doi_patterns"))
    raw["_generic_series"] = [
        re.compile(str(p), re.IGNORECASE) for p in (raw.get("generic_series") or [])
    ]
    return raw


def normalize_issn(issn: str) -> str:
    """'1046-8188' → '10468188'; 'X' stays uppercase; anything
    non-alphanumeric is stripped."""
    return re.sub(r"[^0-9Xx]", "", issn or "").upper()


def load_core_rankings(path: Path) -> dict[str, dict]:
    """Return {acronym_upper → {"rank": str, "title": str}}. On
    collision, keep the entry with the best rank per CORE_RANK_ORDER;
    the title travels with the winning rank so downstream code can
    surface the full conference name."""
    if not path.exists():
        print(
            f"[warn] CORE rankings missing: {path.name} — all conferences will be other_conf.",
            file=sys.stderr,
        )
        return {}
    out: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 5:
                continue
            title = row[1].strip()
            acro = row[2].strip().upper()
            rank = row[4].strip()
            if not acro:
                continue
            prev = out.get(acro)
            if prev is None or CORE_RANK_ORDER.get(rank, 99) < CORE_RANK_ORDER.get(prev.get("rank", ""), 99):
                out[acro] = {"rank": rank, "title": title}
    return out


def load_scimago(path: Path) -> dict[str, dict]:
    """Return {normalized_issn → {"categories": [(name, q), ...], "title": str}}.
    Scimago CSVs are semicolon-separated with a single header row; the
    ISSN column lists one or more ISSNs comma-separated, typically
    without hyphens. Each category appears as 'Name (Qn)' joined by
    '; ' inside a quoted field."""
    if not path.exists():
        print(
            f"[warn] Scimago rankings missing: {path.name} — all journals will be other_journal.\n"
            f"       Download from https://www.scimagojr.com/journalrank.php (Download data).",
            file=sys.stderr,
        )
        return {}
    out: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        # Tolerate minor header casing drift between Scimago editions.
        fields = {name.strip().lower(): name for name in (reader.fieldnames or [])}
        issn_col = fields.get("issn")
        cat_col = fields.get("categories")
        title_col = fields.get("title")
        if not issn_col or not cat_col:
            print(
                f"[warn] Scimago CSV missing Issn/Categories columns — headers were: "
                f"{list(reader.fieldnames or [])}",
                file=sys.stderr,
            )
            return {}
        for row in reader:
            cats_field = row.get(cat_col, "") or ""
            cats: list[tuple[str, int]] = []
            for piece in cats_field.split(";"):
                m = CATEGORY_RE.match(piece.strip())
                if m:
                    cats.append((m.group("name").strip(), int(m.group("q"))))
            if not cats:
                continue
            title = (row.get(title_col, "") if title_col else "") or ""
            entry = {"categories": cats, "title": title.strip()}
            for issn in (row.get(issn_col, "") or "").split(","):
                key = normalize_issn(issn)
                if key:
                    out[key] = entry
    return out


MISC_SLUG = "misc"  # catch-all topic for papers that match nothing else


def load_topics(path: Path) -> tuple[list[dict], dict[str, list[str]]]:
    """Load topics.yml. Returns (topics_list, overrides_map).

    Each topic is a dict with keys: slug, name, and compiled_patterns
    (a list of re.Pattern objects compiled case-insensitive). A topic
    with empty patterns is kept in the list (so it appears in the
    filter bar) but is skipped during auto-matching — the MISC_SLUG
    topic is the canonical such catch-all.
    """
    if not path.exists():
        return [], {}
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    topics = []
    for entry in raw.get("topics", []) or []:
        slug = entry.get("slug")
        name = entry.get("name") or slug
        patterns = entry.get("patterns") or []
        if not slug:
            continue
        topics.append({
            "slug": slug,
            "name": name,
            "compiled_patterns": [re.compile(p, re.IGNORECASE) for p in patterns],
        })
    overrides = raw.get("topic_overrides") or {}
    return topics, overrides


def classify_topics(
    pub: dict,
    topics: list[dict],
    overrides: dict[str, list[str]],
) -> list[str]:
    """Return the list of topic slugs matching this publication.

    An explicit entry in `topic_overrides` (keyed by record key) replaces
    the auto-detected topics. Otherwise each topic's patterns are tested
    against title + venue — any match adds the slug to the result.
    Papers matching no other topic are auto-tagged MISC_SLUG.
    """
    if pub["key"] in overrides:
        return list(overrides[pub["key"]] or [])
    text = f"{pub['title']} {pub['venue']}"
    matched: list[str] = []
    for topic in topics:
        if not topic["compiled_patterns"]:
            continue  # catch-all topic — never matches via regex
        for pat in topic["compiled_patterns"]:
            if pat.search(text):
                matched.append(topic["slug"])
                break
    if not matched:
        matched = [MISC_SLUG]
    return matched


def compile_pattern_table(rows) -> list[tuple[re.Pattern, str]]:
    """Compile a venues.yml [pattern, abbrev] table. Order is preserved —
    these tables are first-match-wins, so a bad reordering is a
    classification bug, not a cosmetic one."""
    table = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            print(f"[warn] venues.yml: skipping malformed pattern row {row!r}",
                  file=sys.stderr)
            continue
        pattern, abbrev = row
        try:
            table.append((re.compile(str(pattern), re.IGNORECASE), str(abbrev).lower()))
        except re.error as exc:
            print(f"[warn] venues.yml: bad regex {pattern!r} ({exc}), skipping",
                  file=sys.stderr)
    return table


def resolve_abbrev(venue_name: str, doi: str, venues: dict,
                   issns: list[str] | None = None) -> tuple[str, str]:
    """Recover a venue abbreviation the way a DBLP key used to hand it
    over for free.

    A journal is identified by its ISSN, which is exact, so that is
    tried first. Otherwise OpenAlex names venues in prose and the
    abbreviation has to be read back out of the name — or out of the
    DOI, which for the ACL Anthology and a few other publishers encodes
    the venue directly.

    Returns (abbrev, how) where `how` is "issn", "doi", "name" or "",
    because which table matched is itself evidence: venue_patterns and
    venue_doi_patterns list conferences and workshops, so a hit there
    says the record is a proceedings paper however OpenAlex typed the
    source. ("", "") means nothing matched; the caller then falls back
    to a name derived from the venue string, and the record classifies
    as an ordinary conference paper rather than being promoted."""
    issn_abbrev = venues.get("_issn_abbrev", {})
    for issn in issns or []:
        hit = issn_abbrev.get(normalize_issn(issn))
        if hit:
            return hit, "issn"
    for pattern, abbrev in venues.get("_doi_patterns", []):
        if doi and pattern.search(doi):
            return abbrev, "doi"
    for pattern, abbrev in venues.get("_venue_patterns", []):
        if venue_name and pattern.search(venue_name):
            return abbrev, "name"
    return "", ""


# Words dropped when falling back to an acronym built from the venue
# name itself — they carry no identity, so "Proceedings of the
# International Conference on Foo Bar" should read "FB", not "PICFB".
ACRONYM_STOPWORDS = {
    "a", "an", "and", "at", "conference", "conferences", "for", "in",
    "international", "of", "on", "proceedings", "the", "annual",
    "symposium", "workshop", "acm", "ieee", "joint",
}


def fallback_venue_short(venue_name: str) -> str:
    """A display label for a venue no pattern recognised: an existing
    parenthesised acronym if the name carries one ("... (CVPR)"), else
    initials of the significant words, else the name truncated."""
    if not venue_name:
        return ""
    paren = re.findall(r"\(([A-Z][A-Za-z0-9\-]{1,12})\)", venue_name)
    if paren:
        return paren[-1].upper()
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]+", venue_name)
             if w.lower() not in ACRONYM_STOPWORDS]
    if 2 <= len(words) <= 6:
        return "".join(w[0] for w in words).upper()
    return venue_name[:28]


NON_MAIN_TRACK_RE = re.compile(
    r"\b(workshops?"
    r"|companion"            # "WWW (Companion Volume)" – posters/workshops bundled
    r"|posters?"             # "WWW (Posters)"
    r"|tutorials?"           # "ACL Tutorials"
    r"|demonstrations?|demos?"  # "EMNLP Demos", "ACL Demonstrations"
    r"|doctoral"             # "ACL Doctoral Consortium"
    r"|abstracts?"           # "NeurIPS Extended Abstracts"
    r"|student"              # "ACL Student Research Workshop" (covered by "workshop" too)
    r")\b",
    re.IGNORECASE,
)


def is_workshop(booktitle: str) -> bool:
    """Return True when a venue name reads as a satellite / companion
    track rather than a main research track.

    Satellite events are marked in several conventions:
      - Plain English: "... Workshop ...", "... Workshops ..."
      - Satellite shorthand: "WSCD@WSDM", "SemEval@NAACL", "Tiny Papers @ ICLR"
      - Parenthesised subvolumes: "WWW (Companion Volume)", "WWW (Posters)",
        "EMNLP (Demonstrations)", "ACL Tutorials", "PKDD/ECML Workshops (2)"
    A main-track paper should never match here; we err on the side of
    exclusion so these records don't leak into A/A* or Q1."""
    if not booktitle:
        return False
    if "@" in booktitle:
        return True
    return bool(NON_MAIN_TRACK_RE.search(booktitle))


def classify_fields(
    kind: str,
    abbrev: str,
    publtype: str | None,
    booktitle: str,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
    issns: list[str] | None = None,
) -> str:
    """The venue classifier, expressed over plain fields rather than a
    source record, so fetched records and manual overlay entries share
    one code path. `kind` is "article" for journals, "inproceedings" for
    conference and workshop papers; `abbrev` is the venue abbreviation
    (resolve_abbrev() for a fetched record, manual_venue_abbrev() for an
    overlay one)."""
    if publtype == "informal" or abbrev == "corr":
        return TYPE_PREPRINT
    if is_workshop(booktitle):
        return TYPE_WORKSHOP

    if kind == "inproceedings":
        entry = core_ranks.get(core_acronym(abbrev, venues))
        if entry and entry.get("rank") in ("A*", "A"):
            return TYPE_A_STAR
        return TYPE_OTHER_CONF

    if kind == "article":
        # OpenAlex reports a journal's ISSNs on the record itself, so
        # those are tried first and the venues.yml table is the fallback
        # for sources it has no ISSN for.
        candidates = list(issns or []) or venues.get("journal_issn", {}).get(abbrev, [])
        for issn in candidates:
            entry = scimago.get(normalize_issn(issn))
            if not entry:
                continue
            for name, q in entry.get("categories", []):
                if q == 1 and name in CS_CATEGORIES:
                    return TYPE_Q1
        # Override: journals Scimago hasn't indexed yet (e.g. new ACM
        # Transactions) but that are clearly Q1 on scimagojr.com.
        if abbrev in venues.get("journal_q1_override", set()):
            return TYPE_Q1
        return TYPE_OTHER_JOURNAL
    return TYPE_OTHER_CONF


def resolve_venue_full(
    pub: dict,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
) -> str:
    """Return the best full name we have for a venue — the CORE title
    for conferences, the Scimago title for journals — falling back to
    the venue name on the record when the external source is silent."""
    abbrev = pub.get("abbrev") or ""
    if pub.get("type") in (TYPE_A_STAR, TYPE_OTHER_CONF, TYPE_WORKSHOP):
        entry = core_ranks.get(core_acronym(abbrev, venues))
        if entry and entry.get("title"):
            return entry["title"]
    elif pub.get("type") in (TYPE_Q1, TYPE_OTHER_JOURNAL):
        candidates = (pub.get("issns")
                      or venues.get("journal_issn", {}).get(abbrev, []))
        for issn in candidates:
            entry = scimago.get(normalize_issn(issn))
            if entry and entry.get("title"):
                return entry["title"]
    return pub.get("venue", "")


def format_author(name: str) -> str:
    """'Fabrizio Silvestri' -> 'F. Silvestri'. Strip the trailing
    disambiguation year some sources append to a name."""
    name = re.sub(r"\s+\d{4}$", "", name).strip()
    parts = name.split()
    if len(parts) < 2:
        return name
    return parts[0][0] + ". " + " ".join(parts[1:])


# OpenAlex work types we publish. Everything else it carries for this
# author — book chapters, dissertations, editorials, paratext, reference
# entries — was never in scope: the DBLP-era script took only <article>
# and <inproceedings>, and these are the same two categories plus the
# preprints that used to arrive as CoRR articles.
OPENALEX_ARTICLE_TYPES = {"article", "review", "letter"}
OPENALEX_INPROCEEDINGS_TYPES = {"conference-paper"}
OPENALEX_PREPRINT_TYPES = {"preprint"}
OPENALEX_KEPT_TYPES = (
    OPENALEX_ARTICLE_TYPES | OPENALEX_INPROCEEDINGS_TYPES | OPENALEX_PREPRINT_TYPES
)

# Crossref types that mean "a paper", used to rescue the records
# OpenAlex mistypes.
CROSSREF_PAPER_TYPES = {"proceedings-article", "journal-article", "posted-content"}

# OpenAlex source types that mean "this is not the venue" — a preprint
# server or an institutional archive standing in for one.
REPOSITORY_SOURCE_TYPES = {"repository"}

ARXIV_ABS_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:v\d+)?(?:\.pdf)?$",
                          re.IGNORECASE)
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)


def bare_doi(work: dict) -> str:
    """The work's DOI without the https://doi.org/ prefix, lowercased."""
    doi = (work.get("doi") or "").strip().lower()
    return doi.replace("https://doi.org/", "").replace("http://dx.doi.org/", "")


def work_locations(work: dict) -> list[dict]:
    """Every location on the work, primary first and de-duplicated."""
    seen, out = set(), []
    for loc in [work.get("primary_location")] + list(work.get("locations") or []):
        if not loc:
            continue
        marker = json.dumps(loc.get("landing_page_url") or loc.get("id") or "")
        if marker in seen:
            continue
        seen.add(marker)
        out.append(loc)
    return out


def arxiv_id(work: dict) -> str:
    """The arXiv identifier for a work, from its arXiv DOI or from an
    arxiv.org location. Returned in arXiv's own spelling ("2510.04727",
    "cs/0407053")."""
    match = ARXIV_DOI_RE.match(bare_doi(work))
    if match:
        return match.group(1)
    for loc in work_locations(work):
        url = loc.get("landing_page_url") or loc.get("pdf_url") or ""
        match = ARXIV_ABS_RE.search(url)
        if match:
            return match.group(1)
    return ""


def record_key(arxiv: str, doi: str, work: dict, is_preprint: bool) -> str:
    """A stable key for a work, in DBLP's spelling wherever DBLP had one.

    An arXiv preprint keeps the CoRR key DBLP minted for it
    ("journals/corr/abs-2510-04727"), because that is what the
    data/manual_publications.yml overrides are keyed on and those
    entries have to survive the move off DBLP. Everything else keys on
    its DOI, which is both stable and legible in the YAML files that
    reference it. A work with neither falls back to its OpenAlex id."""
    if is_preprint and arxiv:
        return "journals/corr/abs-" + arxiv.replace(".", "-").replace("/", "-")
    if doi:
        return "doi/" + doi
    return "openalex/" + (work.get("id") or "").rsplit("/", 1)[-1]


# JATS inline styling, which Crossref hands back inside titles and
# which publishers pretty-print across several indented lines:
#     "X-CLE\n  <scp>a</scp>\n  VER"
# The tags and the layout whitespace around them both have to go, or the
# title comes back as "X-CLE a VER". Only inline styling is treated this
# way; any other tag is removed on its own and the surrounding spacing
# left alone.
JATS_INLINE_RE = re.compile(
    r"\s*</?(?:scp|i|b|em|strong|sub|sup|span|tt|monospace|sc)\b[^>]*>\s*",
    re.IGNORECASE,
)
ANY_TAG_RE = re.compile(r"</?[a-z][^>]*>", re.IGNORECASE)


def clean_text(value: str) -> str:
    """Unescape and de-markup a string from OpenAlex or Crossref.

    Both hand back publisher-registered strings verbatim, which means
    HTML entities ("Information &amp; Knowledge Management" — the
    ampersand the CIKM pattern has to match) and, from Crossref, JATS
    markup in titles."""
    value = JATS_INLINE_RE.sub("", value or "")
    value = ANY_TAG_RE.sub("", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def work_venue(work: dict, venues: dict, xref: dict) -> tuple[str, str, list[str]]:
    """Return (venue_name, source_type, issns) for a work.

    The primary location's source is the answer when there is one, but
    OpenAlex leaves `source` null on roughly a third of conference
    records and keeps only the raw proceedings title, so that is the
    first fallback, then any other location carrying one. Springer files
    its conference proceedings under a book series ("Lecture Notes in
    Computer Science"), which names no venue at all — those go to
    Crossref for the volume title."""
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    name = (source.get("display_name") or "").strip()
    source_type = (source.get("type") or "").strip()
    issns = [i for i in (source.get("issn") or []) if i]
    if source.get("issn_l"):
        issns = [source["issn_l"]] + [i for i in issns if i != source["issn_l"]]

    if not name or source_type in REPOSITORY_SOURCE_TYPES:
        # A repository source (arXiv, an institutional archive) is a
        # host, not a venue: prefer the raw proceedings/journal title the
        # record carries alongside it.
        # ... and if there is none, report no venue at all rather than
        # putting "IRIS Research product catalog (Sapienza University of
        # Rome)" on the page as though it were one.
        replacement = ""
        for loc in work_locations(work):
            raw = (loc.get("raw_source_name") or "").strip()
            if raw and not raw.startswith("http"):
                replacement = raw
                break
        if replacement:
            name, source_type = replacement, "raw"
        elif source_type in REPOSITORY_SOURCE_TYPES:
            name, issns = "", []

    for pattern in venues.get("_generic_series", []):
        if name and pattern.search(name):
            # Crossref lists container-title as [series, volume]; the
            # volume is the one that names the conference.
            containers = (xref.get(bare_doi(work)) or {}).get("containers") or []
            if len(containers) > 1:
                name = containers[-1]
            break
    return clean_text(name), source_type, issns


# Venue names that say "these are proceedings" outright. OpenAlex types
# a great many older conference papers as "article", so the venue string
# is the more reliable signal of which ranking table applies.
PROCEEDINGS_NAME_RE = re.compile(
    r"\b(proceedings|conference|symposium|workshop|congress|meeting)\b",
    re.IGNORECASE,
)


def core_acronym(abbrev: str, venues: dict) -> str:
    """The CORE acronym an abbreviation is ranked under — the venues.yml
    override when there is one, the uppercased abbrev otherwise."""
    return venues.get("conference_core_acronym", {}).get(abbrev) or abbrev.upper()


def record_kind(
    oa_type: str,
    source_type: str,
    venue_name: str,
    abbrev: str,
    matched_by: str,
    issns: list[str],
    venues: dict,
) -> str:
    """"article" (rank against Scimago) or "inproceedings" (rank against
    CORE), the distinction DBLP used to make by element name.

    OpenAlex's own work type is the weakest of the signals available —
    it types plenty of conference papers as "article" — so it is
    consulted last. The venues.yml journal table is the strongest, and
    is what keeps a conference-proceedings journal such as PVLDB on the
    Scimago side exactly as DBLP's journals/ prefix did. Next comes how
    the abbreviation was recovered: venue_patterns and
    venue_doi_patterns list conferences and workshops, so a hit there
    settles it whatever OpenAlex calls the source — IEEE and Springer
    register several proceedings series with an ISSN, and without this
    rule SEBD, WEBI, INFOSCALE and IIR papers all rank against Scimago,
    which has nothing to say about them."""
    if abbrev and abbrev in venues.get("journal_issn", {}):
        return "article"
    if abbrev and matched_by in ("name", "doi"):
        return "inproceedings"
    if PROCEEDINGS_NAME_RE.search(venue_name or ""):
        return "inproceedings"
    if source_type == "journal" and issns:
        return "article"
    if oa_type in OPENALEX_INPROCEEDINGS_TYPES:
        return "inproceedings"
    return "article"


def parse_work(work: dict, venues: dict, xref: dict) -> dict:
    """Turn one OpenAlex work into a record, shaped exactly as the DBLP
    parser used to shape one. Returns None for a work whose type we
    don't publish."""
    oa_type = (work.get("type") or "").strip()
    doi = bare_doi(work)
    crossref = xref.get(doi) or {}
    crossref_type = crossref.get("type") or ""

    if crossref_type in CROSSREF_CONTAINER_TYPES:
        # The proceedings volume, not a paper in it. OpenAlex types the
        # volumes this author edited as ordinary conference papers.
        return None
    if oa_type not in OPENALEX_KEPT_TYPES and crossref_type not in CROSSREF_PAPER_TYPES:
        # OpenAlex mistypes a fair number of real papers — CIKM short
        # papers as "conference-abstract", Springer conference papers as
        # "book-chapter" — so its type alone is not grounds to drop one.
        # Crossref's registered type is the second opinion; the title
        # patterns in venues.yml still filter out the front matter and
        # editorials that both sources type as ordinary papers.
        return None

    venue_name, source_type, issns = work_venue(work, venues, xref)
    abbrev, matched_by = resolve_abbrev(venue_name, doi, venues, issns)
    arxiv = arxiv_id(work)

    # A preprint is a work OpenAlex types as one, or one whose only home
    # is arXiv — the same call DBLP made with publtype="informal".
    is_preprint = oa_type in OPENALEX_PREPRINT_TYPES or (not venue_name and bool(arxiv))
    if is_preprint:
        abbrev = "corr"
        venue_name = venue_name or "CoRR"

    if not venue_name and not doi and not is_preprint:
        # A record with neither a venue nor a DOI is an institutional
        # repository stub — OpenAlex carries a handful of these, and
        # they are either duplicates of a real record or someone else's
        # paper that landed on the profile. There is nothing to
        # classify, cite or link to.
        return None

    # For a record rescued on Crossref's word, OpenAlex's type is the one
    # we just declined to trust, so Crossref's stands in for it.
    kind_type = oa_type if oa_type in OPENALEX_KEPT_TYPES else (
        "conference-paper" if crossref_type == "proceedings-article" else "article"
    )
    kind = record_kind(
        kind_type, source_type, venue_name, abbrev, matched_by, issns, venues,
    )

    venue_short = (
        VENUE_DISPLAY.get(abbrev, abbrev.upper()) if abbrev
        else fallback_venue_short(venue_name)
    )

    # Split the work's links into the publisher's canonical page and the
    # arXiv copy. arxiv.org (and arXiv's own DOI namespace) is always the
    # preprint; anything else — a DOI, the ACL Anthology, IEEE Xplore —
    # is treated as the publisher's page.
    url_publisher = None
    url_arxiv = None
    if doi and not ARXIV_DOI_RE.match(doi):
        url_publisher = "https://doi.org/" + doi
    if arxiv:
        url_arxiv = "https://arxiv.org/abs/" + arxiv
    for loc in work_locations(work):
        url = (loc.get("landing_page_url") or "").strip()
        if not url:
            continue
        if "arxiv.org" in url:
            url_arxiv = url_arxiv or url
        elif url_publisher is None and not url.startswith("https://doi.org/10.48550"):
            url_publisher = url

    return {
        "key": record_key(arxiv, doi, work, is_preprint),
        # Crossref's title wins when it has one: OpenAlex drops the
        # subtitle of anything ACM registered in two halves.
        "title": clean_text(
            crossref.get("title") or work.get("display_name") or ""
        ).rstrip("."),
        "authors": [
            format_author(name)
            for name in (
                (a.get("author") or {}).get("display_name") or a.get("raw_author_name")
                for a in (work.get("authorships") or [])
            )
            if name
        ],
        "year": int(work.get("publication_year") or 0),
        "venue": venue_name,
        "venue_short": venue_short,
        "abbrev": abbrev,
        "issns": issns,
        "url": url_publisher or url_arxiv,
        "url_publisher": url_publisher,
        "url_arxiv": url_arxiv,
        "_kind": kind,
        "_preprint": is_preprint,
    }


def normalize_title_for_match(s: str) -> str:
    """Key used to cross-link conference/journal papers with their
    arXiv preprint — title variants differ in punctuation and trailing
    periods, so strip to alphanumerics+spaces."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def supersedes(candidate: dict, incumbent: dict) -> bool:
    """True when `candidate` is the better of two records for one paper:
    a named venue beats an unnamed one, and a DOI beats no DOI."""
    def rank(pub: dict) -> tuple[int, int]:
        return (
            1 if pub.get("venue") else 0,
            1 if (pub.get("key") or "").startswith("doi/") else 0,
        )
    return rank(candidate) > rank(incumbent)


def cross_link_arxiv(pubs: list[dict]) -> None:
    """For every non-preprint pub, attach `url_arxiv` by finding a
    preprint (type=preprint, host=arxiv.org) with the same normalized
    title. Mutates `pubs` in place."""
    preprint_arxiv: dict[str, str] = {}
    for p in pubs:
        if p.get("type") == TYPE_PREPRINT and p.get("url_arxiv"):
            preprint_arxiv.setdefault(normalize_title_for_match(p["title"]), p["url_arxiv"])
    for p in pubs:
        if p.get("type") == TYPE_PREPRINT or p.get("url_arxiv"):
            continue
        hit = preprint_arxiv.get(normalize_title_for_match(p.get("title", "")))
        if hit:
            p["url_arxiv"] = hit


def http_json(url: str, timeout: int = 60, retries: int = 3):
    """GET a JSON document, retrying on the transient failures a long
    paginated crawl runs into (429 from the shared rate limiter, 5xx
    while OpenAlex reindexes). Raises on anything else."""
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise
            wait = 5 * attempt
            print(f"[warn] {exc.code} from {url.split('?')[0]} — "
                  f"retrying in {wait}s ({attempt}/{retries - 1})", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries:
                raise
            wait = 5 * attempt
            print(f"[warn] {exc} — retrying in {wait}s ({attempt}/{retries - 1})",
                  file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"[error] gave up fetching {url}")


def openalex_params(extra: dict) -> str:
    """Query string for an OpenAlex call, carrying the polite-pool
    mailto and, when $OPENALEX_API_KEY is set, a premium API key.

    A full run is about fifteen requests — three filters paginating to
    eight, plus the Crossref batches — against a polite-pool allowance
    of 100,000 a day, so no key is needed and none is checked in. If
    OpenAlex ever does throttle the nightly job, put one in the
    OPENALEX_API_KEY repository secret and pass it through as an env
    var in the workflow; nothing here has to change."""
    params = dict(extra)
    params["mailto"] = CONTACT_EMAIL
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if api_key:
        params["api_key"] = api_key
    return urllib.parse.urlencode(params)


def fetch_openalex_filter(filter_expr: str) -> list[dict]:
    """Every work matching one OpenAlex filter, paged with a cursor."""
    works: list[dict] = []
    cursor = "*"
    while cursor:
        url = OPENALEX_API + "?" + openalex_params({
            "filter": filter_expr,
            "per-page": OPENALEX_PAGE_SIZE,
            "cursor": cursor,
        })
        payload = http_json(url)
        works.extend(payload.get("results") or [])
        cursor = (payload.get("meta") or {}).get("next_cursor")
    return works


def simple_name(name: str) -> str:
    """A name reduced to lowercase ASCII words, so the spellings the
    sources use ("Silvestri, Fabrizio", "F. Silvestri", "Silvestrì")
    compare equal."""
    ascii_name = (unicodedata.normalize("NFKD", name or "")
                  .encode("ascii", "ignore").decode())
    return " ".join(re.sub(r"[^a-z ]", " ", ascii_name.lower()).split())


def authorship_is_author(authorship: dict) -> bool:
    """True when this authorship names *our* author, by any spelling."""
    display = ((authorship.get("author") or {}).get("display_name") or "")
    raw = authorship.get("raw_author_name") or ""
    return (simple_name(display) in AUTHOR_NAME_FORMS
            or simple_name(raw) in AUTHOR_NAME_FORMS)


def coauthor_ids(work: dict) -> set[str]:
    return {
        (a.get("author") or {}).get("id")
        for a in (work.get("authorships") or [])
        if (a.get("author") or {}).get("id")
    }


def fetch_openalex_works() -> list[dict]:
    """The author's works, unioned over the filters that find them.

    OpenAlex disambiguates authors continuously, which splits a profile
    across several ids and moves records between them; querying the id
    and the ORCID separately covers both sides of a split that hasn't
    settled yet. Neither finds a record that landed on a *fresh* id with
    no ORCID on it, which is where new preprints tend to start life — so
    a third pass searches by raw author name and then has to decide
    which of those records are actually his, since several other
    researchers publish as F. Silvestri. A record qualifies when it
    names him in one of the known spellings AND shares at least
    MIN_SHARED_COAUTHORS with the confirmed set; a namesake in another
    field clears neither bar.

    An empty result is treated as a failure rather than as "no
    publications" — writing an empty data/publications.json over a good
    one is the one outcome worth guarding against, and the site keeps
    serving the last good file."""
    works: dict[str, dict] = {}
    for filter_expr in (
        f"author.id:{OPENALEX_AUTHOR_ID}",
        f"author.orcid:https://orcid.org/{OPENALEX_ORCID}",
    ):
        found = fetch_openalex_filter(filter_expr)
        print(f"OpenAlex {filter_expr}: {len(found)} works", file=sys.stderr)
        for work in found:
            if work.get("id"):
                works[work["id"]] = work

    confirmed_coauthors: set[str] = set()
    for work in works.values():
        confirmed_coauthors |= coauthor_ids(work)
    by_name = fetch_openalex_filter(f"raw_author_name.search:{OPENALEX_AUTHOR_NAME}")
    adopted = 0
    for work in by_name:
        if not work.get("id") or work["id"] in works:
            continue
        if not any(authorship_is_author(a) for a in (work.get("authorships") or [])):
            continue
        shared = len(coauthor_ids(work) & confirmed_coauthors)
        if shared >= MIN_SHARED_COAUTHORS:
            works[work["id"]] = work
            adopted += 1
    print(
        f"OpenAlex raw_author_name:{OPENALEX_AUTHOR_NAME}: {len(by_name)} works, "
        f"{adopted} adopted on co-author evidence",
        file=sys.stderr,
    )

    if not works:
        raise SystemExit(
            "[error] OpenAlex returned no works for "
            f"{OPENALEX_AUTHOR_ID} / ORCID {OPENALEX_ORCID}.\n"
            "        Nothing was written, so the site keeps serving the last\n"
            "        good data/publications.json. Check whether the author id\n"
            "        still resolves at https://api.openalex.org/authors/"
            f"{OPENALEX_AUTHOR_ID}"
        )
    return list(works.values())


# Crossref is queried in batches of DOIs rather than one call per
# record; 50 keeps the filter expression comfortably inside any URL
# length limit while cutting ~300 requests down to ~6.
CROSSREF_BATCH = 50

# Crossref work types that are a *container*, not a paper: the
# proceedings volume itself, an edited book, a whole journal issue.
# OpenAlex lists several of these for this author (an ECIR volume he
# co-edited, a WISE volume) as ordinary conference papers.
CROSSREF_CONTAINER_TYPES = {
    "proceedings", "book", "edited-book", "book-set", "book-series",
    "monograph", "journal", "journal-issue", "journal-volume", "report",
}


def fetch_crossref(dois: list[str]) -> dict[str, dict]:
    """Title, container titles and work type for each DOI, from Crossref.

    Crossref is the companion source that fills three gaps OpenAlex
    leaves:

      * Titles. OpenAlex stores ACM's registered title without its
        subtitle — "Know your neighbors" for what DBLP called "Know your
        neighbors: web spam detection using the web topology". Crossref
        keeps the two halves in separate fields, so the full title can be
        put back together.
      * Venues. Springer files conference proceedings under a book
        series, and OpenAlex keeps only the series name; Crossref keeps
        the volume title too, which is the part that says ECIR.
      * Containers. A proceedings volume the author edited looks exactly
        like a paper in OpenAlex; Crossref types it as one.

    Failures are swallowed — every one of those is an improvement on
    what OpenAlex alone gives, not a precondition, so a Crossref outage
    degrades the run instead of breaking it."""
    out: dict[str, dict] = {}
    dois = [d for d in dict.fromkeys(dois) if d]
    for start in range(0, len(dois), CROSSREF_BATCH):
        batch = dois[start:start + CROSSREF_BATCH]
        url = CROSSREF_API.rstrip("/") + "?" + urllib.parse.urlencode({
            "filter": ",".join("doi:" + d for d in batch),
            "rows": len(batch),
            "select": "DOI,title,subtitle,container-title,type",
            "mailto": CONTACT_EMAIL,
        })
        try:
            items = (http_json(url, timeout=60, retries=2)
                     .get("message", {}).get("items") or [])
        except Exception as exc:  # noqa: BLE001 — never fail the run on this
            print(f"[warn] crossref batch {start // CROSSREF_BATCH + 1} failed: "
                  f"{exc}", file=sys.stderr)
            continue
        for item in items:
            doi = (item.get("DOI") or "").lower()
            if not doi:
                continue
            title = (item.get("title") or [""])[0].strip()
            subtitle = (item.get("subtitle") or [""])[0].strip()
            out[doi] = {
                "title": f"{title}: {subtitle}" if title and subtitle else title,
                "containers": [c for c in (item.get("container-title") or []) if c],
                "type": (item.get("type") or "").strip().lower(),
            }
    print(f"Crossref: resolved {len(out)}/{len(dois)} DOIs", file=sys.stderr)
    return out


TYPE_ORDER = [
    TYPE_A_STAR, TYPE_Q1, TYPE_OTHER_CONF, TYPE_OTHER_JOURNAL,
    TYPE_WORKSHOP, TYPE_PREPRINT,
]


# ---------------------------------------------------------------------------
# Manual overlay — data/manual_publications.yml
#
# OpenAlex indexes a paper weeks or months after it appears, so the
# nightly sync lags reality. The overlay forces a paper in until
# OpenAlex catches up, in two shapes:
#
#   additions:  full records for papers OpenAlex has no entry for at all.
#   overrides:  field patches keyed by record key, for a record the
#               fetch gets partly wrong — a paper still listed only as a
#               preprint, or one whose venue resolved but whose
#               publisher link points at a repository mirror rather than
#               the page the author wants linked.
#
# It is applied after the fetch and classification and before the JSON
# is written, and merged records go through the same topic and venue
# classification helpers as fetched records — nothing downstream (sort,
# counters, filters, renderer) knows a record came from here.
#
# The overlay also prunes itself: an addition OpenAlex has indexed, and
# an override whose every field the fetched record now already carries,
# are dropped from the output *and* deleted from the YAML, so the file
# shrinks back to empty on its own and the nightly workflow commits the
# rewrite like any other change.
# ---------------------------------------------------------------------------

# The exact field list parse_work() + main() emit, in emission order.
# Manual records are built in this order so their JSON is shaped like a
# fetched one; anything else in the YAML is a typo and is reported
# rather than carried silently into the output.
RECORD_FIELDS = [
    "key", "title", "authors", "year", "venue", "venue_short", "abbrev",
    "url", "url_publisher", "url_arxiv", "type", "topics", "citations",
]

VALID_TYPES = set(TYPE_ORDER)

MANUAL_KEY_PREFIX = "manual/"


def manual_venue_abbrev(key: str) -> str:
    """Venue abbreviation for a synthetic overlay key, so the CORE and
    Scimago lookups resolve as they do for a fetched record. An entry
    can also state `abbrev:` outright; this is the fallback that reads
    it out of the key, in the DBLP key shape the overlay has always
    used. Both spellings work — mirror the key the paper will eventually
    get, or drop the conf/journals segment:

        manual/conf/iclr/CasoFMSS26      ->  "iclr"
        manual/journals/tors/SbandiSS26  ->  "tors"
        manual/iclr/some-slug            ->  "iclr"
    """
    rest = key[len(MANUAL_KEY_PREFIX):] if key.startswith(MANUAL_KEY_PREFIX) else key
    parts = [part for part in rest.split("/") if part]
    if not parts:
        return ""
    if parts[0] in ("conf", "journals") and len(parts) >= 2:
        return parts[1].lower()
    return parts[0].lower()

# Journal types, i.e. the ones classify_fields() must see as "article".
JOURNAL_TYPES = {TYPE_Q1, TYPE_OTHER_JOURNAL}

# arXiv's own DOI namespace, kept for the override rescue path below:
# a preprint record whose only link was the arXiv DOI used to carry it
# in url_publisher, so an override pointing url_publisher at the real
# venue would otherwise drop the preprint link entirely.
ARXIV_DOI_MARKER = "10.48550/arxiv"


def manual_yaml_handle():
    """A round-trip YAML handle for the overlay file, or None when
    ruamel.yaml isn't installed. Reading falls back to PyYAML; only
    pruning — which rewrites the file with its comments and key order
    intact — needs ruamel."""
    try:
        from ruamel.yaml import YAML
    except ImportError:
        return None
    handle = YAML()  # round-trip mode
    handle.preserve_quotes = True
    handle.width = 4096  # never re-wrap long titles / URLs
    handle.indent(mapping=2, sequence=4, offset=2)  # "  - key:" list style
    return handle


# ruamel parks the comment block that *follows* an entry on that entry's
# last key, so a plain `del` takes the next section's documentation with
# it. These helpers read, rewrite and hand that block on instead.

def trailing_comment(entry) -> str:
    """The raw comment text sitting between `entry` and whatever comes
    after it in the file."""
    if not isinstance(entry, dict) or not len(entry):
        return ""
    slot = entry.ca.items.get(list(entry.keys())[-1])
    token = slot[2] if slot and len(slot) > 2 else None
    return token.value if token is not None else ""


def set_trailing_comment(entry, text: str) -> None:
    if not isinstance(entry, dict) or not len(entry):
        return
    from ruamel.yaml.error import CommentMark
    from ruamel.yaml.tokens import CommentToken
    slot = entry.ca.items.setdefault(list(entry.keys())[-1], [None, None, None, None])
    while len(slot) < 4:
        slot.append(None)
    if not text:
        slot[2] = None
    elif slot[2] is not None:
        slot[2].value = text
    else:
        slot[2] = CommentToken(text, CommentMark(0))


def drop_entry_header(text: str) -> str:
    """Strip the comment block that sits flush against the entry that
    follows it — that block describes the entry, so it goes when the
    entry does. A block set off by a blank line is file-level prose and
    stays."""
    if not text:
        return ""
    lead, _, body = text.partition("\n")  # the value's own line break
    lines = body.split("\n")
    cut = len(lines)
    while cut and (lines[cut - 1].strip().startswith("#") or not lines[cut - 1].strip()):
        if not lines[cut - 1].strip() and cut < len(lines):
            break  # a blank line separates prose from the entry's header
        cut -= 1
    kept = lines[:cut]
    if not any(line.strip() for line in kept):
        return ""
    return lead + "\n" + "\n".join(kept).rstrip("\n") + "\n"


def prune_yaml_entries(container, victims: list) -> None:
    """Delete `victims` (indices for a sequence, keys for a mapping)
    from a ruamel container, handing each one's trailing comment block
    to the previous entry — or, for the first entry, to the comment
    that introduces the container. Without that, pruning the last
    addition would delete the prose documenting the next section."""
    for victim in sorted(victims, reverse=True):
        addressable = list(container.keys()) if isinstance(container, dict) else None
        position = (addressable.index(victim) if addressable is not None else victim)
        moved = trailing_comment(container[victim])
        if position > 0:
            prev_key = (addressable[position - 1] if addressable is not None
                        else position - 1)
            prev = container[prev_key]
            set_trailing_comment(prev, drop_entry_header(trailing_comment(prev)) + moved)
        elif moved.strip():
            # First entry: its trailing block introduces whatever is now
            # first, so it becomes the container's start comment. The
            # existing start comment described the entry being deleted.
            # Mutated in place where it exists — the parent mapping
            # holds the same list object.
            from ruamel.yaml.error import CommentMark
            from ruamel.yaml.tokens import CommentToken
            text = moved.lstrip("\n")
            token = CommentToken(
                text.lstrip(" "), CommentMark(len(text) - len(text.lstrip(" "))),
            )
            if container.ca.comment is None:
                container.ca.comment = [None, [token]]
            elif container.ca.comment[1] is None:
                container.ca.comment[1] = [token]
            else:
                container.ca.comment[1][:] = [token]
        del container[victim]


def load_manual_overlay(path: Path) -> tuple[dict, object]:
    """Return (document, yaml_handle). The document is mutated in place
    by the pruner and dumped back through the handle; a None handle
    means pruning is unavailable this run."""
    if not path.exists():
        return {}, None
    handle = manual_yaml_handle()
    if handle is None:
        print(
            "[manual] ruamel.yaml not installed — overlay applied read-only, "
            "no self-pruning. pip install -r scripts/requirements.txt",
            file=sys.stderr,
        )
    try:
        with path.open(encoding="utf-8") as f:
            doc = (handle.load(f) if handle is not None else yaml.safe_load(f)) or {}
    except Exception as exc:
        # A hand-edited YAML file is one typo away from unparseable (an
        # unquoted title containing ": " is the classic). That must not
        # take the nightly refresh down with it — skip the overlay and
        # let the fetched results through.
        print(
            f"[warn] [manual] {path.name} could not be parsed, ignoring the "
            f"overlay this run: {exc}",
            file=sys.stderr,
        )
        return {}, None
    return doc, handle


def plain_value(value):
    """Strip ruamel's round-trip wrapper types so a merged record
    serializes to JSON exactly like a fetched one."""
    if isinstance(value, dict):
        return {str(k): plain_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_value(v) for v in value]
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return value


def manual_type(
    entry: dict,
    key: str,
    abbrev: str,
    venue: str,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
) -> str:
    """Resolve a manual record's `type` through classify_fields(), the
    same classifier fetched records use. A declared type wins — it is the
    author's explicit intent, and the only signal for whether to rank
    the venue against CORE or against Scimago, so it also seeds the
    element `kind`. An omitted type is derived outright, as a
    conference paper. A disagreement is reported: it almost always
    means the key's venue abbreviation is wrong."""
    declared = str(entry.get("type") or "").strip()
    if declared and declared not in VALID_TYPES:
        print(
            f"[warn] [manual] {key}: unknown type {declared!r} — "
            f"classifying it instead (allowed: {', '.join(TYPE_ORDER)})",
            file=sys.stderr,
        )
        declared = ""
    derived = classify_fields(
        "article" if declared in JOURNAL_TYPES else "inproceedings",
        abbrev,
        "informal" if declared == TYPE_PREPRINT else None,
        venue,
        venues,
        core_ranks,
        scimago,
    )
    if declared and derived != declared:
        print(
            f"[manual] {key}: declared type {declared} but the venue "
            f"abbreviation classifies as {derived} — keeping {declared}",
            file=sys.stderr,
        )
    return declared or derived


def resolve_manual_topics(
    rec: dict,
    supplied,
    topics: list[dict],
    topic_overrides: dict[str, list[str]],
) -> list[str]:
    """Topics for an overlay record. classify_topics() runs first and
    wins whenever it recognises the paper; the YAML list is the fallback
    for the ones its keyword patterns don't (those come back as the
    catch-all MISC_SLUG). A fallback list is validated against
    topics.yml, and MISC_SLUG is dropped from it — the catch-all only
    means anything on its own."""
    auto = classify_topics(rec, topics, topic_overrides)
    if not supplied or auto != [MISC_SLUG]:
        return auto
    known = {t["slug"] for t in topics}
    out: list[str] = []
    for slug in supplied:
        slug = str(slug)
        if slug not in known:
            print(
                f"[warn] [manual] {rec['key']}: unknown topic {slug!r} — "
                f"not in {TOPICS_FILE.name}, ignoring",
                file=sys.stderr,
            )
        elif slug != MISC_SLUG and slug not in out:
            out.append(slug)
    return out or [MISC_SLUG]


def build_manual_record(
    entry: dict,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
    topics: list[dict],
    topic_overrides: dict[str, list[str]],
    citations: dict[str, int],
) -> dict:
    """Turn one `additions:` entry into a record shaped exactly like
    parse_work() output. Returns None (with a warning) for an entry
    that can't be used — a bad overlay entry never fails the run."""
    key = str(entry.get("key") or "").strip()
    title = str(entry.get("title") or "").strip().rstrip(".")
    if not key or not title:
        print(
            f"[warn] [manual] addition needs both `key` and `title`, skipping: "
            f"{dict(entry)!r}",
            file=sys.stderr,
        )
        return None
    if not key.startswith(MANUAL_KEY_PREFIX):
        print(
            f"[warn] [manual] addition key {key!r} must start with "
            f"{MANUAL_KEY_PREFIX!r}, skipping",
            file=sys.stderr,
        )
        return None
    unknown = [f for f in entry if f not in RECORD_FIELDS]
    if unknown:
        print(
            f"[warn] [manual] {key}: ignoring unknown field(s) "
            f"{', '.join(sorted(unknown))}",
            file=sys.stderr,
        )

    venue = str(entry.get("venue") or "").strip()
    url_publisher = (str(entry.get("url_publisher")).strip()
                     if entry.get("url_publisher") else None)
    url_arxiv = (str(entry.get("url_arxiv")).strip()
                 if entry.get("url_arxiv") else None)
    try:
        year = int(entry.get("year") or 0)
    except (TypeError, ValueError):
        year = 0

    rec = {
        "key": key,
        "title": title,
        # Full names are abbreviated the same way fetched names are;
        # already-abbreviated ones pass through unchanged.
        "authors": [format_author(str(a)) for a in (entry.get("authors") or []) if a],
        "year": year,
        "venue": venue,
        "venue_short": str(entry.get("venue_short") or "").strip(),
        # The venue join key: stated outright, or read out of the key.
        "abbrev": (str(entry.get("abbrev") or "").strip().lower()
                   or manual_venue_abbrev(key)),
        # Same precedence parse_work() applies to a work's locations.
        "url": (str(entry.get("url")).strip() if entry.get("url")
                else (url_publisher or url_arxiv)),
        "url_publisher": url_publisher,
        "url_arxiv": url_arxiv,
    }
    rec["type"] = manual_type(
        entry, key, rec["abbrev"], venue, venues, core_ranks, scimago,
    )
    rec["topics"] = resolve_manual_topics(
        rec, entry.get("topics"), topics, topic_overrides,
    )
    # Scholar counts win when refresh_citations.py has matched the
    # title (it reads the merged list, so manual keys do get counts);
    # the YAML value is only a seed for before that first match.
    try:
        seed = int(entry.get("citations") or 0)
    except (TypeError, ValueError):
        seed = 0
    rec["citations"] = int(citations.get(key, seed))
    return rec


def override_is_redundant(target: dict, fields: dict) -> bool:
    """True when the record already carries every value the override
    sets, so applying it would change nothing."""
    for field, value in (fields or {}).items():
        field = str(field)
        if field == "key" or field not in RECORD_FIELDS or value is None:
            continue
        if target.get(field) != plain_value(value):
            return False
    return True


def apply_override(pub: dict, fields: dict, key: str) -> None:
    """Merge `fields` into `pub` in place, field by field. Anything the
    override doesn't name is left alone — url_arxiv above all, so the
    preprint link survives on the page."""
    was_publisher = pub.get("url_publisher")
    for field, value in fields.items():
        field = str(field)
        if field == "key":
            continue  # the key is the join, never a payload field
        if field not in RECORD_FIELDS:
            print(
                f"[warn] [manual] override {key}: ignoring unknown field {field!r}",
                file=sys.stderr,
            )
            continue
        if value is None:
            # A bare `null` is how an unresearched field is parked in the
            # YAML ("url_publisher: null  # TODO"). Treat it as "not
            # specified" so a placeholder can't wipe the fetched value.
            continue
        if field == "type" and str(value) not in VALID_TYPES:
            print(
                f"[warn] [manual] override {key}: unknown type {str(value)!r}, "
                f"leaving {pub.get('type')!r} (allowed: {', '.join(TYPE_ORDER)})",
                file=sys.stderr,
            )
            continue
        pub[field] = plain_value(value)
    # An override's whole job is to point url_publisher at the real
    # venue. Where the preprint's only link was the arXiv DOI that
    # overwrites the sole reading copy, so rescue it into url_arxiv —
    # otherwise "the preprint link stays" would hold only for the
    # records that carry a separate arxiv.org URL.
    if (
        "url_arxiv" not in fields
        and not pub.get("url_arxiv")
        and ARXIV_DOI_MARKER in (was_publisher or "").lower()
        and pub.get("url_publisher") != was_publisher
    ):
        pub["url_arxiv"] = was_publisher
    if "url" not in fields:
        # Same precedence parse_work() applies: the publisher page is
        # the canonical link once there is one, arXiv is the fallback.
        pub["url"] = pub.get("url_publisher") or pub.get("url_arxiv")


def apply_manual_overlay(
    pubs: list[dict],
    manual_path: Path,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
    topics: list[dict],
    topic_overrides: dict[str, list[str]],
    citations: dict[str, int],
    prune: bool = True,
) -> list[dict]:
    """Merge data/manual_publications.yml into the fetched results and
    prune the entries OpenAlex has caught up with. Returns the merged list;
    `pubs` is also mutated in place for the overridden records.

    Titles are compared normalized (lowercased, punctuation stripped,
    whitespace collapsed) via normalize_title_for_match().
    """
    doc, handle = load_manual_overlay(manual_path)
    additions = doc.get("additions") or []
    overrides = doc.get("overrides") or {}
    if not additions and not overrides:
        return pubs

    by_key = {p["key"]: p for p in pubs}
    # Two title indexes: every fetched record (an addition loses to any
    # of them), and only the published ones (an override whose own CoRR
    # key is gone is superseded by a *published* record of the same
    # title, never by another preprint).
    any_by_title: dict[str, dict] = {}
    published_by_title: dict[str, dict] = {}
    for p in pubs:
        norm = normalize_title_for_match(p.get("title", ""))
        if not norm:
            continue
        any_by_title.setdefault(norm, p)
        if p.get("type") != TYPE_PREPRINT:
            published_by_title.setdefault(norm, p)

    pruned_overrides: list[str] = []
    applied_overrides = 0
    for corr_key in list(overrides.keys()):
        fields = overrides.get(corr_key) or {}
        target = by_key.get(corr_key)
        # The override's own `title` is what lets the pruner recognise
        # the superseding record once the CoRR key itself is gone; while
        # the key is still there, the fetched title serves just as well.
        title = str(fields.get("title") or (target or {}).get("title") or "")
        norm = normalize_title_for_match(title)
        superseder = published_by_title.get(norm) if norm else None
        if superseder is target:
            # The record the override points at is, of course, the one
            # with that title. Supersession means *another* record has
            # taken over, which is the case worth pruning for.
            superseder = None
        if superseder is not None:
            print(
                f"[manual] pruned override {corr_key}, "
                f"superseded by {superseder['key']}",
                file=sys.stderr,
            )
            pruned_overrides.append(corr_key)
            continue
        if target is None:
            # Can't tell "the record was re-keyed" from "the key never
            # existed" in a single run, and blindly deleting on an
            # upstream hiccup loses a hand-written entry — so warn and
            # carry on.
            print(
                f"[warn] [manual] override {corr_key} targets a key that is "
                f"not in the current results — left in place"
                + ("" if fields.get("title") else
                   " (add a `title:` so a superseding record can be detected)"),
                file=sys.stderr,
            )
            continue
        if override_is_redundant(target, fields):
            # Every field the override sets, the fetched record already
            # says — so it has nothing left to patch. This is the test
            # rather than "the record is no longer a preprint", because
            # OpenAlex resolves a venue while still reporting a worse
            # publisher link than the one the override was written to
            # supply: the record stops being a preprint, but the
            # override is still doing work.
            print(
                f"[manual] pruned override {corr_key}, "
                f"fully superseded by {target['key']}",
                file=sys.stderr,
            )
            pruned_overrides.append(corr_key)
            continue
        apply_override(target, fields, corr_key)
        # The venue is part of what topic patterns match against, so
        # topics are re-derived through the usual path after the patch.
        target["topics"] = resolve_manual_topics(
            target, fields.get("topics"), topics, topic_overrides,
        )
        applied_overrides += 1

    pruned_additions: list[int] = []
    merged = list(pubs)
    for idx, entry in enumerate(additions):
        if not entry:
            continue
        rec = build_manual_record(
            entry, venues, core_ranks, scimago, topics, topic_overrides, citations,
        )
        if rec is None:
            continue
        hit = any_by_title.get(normalize_title_for_match(rec["title"]))
        if hit is not None:
            print(
                f'[manual] pruned addition "{rec["title"]}", '
                f'OpenAlex now has it as {hit["key"]}',
                file=sys.stderr,
            )
            if hit.get("type") == TYPE_PREPRINT:
                print(
                    f"[warn] [manual] {hit['key']} is still only a preprint — if "
                    f"the paper has a real venue, add an `overrides:` entry for "
                    f"that key",
                    file=sys.stderr,
                )
            pruned_additions.append(idx)
            continue
        merged.append(rec)

    if applied_overrides or len(merged) > len(pubs):
        print(
            f"[manual] applied {len(merged) - len(pubs)} addition(s), "
            f"{applied_overrides} override(s)",
            file=sys.stderr,
        )

    if pruned_additions or pruned_overrides:
        stale = len(pruned_additions) + len(pruned_overrides)
        if not prune:
            print(
                f"[manual] --no-prune: {stale} stale entr"
                f"{'y' if stale == 1 else 'ies'} left in "
                f"{manual_path.name} (still kept out of the JSON)",
                file=sys.stderr,
            )
        elif handle is None:
            print(
                f"[warn] [manual] {stale} stale entr"
                f"{'y' if stale == 1 else 'ies'} could not be removed from "
                f"{manual_path.name} — ruamel.yaml is not installed",
                file=sys.stderr,
            )
        else:
            prune_yaml_entries(doc["additions"], pruned_additions)
            prune_yaml_entries(doc["overrides"], pruned_overrides)
            with manual_path.open("w", encoding="utf-8") as f:
                handle.dump(doc, f)
            print(f"[manual] rewrote {manual_path.name}", file=sys.stderr)

    return merged


def load_awards(path: Path) -> list[dict]:
    """Read the hand-curated awards list. Each entry must at minimum
    have year + title; issuer/description/url are optional. Awards are
    sorted most-recent-first for display."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    awards = []
    for entry in raw.get("awards") or []:
        if not entry:
            continue
        title = (entry.get("title") or "").strip()
        year = entry.get("year")
        if not title or not year:
            continue
        awards.append({
            "year": int(year),
            "title": title,
            "issuer": (entry.get("issuer") or "").strip(),
            "description": (entry.get("description") or "").strip(),
            "url": (entry.get("url") or "").strip(),
        })
    awards.sort(key=lambda a: -a["year"])
    return awards


def load_talks(path: Path) -> list[dict]:
    """Read the hand-curated talks list — keynotes, invited talks,
    tutorials, panels. Each entry needs year + title at minimum;
    venue/role/location/url are optional. Talks render most-recent-first."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    talks = []
    for entry in raw.get("talks") or []:
        if not entry:
            continue
        title = (entry.get("title") or "").strip()
        year = entry.get("year")
        if not title or not year:
            continue
        talks.append({
            "year": int(year),
            "title": title,
            "venue": (entry.get("venue") or "").strip(),
            "role": (entry.get("role") or "").strip(),
            "location": (entry.get("location") or "").strip(),
            "url": (entry.get("url") or "").strip(),
        })
    talks.sort(key=lambda t: -t["year"])
    return talks


def load_citations(path: Path) -> tuple[dict[str, int], str]:
    """Return ({record key → citation_count}, fetched_at_iso_date) from the
    Scholar scrape cache. Missing file → empty dict + empty date with a
    console note (citations are optional)."""
    if not path.exists():
        print(
            f"[warn] Citations cache missing: {path.name} — "
            f"publication items will render without cite counts. "
            f"Run scripts/refresh_citations.py to populate.",
            file=sys.stderr,
        )
        return {}, ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    counts = {k: int(v) for k, v in (payload.get("citations") or {}).items()}
    # fetched_at is ISO-8601 with time; keep just the date for display.
    fetched_at = (payload.get("fetched_at") or "")[:10]
    return counts, fetched_at


def main(prune_manual: bool = True) -> int:
    venues = load_venues(VENUES_FILE)
    topics, topic_overrides = load_topics(TOPICS_FILE)
    core_ranks = load_core_rankings(CORE_FILE)
    scimago = load_scimago(SCIMAGO_FILE)
    citations, citations_fetched_at = load_citations(CITATIONS_FILE)
    awards = load_awards(AWARDS_FILE)
    talks = load_talks(TALKS_FILE)
    print(
        f"Loaded venues: {len(venues.get('conference_core_acronym', {}))} CORE overrides, "
        f"{len(venues.get('journal_issn', {}))} journal ISSN mappings; "
        f"{len(core_ranks)} CORE entries, {len(scimago)} Scimago ISSNs; "
        f"{len(topics)} topics; {len(citations)} citation counts "
        f"(fetched {citations_fetched_at or '?'}); "
        f"{len(awards)} awards; {len(talks)} talks",
        file=sys.stderr,
    )

    works = fetch_openalex_works()
    xref = fetch_crossref([bare_doi(w) for w in works])

    skip_patterns = [
        re.compile(p, re.IGNORECASE) for p in venues.get("skip_title_patterns", [])
    ]
    skip_keys = set(venues.get("skip_keys", []))

    pubs: list[dict] = []
    by_key: dict[str, dict] = {}
    by_title: dict[tuple[str, bool], dict] = {}
    skipped = 0
    for work in works:
        parsed = parse_work(work, venues, xref)
        if parsed is None or not parsed["title"]:
            continue
        if parsed["key"] in skip_keys:
            skipped += 1
            continue
        if any(pat.search(parsed["title"]) for pat in skip_patterns):
            skipped += 1
            continue
        parsed["type"] = classify_fields(
            parsed.pop("_kind"),
            parsed["abbrev"],
            "informal" if parsed.pop("_preprint") else None,
            parsed["venue"],
            venues,
            core_ranks,
            scimago,
            issns=parsed["issns"],
        )
        # The hand-set verdict for the records no signal classifies
        # right — see type_overrides in venues.yml.
        forced = venues["type_overrides"].get(parsed["key"])
        if forced:
            parsed["type"] = forced
        parsed["venue"] = resolve_venue_full(parsed, venues, core_ranks, scimago)
        parsed["topics"] = classify_topics(parsed, topics, topic_overrides)
        parsed["citations"] = citations.get(parsed["key"], 0)
        parsed.pop("issns")
        # OpenAlex carries a fair number of papers twice — a publisher
        # record and a repository copy, or two preprint records for one
        # arXiv posting — so the same paper can arrive under two work
        # ids and two keys. De-duplicate on key first, then on
        # normalized title — but only within one standing, since a
        # preprint and the paper it became are not duplicates: the site
        # lists both, on separate tabs, and cross_link_arxiv() ties them
        # together. Of two genuine duplicates the fuller record wins.
        if parsed["key"] in by_key:
            continue
        title_key = (normalize_title_for_match(parsed["title"]),
                     parsed["type"] == TYPE_PREPRINT)
        seen = by_title.get(title_key)
        if seen is not None:
            if not supersedes(parsed, seen):
                continue
            pubs.remove(seen)
            by_key.pop(seen["key"], None)
        by_key[parsed["key"]] = parsed
        by_title[title_key] = parsed
        pubs.append(parsed)

    # Force in the papers OpenAlex hasn't indexed yet, and patch the ones
    # it still lists as preprint-only. Runs before cross_link_arxiv so manual
    # records take part in preprint↔paper linking like any other.
    pubs = apply_manual_overlay(
        pubs,
        MANUAL_FILE,
        venues,
        core_ranks,
        scimago,
        topics,
        topic_overrides,
        citations,
        prune=prune_manual,
    )

    cross_link_arxiv(pubs)

    pubs.sort(
        key=lambda p: (
            -p["year"],
            TYPE_ORDER.index(p["type"]) if p["type"] in TYPE_ORDER else 99,
            (p.get("venue_short") or p.get("venue") or "").lower(),
            p["title"].lower(),
        )
    )

    counts = {t: sum(1 for p in pubs if p["type"] == t) for t in TYPE_ORDER}
    counts_by_topic = {
        t["slug"]: sum(1 for p in pubs if t["slug"] in p.get("topics", []))
        for t in topics
    }
    years = sorted({p["year"] for p in pubs if p["year"] > 0}, reverse=True)

    # Emit the topic metadata the renderer needs: ordered slug+name pairs.
    topics_meta = [{"slug": t["slug"], "name": t["name"]} for t in topics]

    payload = {
        "last_updated": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "citations_fetched_at": citations_fetched_at,
        "source": f"{OPENALEX_API}?filter=author.id:{OPENALEX_AUTHOR_ID}",
        "count": len(pubs),
        "counts_by_type": counts,
        "counts_by_topic": counts_by_topic,
        "years": years,
        "topics_meta": topics_meta,
        "publications": pubs,
        "awards": awards,
        "talks": talks,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    today = date.today().isoformat()

    # Bump ?v=... on cache-busted assets to the file's content hash so
    # browsers refetch the moment the asset actually changes — whether by
    # this script, a manual edit, or a downstream workflow.
    bump_cache_busters(ROOT, INDEX_HTML, CACHE_BUSTED_ASSETS)

    # Refresh sitemap lastmod so crawlers know the page changed today.
    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url>\n'
        f'    <loc>{SITE_URL}</loc>\n'
        f'    <lastmod>{today}</lastmod>\n'
        '    <changefreq>daily</changefreq>\n'
        '    <priority>1.0</priority>\n'
        '  </url>\n'
        '</urlset>\n'
    )
    OUT_SITEMAP.write_text(sitemap_xml, encoding="utf-8")
    # A duplicate at /sitemap_index.xml exists purely as a workaround for a
    # Search Console quirk: once a sitemap URL has been submitted, Google
    # caches its fetch result indefinitely (you can't remove a sitemap from
    # the Search Console UI any more). When the original /sitemap.xml gets
    # stuck on "Couldn't fetch", submitting /sitemap_index.xml gives Google
    # a fresh URL to crawl with no cached state. Both files are kept in
    # sync on every nightly run.
    OUT_SITEMAP_INDEX.write_text(sitemap_xml, encoding="utf-8")

    print(
        f"Wrote {len(pubs)} publications "
        f"(A*={counts[TYPE_A_STAR]}, Q1={counts[TYPE_Q1]}, "
        f"OtherConf={counts[TYPE_OTHER_CONF]}, OtherJrnl={counts[TYPE_OTHER_JOURNAL]}, "
        f"Workshop={counts[TYPE_WORKSHOP]}, Preprint={counts[TYPE_PREPRINT]}) "
        f"spanning {years[-1] if years else '?'}–{years[0] if years else '?'} "
        f"— skipped {skipped} entries matching skip_title_patterns",
        file=sys.stderr,
    )
    if counts_by_topic:
        topic_summary = ", ".join(
            f"{slug}={n}" for slug, n in sorted(counts_by_topic.items(), key=lambda kv: -kv[1])
        )
        print(f"Topic coverage: {topic_summary}", file=sys.stderr)
        untagged = sum(1 for p in pubs if not p.get("topics"))
        print(f"Papers with no topic matched: {untagged}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch publications from OpenAlex, classify them, and write "
                    "data/publications.json.",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="don't rewrite data/manual_publications.yml: report which overlay "
             "entries OpenAlex has caught up with and leave the file alone. They "
             "are still kept out of the generated JSON.",
    )
    args = parser.parse_args()
    sys.exit(main(prune_manual=not args.no_prune))
