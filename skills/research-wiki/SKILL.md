---
name: research-wiki
description: Build and maintain a per-direction LLM Wiki (Obsidian-style knowledge base) of AI research papers. Sets up a fresh data repo, registers a research direction, cold-start backfills ~6 months of arXiv + surveys, then does daily incremental updates that fetch new papers, filter by relevance, extract full text + figures, compile cross-linked Chinese wiki pages, and emit a daily briefing (简报). Use this skill whenever the user wants to set up or initialize a paper/literature knowledge base, start tracking an AI research direction or topic, build a research wiki, fetch or pull "today's" / latest arXiv papers for a topic, run a daily/scheduled paper update, generate a research briefing or digest, quickly read/summarize a single paper (by arXiv id/URL or local PDF) to pull out its key info, query an existing paper knowledge base, or health-check (lint) a vault — even if they don't say "research-wiki" by name. Supports multiple independent directions via a registry; each direction is one self-contained vault.
---

# Research Wiki

Maintain a research literature knowledge base using Karpathy's LLM Wiki pattern:
read raw papers, **compile** them into a persistent, cross-linked Markdown wiki
(do not re-retrieve from scratch each time). Each research direction is one
self-contained vault under `<home>/data/vaults/<slug>/`.

## Lifecycle (do these in order on a fresh install)

A direction goes: **setup → init-repo → new → init (cold-start backfill) →
ingest (daily) → query / lint**. The first three are one-time; `ingest` is the
recurring everyday command.

```
0. setup       uv sync                                  install deps (once per machine)
1. init-repo   vault_admin.py init-repo                 create the data/ repo + registry
2. new         vault_admin.py new --slug <s> --title …  register a direction + empty vault
3. init        cold-start backfill (~6 months + surveys)         first papers
4. ingest      daily incremental update + 简报           the recurring command (cron)
   query       answer questions from the wiki
   lint        health-check the vault
```

**Figure out where the user is in this lifecycle before acting.** Brand-new
("set up a research wiki for X") → run setup → init-repo → new → init. Already
has a vault ("update my agent papers", "today's arXiv") → go straight to ingest.
`vault_admin.py list` shows what exists and each direction's state.

### The data home & vault resolution
The **home** is the directory that holds `data/` (registry + all vaults).
`init-repo` creates it. Resolution (no flags needed once it exists):
`--home <path>` → `$AUTORESEARCH_HOME` → the repo root the skill sits in →
`~/.research-wiki`. Every fetch/extract command then finds a direction by:
- `--direction <slug>` — looked up in the home's `data/directions/registry.yaml`
  (this is the normal path; works flag-free after `init-repo`).
- `--vault <path>` — explicit, registry-free (keeps the skill standalone).

## Setup (once per machine)
- Install deps from the skill dir: `uv sync` (or `pip install pymupdf pyyaml`).
  Prefix script calls with the venv: `.venv/bin/python scripts/<x>.py …`.
  **PyMuPDF is required** — it does PDF→full-text + figure extraction. PyYAML is
  needed for the registry. `init-repo` prints a deps check so you catch a missing
  one before fetching.
- Optional `S2_API_KEY` env var raises Semantic Scholar rate limits (init snowball).
- **Optional** GROBID (richer references/section structure only):
  `docker run --rm -p 8070:8070 lfoppiano/grobid:latest`. Not required — the
  default pipeline extracts full text with PyMuPDF and needs no Docker.

## Workflow: `init-repo` (create the data repo — run once)
```
vault_admin.py init-repo [--home <path>]
```
Creates `<home>/data/directions/` + `<home>/data/vaults/` and an empty
`registry.yaml` (`{default: null, directions: []}`). Idempotent — re-running is
safe and never clobbers existing data. It prints the resolved home, the registry
path, and a dependency check. To put the repo somewhere specific, pass `--home`
or export `$AUTORESEARCH_HOME` (and keep it set for later commands).

## Division of labor (important)
Scripts do the **deterministic** work; you (with the `librarian` sub-agent) do
the **judgment**. Never hand scoring/synthesis to a hardcoded heuristic except
for offline smoke tests.

| Step | Who | How |
|---|---|---|
| fetch candidates | script | `scripts/arxiv_fetch.py` |
| seed expansion (init) | script | `scripts/bootstrap_seed.py` (surveys + citation snowball) |
| relevance scoring | **you** | `relevance_filter.py emit` → you score abstracts → `apply` |
| PDF + **full text** | script | `scripts/pdf_extract.py` (download + PyMuPDF full text) |
| **architecture figure** | script | `scripts/figure_extract.py` (crops the PDF's key figure) |
| richer refs (optional) | script | `scripts/grobid_extract.py` (only if GROBID running) |
| write wiki pages | **librarian** | per `agents/librarian.md` + vault `CLAUDE.md` |

**Full text, not abstracts.** Wiki pages are compiled from each paper's
extracted body text in `raw/text/<id>.txt` — never from the abstract alone.
`pdf_extract.py` downloads the PDF to `raw/paper/<id>.pdf` and writes the full
text to `raw/text/<id>.txt`. All summary/synthesis content the librarian writes
is in **Chinese (中文)**.

## Workflow: `new` (register a direction + build its vault)
First **interview the user** to pin down the direction — this is the single
most important input, because every relevance score is judged against it. Get:
the one-line scope, what's in-scope vs explicitly out-of-scope, the scoring
rubric, anchor works, and the arXiv `categories` + `keywords` to search. Write
that into a markdown file (use the headings in `research_direction.md`), then:
```
vault_admin.py new --slug <slug> --title "..." \
    --categories cs.AI cs.CL --keywords "agent harness" "tool use" \
    --threshold 0.6 --bootstrap-months 6 \
    --direction-file <the file you wrote>      # or --description "<inline text>"
```
This appends the registry entry, builds the full vault skeleton
(`raw/` + `wiki/` + `report/`), copies `assets/CLAUDE.vault.md` → `<vault>/CLAUDE.md`,
writes `research_direction.md` and `state.json`. It sets the new slug as the
registry `default` if none was set.

If you omit `--direction-file`/`--description`, it writes a **stub**
`research_direction.md` and warns you — fill that in (be specific, down to target
papers/problems) before `init`, or relevance scoring has nothing to judge against.
Run `vault_admin.py list` to confirm.

## Workflow: `init` (cold start — backfill ~6 months + surveys)
Run once per direction so idea-forge has material from day one.
```
1. arxiv_fetch.py  --direction <slug> --months 6 --out recent.json
2. bootstrap_seed.py --candidates recent.json --top 30 --out seed.json
     # tags surveys, snowballs foundational works via citation graph
3. relevance_filter.py emit --candidates seed.json \
     --direction-file <vault>/research_direction.md --out ws.json
     # YOU read ws.json, score each 0-1, write scores.json {arxiv_id: score}
4. relevance_filter.py apply --candidates seed.json --scores scores.json \
     --threshold <registry> --out kept.json
     # priority cap to --max-papers: survey > high-relevance recent > snowball
5. pdf_extract.py --candidates kept.json --direction <slug>
     # downloads each PDF -> raw/paper/<slug>.pdf, full text -> raw/text/<slug>.txt,
     # merges extraction facts into raw/meta/<slug>.json. Resume-safe; failures
     # are logged & skipped so one bad PDF never aborts the batch.
5b. figure_extract.py --direction <slug>
     # crops each paper's key architecture/overview figure -> raw/figures/<slug>.png
     # (+ .json sidecar). Resume-safe; papers with no extractable figure are skipped.
6. librarian: batch-ingest kept papers into the vault, compiling each page FROM
   raw/text/<slug>.txt (full text, not the abstract); embed raw/figures/<slug>.png
   in the page's 架构图 section. Surveys → wiki/surveys/. All synthesis in 中文.
   Build index.md (relevance · 发表日 · link), seed concepts/, append
   `## [date] init | <slug> | N papers`. Optionally drop a `report/<date>.md`
   summarizing the backfill (same shape as the daily 简报).
7. set state.json initialized=true, last_ingest=today, paper_count; record the
   ingested ids (e.g. init_progress.processed). Bump the registry entry's
   `initialized: true` and `last_ingest` so daily `ingest` knows where to resume.
```
`init` is heavy (hundreds of PDFs). Run `pdf_extract.py` in the background;
`--max-papers` and the relevance threshold are the cost knobs.

## Workflow: `ingest` (daily incremental)
Same pipeline minus bootstrap_seed; `arxiv_fetch.py` reads the `last_ingest`
watermark from `state.json` and only pulls newer papers.

> **Fetch correctness (read this).** `arxiv_fetch.py` queries arXiv **by category
> only** and applies the direction's keywords as a *local* pre-screen on the
> fetched title+abstract. It does **not** AND keywords into the arXiv query:
> arXiv's full-text index (`all:"..."`) lags ~a day for brand-new papers, so a
> server-side keyword AND silently drops the very newest papers (a daily run
> reported 0 while 300+ same-day papers existed). The script prints how many the
> pre-screen dropped and warns loudly on a 0/low yield. **If a daily run returns
> 0 or the newest result predates the watermark, do not conclude "nothing today"
> — re-run with `--no-keyword-filter` (and/or a wider `--since`) as a sanity
> check before reporting.** Avoid rapid repeated probes: arXiv rate-limits (429)
> aggressively; prefer one category-only fetch with a high `--max-results`.
```
1. arxiv_fetch.py --direction <slug>          # category-only + local keyword pre-screen; uses last_ingest watermark (re-scans --lookback-days=1 before it)
     # dedup candidates against state.json init_progress.processed (already-in-vault ids)
     # 0/low yield prints a WARNING; use --no-keyword-filter to see full daily volume
2. relevance_filter.py emit → YOU score → apply --threshold <registry>   → kept.json
3. pdf_extract.py --candidates kept.json --direction <slug>    # full text → raw/text
4. figure_extract.py --direction <slug>                        # key figure → raw/figures
5. librarian: compile each kept paper FROM raw/text/<slug>.txt into wiki/papers
     (survey→wiki/surveys), embed raw/figures/<slug>.png; update index.md lines,
     relevant concepts/, append `## [date] ingest | <slug> | +N papers` to log.md
6. **daily report (简报)**: write `<vault>/report/<YYYY-MM-DD>.md` — a 中文 briefing of
     THIS run's papers (per-paper TL;DR + 看点 + 与方向关系 + 概念链接, plus an
     observation note and the excluded/<0.6 list). Create `<vault>/report/` if absent;
     one file per ingest day. Add/refresh its line under index.md's `## 每日简报` section.
7. **rolling trends (趋势综述)**: fold this run's `本期观察` into `<vault>/wiki/trends.md`
     — extend/open concept-anchored 主线, bump 概念热度, demote stale threads. This is
     the cross-period rollup (the daily report is per-day; trends is the compounding view).
     Link it once under index.md. See the vault `CLAUDE.md` trends schema.
8. advance state.json last_ingest=today, paper_count, append the new ids to
     init_progress.processed; bump registry `last_ingest`.
```
`--all` loops every `status: active` direction. The `report/` briefing is the
human-facing daily digest (the wiki is the durable store); keep them in sync via log.md.

## Workflow: `read` (single-paper quick path — no direction, no registry)
The fast lane for "just read this one paper and pull out the key info". No
direction setup, no relevance scoring, never touches a registered vault.
```
read_paper.py <arxiv_id | arxiv_url | --pdf local.pdf> [--title ...] [--inbox <dir>]
   # downloads/copies the PDF, extracts full text + key figure into a registry-free
   # inbox (default <home>/data/inbox), prints {slug, paths}. Resume-safe (--force redo).
```
Then the librarian compiles **one** 中文 summary page from `inbox/raw/text/<slug>.txt`
into `inbox/reads/<slug>.md` using the paper schema (TL;DR / 摘要 / 架构图 / 问题动机 /
方法 / 实验与结论 / **局限与存疑** / 可借鉴点 / **资源（代码·数据·benchmark）**).
`[[concepts/...]]` links are optional here. Use this when the user hands you a
paper/link/PDF and wants its key points now — not to grow a tracked direction.

## Workflow: `query`
Delegate to the `librarian`: read `<vault>/wiki/index.md` first (and `trends.md`
for "where is X heading"), drill into relevant pages, answer **with `[[wikilink]]`
citations**.

## Workflow: `lint`
Delegate to the `librarian` lint workflow: report contradictions, stale
(`status: superseded`) claims, orphan pages, missing concept pages / cross-refs.

## Resources
- `scripts/` —
  - `vault_admin.py` — repo & direction admin: `init-repo`, `new`, `list`,
    `status`. The deterministic cold-start plumbing (creates data repo + vault
    skeletons); run this before any fetch.
  - `arxiv_fetch.py` — fetch candidates (`--since` watermark / `--months` backfill).
    Queries **by category only** (realtime listing) and pre-screens keywords
    **locally** (lag-free) — never ANDs keywords into the arXiv query. Flags:
    `--lookback-days` (default 1, catches late arrivals), `--no-keyword-filter`
    (full volume / sanity check). Warns on 0/low yield instead of failing silently.
  - `read_paper.py` — single-paper quick read: arXiv id/URL or local PDF →
    download + full text + key figure into a registry-free `inbox/` (the `read`
    workflow). Standalone; never touches a tracked vault.
  - `bootstrap_seed.py` — init-only seed expansion (surveys + citation snowball).
  - `relevance_filter.py` — `emit` worksheet → you score → `apply` threshold.
  - `pdf_extract.py` — PDF download + PyMuPDF full-text extraction (primary).
    Tries multiple PDF URLs per paper (version-pinned `…vN`, unversioned, and the
    `export.arxiv.org` host) so a single 404 on one path doesn't fail the paper.
  - `figure_extract.py` — crops the key architecture figure → `raw/figures/<slug>.png`.
  - `grobid_extract.py` — optional GROBID enrichment (only if GROBID running).
  - `scripts/lib/` — vendored `vault_io.py` / `semantic_scholar.py` (masters in
    repo `shared/`, synced by `shared/vendor.sh`; edit the master, then vendor).
- `agents/librarian.md` — the sub-agent that writes/maintains the vault.
- `assets/CLAUDE.vault.md` — the vault schema/"constitution" copied into each
  new vault as its `CLAUDE.md` (paper/idea/concept schemas + workflows, incl. the
  `report/` daily-briefing schema).
