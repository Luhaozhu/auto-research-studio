# Vault Constitution (LLM Wiki schema)

This file is the authoritative schema and workflow guide for **this vault**.
The `librarian` agent reads it first and obeys it. It makes the LLM a
disciplined wiki maintainer, not a generic chatbot.

## Layout
Files are named by a readable **title slug** (e.g. `harbor-automated-harness-optimization`),
not the arXiv id. The stable `arxiv_id` lives in each page's frontmatter and meta
json. One paper ⇒ same slug across `raw/paper`, `raw/text`, `raw/meta`, and `wiki/`.
```
raw/paper/<slug>.pdf          downloaded source PDF — READ ONLY
raw/text/<slug>.txt           extracted FULL TEXT (PyMuPDF) — the synthesis source
raw/figures/<slug>.png        key architecture figure cropped from the PDF
raw/figures/<slug>.json       sidecar {fig_label, caption, page, method}
raw/meta/<slug>.json          arxiv_id + arXiv fields + extraction facts — READ ONLY
wiki/index.md                 catalog of every page (updated on every ingest)
wiki/log.md                   append-only event log
wiki/trends.md                rolling cross-period synthesis (每日「本期观察」沉淀成方向级主线)
wiki/papers/<slug>.md         one page per paper (this direction's view)
wiki/surveys/<slug>.md        surveys/reviews — the field map
wiki/concepts/<slug>.md       method/concept entity pages
wiki/ideas/<idea_id>.md       idea knowledge base (written by idea-forge / code-to-idea)
report/<YYYY-MM-DD>.md        per-ingest daily briefing (简报) of that day's papers
```
`raw/` holds everything derived straight from the PDF (pdf, text, figures, meta);
`wiki/` holds the synthesized Markdown; `report/` holds the human-facing daily
digests. Pages embed figures via the relative path `../../raw/figures/<slug>.png`;
report pages link wiki pages as `[[papers/<slug>]]` / `[[concepts/<slug>]]`.

## Invariants
- `raw/` is read-only. Never modify it.
- **Compile from full text.** Every paper/survey page is written from
  `raw/text/<arxiv_id>.txt` (the full body), never from the abstract alone.
  If `raw/text/<id>.txt` is missing, the page is not ready — run `pdf_extract.py`.
- **中文 synthesis.** TL;DR, 摘要, 问题/动机, 方法, 实验, 与方向的关系, 可借鉴点 —
  all written in Chinese. Keep paper/method/concept proper nouns in their
  original form (e.g. ReAct, ADAS); quoted metrics keep their numbers.
- Every page has YAML frontmatter (schemas below).
- Cross-link with `[[wikilinks]]`. Every paper links ≥1 concept; every idea links ≥1 paper.
- `index.md` is always current. `log.md` is append-only.
- This vault is isolated — never read or write another vault.

## Page schemas

### papers/<arxiv_id>.md (surveys/ uses the same schema)
```markdown
---
type: paper            # or: survey
arxiv_id: "2504.08066"
title: "..."
authors: ["..."]
published: 2026-04-10
ingested: 2026-05-29
categories: ["cs.LG"]
tags: [<direction-tag>, ...]
relevance_score: 0.87
cites: ["[[2408.06292]]"]    # from Semantic Scholar
status: ingested            # ingested | summarized | superseded
source: recent              # recent | survey | snowball (how it entered the vault)
full_text_chars: 77326      # from raw/meta; 0/absent ⇒ page not yet full-text-ready
code: ""                    # 开源代码仓库 URL（正文/脚注里找；无则空串）
data: []                    # 用到/发布的数据集 · benchmark 名称或链接（无则 []）
evidence: real              # 证据强度: real | synthetic | toy | mixed（实验落在真实/合成/玩具/混合数据）
---
# {{title}}
## TL;DR            (中文, 1–2 句)
## 摘要             (中文; 译/缩写自原文摘要，不是英文照搬)
## 架构图            (PDF 抽取的关键架构图 + 简短图注; 无图时给出说明。紧跟摘要之后)
![架构图](../../raw/figures/<slug>.png)
> 原文 Figure N（p<page>）：<caption 简短引用>
## 问题 / 动机       (中文, 取自正文 Intro)
## 方法（核心贡献）   (中文, 取自正文 Method — 具体机制/组件/算法，非泛泛而谈)
## 实验与结论        (中文; 关键数据/基准/结论保留数字)
## 局限与存疑        (中文; 两类合写: ① 作者自陈 limitations ② 你的批判性读法 —
                     #  证据强度(合成/玩具 vs 真实)、未覆盖的设定、可能被推翻处。
                     #  没有局限是危险信号——至少给出适用边界。feeds idea-forge 查重/反驳)
## 与本研究方向的关系  (中文; support / contradict / borrowable — feeds idea-forge)
## 可借鉴点 (actionable)  (中文; 对 harness 工程/自改进的可迁移点)
## 资源（代码 / 数据 / Benchmark）  (中文; 开源仓库、数据集、benchmark、leaderboard、
                     #  权重等可复现/可上手资产，附链接; 全无则写「未发现公开资源」)
## 相关概念
[[concepts/...]]

---
本地原文：[PDF](../../raw/paper/<slug>.pdf) · [全文 TXT](../../raw/text/<slug>.txt) · arXiv: https://arxiv.org/abs/<arxiv_id>
```
The footer links the **locally downloaded** PDF/full text (`raw/paper`, `raw/text`),
not a remote URL — papers are already in the vault. Keep the arXiv abstract URL
only as an external reference.
A page must be compiled from `raw/text/<id>.txt`. Cite specifics from the body
(机制名、数字、消融结论), not just a paraphrase of the abstract. The 架构图 is
produced by `pdf_extract`'s companion `figure_extract.py` (crops the paper's
architecture/overview figure to `raw/figures/<slug>.png`); if no figure can be
auto-extracted, keep the heading with a one-line note instead of an image.

### concepts/<slug>.md
```markdown
---
type: concept
title: "..."
aliases: ["..."]
---
# {{title}}
（定义 / 关键论文 / 与相邻概念的关系）
Papers: [[papers/...]] · Related: [[concepts/...]]
```

**Concepts are a LIVING taxonomy, not a fixed list.** The set of concept pages
must grow, split, and merge as the corpus grows — never freeze it at whatever
`init` seeded. On every ingest run a lightweight **concept-curation** pass over
the new papers, applying these triggers (judgment, not a script):
- **NEW** — ≥3 papers cluster on a coherent sub-theme that no existing concept
  cleanly covers → create a new `concepts/<slug>.md`, move those papers' primary
  grouping to it, add it to `index.md`'s 概念地图 + a 论文目录 group, and to
  `trends.md` 概念热度. (Below 3, just note the emerging theme in the nearest
  concept page; don't spawn a 1-paper concept.)
- **SPLIT** — a concept exceeds ~15 papers AND contains a self-contained
  sub-cluster → split the sub-cluster into its own concept; leave a `Related:`
  pointer from the parent and re-point the moved papers' 相关概念.
- **MERGE / RETIRE** — two concepts overlap heavily, or one stays <2 papers for
  several ingests → merge into the better-populated one, keep the dropped title
  as an `aliases:` entry so old `[[links]]` still resolve (don't break links).
- A paper may link **multiple** concepts; only its *primary* concept decides its
  `index.md` group. Secondary concepts are `[[links]]` in 相关概念 / concept pages.

Record each curation action (created/split/merged concept + which papers moved)
in `log.md` as `## [YYYY-MM-DD] concepts | <action> …` so the taxonomy's
evolution is auditable. The `trends.md` 概念热度 counts are the signal that drives
this — a concept ballooning past ~15 is a split candidate; a flat <2 is a
merge/grow candidate.

### ideas/<idea_id>.md  (written by downstream skills; schema kept here for linkage)
```markdown
---
type: idea
idea_id: "I-YYYYMMDD-NNN"
origin: idea-forge          # idea-forge | code-to-idea
status: candidate           # candidate | accepted | implemented | rejected
scores: {novelty: , feasibility: , operability: , impact: , composite: }
elo:
novelty_check: {closest_prior: [], verdict: }
cross_direction: []         # other direction slugs if this idea spans vaults
---
# {{title}}
## 一句话 idea / 出发点(grounding) / 具体方案 / 为何新颖 / MVP 实验 / 风险 / 评审记录
## 关联论文
[[papers/...]]
```

### report/<YYYY-MM-DD>.md  (daily briefing / 简报)
```markdown
---
type: report
direction: <slug>
date: YYYY-MM-DD
candidates: <fetched>
kept: <ingested>
threshold: <relevance>
---
# <Direction> 每日简报 · YYYY-MM-DD
> 一行方向说明 + 本期候选/入库/库存计数；链 [[wiki/index]] / [[wiki/log]]。
## 今日入库（N 篇，按 relevance 降序）
（每篇：arxiv_id · 日期 · 分类 · [[papers/<slug>]]；TL;DR、看点、与方向关系、概念链接）
## 本期观察   （跨论文的主线/趋势，1–3 条，可链既有 concepts）
## 排除清单   （候选 − 入库 = 低于阈值的，附 arxiv_id + 一句排除理由）
```
One report per ingest day; `report/` is the human-facing digest. The wiki is the
durable store — keep them consistent through `log.md`. Surface each report under
`index.md`'s `## 每日简报` section.

### wiki/trends.md  (rolling cross-period synthesis — the compounding view)
The daily `report` answers "what landed today"; `trends.md` answers "where is
this direction *going*". It is the durable rollup that turns each day's
`## 本期观察` into living, concept-anchored threads. **One per vault**; rewritten
in place on each ingest (it is synthesis, not an append-only log).
```markdown
---
type: trends
direction: <slug>
updated: YYYY-MM-DD
periods: <how many ingest days folded in>
---
# <Direction> 趋势综述（滚动）
> 跨期 rollup：把每日「本期观察」沉淀为方向级主线；每次 ingest 刷新。链 [[index]] / [[log]]。

## 活跃主线（按近期热度降序）
### <主线一句话标题> · [[concepts/...]]
- **现状**：1–2 句，随新证据更新（不是逐条堆叠，而是综合改写）。
- **证据轨迹**（按日期）：
  - `YYYY-MM-DD` [[papers/<slug>]] — 一句该论文对此主线的贡献
  - `YYYY-MM-DD` [[surveys/<slug>]] — …
- **张力 / 开放问题**：相互矛盾的结论、尚未解决的问题（→ idea-forge 的钩子）。

## 概念热度（近 N 期入库计数）
- [[concepts/x]] — 本期 +k · 累计 m
- …（按累计降序，反映方向重心迁移）

## 已收敛 / 沉寂
- <旧主线> — 一句话结论 + 为何不再更新（保留 [[papers/...]] 指针，不删除）。
```
**Maintenance rules** (judgment, not a script): on each ingest, fold today's
`本期观察` + new papers into trends — extend an existing 主线's 证据轨迹 or open a
new one; refresh each 现状 by *rewriting*, not appending; bump 概念热度 counts;
demote a thread to 已收敛 when ~3+ ingests add nothing new. Keep it bounded:
merge near-duplicate threads, cap active 主线 at ~8 (the rest go to 已收敛).

## Workflows
- **ingest**: read raw meta → write/update `papers/<id>.md` (survey→`surveys/`) →
  update/create relevant `concepts/*` → **concept-curation pass** (NEW/SPLIT/
  MERGE per the living-taxonomy rules; log any action) → refresh `index.md` line →
  append `## [YYYY-MM-DD] ingest | <title>` to `log.md` →
  write `report/<YYYY-MM-DD>.md` (当日简报) and link it under `index.md` `## 每日简报` →
  **fold this run's `本期观察` into `wiki/trends.md`** (extend/open 主线, bump 概念热度).
- **read** (single-paper quick path): a `read_paper.py` run drops one paper into
  the registry-free `inbox/` (`raw/{paper,text,meta,figures}`); compile a single
  中文 summary page into `inbox/reads/<slug>.md` using the **paper schema above**
  (TL;DR…摘要…架构图…局限与存疑…资源). No index/log/concepts upkeep — it is standalone;
  `[[concepts/...]]` links are optional. This never touches a real vault.
- **init**: batch ingest; build `index.md` by category; seed `concepts/` from
  surveys first; append `## [YYYY-MM-DD] init | <slug> | N papers`. Seed
  `wiki/trends.md` from the backfill's main threads (link it under `index.md`).
- **query**: read `index.md` (and `trends.md` for "where is X heading") → drill
  into pages → answer with `[[links]]`.
- **lint**: report contradictions / stale / orphan pages / missing concepts &
  cross-refs; flag `trends.md` 主线 whose 证据轨迹 has gone stale (demote to 已收敛);
  **audit the taxonomy** — list concepts >~15 papers (SPLIT candidates) and <2
  papers (MERGE/grow candidates), and sub-themes recurring across ≥3 papers with
  no concept page (NEW candidates).
