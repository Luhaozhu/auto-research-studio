# auto-research-studio

[简体中文](README.md) | **English**

A local knowledge-base system that **automatically tracks an AI research
direction**. Its core is the `research-wiki` skill: every day it fetches the
latest arXiv papers for a direction, lets Claude score relevance and extract
full text + architecture figures, then **compiles the kept papers into a
cross-linked wiki (Obsidian-style)** and emits a daily briefing. The base is
**persistent and cumulative** — instead of re-searching from scratch each day,
it grows like an ever-thickening encyclopedia.

Inspired by Karpathy's "LLM Wiki" pattern: read the raw papers → **compile**
them into persistent, mutually `[[wikilink]]`-ed Markdown, rather than
re-retrieving from zero every time.

---

## What you end up with

Each research direction is a **self-contained vault**, structured like this
(using the live `agent-harness` direction as an example, currently 127 papers):

```
data/vaults/<direction-slug>/
├── research_direction.md      # direction definition (interview output; the yardstick for all scoring)
├── state.json                 # watermarks: last_ingest / paper_count / processed ids
├── wiki/
│   ├── index.md               # index: trends entry + daily-briefing list + concept map + papers grouped by concept
│   ├── trends.md              # rolling trend synthesis (cross-period rollup: main threads + concept heat)
│   ├── log.md                 # append-only log of every init/ingest
│   ├── papers/                # one page per regular paper (Chinese, from the PDF full text)
│   ├── surveys/               # surveys / position papers, filed separately
│   ├── concepts/              # concept pages (the direction's knowledge map; papers hang off them)
│   └── ideas/                 # idea / topic pages (optional)
├── report/
│   └── <YYYY-MM-DD>.md         # daily briefing: TL;DR + highlights + excluded list for that day's papers
└── raw/                       # raw material (PDF full text, figures, metadata)
    ├── paper/  <id>.pdf
    ├── text/   <id>.txt        # full text extracted by PyMuPDF (wiki pages are built from this, not the abstract)
    ├── figures/<id>.png        # cropped key architecture figure, embedded into the paper page
    └── meta/   <id>.json
```

**Layout of a single paper page** (all Chinese, compressed from the PDF full
text — not a translation of the abstract):

```
---
type: paper
arxiv_id / title / authors / published / relevance_score / tags / status ...
---
# Title
## TL;DR           one-line core
## 摘要             direction-relevant refined summary
## 架构图           the key figure from raw/figures/ + a Chinese caption
## 问题 / 动机       problem / motivation
## 方法（核心贡献）   method (core contribution)
## 实验与结论        experiments & conclusions
## 局限与存疑        limitations & open questions
## 可借鉴点          actionable takeaways
## 资源（代码 · 数据 · benchmark）   resources (code · data · benchmark)
```

The **index page** groups papers by primary concept, sorts each group by
relevance descending, and shows the score, publication date, and whether a
figure is present per row — with the trends entry and the daily-briefing
timeline up top. The **concept pages** are the lateral knowledge map, organizing
papers by method family / theme and cross-linking them.

> In one line: run it for a while and you get a **self-grown, cross-referenced
> Chinese research encyclopedia**, plus a daily "what's worth reading today"
> briefing.

---

## The whole flow (the research-wiki lifecycle)

Two scopes. A **once-per-machine** install, a **once-per-direction** build-out,
then the **daily** increment.

```
once per machine
  0. setup        install deps (uv sync: PyMuPDF + PyYAML)
  1. init-repo    create the data/ repo + the direction registry

once per new direction  ← the "interview-driven build-out", always run, never skipped
  2. interview    pin down the direction conversationally (goal / in-scope / out-of-scope /
                  scoring rubric / anchor works / search config …), write research_direction.md
  3. new          register the direction + build the empty vault skeleton
  4. init         cold-start backfill (~6 months of arXiv + surveys), seed the first batch

daily / per direction
  5. ingest       incremental update + briefing   ← the one the cron job runs daily
     query        answer questions from the wiki (with [[wikilink]] citations)
     lint         health-check the vault (contradictions / stale / orphans / missing concept pages)
```

**What `ingest` does each day** (run automatically by the cron job):

1. **Fetch** — `arxiv_fetch.py` pulls the latest papers by arXiv category and
   pre-screens with the direction's keywords *locally* (it does **not** AND the
   keywords into the arXiv query, because arXiv's full-text index lags ~a day for
   new papers and an AND would silently drop the very newest ones). It reads the
   `last_ingest` watermark from `state.json` and only takes newer papers.
2. **Score** — Claude reads each abstract and scores 0–1 against the direction's
   rubric; papers above the threshold (default 0.6) are kept.
3. **Extract** — `pdf_extract.py` downloads the PDF and extracts full text;
   `figure_extract.py` crops the key architecture figure. A failing paper is
   skipped without aborting the batch.
4. **Compile into the vault** — the `librarian` sub-agent compresses each paper
   into one Chinese wiki page **from the full text**, embeds the figure, and
   updates `index.md` / the relevant `concepts/` / `trends.md` / `log.md`.
5. **Briefing** — writes that day's `report/<date>.md` with each paper's TL;DR,
   highlights, relation to the direction, and the excluded / low-score list.
6. **Advance watermarks** — updates `last_ingest` in `state.json` and the registry.

> **On "why some days only the last day or two of papers show up"**: arXiv's
> announcement schedule itself has cadence and lag, and nothing is published on
> weekends. If upstream hasn't released a new batch yet, `ingest` automatically
> re-checks with `--no-keyword-filter` + a widened time window to confirm "it's
> upstream that hasn't published, not a missed fetch", and backfills the latest
> available batch (including the borderline-score tier deliberately held over).
> This is normal behavior, not a fault.

---

## Quick start (a manual run)

Requirements: Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). All scripts
are invoked through the skill's bundled virtualenv.

```bash
# 0. install deps (in the skill dir)
cd skills/research-wiki && uv sync && cd -

# 1. create the data repo (once per machine)
skills/research-wiki/.venv/bin/python skills/research-wiki/scripts/vault_admin.py init-repo

# 1b. (optional, for the cron job) prepare local config: copy .env.example to .env and fill in your contact email, etc.
cp .env.example .env   # then edit ARXIV_CONTACT_EMAIL / DIRECTION / MODEL / PROXY

# 2~4. create a direction: the easiest way is to just let Claude Code run the research-wiki skill —
#      it interviews you to pin down the direction, then runs new + init for the cold start.
#      (research-wiki is a Claude Code skill — see skills/research-wiki/SKILL.md)

# 5. the daily increment afterwards (also handed to a cron job, see below)
#    likewise run the skill's `ingest` workflow via Claude Code, since scoring/compiling needs model judgment.
```

> `research-wiki` is a skill for **Claude Code**: the scripts handle the
> deterministic work (fetching / extraction), and the model handles the judgment
> work (relevance scoring / compiling the wiki / writing the briefing). See
> `skills/research-wiki/SKILL.md` for the full commands and per-script notes.

---

## Starting the daily automation

`run_daily_ingest.sh` is the cron entry point: unattended, it launches a
headless `claude -p`, runs one `ingest` for the configured direction, writes the
results into the local vault, and records the whole output to that day's log. The
script itself contains **no machine-specific paths** — the repo root is inferred
from the script's own location, and the rest of the config comes from `.env`.

**1. Config (copy `.env.example` to `.env` and edit)**: `.env` is gitignored and
never committed.

| Variable | Meaning |
|---|---|
| `DIRECTION` | the direction slug to update daily (default `agent-harness`) |
| `MODEL` | which model to use (`claude-opus-4-8`; switch to `claude-sonnet-4-6` to cut cost) |
| `ARXIV_CONTACT_EMAIL` | contact email baked into the arXiv User-Agent (arXiv etiquette; reduces 429s) |
| `PROXY` | **optional** outbound proxy. Only needed if direct egress to the Anthropic API is blocked on your host; arXiv always goes direct. Leave empty for a plain direct setup. The script preflights it and ABORTs with a clear log line if unreachable |

The script auto-populates `PATH` / `HOME` / `AUTORESEARCH_HOME`, because cron's
environment is minimal — `uv`, `claude`, etc. must be findable (a past gotcha:
`uv` off the default PATH made `uv sync` a silent no-op).

**2. Install into crontab** (e.g. run once daily at 8:00 AM):

```bash
crontab -e
# add one line (replace <repo> with this repo's actual path):
0 8 * * * <repo>/run_daily_ingest.sh
```

**3. Check the results**: each run leaves a full output at
`logs/ingest-<date>.log`; an `ingest end (rc=0)` at the end means success, and
the vault gains that day's `report/<date>.md` briefing plus new paper pages.

**Notes**

- **The network must be reachable**: before running, the script probes
  `api.anthropic.com` (through `PROXY` if set); if unreachable it ABORTs and
  writes the reason to the log, avoiding an empty run.
- **cron only fires while the machine is on**: if the box / WSL is off at the
  scheduled time, that run is skipped — but the next run resumes from the
  `state.json` watermark, so no papers are missed (the briefing just merges the
  catch-up batch).
- **Exit codes**: `rc=3` network/proxy unreachable; `rc=4` the model returned 0
  but wrote no briefing for the day (suspected empty run, so cron monitoring can
  catch it); `rc=0` normal.

---

## Repository layout

```
.
├── run_daily_ingest.sh        # cron entry point (headless ingest + logs)
├── .env.example               # local config template for the cron job (copy to .env, gitignored)
├── skills/research-wiki/      # the research-wiki skill (scripts + sub-agent + SKILL.md + its own README)
│   ├── SKILL.md               # full workflows and command reference
│   ├── scripts/               # arxiv_fetch / relevance_filter / pdf_extract / figure_extract …
│   ├── agents/librarian.md    # the sub-agent that writes and maintains the vault
│   └── assets/                # the vault "constitution" CLAUDE.md template + the direction interview template
├── shared/                    # shared libs across skills (vendored into the skill)
├── data/                      # persistent vaults (gitignored, accumulates locally, not committed)
└── logs/                      # one ingest-<date>.log per run (gitignored)
```

> `data/` and `logs/` are not version-controlled: a vault is local, stateful
> output, synced manually by choice and not committed.

---

## Multiple directions

The registry supports multiple mutually independent directions, each a
self-contained vault. When adding a direction, **always re-run the interview →
`new` → `init` flow** — do not dump a new topic into an existing, unrelated
vault. `vault_admin.py list` shows the registered directions and their state.
