# fabsilvestri.github.io

Personal homepage for Fabrizio Silvestri — Full Professor at Sapienza University of Rome.

Single-page static site with a "glass-light" aesthetic. Publications are
auto-synced from [DBLP](https://dblp.org/pid/s/FabrizioSilvestri.html)
nightly by a GitHub Action.

## Structure

```
.
├── index.html                        # single page
├── assets/
│   ├── css/style.css                 # glass-light theme
│   ├── js/publications.js            # renderer (DOM)
│   ├── js/publications-data.js       # generated — window.PUBLICATIONS
│   └── img/profile.jpg               # hero photo
├── data/
│   ├── publications.json             # generated — canonical JSON
│   ├── venues.yml                    # DBLP → CORE acronym / Scimago ISSN map
│   ├── core_rankings.csv             # CORE conference rankings (vendored)
│   └── scimago_journal_rank.csv      # Scimago journal quartiles (manual download)
├── scripts/
│   ├── fetch_publications.py         # DBLP fetch + classify
│   ├── refresh_scimago.py            # yearly Scimago CSV refresh
│   ├── refresh_citations.py          # Scholar citation cache refresh
│   ├── discover_awards_claude.py     # weekly Claude web-search award scan
│   ├── discover_awards.py            # DuckDuckGo fallback (no API key)
│   └── requirements.txt
└── .github/workflows/
    ├── update-publications.yml       # nightly cron (04:00 UTC)
    ├── discover-awards.yml           # weekly cron (Mon 05:30 UTC)
    └── pages.yml                     # deploy on push to main
```

## Local development

The publications renderer loads data from a `<script>` tag, so the site
works over `file://` too. But the smoothest dev experience is a local
server:

```bash
python3 -m http.server 8000
open http://localhost:8000
```

## Refreshing publications manually

```bash
python3 scripts/fetch_publications.py
```

This regenerates both `data/publications.json` and
`assets/js/publications-data.js`. No dependencies — the script uses only
the Python standard library.

## Editing venue classification

Conference ranks are looked up in [CORE](https://portal.core.edu.au/conf-ranks/)
and journal quartiles in [Scimago](https://www.scimagojr.com/). The DBLP
venue abbreviation is the segment after `conf/` or `journals/` in a
DBLP record key — e.g. a paper with key `conf/sigir/SmithJ24` has
abbreviation `sigir`.

`data/venues.yml` is a thin translation layer:

- `conference_core_acronym` — only for DBLP abbrevs that don't match their
  CORE acronym when uppercased (e.g. `nips` → `NeurIPS`).
- `journal_issn` — DBLP abbrev → ISSN(s) used to look up the journal in
  Scimago. A journal not listed here can never be classified Q1.

Classification rules:

- `publtype="informal"` or venue `corr` → **Preprint**
- Booktitle containing "workshop" or the `X@Y` shorthand → **Workshop**
- `inproceedings` whose resolved CORE rank is `A*` or `A` → **A/A\* Conference**
- `article` whose resolved Scimago ISSN has quartile Q1 in any
  [Computer Science category](scripts/fetch_publications.py) → **Q1 Journal**
- Everything else → **Other Conferences & Journals**

### Refreshing the ranking data

CORE (every ~2 years, last edition CORE2023):

```bash
curl -L 'https://portal.core.edu.au/conf-ranks/?search=&by=all&source=CORE2023&sort=atitle&page=1&do=Export' \
  -o data/core_rankings.csv
```

Google Scholar citations (refresh whenever you want fresh numbers;
nightly is fine, but Scholar will rate-limit from CI so run locally):

```bash
pip install requests beautifulsoup4   # first time
python3 scripts/refresh_citations.py
```

Scrapes `scholar.google.com/citations?user=pi985dQAAAAJ`, fuzzy-matches
each row to a DBLP title, and writes `data/citations.json`
(`{dblp_key → cite_count}`). Unmatched Scholar rows (editorials, PhD
thesis, workshop abstracts, etc.) are listed in the `unmatched` field
of the same file. The homepage's "Selected" tab uses these counts to
pick high-impact papers — definition: top-tier venue (CORE A/A* or
Scimago-Q1 CS) **and** (≥ 20 Scholar citations **or** published in the
last 2 years).

Scimago (yearly). The official download at scimagojr.com is
Cloudflare-protected, so we pull the same data from the
[ikashnitsky/sjrdata](https://github.com/ikashnitsky/sjrdata) GitHub
mirror, which publishes the Scimago export as yearly parquet files:

```bash
pip install pandas pyarrow   # one-time
python3 scripts/refresh_scimago.py
```

That downloads the newest parquet, filters to the most recent year,
and writes a slim CSV (Title, Issn, SJR Best Quartile, Categories) to
`data/scimago_journal_rank.csv`. Manual fallback if the mirror is ever
unavailable: download from <https://www.scimagojr.com/journalrank.php>
("Download data" button) and save the file under the same name — the
classifier reads it the same way.

## Awards discovery

The on-page Awards section is driven entirely by hand-curated
`data/awards.yml`. Two helpers surface *candidates* for review —
neither auto-publishes:

**Weekly, high-quality (primary)** — Claude Opus 4.7 plans and runs
web searches via the server-side `web_search` tool, reads the pages,
disambiguates namesakes, and returns a structured JSON list with
confidence labels. Requires an Anthropic API key.

```bash
pip install "anthropic>=0.88"
export ANTHROPIC_API_KEY=sk-ant-…
python3 scripts/discover_awards_claude.py
```

Outputs `data/awards_candidates.json` (structured) and
`data/awards_candidates.md` (human-readable). Costs a few cents per
run with prompt caching; the system prompt sits behind a cache
breakpoint so weekly runs get near-90% cache reads on input.

A GitHub Action (`.github/workflows/discover-awards.yml`) runs this
every Monday at 05:30 UTC and opens a PR when the candidates change.
One-time setup: add `ANTHROPIC_API_KEY` to the repo's Actions secrets.

**Zero-cost fallback** — `scripts/discover_awards.py` runs a handful
of DuckDuckGo queries and writes raw result snippets to the same
`awards_candidates.md`. Useful offline / when no API key is available.

Workflow either way: review the candidates file, verify each lead,
then add the ones you want to keep to `data/awards.yml`.

## Deployment

Push to `main`. The `pages.yml` workflow deploys the repo to GitHub Pages.
One-time setup in the repo: Settings → Pages → Build and deployment →
Source: **GitHub Actions**.

The nightly publication update commits any changes directly to `main`;
that push triggers a redeploy automatically.
