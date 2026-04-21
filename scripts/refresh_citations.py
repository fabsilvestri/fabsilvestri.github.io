#!/usr/bin/env python3
"""Refresh data/citations.json from Google Scholar.

Scrapes the author profile at scholar.google.com/citations?user=<id>,
paginating until the profile is exhausted, then fuzzy-matches each row
against DBLP titles (normalized, with a prefix-match fallback for the
titles Scholar truncates with "..."). Writes:

    data/citations.json = {
      "scholar_id":   "pi985dQAAAAJ",
      "fetched_at":   "2026-04-21T14:30:00+00:00",
      "total_cites":  <summed citations across matched papers>,
      "citations":    { "<dblp_key>": <cite_count>, ... },
      "unmatched":    [ { "title": ..., "year": ..., "cites": ... }, ... ]
    }

Google Scholar has no public API and rate-limits aggressively — this
script is meant to be run manually from a browser-friendly environment
(local machine, not CI). If the profile page returns an interstitial
instead of the expected HTML, we abort with a clear message; the user
can retry later.

Requires: requests + beautifulsoup4. Install with:
    pip install requests beautifulsoup4
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SCHOLAR_ID = "pi985dQAAAAJ"
ROOT = Path(__file__).resolve().parent.parent
PUBS_JSON = ROOT / "data" / "publications.json"
OUT = ROOT / "data" / "citations.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)
PAGE_SIZE = 100
REQUEST_PAUSE = 1.5  # seconds between pages, be polite


def normalize_title(s: str) -> str:
    """Lowercase, strip non-alphanumeric, collapse whitespace — so
    titles match across quoting/punctuation/Unicode-dash differences."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_page(session: requests.Session, cstart: int) -> str:
    url = (
        f"https://scholar.google.com/citations?"
        f"user={SCHOLAR_ID}&hl=en&cstart={cstart}&pagesize={PAGE_SIZE}"
    )
    r = session.get(url, timeout=30)
    r.raise_for_status()
    html = r.text
    # If Scholar decides to challenge us, we get a "Please show you're
    # not a robot" page or a redirect with no publication table.
    if "gsc_a_tr" not in html:
        raise SystemExit(
            f"Scholar returned no publication rows at cstart={cstart}. "
            "Likely blocked — try again later or from a different IP."
        )
    return html


def parse_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.select("tr.gsc_a_tr"):
        title_el = tr.select_one(".gsc_a_t a")
        cite_el = tr.select_one(".gsc_a_c a")
        year_el = tr.select_one(".gsc_a_y span")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        cites_txt = (cite_el.get_text(strip=True) if cite_el else "") or "0"
        # Scholar sometimes shows "*" or other glyphs — strip to digits.
        cites = int(re.sub(r"\D", "", cites_txt) or 0)
        year_txt = (year_el.get_text(strip=True) if year_el else "") or "0"
        try:
            year = int(year_txt)
        except ValueError:
            year = 0
        out.append({"title": title, "cites": cites, "year": year})
    return out


def fetch_all_scholar(session: requests.Session) -> list[dict]:
    rows: list[dict] = []
    cstart = 0
    while True:
        print(f"  fetching cstart={cstart} …", file=sys.stderr)
        html = fetch_page(session, cstart)
        page_rows = parse_rows(html)
        rows.extend(page_rows)
        if len(page_rows) < PAGE_SIZE:
            break
        cstart += PAGE_SIZE
        time.sleep(REQUEST_PAUSE)
    return rows


def match_to_dblp(scholar_rows: list[dict], dblp_pubs: list[dict]) -> tuple[dict[str, int], list[dict]]:
    """Build {dblp_key → cite_count}. Matching strategy: first try exact
    normalized-title equality; then, because Scholar truncates long
    titles with an ellipsis, try prefix containment (Scholar prefix of
    DBLP title, or DBLP prefix of Scholar title) and require the years
    to be within 1."""
    by_norm_title: dict[str, dict] = {}
    # Prefer the row with the most cites if Scholar lists duplicates.
    for row in scholar_rows:
        key = normalize_title(row["title"])
        if not key:
            continue
        prev = by_norm_title.get(key)
        if prev is None or row["cites"] > prev["cites"]:
            by_norm_title[key] = row

    citations: dict[str, int] = {}
    matched_scholar_keys: set[str] = set()

    # Pass 1 — exact normalized-title equality.
    for pub in dblp_pubs:
        norm = normalize_title(pub.get("title", ""))
        if norm in by_norm_title:
            row = by_norm_title[norm]
            citations[pub["key"]] = row["cites"]
            matched_scholar_keys.add(norm)

    # Pass 2 — prefix match, year within 1.
    for pub in dblp_pubs:
        if pub["key"] in citations:
            continue
        dblp_norm = normalize_title(pub.get("title", ""))
        dblp_year = pub.get("year", 0) or 0
        for norm, row in by_norm_title.items():
            if norm in matched_scholar_keys:
                continue
            if not norm or not dblp_norm:
                continue
            short, long = (norm, dblp_norm) if len(norm) < len(dblp_norm) else (dblp_norm, norm)
            # Scholar truncates at ~80 chars; require a real prefix of
            # at least 40 chars to rule out accidental matches.
            if len(short) < 40:
                continue
            if not long.startswith(short):
                continue
            if abs(row["year"] - dblp_year) > 1 and dblp_year and row["year"]:
                continue
            citations[pub["key"]] = row["cites"]
            matched_scholar_keys.add(norm)
            break

    unmatched = [
        row for norm, row in by_norm_title.items() if norm not in matched_scholar_keys
    ]
    return citations, unmatched


def main() -> int:
    if not PUBS_JSON.exists():
        raise SystemExit(
            "data/publications.json missing — run fetch_publications.py first."
        )
    pubs_payload = json.loads(PUBS_JSON.read_text(encoding="utf-8"))
    dblp_pubs = pubs_payload.get("publications", [])

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })
        print(f"Fetching Scholar profile user={SCHOLAR_ID} …", file=sys.stderr)
        scholar_rows = fetch_all_scholar(session)

    print(
        f"Scholar profile has {len(scholar_rows)} rows; DBLP has {len(dblp_pubs)}.",
        file=sys.stderr,
    )

    citations, unmatched = match_to_dblp(scholar_rows, dblp_pubs)
    total = sum(citations.values())

    payload = {
        "scholar_id": SCHOLAR_ID,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_cites": total,
        "citations": citations,
        "unmatched": unmatched,
    }
    OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Matched {len(citations)}/{len(dblp_pubs)} DBLP pubs to Scholar "
        f"({total} total citations). {len(unmatched)} Scholar rows unmatched.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
