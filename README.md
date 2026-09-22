# fabsilvestri.github.io

Personal homepage for Fabrizio Silvestri — Full Professor at Sapienza University of Rome.

Single-page static site with a "glass-light" aesthetic. Publications are
auto-synced from [OpenAlex](https://openalex.org/A5044165871) nightly by a
GitHub Action, with [Crossref](https://www.crossref.org/) filling in the
titles and proceedings volumes OpenAlex leaves incomplete.

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
│   ├── manual_publications.yml       # manual overlay — papers OpenAlex hasn't indexed yet
│   ├── venues.yml                    # venue name → abbrev, CORE acronym, Scimago ISSN
│   ├── awards.yml                    # hand-curated awards and honours
│   ├── talks.yml                     # hand-curated keynotes and invited talks
│   ├── services.yml                  # hand-curated editorial boards and chairing roles
│   ├── core_rankings.csv             # CORE conference rankings (vendored)
│   └── scimago_journal_rank.csv      # Scimago journal quartiles (manual download)
├── scripts/
│   ├── fetch_publications.py         # OpenAlex fetch + classify + manual overlay
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

Both APIs it calls are open and need no credentials, locally or in CI.
A full run is about fifteen requests — three OpenAlex filters paginating
to eight, plus seven batched Crossref calls — against a polite-pool
allowance of 100,000 a day, so no API key is required and none is
checked in. If OpenAlex ever does throttle the nightly job, put a key in
an `OPENALEX_API_KEY` repository secret and pass it to the step as an
env var; the script already reads it:

```bash
OPENALEX_API_KEY=… python3 scripts/fetch_publications.py
```

If OpenAlex returns nothing at all — the author id stopped resolving,
say — the script exits without writing, so the site keeps serving the
last good `data/publications.json`.

## Manual publications

OpenAlex indexes a paper weeks or months after it appears, and
`data/publications.json` is overwritten by the nightly sync, so editing
it by hand achieves nothing. `data/manual_publications.yml` is the
supported way to force a paper in until OpenAlex catches up. It has two
sections:

- **`additions`** — full records for papers OpenAlex has no entry for at
  all. Same fields the generator emits, under a synthetic key starting
  with `manual/`. Set `abbrev:` to the venue abbreviation (`iclr`,
  `tors`) so the CORE and Scimago lookups land, or leave it out and
  encode it in the key (`manual/conf/iclr/…`, `manual/journals/tors/…`,
  or the short `manual/iclr/…`) — either way the venue is ranked exactly
  as it would be for a fetched record.
- **`overrides`** — field patches keyed by record key, for a record the
  fetch gets partly wrong: a paper still listed only as a preprint, or
  one whose venue resolved but whose publisher link points at a
  repository mirror instead of the page you want linked. List only the
  fields to replace; everything else survives. A `null` is a TODO
  placeholder, not an erase. Where a preprint's only link was its
  `10.48550` arXiv DOI under `url_publisher`, an override that sets the
  real publisher page moves that DOI to `url_arxiv` — pointing a record
  at its venue never costs it its preprint link.

Record keys are minted by the fetcher: `journals/corr/abs-<arxiv id>`
for an arXiv preprint (DBLP's old spelling, kept so existing overrides
still resolve), `doi/<doi>` for anything with a DOI, and
`openalex/<work id>` for the rest.

The overlay is merged in after the fetch and classification, and merged
records go through the same topic and venue classification path as
fetched records — the renderer never learns where a record came from.
Topics come from the `data/topics.yml` keyword patterns; a `topics:`
list in the overlay is only the fallback for papers those patterns
don't recognise. To beat the patterns, add the key to `topic_overrides`
in `data/topics.yml` — that works for `manual/…` keys too.

**It prunes itself.** Every run compares each entry against the live
results, using normalized titles (lowercased, punctuation stripped,
whitespace collapsed):

- an addition whose title the fetch now carries is dropped in favour of
  the fetched record;
- an override is dropped once the fetched record already says
  everything the override sets, or once a *different* published record
  with the same title shows up;
- an override pointing at a key the fetch doesn't have is reported and
  left alone — a stale overlay entry never fails the nightly run.

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
and journal quartiles in [Scimago](https://www.scimagojr.com/), both
joined on a short **venue abbreviation** (`sigir`, `tois`). DBLP handed
that abbreviation over in its record keys; OpenAlex names venues in
prose ("Proceedings of the 45th International ACM SIGIR Conference on
…") and leaves the source empty on about a third of conference records,
so the abbreviation has to be recovered before anything can be ranked.

`data/venues.yml` does the recovery and the translation:

- `venue_patterns` — regex over the venue name → abbrev. **First match
  wins**, so the list is ordered most-specific-first: ICTIR's
  proceedings title contains "ACM SIGIR", and PKDD's contains
  "Knowledge Discovery in Databases", so each sits above the venue that
  would otherwise swallow it.
- `venue_doi_patterns` — regex over the DOI → abbrev, tried first. The
  ACL Anthology encodes the venue in the DOI (`2025.emnlp-main.1422`),
  which is more reliable than its prose title.
- `generic_series` — source names that are a publisher's book series
  rather than a venue. Springer files conference proceedings under
  "Lecture Notes in Computer Science" and drops the volume title, so a
  record matching one of these is looked up in Crossref for the volume
  title and matched again.
- `conference_core_acronym` — only for abbrevs that don't match their
  CORE acronym when uppercased (e.g. `nips` → `NeurIPS`).
- `journal_issn` — abbrev → ISSN(s). OpenAlex reports a journal's ISSN
  on the record, so this is now a *fallback* for sources it has no ISSN
  for — but it is also the reverse lookup that puts an ISSN back on its
  abbreviation, which is what keeps "TOIS" on the page.
- `type_overrides` — key → type, for the few papers no signal
  classifies right. OpenAlex flattens a conference's satellite tracks
  into its main proceedings, so a WWW Companion paper is
  indistinguishable from a WWW research paper; DBLP recorded the
  difference and nothing in OpenAlex or Crossref does.
- `skip_keys` / `skip_title_patterns` — records to drop outright:
  front matter, proceedings volumes, and papers by other researchers
  named Silvestri that OpenAlex's author disambiguation mis-assigns.

Classification rules:

- An arXiv-only record → **Preprint**
- Venue name containing "workshop" or the `X@Y` shorthand → **Workshop**
- A proceedings paper whose resolved CORE rank is `A*` or `A` →
  **A/A\* Conference**
- A journal article whose ISSN has Scimago quartile Q1 in any
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

## Services

The Services section (editorial boards, conference chairing roles,
program committees) is driven by hand-curated `data/services.yml`.
Entries are grouped, and both the groups and the items inside them
render in file order — chairing roles are listed most-recent-first.
`fetch_publications.py` copies the file into `publications.json` under
the `services` key on every run, so editing the YAML and re-running the
fetch (or waiting for the nightly Action) is all it takes.
