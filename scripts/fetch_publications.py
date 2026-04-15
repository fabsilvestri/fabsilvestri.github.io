#!/usr/bin/env python3
"""Fetch Fabrizio Silvestri's publications from DBLP and classify them.

Reads data/venues.yml for the A*/Q1 classification map and writes
assets/js/publications-data.js and data/publications.json.

No third-party dependencies — uses only the Python standard library.
Run locally:  python3 scripts/fetch_publications.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

DBLP_PID = "s/FabrizioSilvestri"
DBLP_URL = f"https://dblp.org/pid/{DBLP_PID}.xml"
USER_AGENT = "fabsilvestri-homepage/1.0 (+https://fabsilvestri.github.io)"

ROOT = Path(__file__).resolve().parent.parent
VENUES_FILE = ROOT / "data" / "venues.yml"
OUT_JSON = ROOT / "data" / "publications.json"
OUT_JS = ROOT / "assets" / "js" / "publications-data.js"

TYPE_A_STAR = "a_star_conf"
TYPE_Q1 = "q1_journal"
TYPE_OTHER = "other"
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


def load_venues(path: Path) -> dict[str, list[str]]:
    """Tiny YAML loader for the specific venues.yml format.

    Supports: top-level keys whose values are lists of strings, "#" comments,
    and inline "<value> # comment" annotations. Does NOT support nested maps
    or anchors — we don't need them here, and this keeps the script
    dependency-free so it can run in any CI container without pip install.
    """
    venues: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        # Drop inline comments: whitespace + "#" + rest-of-line.
        line = re.sub(r"\s+#.*$", "", raw)
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            current_key = stripped[:-1].strip()
            venues[current_key] = []
        elif stripped.startswith("- ") and current_key is not None:
            item = stripped[2:].strip().strip('"').strip("'")
            if item:
                venues[current_key].append(item.lower())
    return venues


def venue_abbrev(dblp_key: str) -> str:
    """conf/sigir/SmithJ24 -> 'sigir'; journals/tors/ChenHS26 -> 'tors'."""
    parts = dblp_key.split("/")
    return parts[1].lower() if len(parts) >= 2 else ""


def is_workshop(booktitle: str) -> bool:
    return bool(booktitle and re.search(r"\bworkshop\b", booktitle, re.I))


def classify(record: ET.Element, venues: dict[str, list[str]]) -> str:
    tag = record.tag
    key = record.get("key", "")
    abbrev = venue_abbrev(key)
    booktitle = (record.findtext("booktitle") or "").strip()

    if record.get("publtype") == "informal" or abbrev == "corr":
        return TYPE_PREPRINT
    if is_workshop(booktitle):
        return TYPE_PREPRINT
    if tag == "inproceedings" and abbrev in venues.get("a_star_confs", []):
        return TYPE_A_STAR
    if tag == "article" and abbrev in venues.get("q1_journals", []):
        return TYPE_Q1
    return TYPE_OTHER


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
    url = None
    for ee in record.findall("ee"):
        candidate = (ee.text or "").strip()
        if candidate:
            url = candidate
            break
    return {
        "key": record.get("key"),
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue_name,
        "venue_short": venue_short,
        "url": url,
    }


def fetch_dblp_xml() -> bytes:
    req = urllib.request.Request(DBLP_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


TYPE_ORDER = [TYPE_A_STAR, TYPE_Q1, TYPE_OTHER, TYPE_PREPRINT]


def main() -> int:
    venues = load_venues(VENUES_FILE)
    print(
        f"Loaded venues: {len(venues.get('a_star_confs', []))} A* confs, "
        f"{len(venues.get('q1_journals', []))} Q1 journals",
        file=sys.stderr,
    )

    xml_bytes = fetch_dblp_xml()
    root = ET.fromstring(xml_bytes)

    skip_patterns = [
        re.compile(p, re.IGNORECASE) for p in venues.get("skip_title_patterns", [])
    ]

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
        parsed = parse_record(record)
        if any(pat.search(parsed["title"]) for pat in skip_patterns):
            skipped += 1
            continue
        parsed["type"] = classify(record, venues)
        pubs.append(parsed)

    pubs.sort(
        key=lambda p: (
            -p["year"],
            TYPE_ORDER.index(p["type"]) if p["type"] in TYPE_ORDER else 99,
            p["title"].lower(),
        )
    )

    counts = {t: sum(1 for p in pubs if p["type"] == t) for t in TYPE_ORDER}
    years = sorted({p["year"] for p in pubs if p["year"] > 0}, reverse=True)

    payload = {
        "last_updated": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": DBLP_URL,
        "count": len(pubs),
        "counts_by_type": counts,
        "years": years,
        "publications": pubs,
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

    print(
        f"Wrote {len(pubs)} publications "
        f"(A*={counts[TYPE_A_STAR]}, Q1={counts[TYPE_Q1]}, "
        f"Other={counts[TYPE_OTHER]}, Preprint={counts[TYPE_PREPRINT]}) "
        f"spanning {years[-1] if years else '?'}–{years[0] if years else '?'} "
        f"— skipped {skipped} entries matching skip_title_patterns",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
