#!/usr/bin/env python3
"""Fetch Fabrizio Silvestri's publications from DBLP and classify them.

Conferences are ranked against CORE (data/core_rankings.csv); journals
are ranked against Scimago (data/scimago_journal_rank.csv). The
DBLP→CORE acronym and DBLP→ISSN mappings live in data/venues.yml.
Topic tagging lives in data/topics.yml. data/manual_publications.yml
is a manual overlay merged in after the fetch, for papers DBLP has not
indexed yet; it prunes itself once DBLP catches up. Outputs are written to
data/publications.json (fetched at runtime by assets/js/publications.js
with cache: 'no-store' so counters and the publication list always
reflect the latest run).

Dependencies: PyYAML + ruamel.yaml (pip install -r scripts/requirements.txt).
Run locally:  python3 scripts/fetch_publications.py
              python3 scripts/fetch_publications.py --no-prune   # dry run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

DBLP_PID = "s/FabrizioSilvestri"
DBLP_URL = f"https://dblp.org/pid/{DBLP_PID}.xml"
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

    An explicit entry in `topic_overrides` (keyed by DBLP key) replaces
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


def venue_abbrev(dblp_key: str) -> str:
    """conf/sigir/SmithJ24 -> 'sigir'; journals/tors/ChenHS26 -> 'tors'."""
    parts = dblp_key.split("/")
    return parts[1].lower() if len(parts) >= 2 else ""


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
    """Return True when a DBLP booktitle reads as a satellite / companion
    track rather than a main research track.

    DBLP marks satellite events in several conventions:
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
) -> str:
    """The venue classifier, expressed over plain fields rather than a
    DBLP element, so DBLP records and manual overlay entries share one
    code path. `kind` is the DBLP element name: "article" for journals,
    "inproceedings" for conference and workshop papers; `abbrev` is the
    venue abbreviation (venue_abbrev() for a DBLP key,
    manual_venue_abbrev() for an overlay one)."""
    if publtype == "informal" or abbrev == "corr":
        return TYPE_PREPRINT
    if is_workshop(booktitle):
        return TYPE_WORKSHOP

    if kind == "inproceedings":
        acro = venues.get("conference_core_acronym", {}).get(abbrev) or abbrev.upper()
        entry = core_ranks.get(acro)
        if entry and entry.get("rank") in ("A*", "A"):
            return TYPE_A_STAR
        return TYPE_OTHER_CONF

    if kind == "article":
        for issn in venues.get("journal_issn", {}).get(abbrev, []):
            entry = scimago.get(issn)
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


def classify(
    record: ET.Element,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
) -> str:
    return classify_fields(
        record.tag,
        venue_abbrev(record.get("key", "")),
        record.get("publtype"),
        (record.findtext("booktitle") or "").strip(),
        venues,
        core_ranks,
        scimago,
    )


def resolve_venue_full(
    pub: dict,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
) -> str:
    """Return the best full name we have for a venue — the CORE title
    for conferences, the Scimago title for journals — falling back to
    DBLP's booktitle/journal field when the external source is silent."""
    abbrev = venue_abbrev(pub.get("key", ""))
    if pub.get("type") in (TYPE_A_STAR, TYPE_OTHER_CONF, TYPE_WORKSHOP):
        acro = venues.get("conference_core_acronym", {}).get(abbrev) or abbrev.upper()
        entry = core_ranks.get(acro)
        if entry and entry.get("title"):
            return entry["title"]
    elif pub.get("type") in (TYPE_Q1, TYPE_OTHER_JOURNAL):
        for issn in venues.get("journal_issn", {}).get(abbrev, []):
            entry = scimago.get(issn)
            if entry and entry.get("title"):
                return entry["title"]
    return pub.get("venue", "")


def format_author(name: str) -> str:
    """'Fabrizio Silvestri' -> 'F. Silvestri'. Strip DBLP disambiguation digits."""
    name = re.sub(r"\s+\d{4}$", "", name).strip()
    parts = name.split()
    if len(parts) < 2:
        return name
    return parts[0][0] + ". " + " ".join(parts[1:])


def parse_record(record: ET.Element) -> dict:
    title = (record.findtext("title") or "").strip().rstrip(".")
    year_text = record.findtext("year") or "0"
    try:
        year = int(year_text)
    except ValueError:
        year = 0
    raw_authors = [(a.text or "").strip() for a in record.findall("author")]
    authors = [format_author(a) for a in raw_authors if a]
    venue_name = (
        record.findtext("journal") or record.findtext("booktitle") or ""
    ).strip()
    abbrev = venue_abbrev(record.get("key", ""))
    venue_short = VENUE_DISPLAY.get(abbrev, abbrev.upper()) if abbrev else ""

    # Collect every <ee> on this record. We classify into publisher vs
    # arXiv based on host: arxiv.org is always the preprint, anything
    # else (DOI, ACL Anthology, IEEE Xplore, CVPR open-access, …) is
    # treated as the publisher's canonical page. We skip wikidata.org
    # (DBLP injects these as auxiliary identifiers, not reading copies).
    all_ees = [(ee.text or "").strip() for ee in record.findall("ee") if (ee.text or "").strip()]
    url_publisher = None
    url_arxiv = None
    for u in all_ees:
        if "wikidata.org" in u:
            continue
        if "arxiv.org" in u:
            if url_arxiv is None:
                url_arxiv = u
        else:
            if url_publisher is None:
                url_publisher = u

    return {
        "key": record.get("key"),
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue_name,
        "venue_short": venue_short,
        "url": url_publisher or url_arxiv,
        "url_publisher": url_publisher,
        "url_arxiv": url_arxiv,
    }


def normalize_title_for_match(s: str) -> str:
    """Key used to cross-link conference/journal papers with their
    arXiv preprint — title variants differ in punctuation and trailing
    periods, so strip to alphanumerics+spaces."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


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


def fetch_dblp_xml() -> bytes:
    req = urllib.request.Request(DBLP_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


TYPE_ORDER = [
    TYPE_A_STAR, TYPE_Q1, TYPE_OTHER_CONF, TYPE_OTHER_JOURNAL,
    TYPE_WORKSHOP, TYPE_PREPRINT,
]


# ---------------------------------------------------------------------------
# Manual overlay — data/manual_publications.yml
#
# DBLP indexes a paper weeks or months after it appears, so the nightly
# sync lags reality. The overlay forces a paper in until DBLP catches
# up, in two shapes:
#
#   additions:  full records for papers DBLP has no entry for at all.
#   overrides:  field patches keyed by DBLP key, for papers DBLP knows
#               only as a CoRR preprint but that have since appeared at
#               a real venue.
#
# It is applied after the fetch and classification and before the JSON
# is written, and merged records go through the same topic and venue
# classification helpers as DBLP records — nothing downstream (sort,
# counters, filters, renderer) knows a record came from here.
#
# The overlay also prunes itself: an entry DBLP has caught up with is
# dropped from the output *and* deleted from the YAML, so the file
# shrinks back to empty on its own and the nightly workflow commits the
# rewrite like any other change.
# ---------------------------------------------------------------------------

# The exact field list parse_record() + main() emit, in emission order.
# Manual records are built in this order so their JSON is shaped like a
# DBLP one; anything else in the YAML is a typo and is reported rather
# than carried silently into the output.
RECORD_FIELDS = [
    "key", "title", "authors", "year", "venue", "venue_short",
    "url", "url_publisher", "url_arxiv", "type", "topics", "citations",
]

VALID_TYPES = set(TYPE_ORDER)

MANUAL_KEY_PREFIX = "manual/"


def manual_venue_abbrev(key: str) -> str:
    """Venue abbreviation for a synthetic overlay key, so the CORE and
    Scimago lookups resolve as they do for a real DBLP key. Both shapes
    work — mirror the DBLP key the paper will eventually get, or drop
    the conf/journals segment:

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

# arXiv's own DOI namespace. DBLP lists a CoRR paper's arXiv copy as
# "https://doi.org/10.48550/arXiv.2510.04727" rather than an arxiv.org
# URL, and parse_record files anything that isn't arxiv.org under
# url_publisher — so on most CoRR records the preprint link lives in
# url_publisher and url_arxiv is empty.
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
        # let the DBLP results through.
        print(
            f"[warn] [manual] {path.name} could not be parsed, ignoring the "
            f"overlay this run: {exc}",
            file=sys.stderr,
        )
        return {}, None
    return doc, handle


def plain_value(value):
    """Strip ruamel's round-trip wrapper types so a merged record
    serializes to JSON exactly like a DBLP-derived one."""
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
    venue: str,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
) -> str:
    """Resolve a manual record's `type` through classify_fields(), the
    same classifier DBLP records use. A declared type wins — it is the
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
        manual_venue_abbrev(key),
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
    parse_record() output. Returns None (with a warning) for an entry
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
        # Full names are abbreviated the same way DBLP names are;
        # already-abbreviated ones pass through unchanged.
        "authors": [format_author(str(a)) for a in (entry.get("authors") or []) if a],
        "year": year,
        "venue": venue,
        "venue_short": str(entry.get("venue_short") or "").strip(),
        # Same precedence parse_record() applies to a record's <ee> list.
        "url": (str(entry.get("url")).strip() if entry.get("url")
                else (url_publisher or url_arxiv)),
        "url_publisher": url_publisher,
        "url_arxiv": url_arxiv,
    }
    rec["type"] = manual_type(entry, key, venue, venues, core_ranks, scimago)
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
            # specified" so a placeholder can't wipe DBLP's value.
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
    # venue. On a CoRR record that overwrites the arXiv DOI, which is
    # the only preprint link there is, so rescue it into url_arxiv —
    # otherwise "the preprint link stays" holds only for the minority of
    # records where DBLP also listed an arxiv.org URL.
    if (
        "url_arxiv" not in fields
        and not pub.get("url_arxiv")
        and ARXIV_DOI_MARKER in (was_publisher or "").lower()
        and pub.get("url_publisher") != was_publisher
    ):
        pub["url_arxiv"] = was_publisher
    if "url" not in fields:
        # Same precedence parse_record() applies: the publisher page is
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
    """Merge data/manual_publications.yml into the DBLP results and
    prune the entries DBLP has caught up with. Returns the merged list;
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
    # Two title indexes: every DBLP record (an addition loses to any of
    # them), and only the published ones (an override is superseded
    # solely by a record that is no longer a preprint — classify_fields
    # returns preprint for every CoRR key, so "not a preprint" is the
    # same test as "not CoRR").
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
        # the key is still there, DBLP's title serves just as well.
        title = str(fields.get("title") or (target or {}).get("title") or "")
        norm = normalize_title_for_match(title)
        superseder = published_by_title.get(norm) if norm else None
        if superseder is not None:
            print(
                f"[manual] pruned override {corr_key}, "
                f"superseded by {superseder['key']}",
                file=sys.stderr,
            )
            pruned_overrides.append(corr_key)
            continue
        if target is None:
            # Can't tell "DBLP dropped the key" from "the key never
            # existed" in a single run, and blindly deleting on a DBLP
            # hiccup loses a hand-written entry — so warn and carry on.
            print(
                f"[warn] [manual] override {corr_key} targets a DBLP key that is "
                f"not in the current results — left in place"
                + ("" if fields.get("title") else
                   " (add a `title:` so a superseding record can be detected)"),
                file=sys.stderr,
            )
            continue
        if target.get("type") != TYPE_PREPRINT:
            # DBLP re-typed the record itself; the patch adds nothing.
            print(
                f"[manual] pruned override {corr_key}, "
                f"superseded by {target['key']}",
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
                f'DBLP now has it as {hit["key"]}',
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
    """Return ({dblp_key → citation_count}, fetched_at_iso_date) from the
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

    xml_bytes = fetch_dblp_xml()
    root = ET.fromstring(xml_bytes)

    skip_patterns = [
        re.compile(p, re.IGNORECASE) for p in venues.get("skip_title_patterns", [])
    ]
    skip_keys = set(venues.get("skip_keys", []))

    pubs: list[dict] = []
    skipped = 0
    for r in root.findall("r"):
        record = None
        for child in r:
            if child.tag in ("article", "inproceedings"):
                record = child
                break
        if record is None:
            continue
        if record.get("key") in skip_keys:
            skipped += 1
            continue
        parsed = parse_record(record)
        if any(pat.search(parsed["title"]) for pat in skip_patterns):
            skipped += 1
            continue
        parsed["type"] = classify(record, venues, core_ranks, scimago)
        parsed["topics"] = classify_topics(parsed, topics, topic_overrides)
        parsed["citations"] = citations.get(parsed["key"], 0)
        pubs.append(parsed)

    # Force in the papers DBLP hasn't indexed yet, and patch the ones it
    # still lists as CoRR-only. Runs before cross_link_arxiv so manual
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
        "source": DBLP_URL,
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
        description="Fetch publications from DBLP, classify them, and write "
                    "data/publications.json.",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="don't rewrite data/manual_publications.yml: report which overlay "
             "entries DBLP has caught up with and leave the file alone. They "
             "are still kept out of the generated JSON.",
    )
    args = parser.parse_args()
    sys.exit(main(prune_manual=not args.no_prune))
