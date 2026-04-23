# PROMPT — clone this homepage for another academic

This file is a standalone spec. Given a filled-in **Inputs** block below, an
LLM generates an identical-looking homepage for a different professor by
pulling down the template repo, substituting a fixed set of values, and
pushing to a new repo. Everything not listed in **§Edits** is copied verbatim.

**Template source:** `https://github.com/fabsilvestri/fabsilvestri.github.io.git`

## Usage

Assume the LLM is started in an empty working directory that contains nothing
but this file. The LLM should perform every step below; no pre-existing tree
is required.

1. Collect inputs. Ask the user only for what you cannot web-research (bio,
   research cards, topic patterns, colour). Derive the rest from DBLP, Scholar,
   and the university faculty page.
2. Materialise the template. Check whether you're already inside a clone
   (a sibling `index.html` and `scripts/fetch_publications.py` exist alongside
   this `PROMPT.md`). If **yes**, skip this step and treat the current
   directory as your working directory. If **no**, pull the template into a
   fresh subdirectory and drop its git history so the new site starts clean:
   ```bash
   git clone https://github.com/fabsilvestri/fabsilvestri.github.io.git site
   cd site
   rm -rf .git
   git init -b main
   ```
   From here on, all paths are relative to the working directory.
3. Apply **§Edits**; keep every other file as-is.
4. Run **§Bootstrap** to populate the generated data files.
5. Commit and push. Assumes the user already created an empty repo at
   `https://github.com/<github_user>/<github_user>.github.io`:
   ```bash
   git add -A
   git commit -m "Initial site"
   # Add origin only if one isn't already set (already-inside-a-fork case).
   git remote get-url origin >/dev/null 2>&1 \
     || git remote add origin https://github.com/<github_user>/<github_user>.github.io.git
   git push -u origin main
   ```

## Inputs

```yaml
# Identity
full_name:     "Jane Q. Public"
short_name:    "J. Q. Public"              # how the author name renders in pub lists
title:         "Full Professor of Computer Science"
tagline:       "Algorithms & Game Theory"  # 3-5 words — used in <title>, og:title
university:    "Sapienza University of Rome"
department:    "DIAG — ..."
street:        "Via Ariosto 25"
city:          "Rome"
postal:        "00185"
country:       "IT"
office_room:   "Room B2xx"                  # optional
email:         "jane@uni.it"
phone:         "+39 ..."                    # optional
alumni_of:                                  # past institutions for JSON-LD
  - "ETH Zürich"
  - "Max Planck Institute for Informatics"

# Hosting
github_user:   "janepublic"
site_domain:   "janepublic.github.io"       # usually "<github_user>.github.io"
photo_url:     "https://.../portrait.jpg"

# External identifiers (omit meta tags and .sameAs entries when empty)
dblp_pid:      "p/JanePublic"               # path after /pid/ on dblp.org
scholar_user:  ""                           # user=... on scholar.google.com
orcid:         ""
github:        ""                           # handle
linkedin:      ""                           # slug (e.g. "jane-public-123")
twitter:       ""                           # handle (without @)
wikidata:      ""                           # Qxxxxx

# Hero + about
eyebrow:       "Full Professor · Sapienza University of Rome"
hero_lede: |
  2-4 sentences. Name the group / programme and the research areas.
  Wrap area keywords in <strong>.

about:                                      # exactly 3 paragraphs (HTML allowed)
  - "Who they are, role, thrust."
  - "Industrial / academic stints."
  - "Publication record, service, awards summary."

research_cards:                             # exactly 4, single-glyph icon each
  - { icon: "◉", title: "Area 1", description: "One paragraph." }
  - { icon: "✎", title: "Area 2", description: "..." }
  - { icon: "✧", title: "Area 3", description: "..." }
  - { icon: "⚑", title: "Area 4", description: "..." }

# Publication-filter chips. Patterns are case-insensitive regex over title+venue.
topics:
  - { slug: algo, name: "Algorithms",
      patterns: ["approximat", "online algorithm", "scheduling"] }
  # …up to ~15; the catch-all "misc" slug is auto-added by the classifier.

teaching_intro: |
  Optional HTML opener (e.g. "I coordinate the X programme…").
  Fallback: "I currently teach the following courses:"
teaching_note: |
  Optional HTML closer.
  Fallback: "I regularly supervise MSc and PhD theses. Prospective
  students are welcome to get in touch."

courses:
  - { title: "Algorithm Design", lang: EN, note: "MSc — Eng. of CS.", url: "" }

# Q1 journal ISSNs — list only journals this person publishes in
journal_issns:
  talg:  ["1549-6325"]
  jacm:  ["0004-5411", "1557-735X"]

# CORE acronym overrides — only where dblp abbrev ≠ CORE acronym
conf_core_overrides:
  nips: NeurIPS

awards: []                                  # see data/awards.yml schema
talks:  []                                  # see data/talks.yml schema

# Branding (defaults keep Sapienza amaranto + gold)
primary_hex:    "#8e1f2d"
complement_hex: "#a88929"

# Optional SEO + tracking
google_verification: ""                     # Search Console HTML tag content
ga4_id:              ""                     # G-XXXXXXXXXX
```

## Derivations

Compute from inputs:

- **`initials`** = first letter of `full_name`'s first word + first letter of
  its last word (e.g. "Stefano Leonardi" → `SL`). Used as nav brand and as
  the title lookup in author-highlight regex.
- **`last_name`** = last whitespace-separated word of `full_name`. Used in
  `ME_RE`, IEEE download filename, and author formatter.
- **`<title>`** / **`og:title`** =
  `"<full_name> — <tagline> · <title>, <short university>"`
  where *short university* drops "University of" / "Università di" filler
  (e.g. "Sapienza University of Rome" → "Sapienza University of Rome"
  long form; "Sapienza Rome" short form is fine for og).
- **Meta keywords** = `full_name`, `university`, each `research_cards[*].title`,
  each `topics[*].name`, plus any `alumni_of` entry names — comma-separated.
- **JSON-LD `knowsAbout`** = the `title` of each `research_card` ∪ the `name`
  of each `topic` (deduplicated).
- **JSON-LD `sameAs`** and **contact `.social`** block = one URL per non-empty
  identifier:
  `https://dblp.org/pid/<dblp_pid>.html`,
  `https://scholar.google.com/citations?user=<scholar_user>`,
  `https://orcid.org/<orcid>`,
  `https://github.com/<github>`,
  `https://www.linkedin.com/in/<linkedin>/`,
  `https://twitter.com/<twitter>`,
  `https://www.wikidata.org/entity/<wikidata>`.
  Skip entries for empty inputs. Use the same list in both places.
- **CSS palette** — set `--accent-1` = `primary_hex`. Derive:
  `--accent-2` ≈ 18% lighter sibling (blended with white),
  `--accent-3` ≈ 25% darker sibling,
  `--accent-gold` = `complement_hex`, `--accent-gold-deep` ≈ 20% darker.
  Retint the three `.orb-*` background hexes to pastel siblings of the primary
  and update every `rgba(90, 22, 34, …)` shadow tint to the primary's RGB.

## Edits

Every file not listed here is copied verbatim.

| File | Action |
|---|---|
| `index.html` | Rewrite in full: `<title>`, every `<meta>` (description, keywords, author, `og:*`, `twitter:*`, `profile:first_name/last_name`), `<link rel="canonical">`, the Search-Console `<meta>` (set to `google_verification` or remove), `<script type="application/ld+json">` (`name`, `givenName`, `familyName`, `jobTitle`, `worksFor`, `alumniOf`, `email`, `url`, `image`, `sameAs`, `knowsAbout`, `hasOccupation.occupationLocation.name`), nav brand initials, nav-cta "Scholar ↗" `href`, hero (eyebrow, h1, lede, photo alt), About paragraphs, research cards, teaching prose + course list, the `.pub-meta` DBLP link, the footer copyright name, contact `<div class="card contact-card">` blocks (office, email/phone, `.social` links). Omit `twitter:site` / `twitter:creator` / contact-card Twitter entry when `twitter` is empty — same for every external identifier. `og:image` / `twitter:image` absolute URL = `https://<site_domain>/assets/img/profile.jpg`. |
| `assets/img/profile.jpg` | Download `photo_url`, centre-crop to square, ~640 px, JPEG q≈85. |
| `assets/img/favicon.png` | Regenerate from the new portrait (32×32 or 64×64), or replace with a plain initials tile in the primary colour. |
| `assets/css/style.css` | Apply the palette derivation above. Update the file's top comment to name the new owner. Nothing else changes. |
| `assets/js/publications.js` | Update three person-specific constants: `ME_RE = /^<FirstInitial>\.?\s*<LastName>$/i`; `"Publications — <full_name>"` in `buildIEEEDocument` header; `"Source: https://dblp.org/pid/<dblp_pid>.html"` in the same header; `a.download = "<lastname>-publications-ieee.txt"` in `downloadIEEE`. All other logic is unchanged. |
| `assets/js/analytics.js` | `GA4_ID` ← `ga4_id` (or keep `"G-XXXXXXXXXX"` placeholder to ship dormant). |
| `data/venues.yml` | Keep `skip_keys`, `skip_title_patterns`, and the header comment. Replace `conference_core_acronym` with `conf_core_overrides`, `journal_issn` with `journal_issns`. |
| `data/topics.yml` | Replace `topics:` with inputs `topics`. Reset `topic_overrides: {}`. |
| `data/awards.yml` | `awards:` ← `awards`. |
| `data/talks.yml` | `talks:` ← `talks`. |
| `scripts/fetch_publications.py` | `DBLP_PID` ← `dblp_pid`. Optionally update `USER_AGENT` to reference the new site. |
| `scripts/refresh_citations.py` | `SCHOLAR_ID` ← `scholar_user`. Skip the run when empty. |
| `scripts/discover_awards.py` | Replace the literal `"Fabrizio Silvestri"` in `QUERIES` with `full_name`. |
| `scripts/discover_awards_claude.py` | Rewrite the "Target person" block inside `SYSTEM_PROMPT` with the new identity: name, title, department, present & past affiliations, DBLP/Scholar IDs, research areas, plausible namesakes to disambiguate. |
| `robots.txt` | `Sitemap:` URL ← `https://<site_domain>/sitemap.xml`. |
| `sitemap.xml` | `<loc>` ← `https://<site_domain>/`. |
| `README.md` | Rewrite the opening paragraph for the new owner; swap DBLP/Scholar links. Keep the refresh-cadence sections unchanged — they apply to any installation. |

## Bootstrap

Run these from inside `site/` (the clone target from §Usage step 2) **after**
applying §Edits. The commit / push is handled in §Usage step 5.

```bash
pip install -r scripts/requirements.txt
pip install pandas pyarrow                  # refresh_scimago.py, first run only

python3 scripts/fetch_publications.py       # DBLP → data/publications.json
python3 scripts/refresh_citations.py        # Scholar → data/citations.json (skip if scholar_user is empty)
# python3 scripts/refresh_scimago.py        # only if data/scimago_journal_rank.csv is stale
```

## Automation that comes with the clone

The cloned repo carries three GitHub Actions workflows — all per-person-agnostic,
copy verbatim, no edits needed:

- `.github/workflows/update-publications.yml` — runs `fetch_publications.py`
  nightly at 04:00 UTC and commits any change to `data/publications.json` +
  `assets/js/publications-data.js` + `sitemap.xml` + `index.html` (the last
  one for the asset cache-buster).
- `.github/workflows/refresh-citations.yml` — runs `refresh_citations.py`
  on the 1st and 15th of each month (≈ biweekly) to scrape Google Scholar.
  Best effort: Scholar rate-limits CI IPs, so some runs may abort. The
  workflow swallows the failure and the next run tries again.
- `.github/workflows/discover-awards.yml` — runs `discover_awards_claude.py`
  every Monday at 05:30 UTC and opens a PR with `data/awards_candidates.{json,md}`
  for review.
- `.github/workflows/pages.yml` — deploys the site to GitHub Pages on every
  push to `main`.

**One-time GitHub setup** (the LLM can't do this — instruct the user):

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Settings → Secrets and variables → Actions → New repository secret**
   → `ANTHROPIC_API_KEY` = the user's Anthropic key (only needed for the
   weekly award-discovery PR; without it that workflow will fail silently —
   the site still works).
3. **Settings → Actions → General → Workflow permissions → Read and write
   permissions** (so the nightly job can commit and the discovery job can
   open PRs).

## Classification rules (reference — unchanged across installations)

Every DBLP record lands in one of six buckets:

- `preprint` — `publtype="informal"` or venue `corr`.
- `workshop` — booktitle matches `workshop|companion|posters?|tutorials?|demonstrations?|demos?|doctoral|abstracts?|student` or contains `@`.
- `a_star_conf` — `inproceedings` whose resolved CORE rank is `A*` or `A`.
- `q1_journal` — `article` whose ISSN resolves to Q1 in any Scimago Computer Science category.
- `other_conf` / `other_journal` — fallbacks.

The **Selected** on-page view shows the top 15 most-cited papers from the
`a_star_conf + q1_journal` pool. The IEEE `.txt` download mirrors that set.

## Post-generation sanity checks

```bash
# No residual template-owner mentions:
grep -rniE 'silvestri|fabsilvestri|fabreetseo|pi985dQAAAAJ|rstless|Q130843901' . \
    --include='*.html' --include='*.md' --include='*.yml' \
    --include='*.js' --include='*.py' --include='*.xml' --include='*.txt'

# Pipeline produces non-zero counts for every bucket:
python3 scripts/fetch_publications.py
```

After `fetch_publications.py`, the hero stats on the rendered page
(Publications, A/A\* Conf. papers, Years active) should show real numbers.

---

# For non-experts — end-to-end walkthrough

The sections above are written for an LLM applying the prompt. If you are the
professor whose site is being built and you'd rather click than type, this
section is for you. The whole thing takes ~45 minutes, one time, then runs
itself.

## What you need

- A **GitHub** account (free — <https://github.com/signup>).
- An **LLM subscription** (see §Recommended subscriptions below). We'll assume
  you pick **Claude Pro** — the rest of this walkthrough uses Claude Code.
- **Python 3.10+** installed on your computer. Mac: usually pre-installed; on
  Windows, install from <https://www.python.org/downloads/>.
- A **portrait photo** (~1000 px square, JPEG).

## Step 1 — fork the template

1. While signed in to GitHub, visit <https://github.com/fabsilvestri/fabsilvestri.github.io>.
2. Click the **Fork** button (top right). Name your fork `<yourusername>.github.io`
   (e.g. `janepublic.github.io`). This gives you a full copy you can edit.

GitHub Pages will later publish anything on that repo's `main` branch to
`https://<yourusername>.github.io/` automatically.

## Step 2 — install Claude Code on your computer

Follow the installer at <https://www.anthropic.com/claude-code>. When it asks
you to sign in, use the same email as your Claude Pro subscription.

## Step 3 — hand the prompt to Claude Code

1. Clone your forked repo to your computer. Either use the green **<> Code**
   button on GitHub → **Open with GitHub Desktop**, or open a terminal and run:
   ```bash
   git clone https://github.com/<yourusername>/<yourusername>.github.io.git
   cd <yourusername>.github.io
   ```
2. Launch Claude Code in that folder:
   ```bash
   claude
   ```
3. Tell Claude:

   > Read `PROMPT.md`. Apply it to me. My information: [paste the filled-in
   > Inputs block].

   Fill in the YAML **Inputs** block from §Inputs above with your details. For
   the fields you don't know how to answer (e.g. `research_cards`, `topics`,
   `hero_lede`), ask Claude for drafts: *"Draft 4 research cards based on my
   DBLP profile at https://dblp.org/pid/.../"*. Review and revise.

Claude Code will edit the files, run the bootstrap scripts, and commit the
changes for you. Follow its prompts.

## Step 4 — push to GitHub

When Claude finishes, ask:

> Push the changes to GitHub.

Claude Code will run `git push`. (If it asks you to authenticate, follow the
GitHub device-login URL it prints.)

## Step 5 — three GitHub clicks (one-time)

In the repo's web page on github.com:

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Settings → Actions → General → Workflow permissions → Read and write permissions** (then Save).
3. **Settings → Secrets and variables → Actions → New repository secret.**
   - Name: `ANTHROPIC_API_KEY`
   - Value: your API key from <https://console.anthropic.com/> → Settings → API Keys.
   - (Skip this if you don't want the weekly automated award-discovery PR —
     the rest of the site works without it.)

Wait ~2 minutes. Visit `https://<yourusername>.github.io/`. Your site is live.

## Step 6 — ongoing maintenance

You don't have to do anything. Every night at 04:00 UTC the nightly workflow
pulls fresh publications from DBLP and updates the site. Every Monday the
award-discovery workflow opens a PR with candidate awards for you to review.

When you want to add an invited talk or update the About section, edit
`data/talks.yml` or `index.html` directly in GitHub's web UI — the workflows
will redeploy automatically.

# Recommended subscriptions

| What | Option | Cost | Why |
|---|---|---|---|
| **LLM for the initial clone + ongoing tweaks** | **Claude Pro** + Claude Code | **$20 / month** | Best integration with files + git; handles the full clone/patch/push flow autonomously. This is the recommended choice for one-off setup and occasional edits. |
| | Claude Max | $100–200 / month | Only worth it if you'll use Claude heavily for other research/coding too. Overkill just for this site. |
| | ChatGPT Plus | $20 / month | Works but needs more hand-holding on local files and git. |
| | Cursor Pro | $20 / month | IDE-based alternative to Claude Code; also fine. |
| **API key for the weekly award-discovery workflow** | **Anthropic API** (pay-as-you-go, no subscription) | **~$8 / year** | Each weekly run costs roughly $0.10–0.30 with prompt caching; 52 runs/year ≈ $8. Create the key at <https://console.anthropic.com/>. |
| **GitHub hosting** | **GitHub Free** | **$0** | GitHub Pages + Actions minutes are free for public repos on any plan. No need for Pro. |
| **Domain name** (optional) | Namecheap / Cloudflare | ~$10 / year | Only if you want a custom domain like `janepublic.it` instead of the default `janepublic.github.io`. Add it in **Settings → Pages → Custom domain** after buying. |
| **Professional headshot** | Local photographer | one-time | Optional. A clean square JPEG in good light is all you need. |

**Total, minimum realistic spend for one year:** ~$248 (Claude Pro $240 + API
$8). If you cancel Claude Pro after the initial setup, ongoing cost drops to
~$8 / year.

**Cheapest path (for someone willing to learn a bit):** skip the monthly
subscription and use the Anthropic API directly for both the setup and the
weekly workflow. Setup costs roughly $2–5 in API credits. Ongoing: ~$8 / year.
Total first year: ~$15. This assumes you're comfortable reading error messages
and running Python scripts.
