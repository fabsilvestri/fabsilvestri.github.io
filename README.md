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
│   ├── js/publications.js            # renderer (DOM) — fetches publications.json at runtime
│   └── img/profile.jpg               # hero photo
├── data/
│   ├── publications.json             # generated — canonical JSON, served live to the page
│   ├── manual_publications.yml       # manual overlay — papers DBLP hasn't indexed yet
│   ├── venues.yml                    # DBLP → CORE acronym / Scimago ISSN map
│   ├── core_rankings.csv             # CORE conference rankings (vendored)
│   └── scimago_journal_rank.csv      # Scimago journal quartiles (manual download)
├── scripts/
│   ├── fetch_publications.py         # DBLP fetch + classify + manual overlay
│   ├── test_manual_overlay.py        # tests for the overlay merge/prune
│   ├── refresh_scimago.py            # yearly Scimago CSV refresh
│   ├── refresh_citations.py          # Scholar citation cache refresh
│   ├── discover_awards_claude.py     # weekly Claude web-search award scan
│   ├── discover_awards.py            # DuckDuckGo fallback (no API key)
│   └── requirements.txt
└── .github/workflows/
    ├── update-publications.yml       # nightly cron (04:00 UTC)
    ├── refresh-citations.yml         # weekly cron (Sun 05:15 UTC)
    ├── discover-awards.yml           # weekly cron (Mon 05:30 UTC)
    ├── bump-cache-buster.yml         # on push: rehash CSS/JS, rewrite index.html
    └── pages.yml                     # deploy on push to main (and after bot workflows)
```

## How counters stay live

`assets/js/publications.js` fetches `data/publications.json` at page
load with `cache: 'no-store'`, so the hero stats and publication list
always reflect the latest nightly refresh — no need to wait for the
cached HTML to expire. The other static assets (`publications.js`,
`analytics.js`, `style.css`) carry a `?v=<content-hash>` cache buster
that's recomputed by `fetch_publications.py` and by the
`bump-cache-buster` workflow, so a manual edit to any of them is
picked up by visitors as soon as the next deploy lands.

## Local development

```bash
python3 -m http.server 8000
open http://localhost:8000
```

(Note: the `file://` protocol won't work any more — the renderer
needs a real HTTP origin to fetch `data/publications.json`.)

## Refreshing publications manually

```bash
python3 scripts/fetch_publications.py
```

This regenerates `data/publications.json` and rewrites the
`?v=<content-hash>` query strings in `index.html`. Requires PyYAML and
ruamel.yaml (`pip install -r scripts/requirements.txt`).

## Manual publications

DBLP indexes a paper weeks or months after it appears, and
`data/publications.json` is overwritten by the nightly sync, so editing
it by hand achieves nothing. `data/manual_publications.yml` is the
supported way to force a paper in until DBLP catches up. It has two
sections:

- **`additions`** — full records for papers DBLP has no entry for at
  all. Same fields the generator emits, under a synthetic key that must
  start with `manual/`. The segment after that is the DBLP venue
  abbreviation (`manual/sigir/…`, `manual/tois/…`), so CORE and Scimago
  rank the venue exactly as they would for a real DBLP key.
- **`overrides`** — field patches keyed by DBLP key, for papers DBLP
  knows only as a CoRR preprint but that have since appeared at a real
  venue. List only the fields to replace; everything else survives, so
  the arXiv link stays on the page.

The overlay is merged in after the DBLP fetch and classification, and
merged records go through the same topic and venue classification path
as DBLP records — the renderer never learns where a record came from.

**It prunes itself.** Every run compares each entry against the live
DBLP results, using normalized titles (lowercased, punctuation
stripped, whitespace collapsed):

- an addition whose title DBLP now carries is dropped in favour of the
  DBLP record;
- an override is dropped once its target is no longer a preprint, or
  once a published DBLP record with the same title shows up;
- an override pointing at a key DBLP doesn't have is reported and left
  alone — a stale overlay entry never fails the nightly run.

Pruned entries are deleted from the YAML in place (comments and key
order preserved) and the nightly workflow commits the rewrite, so the
file empties itself without anyone tending it. To see what would go
without touching the file:

```bash
python3 scripts/fetch_publications.py --no-prune
```

The file itself documents every field. Tests:

```bash
python3 scripts/test_manual_overlay.py
```

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
each row to a title in `data/publications.json` — the merged list, so
manual-overlay records pick up counts under their `manual/…` key too —
and writes `data/citations.json` (`{key → cite_count}`). Unmatched
Scholar rows (editorials, PhD thesis, workshop abstracts, etc.) are
listed in the `unmatched` field
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
