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
│   └── venues.yml                    # curated A*/Q1 venue map — edit me
├── scripts/
│   ├── fetch_publications.py         # DBLP fetch + classify
│   └── requirements.txt              # (empty — stdlib only)
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

Open `data/venues.yml` and add or remove DBLP venue abbreviations under
`a_star_confs` or `q1_journals`. The abbreviation is the segment after
`conf/` or `journals/` in a DBLP record key — e.g. a paper with key
`conf/sigir/SmithJ24` has abbreviation `sigir`. Re-run the fetch script
after editing to regenerate the data.

Classification rules:

- `publtype="informal"` or venue `corr` → **Preprint**
- Booktitle containing "workshop" → **Preprint** (workshop)
- `inproceedings` whose venue abbreviation is in `a_star_confs` → **A* Conference**
- `article` whose venue abbreviation is in `q1_journals` → **Q1 Journal**
- Everything else → **Other Conferences & Journals**

## Deployment

Push to `main`. The `pages.yml` workflow deploys the repo to GitHub Pages.
One-time setup in the repo: Settings → Pages → Build and deployment →
Source: **GitHub Actions**.

The nightly publication update commits any changes directly to `main`;
that push triggers a redeploy automatically.
