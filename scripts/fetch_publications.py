#!/usr/bin/env python3
"""Fetch Fabrizio Silvestri's publications from DBLP and classify them.

Conferences are ranked against CORE (data/core_rankings.csv); journals
are ranked against Scimago (data/scimago_journal_rank.csv). The
DBLP→CORE acronym and DBLP→ISSN mappings live in data/venues.yml.
Topic tagging lives in data/topics.yml. Outputs are written to
data/publications.json and assets/js/publications-data.js.

Dependencies: PyYAML (pip install -r scripts/requirements.txt).
Run locally:  python3 scripts/fetch_publications.py
"""
from __future__ import annotations

import csv
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
OUT_JSON = ROOT / "data" / "publications.json"
OUT_JS = ROOT / "assets" / "js" / "publications-data.js"
OUT_SITEMAP = ROOT / "sitemap.xml"
SITE_URL = "https://fabsilvestri.github.io/"

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


def classify(
    record: ET.Element,
    venues: dict,
    core_ranks: dict[str, dict],
    scimago: dict[str, dict],
) -> str:
    tag = record.tag
    key = record.get("key", "")
    abbrev = venue_abbrev(key)
    booktitle = (record.findtext("booktitle") or "").strip()

    if record.get("publtype") == "informal" or abbrev == "corr":
        return TYPE_PREPRINT
    if is_workshop(booktitle):
        return TYPE_WORKSHOP

    if tag == "inproceedings":
        acro = venues.get("conference_core_acronym", {}).get(abbrev) or abbrev.upper()
        entry = core_ranks.get(acro)
        if entry and entry.get("rank") in ("A*", "A"):
            return TYPE_A_STAR
        return TYPE_OTHER_CONF

    if tag == "article":
        for issn in venues.get("journal_issn", {}).get(abbrev, []):
            entry = scimago.get(issn)
            if not entry:
                continue
            for name, q in entry.get("categories", []):
                if q == 1 and name in CS_CATEGORIES:
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


def load_citations(path: Path) -> dict[str, int]:
    """Return {dblp_key → citation_count} from the Scholar scrape cache.
    Missing file → empty dict with a console note (citations are optional)."""
    if not path.exists():
        print(
            f"[warn] Citations cache missing: {path.name} — "
            f"publication items will render without cite counts. "
            f"Run scripts/refresh_citations.py to populate.",
            file=sys.stderr,
        )
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in (payload.get("citations") or {}).items()}


def main() -> int:
    venues = load_venues(VENUES_FILE)
    topics, topic_overrides = load_topics(TOPICS_FILE)
    core_ranks = load_core_rankings(CORE_FILE)
    scimago = load_scimago(SCIMAGO_FILE)
    citations = load_citations(CITATIONS_FILE)
    awards = load_awards(AWARDS_FILE)
    talks = load_talks(TALKS_FILE)
    print(
        f"Loaded venues: {len(venues.get('conference_core_acronym', {}))} CORE overrides, "
        f"{len(venues.get('journal_issn', {}))} journal ISSN mappings; "
        f"{len(core_ranks)} CORE entries, {len(scimago)} Scimago ISSNs; "
        f"{len(topics)} topics; {len(citations)} citation counts; "
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

    cross_link_arxiv(pubs)

    pubs.sort(
        key=lambda p: (
            -p["year"],
            TYPE_ORDER.index(p["type"]) if p["type"] in TYPE_ORDER else 99,
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

    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    js_body = json.dumps(payload, indent=2, ensure_ascii=False)
    OUT_JS.write_text(
        "// Auto-generated by scripts/fetch_publications.py — do not edit by hand.\n"
        f"window.PUBLICATIONS = {js_body};\n",
        encoding="utf-8",
    )

    # Refresh sitemap lastmod so crawlers know the page changed today.
    today = date.today().isoformat()
    OUT_SITEMAP.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url>\n'
        f'    <loc>{SITE_URL}</loc>\n'
        f'    <lastmod>{today}</lastmod>\n'
        '    <changefreq>daily</changefreq>\n'
        '    <priority>1.0</priority>\n'
        '  </url>\n'
        '</urlset>\n',
        encoding="utf-8",
    )

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
    sys.exit(main())
