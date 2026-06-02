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

## 引导式上手（首次安装后，一步步带用户走）
当用户**第一次**使用本 skill（还没有任何 vault），不要直接闷头跑脚本——按下面的
节奏一步步带着用户走，每一步都先说明在做什么、再执行、再把结果告诉用户。

**Step 0 · 装依赖（一次）** — 在 skill 目录执行 `uv sync`（或 `pip install
pymupdf pyyaml`）。装好后所有脚本用 `.venv/bin/python scripts/<x>.py` 调用。

**Step 1 · 建数据仓库（一次）** — `vault_admin.py init-repo`。把它打印的 home、
registry 路径、依赖自检结果回报给用户，确认 home 落在用户期望的位置（默认就是
skill 所在的仓库根；要换地方就 `--home` 或 `$AUTORESEARCH_HOME`）。

**Step 2 · 采访研究方向（最重要的一步，要问得细）** — 这是整个 Wiki 的基石，
每一次打分取舍都以它为准。**不要只问一句「你想研究什么」就开建**。按下面的清单
**逐簇追问**，一次问 1–2 簇，把用户的回答消化成具体的、可判定的描述：

  1. **方向与目标**：一句话精确定义（拒绝「Agent 相关」这种泛词，追问到方法/问题
     层级）；做这个 Wiki 的目的（选题找 gap / 工程选型 / 写综述 / 追 SOTA / 教学）；
     用户已熟悉的工作（避免收录常识）；最想从每日简报里得到什么。
  2. **in-scope（细分子主题）**：要收录哪几类贡献？每类给 1–2 个典型例子。
  3. **out-of-scope（明确排除）**：哪些沾边但坚决不要？（如纯预训练技巧、无方法贡献的
     应用 demo、纯 prompt trick）——排除项写得越明确，打分越稳。
  4. **具体问题 / 方法族 / benchmark**：方向想解决的 3–5 个具体问题；关键方法族；
     关注的 benchmark/数据集（用来判断论文成色）。
  5. **打分 rubric**：0.85–1.0 / 0.6–0.85 / 0.4–0.6 / <0.4 各代表什么；阈值（默认 0.6）。
  6. **锚点工作 3–8 个**：代表性论文/方法名，既做打分参照系，也做 citation 雪球种子。
  7. **检索配置**：arXiv categories；keywords（**务必连同义词/缩写一起列全**，召回靠它）。
  8. **节奏与规模**：bootstrap 回溯月数（默认 6，新兴方向 12–14）；冷启动收录上限
     `--max-papers`；每日/每周抓取节奏与触发时间。

  把采访结果**写进一个 markdown 文件**（结构照 `assets/research_direction.template.md`），
  这个文件就是下一步 `--direction-file` 的输入。模板每个小节都要填实，别留 `<...>` 占位符。

**Step 3 · 注册方向 + 建 vault（一次）** — `vault_admin.py new --slug <slug>
--title "..." --categories ... --keywords ... --threshold 0.6
--bootstrap-months <N> --direction-file <你写的方向文件>`。跑完用
`vault_admin.py list` 确认。**校验关卡**：若你没传 `--direction-file`/`--description`，
脚本会写一个占位 stub 并告警——那说明 Step 2 没做扎实，回去补完再继续，否则相关性
打分没有判据。

**Step 4 · 冷启动回填（一次，较重）** — 跑下面「Workflow: `init`」整条流水线，
给方向灌入最初的一批论文（约 N 个月 + 综述）。`pdf_extract.py` 建议后台跑。

**Step 5 · 之后每天** — 跑「Workflow: `ingest`」做增量更新并出简报；可选地用
`schedule`/cron 定时。`query` 答疑、`lint` 体检。

> 一句话记牢顺序：**setup → init-repo → 采访方向 → new → init →（每天）ingest**。
> 前四步一次性；`init` 一次性但重；`ingest` 是天天跑的那条。

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
most important input, because every relevance score is judged against it. Run
the full interview in **「引导式上手 · Step 2」** above (8 clusters: 方向/目标、
in-scope、out-of-scope、问题/方法/benchmark、打分 rubric、锚点工作、检索配置、
节奏规模). Write the answers into a markdown file using
`assets/research_direction.template.md` as the skeleton (fill every section —
no `<...>` placeholders left), then pass it as `--direction-file`:
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
