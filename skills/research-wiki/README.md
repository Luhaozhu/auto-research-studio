# Research Wiki · 科研文献知识库 skill

按 Karpathy 的 *LLM Wiki* 模式，把 arXiv 论文**编译**成一份持久、可交叉链接的
Markdown 知识库：读原文 → 抽全文 → 由 librarian 写成中文 wiki 页 → 每天增量更新并出
**简报**。不是每次从头检索，而是**沉淀**——读过的论文进 vault，越积越厚。

每个研究方向 = 一个自包含的 vault，位于 `<home>/data/vaults/<slug>/`，互不干扰。

---

## 核心理念

| 谁做 | 做什么 | 怎么做 |
|---|---|---|
| **脚本** | 确定性的脏活 | 抓取、下载 PDF、PyMuPDF 抽全文、裁架构图、citation 雪球 |
| **你（+ librarian 子 agent）** | 需要判断的活 | 相关性打分、中文综述/编译、趋势归纳 |

**永远基于全文，不是摘要**：wiki 页由 `raw/text/<id>.txt`（PyMuPDF 抽出的正文）编译，
所有综述/总结内容用**中文**。

---

## 目录结构

```
skills/research-wiki/
├── SKILL.md                 # 给 agent 看的操作手册（最权威，先读它）
├── README.md                # 本文件：给人看的总览
├── pyproject.toml           # 依赖：pymupdf + pyyaml
├── scripts/                 # 确定性脚本
│   ├── vault_admin.py       # init-repo / new / list / status —— 冷启动管理
│   ├── arxiv_fetch.py       # 按 category 抓 + 本地 keyword 预筛
│   ├── bootstrap_seed.py    # 综述标注 + citation 雪球（仅 init 用）
│   ├── relevance_filter.py  # emit 打分表 → (你打分) → apply 按阈值保留
│   ├── pdf_extract.py       # 下载 PDF + 抽全文 → raw/text
│   ├── figure_extract.py    # 裁取关键架构图 → raw/figures
│   ├── read_paper.py        # 单篇速读（不进 registry）
│   └── grobid_extract.py    # 可选：GROBID 抽更细的参考文献/章节
├── agents/librarian.md      # librarian 子 agent 的职责定义
└── assets/
    ├── CLAUDE.vault.md                  # 每个 vault 的「宪法」，new 时拷进 vault
    └── research_direction.template.md   # 研究方向采访模板（new 的输入骨架）

<home>/data/                 # init-repo 创建（本仓库里被 gitignore）
├── directions/registry.yaml # 所有方向的注册表 + 默认方向
└── vaults/<slug>/
    ├── CLAUDE.md            ├── research_direction.md   ├── state.json
    ├── raw/{paper,text,figures,meta}/
    ├── wiki/{papers,surveys,concepts}/  index.md  trends.md  log.md
    └── report/<YYYY-MM-DD>.md           # 每日简报
```

---

## 安装（每台机器一次）

```bash
cd skills/research-wiki
uv sync                       # 或：pip install pymupdf pyyaml
```

之后所有脚本都用 venv 调用：`.venv/bin/python scripts/<x>.py …`。
- **PyMuPDF** 必装（PDF→全文 + 裁图）。**PyYAML** 用于 registry。
- 可选 `S2_API_KEY` 环境变量：提高 Semantic Scholar 限额（init 的雪球更顺）。
- 可选 GROBID（更细的参考文献，需 Docker）：`docker run --rm -p 8070:8070 lfoppiano/grobid:latest`。默认流水线不需要它。

---

## 完整生命周期

> **（每台机器一次）setup → init-repo；（每开一个新方向都走）采访方向 → new →
> init →（每天）ingest → query / lint**
> `setup` / `init-repo` 每台机器一次；**新建任何一个方向都要重走「采访 → new → init」**
> （不管是第 1 个还是第 N 个方向，采访都是硬关卡，方向没问清不进论文搜索）；
> `init` 一次性但重；`ingest` 是天天跑的那条。

### Step 1 · `init-repo`（建数据仓库，一次）
```bash
.venv/bin/python scripts/vault_admin.py init-repo            # 可加 --home <path>
```
创建 `data/directions/` + `data/vaults/` + 空 `registry.yaml`，并打印 home / registry
路径与依赖自检。幂等，可重复跑，不会覆盖已有数据。

### Step 2 · 采访研究方向（最重要！要问得细；每开一个新方向都走）
方向文件是整个 Wiki 的基石——每一次相关性打分都以它为准。**这是硬关卡：方向没采访
清楚、模板没填实，就不进入 new/init 的论文搜索。** 不管是第一次用还是已有 vault 再
新开方向，都从这一步开始。**不要只问一句「研究什么」**，用对话式逐簇追问，按
`assets/research_direction.template.md` 的 8 个小节逐项采访用户（一次问 1–2 簇）：

1. 方向与目标（一句话精确定义 + 做 Wiki 的目的 + 已知工作 + 想从简报得到什么）
2. in-scope 细分子主题（每类给典型例子）
3. out-of-scope 明确排除项
4. 具体问题 / 方法族 / benchmark
5. 打分 rubric（0.85–1.0 / 0.6–0.85 / 0.4–0.6 / <0.4 各代表什么）
6. 锚点工作 3–8 个
7. 检索配置（arXiv categories + keywords，**连同义词/缩写一起列全**）
8. 节奏与规模（bootstrap 月数 / max-papers / 抓取节奏）

把答案写进一个 markdown 文件，作为下一步的 `--direction-file`。

### Step 3 · `new`（注册方向 + 建 vault 骨架，一次）
```bash
.venv/bin/python scripts/vault_admin.py new \
    --slug agent-harness --title "Agent Harness / 自改进与 Harness 工程" \
    --categories cs.AI cs.CL cs.LG cs.MA cs.SE \
    --keywords "agent harness" "agent scaffolding" "self-improving agent" \
    --threshold 0.6 --bootstrap-months 6 \
    --direction-file <你写的方向文件>
```
不传 `--direction-file`/`--description` 会写占位 stub 并告警——那就回 Step 2 补完。
`vault_admin.py list` 确认结果。

### Step 4 · `init`（冷启动回填 ~6 个月 + 综述，一次，较重）
```bash
1. arxiv_fetch.py    --direction <slug> --months 6 --out recent.json
2. bootstrap_seed.py --candidates recent.json --top 30 --out seed.json
3. relevance_filter.py emit --candidates seed.json \
       --direction-file <vault>/research_direction.md --out ws.json
   #   你读 ws.json，对每篇打 0-1 分，写 scores.json {arxiv_id: score}
4. relevance_filter.py apply --candidates seed.json --scores scores.json \
       --threshold 0.6 --out kept.json
5. pdf_extract.py    --candidates kept.json --direction <slug>     # 全文 → raw/text
5b. figure_extract.py --direction <slug>                           # 架构图 → raw/figures
6. librarian: 逐篇编译进 wiki/papers（综述进 wiki/surveys），嵌入架构图，建 index.md
7. 置 state.json initialized=true、last_ingest=today、paper_count；registry 同步
```
`init` 很重（可能上百篇 PDF）。`pdf_extract.py` 建议后台跑；`--max-papers` 与阈值是成本闸门。

### Step 5 · `ingest`（每日增量 + 简报，天天跑）
和 init 同流水线，去掉 bootstrap_seed；`arxiv_fetch.py` 读 `state.json` 的 `last_ingest`
水位线，只拉更新的论文。

> **抓取正确性（必读）**：`arxiv_fetch.py` **只按 category** 查 arXiv，keywords 作为
> 本地预筛（不 AND 进 arXiv 查询——因为 arXiv 全文索引对当天新论文有约 1 天延迟，
> 服务端 AND 会把最新论文漏掉）。**若某天返回 0 或最新结果早于水位线，先用
> `--no-keyword-filter`（和/或放宽 `--since`）复核，再下结论「今天没有」**。
> arXiv 会限流（429），别高频探测——一次 category 抓取配高 `--max-results` 即可。

```bash
1. arxiv_fetch.py --direction <slug>          # 用 last_ingest 水位线；去重已入库 id
2. relevance_filter.py emit → 你打分 → apply --threshold <registry> → kept.json
3. pdf_extract.py --candidates kept.json --direction <slug>
4. figure_extract.py --direction <slug>
5. librarian: 逐篇编译进 wiki/papers，更新 index.md、concepts/、log.md
6. 每日简报：写 <vault>/report/<YYYY-MM-DD>.md（中文：每篇 TL;DR + 看点 + 与方向关系
     + 概念链接，加一段本期观察，以及被排除/<0.6 列表）
7. 滚动趋势：把本期观察折进 <vault>/wiki/trends.md（跨期归纳）
8. 推进 state.json last_ingest=today、paper_count；registry 同步
```
`--all` 会遍历所有 `status: active` 的方向。

---

## 其它工作流

- **`read`（单篇速读）**：`read_paper.py <arxiv_id | url | --pdf 本地.pdf>` —— 不建方向、
  不进 registry，下载 + 抽全文 + 裁图到 inbox，librarian 编一页中文摘要。用户丢来一篇
  论文想立刻要点时用它。
- **`query`**：先读 `<vault>/wiki/index.md`（「往哪走」再读 `trends.md`），下钻相关页，
  带 `[[wikilink]]` 引用回答。
- **`lint`**：体检 vault——报矛盾、过时（superseded）结论、孤儿页、缺失的概念页/交叉引用。
- **`status` / `list`**：`vault_admin.py status --direction <slug>` 看单方向计数；
  `vault_admin.py list` 看所有方向状态。

---

## 数据 home 解析
home 是装着 `data/` 的目录。解析顺序：
`--home <path>` → `$AUTORESEARCH_HOME` → skill 所在的仓库根 → `~/.research-wiki`。
方向定位：`--direction <slug>`（查 registry，常规用法）或 `--vault <path>`（显式、免 registry）。

---

## 每日自动化
配合 `schedule`（远程定时 agent）或本地 cron 跑 `ingest` 即可每日出简报。
注意：本 skill 是**本地有状态**的——vault 与水位线需在两次运行间持久化。远程定时跑时，
要么把 vault 放进会被克隆/推回的 git 仓库，要么接受「只出简报、不沉淀 wiki」的退化模式。

---

## 常见问题
- **某天 ingest 返回 0**：见上「抓取正确性」——先 `--no-keyword-filter` 复核再下结论。
- **`PyYAML required` / `fitz` 缺失**：在 skill 目录 `uv sync`。
- **相关性打分没判据**：`research_direction.md` 还是占位 stub——回去把方向采访补实。
- **429 限流**：降低抓取频率，一次抓取用高 `--max-results`，必要时 `--delay` 退避。
