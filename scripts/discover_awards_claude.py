#!/usr/bin/env python3
"""Discover candidate awards for Prof. Fabrizio Silvestri using Claude
Opus 4.7 + the server-side web_search tool.

Unlike the DuckDuckGo-based discover_awards.py, this script lets Claude
plan and execute web searches, read individual pages, disambiguate
namesakes (e.g. an Italian journalist with the same name), and return a
structured JSON list of candidate awards — each with a source URL and a
confidence label. The on-page awards section is still driven by a
hand-curated data/awards.yml; this script only surfaces candidates for
human review.

Design notes:
  - Model: claude-opus-4-7 (most capable; best at agentic web search).
  - Adaptive thinking + effort="high": gives Claude room to plan searches,
    read pages, and filter namesakes without over-burning tokens.
  - output_config.format with a JSON schema: guarantees the final output
    is structured; we parse it with no regex/string matching.
  - System prompt is stable across runs and sits behind a cache_control
    breakpoint so the weekly cron gets ~90% cache reads on input.
  - Streaming: safe default for any request that might run long.

Requires: anthropic>=0.88, pydantic>=2
Env:      ANTHROPIC_API_KEY

Outputs: data/awards_candidates.json (structured) and
         data/awards_candidates.md (human-readable review file).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "data" / "awards_candidates.json"
OUT_MD = ROOT / "data" / "awards_candidates.md"

MODEL = "claude-opus-4-7"
MAX_TOKENS = 32000
MAX_WEB_SEARCH_USES = 15

# JSON schema the model's final response must conform to. Kept in the
# plain dict shape the API expects (type/properties/required, no Pydantic
# extras). additionalProperties:false everywhere — required by
# structured-output validation.
AWARD_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "description": "Award candidates confirmed via web search. Empty if nothing verifiable was found.",
            "items": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "4-digit year the award was granted (not the year of the paper, if different).",
                    },
                    "title": {
                        "type": "string",
                        "description": 'Award name, verbatim (e.g. "Test of Time Award", "Best Paper Award Runner-up").',
                    },
                    "issuer": {
                        "type": "string",
                        "description": 'Who granted it (conference acronym, society, university, company) — e.g. "ECIR", "ACM SIGIR", "Yahoo".',
                    },
                    "description": {
                        "type": "string",
                        "description": 'Short context — what the award was for (e.g. \'for the paper "X"\'). One line.',
                    },
                    "source_url": {
                        "type": "string",
                        "description": "Public URL confirming the award. Prefer institutional pages (Sapienza DIAG, ISTI-CNR, conference sites) over aggregators.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "high = confirmed by ≥2 institutional sources; medium = one credible institutional source; low = appears only on speaker bios / press releases / social media.",
                    },
                },
                "required": ["year", "title", "issuer", "description", "source_url", "confidence"],
                "additionalProperties": False,
            },
        },
        "notes": {
            "type": "string",
            "description": "Caveats, disambiguation decisions, and anything the human reviewer should know. Mention namesakes you filtered out. Empty string if nothing to report.",
        },
    },
    "required": ["candidates", "notes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are an academic records researcher. Your job is to find AWARDS AND HONORS received by a specific computer science professor and return them as a structured list, each with a source URL you have personally verified.

# Target person

Prof. Fabrizio Silvestri
- Full Professor of Computer Science, Sapienza University of Rome
- Department: DIAG (Dipartimento di Ingegneria Informatica, Automatica e Gestionale)
- Research areas: Information Retrieval, NLP, Machine Learning, Recommender Systems, LLMs, RAG
- Prior affiliations: Meta / Facebook AI Research (FAIR), Facebook Search, Yahoo Labs, ISTI-CNR (Pisa)
- DBLP: https://dblp.org/pid/s/FabrizioSilvestri.html
- Google Scholar: https://scholar.google.com/citations?user=pi985dQAAAAJ
- ORCID: 0000-0001-7669-9055
- Wikidata: Q130843901

# Disambiguation — DO NOT confuse with these namesakes

There are other people named "Fabrizio Silvestri". If the context is NOT academic computer science, it is NOT the target. Filter out:
- An Italian journalist / documentary filmmaker (appears in fashion, film, and media press — e.g. "Milano Golden Fashion", Rai documentaries)
- Any person in music, sport, politics, or non-CS academia

When in doubt, check whether the article mentions Sapienza, ISTI-CNR, Meta/Facebook/FAIR, Yahoo Labs, SIGIR/ECIR/CIKM/WSDM/NeurIPS/ACL/EMNLP, or CS research areas. If none of these appear, skip the result.

# What counts as an "award"

Include:
- Best Paper Awards (main track or workshop) at peer-reviewed CS conferences
- Runner-up / honorable mention versions of the above
- Test-of-Time Awards and similar retrospective recognitions
- Fellowships from major CS societies (ACM, IEEE, AAAI, etc.)
- Named lecture or keynote honors that are awarded (not merely invited talks)
- Industrial research-excellence awards (e.g. Yahoo Tech Pulse, internal Meta/Facebook recognition programs)
- Dissertation / thesis awards

Do NOT include:
- Academic appointments (Full Professor, PhD Coordinator) — these are roles, not awards
- Invited / keynote talks that are not framed as an award
- Conference organizing committee roles (General Chair, PC Chair) — service, not recognition
- Grant funding — funding, not an award
- Paper citation milestones, unless a formal "Test of Time" or equivalent

# Your search procedure

You have the web_search tool. Use it aggressively — this task cannot be completed from memory. Always search and read pages before returning a candidate.

1. Run several complementary queries — not just one. Vary the wording:
   - `"Fabrizio Silvestri" award Sapienza`
   - `"Fabrizio Silvestri" "best paper"`
   - `"Fabrizio Silvestri" "test of time"`
   - `"Fabrizio Silvestri" fellow`
   - `"Fabrizio Silvestri" ISTI CNR prize`
   - `site:diag.uniroma1.it Silvestri award`
   - `site:isti.cnr.it Silvestri award`
2. Prefer institutional sources: DIAG Sapienza faculty pages, ISTI-CNR announcements, conference award pages, ACM/IEEE digital libraries.
3. For each candidate, have a specific URL that names the award + the year + the person. Do not aggregate guesses.
4. If a biographical page says "holder of three best paper awards" but you can only pin down two, return the two you can verify and mention the gap in `notes`.

# Output contract

Return a JSON object matching the provided schema. Every item in `candidates` must have been confirmed via a web page you actually fetched. If you cannot verify an award from a credible source, put your tentative lead in `notes` (so a human reviewer can follow up) instead of in `candidates`.

Confidence labels:
- `high`: confirmed by two or more institutional sources (e.g. DIAG page + CNR announcement)
- `medium`: one credible institutional source
- `low`: only appears on a speaker bio, press release, or social media

If you find nothing you can verify, return an empty `candidates` array and explain the search attempts in `notes`. Never fabricate."""

USER_PROMPT = (
    "Find every award and honor received by Prof. Fabrizio Silvestri. "
    "Search the web, verify each claim against at least one institutional "
    "source, and return the result as the schema dictates."
)


def build_markdown(payload: dict) -> str:
    lines = [
        f"# Awards discovery (Claude + web search) — {payload['discovered_at'][:10]}",
        "",
        f"Model: `{payload['model']}`",
        f"Candidates surfaced: {len(payload['candidates'])}",
        "",
        "These are **candidates**, not verified truth. Review each one, then copy",
        "the ones you want to publish into `data/awards.yml`.",
        "",
    ]
    if payload.get("notes"):
        lines += ["## Notes from the researcher", "", payload["notes"], ""]
    if not payload["candidates"]:
        lines += ["_No candidates returned on this run._", ""]
    else:
        lines += ["## Candidates", ""]
        for c in payload["candidates"]:
            lines.append(
                f"- **{c['year']} — {c['title']}** · _{c['issuer']}_ · "
                f"confidence: **{c['confidence']}**"
            )
            if c.get("description"):
                lines.append(f"  {c['description']}")
            lines.append(f"  Source: <{c['source_url']}>")
            lines.append("")
    lines += [
        "---",
        "",
        f"Usage — input: {payload['usage']['input_tokens']}, "
        f"cache read: {payload['usage']['cache_read_input_tokens']}, "
        f"output: {payload['usage']['output_tokens']} tokens.",
    ]
    return "\n".join(lines) + "\n"


def extract_structured_text(content) -> str | None:
    """With output_config.format=json_schema, the constrained JSON lives
    in the last text block on the final response (earlier text blocks may
    contain progress narration from between tool calls)."""
    for block in reversed(content):
        if block.type == "text" and block.text.strip():
            return block.text
    return None


def main() -> int:
    client = anthropic.Anthropic()

    stream = client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": AWARD_SCHEMA},
        },
        tools=[
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": MAX_WEB_SEARCH_USES,
            }
        ],
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": USER_PROMPT}],
    )

    print(f"Running {MODEL} with web_search (max {MAX_WEB_SEARCH_USES} queries)…", file=sys.stderr)
    with stream as s:
        final = s.get_final_message()

    if final.stop_reason == "pause_turn":
        print(
            f"[error] Web-search loop hit its iteration cap (stop_reason=pause_turn). "
            f"Re-run; if this persists, lower MAX_WEB_SEARCH_USES.",
            file=sys.stderr,
        )
        return 2

    text = extract_structured_text(final.content)
    if not text:
        print("[error] No text block in the response — cannot parse structured output.", file=sys.stderr)
        return 3

    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[error] Model returned non-JSON final text: {exc}\n----\n{text}\n----", file=sys.stderr)
        return 4

    payload = {
        "discovered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": final.model,
        "candidates": result.get("candidates", []),
        "notes": result.get("notes", ""),
        "usage": {
            "input_tokens": final.usage.input_tokens,
            "cache_read_input_tokens": final.usage.cache_read_input_tokens,
            "cache_creation_input_tokens": final.usage.cache_creation_input_tokens,
            "output_tokens": final.usage.output_tokens,
        },
        "stop_reason": final.stop_reason,
    }

    OUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    OUT_MD.write_text(build_markdown(payload), encoding="utf-8")

    print(
        f"Wrote {len(payload['candidates'])} candidates → {OUT_JSON.name} + {OUT_MD.name}. "
        f"Usage: input={final.usage.input_tokens} (cache_read={final.usage.cache_read_input_tokens}), "
        f"output={final.usage.output_tokens}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
