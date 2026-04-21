#!/usr/bin/env python3
"""Discover candidate awards for Fabrizio Silvestri via web search.

Runs a handful of DuckDuckGo HTML queries with award-related keywords,
collects matching result URLs + snippets, and writes a review-ready
markdown file at data/awards_candidates.md. This is intentionally a
*candidate list*, not an auto-populated awards section: only entries
the user reviews and copies into data/awards.yml appear on the page.

Why DuckDuckGo HTML (and not Google / an LLM)?
  - Google + Bing block headless scrapers.
  - Paid search APIs (Serper, SerpAPI) cost $20-50/mo.
  - An LLM with web-search tools gives the best quality but needs an
    API key + budget. If/when the user wires one up, swap this script
    for an LLM-backed version — the data/awards.yml contract stays
    the same.

Dependencies: requests + beautifulsoup4.

Run: python3 scripts/discover_awards.py
"""
from __future__ import annotations

import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "awards_candidates.md"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)
DDG_URL = "https://html.duckduckgo.com/html/"
REQUEST_PAUSE = 2.0  # seconds between queries

QUERIES = [
    '"Fabrizio Silvestri" award',
    '"Fabrizio Silvestri" "best paper"',
    '"Fabrizio Silvestri" prize',
    '"Fabrizio Silvestri" fellow',
    '"Fabrizio Silvestri" Sapienza recognition',
    '"Fabrizio Silvestri" honored',
]

# Hosts that clutter results without adding signal — dblp mirrors of
# the same paper, scholar proxies, personal scrapes, etc.
NOISE_HOSTS = (
    "dblp.org",
    "scholar.google.com",
    "scholar.googleusercontent.com",
    "linkedin.com",
    "researchgate.net",
    "arxiv.org",
    "doi.org",
)


def unwrap_ddg_url(href: str) -> str:
    """DuckDuckGo wraps outgoing links as /l/?kh=-1&uddg=<urlencoded>."""
    if href.startswith("//duckduckgo.com/l/") or href.startswith("/l/"):
        qs = parse_qs(urlparse(href).query)
        inner = qs.get("uddg", [""])[0]
        if inner:
            return unquote(inner)
    return href


def run_query(session: requests.Session, q: str) -> list[dict]:
    r = session.post(DDG_URL, data={"q": q}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    hits: list[dict] = []
    for block in soup.select(".result"):
        a = block.select_one("a.result__a")
        snip = block.select_one(".result__snippet")
        if not a:
            continue
        url = unwrap_ddg_url(a.get("href", ""))
        host = urlparse(url).netloc.lower()
        if any(host.endswith(n) for n in NOISE_HOSTS):
            continue
        title = a.get_text(" ", strip=True)
        snippet = snip.get_text(" ", strip=True) if snip else ""
        hits.append({"title": title, "url": url, "host": host, "snippet": snippet})
    return hits


def main() -> int:
    seen: dict[str, dict] = {}
    by_query: dict[str, list[dict]] = {}
    with requests.Session() as session:
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })
        for q in QUERIES:
            print(f"  querying: {q}", file=sys.stderr)
            try:
                hits = run_query(session, q)
            except Exception as exc:
                print(f"    failed: {exc}", file=sys.stderr)
                hits = []
            by_query[q] = hits
            for h in hits:
                if h["url"] not in seen:
                    seen[h["url"]] = h
            time.sleep(REQUEST_PAUSE)

    lines = [
        f"# Awards discovery — {date.today().isoformat()}",
        "",
        "Candidates surfaced by `scripts/discover_awards.py`. Review each one",
        "and — if it describes a real award — add it to `data/awards.yml`.",
        "These results are raw search hits: expect false positives (namesakes,",
        "paper pages that mention \"award\" in unrelated context, etc.).",
        "",
        f"Total unique URLs: {len(seen)}",
        "",
    ]
    for q, hits in by_query.items():
        lines.append(f"## Query: `{q}`")
        lines.append(f"_{len(hits)} results_")
        lines.append("")
        if not hits:
            lines.append("_no hits_")
            lines.append("")
            continue
        for h in hits:
            lines.append(f"- **[{h['title']}]({h['url']})** · _{h['host']}_")
            if h["snippet"]:
                lines.append(f"  {h['snippet']}")
            lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"Wrote {len(seen)} unique candidates across {len(QUERIES)} queries → {OUT}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
