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
│   └── requirements.txt
└── .github/workflows/
    ├── update-publications.yml       # nightly cron (04:00 UTC)
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
- `inproceedings` whose resolved CORE rank is `A*` → **A\* Conference**
- `article` whose resolved Scimago ISSN has quartile Q1 in any
  [Computer Science category](scripts/fetch_publications.py) → **Q1 Journal**
- Everything else → **Other Conferences & Journals**

### Refreshing the ranking data

CORE (every ~2 years, last edition CORE2023):

```bash
curl -L 'https://portal.core.edu.au/conf-ranks/?search=&by=all&source=CORE2023&sort=atitle&page=1&do=Export' \
  -o data/core_rankings.csv
```

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

## Deployment

Push to `main`. The `pages.yml` workflow deploys the repo to GitHub Pages.
One-time setup in the repo: Settings → Pages → Build and deployment →
Source: **GitHub Actions**.

The nightly publication update commits any changes directly to `main`;
that push triggers a redeploy automatically.
