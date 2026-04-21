#!/usr/bin/env python3
"""Refresh data/scimago_journal_rank.csv from the ikashnitsky/sjrdata mirror.

The official Scimago download (scimagojr.com) is Cloudflare-protected
and cannot be fetched headlessly. Ilya Kashnitsky publishes a GitHub
mirror as yearly parquet files at ikashnitsky/sjrdata. This script
grabs the newest parquet, filters to the most recent year, and writes
a CSV in Scimago's own format (semicolon-separated, Title Case headers)
so fetch_publications.py can read it the same way as an official
download.

Run once a year when Scimago publishes a new edition. Requires
pandas + pyarrow — install with:
    pip install pandas pyarrow
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "scimago_journal_rank.csv"

TREE_API = (
    "https://api.github.com/repos/ikashnitsky/sjrdata/contents/data-raw/sjr-journal"
)
RAW_BASE = "https://raw.githubusercontent.com/ikashnitsky/sjrdata/master/data-raw/sjr-journal"
USER_AGENT = "fabsilvestri-homepage/1.0 (+https://fabsilvestri.github.io)"

# Parquet column name → output CSV header. Kept minimal — only the
# columns fetch_publications.py reads (Issn, Categories, SJR Best
# Quartile) plus Title for human debugging. Drops the full Scimago
# dump from ~10 MB to ~4 MB.
COLUMN_MAP = {
    "title": "Title",
    "issn": "Issn",
    "sjr_best_quartile": "SJR Best Quartile",
    "categories": "Categories",
}


def pick_latest_parquet() -> str:
    req = urllib.request.Request(TREE_API, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        entries = json.loads(resp.read())
    parquets = [e["name"] for e in entries if e["name"].endswith(".parquet")]
    if not parquets:
        raise SystemExit("No parquet files listed in sjrdata mirror.")
    return sorted(parquets)[-1]


def main() -> int:
    fname = pick_latest_parquet()
    url = f"{RAW_BASE}/{fname}"
    print(f"Fetching {url} …", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        buf = io.BytesIO(resp.read())

    df = pd.read_parquet(buf)
    latest_year = int(df["year"].max())
    sub = df[df["year"] == latest_year].copy()

    missing = [c for c in COLUMN_MAP if c not in sub.columns]
    if missing:
        raise SystemExit(f"Mirror schema changed — missing columns: {missing}")

    sub = sub[list(COLUMN_MAP.keys())].rename(columns=COLUMN_MAP)
    sub.to_csv(OUT, sep=";", index=False, encoding="utf-8")

    print(
        f"Wrote {len(sub)} journals for year {latest_year} from {fname} → {OUT}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
