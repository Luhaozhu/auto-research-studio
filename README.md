# auto-research-studio

一个**自动追踪 AI 研究方向**的本地知识库系统。核心是 `research-wiki` skill：
每天定时抓取某个研究方向的最新 arXiv 论文，由 Claude 做相关性打分、抽全文与架构图，
再把保留的论文**编译进一个交叉链接的中文 Wiki（Obsidian 风格）**，并产出当日简报。
库是**持久累积**的——不是每天重新检索，而是像维护一本不断加厚的百科全书。

灵感来自 Karpathy 的「LLM Wiki」范式：读原始论文 → **compile** 成持久的、互相 `[[wikilink]]`
的 Markdown，而非每次从零重检索。

---

## 它最终长什么样

每个研究方向是一个**自包含的 vault**，结构如下（以已运行的 `agent-harness` 方向为例，
当前 127 篇论文）：

```
data/vaults/<方向 slug>/
├── research_direction.md      # 方向定义（采访产出，所有打分的判据）
├── state.json                 # 水位线：last_ingest / paper_count / 已处理 id
├── wiki/
│   ├── index.md               # 索引：趋势入口 + 每日简报列表 + 概念地图 + 按概念分组的论文目录
│   ├── trends.md              # 滚动趋势综述（跨期 rollup，主线 + 概念热度）
│   ├── log.md                 # 每次 init/ingest 的操作流水
│   ├── papers/                # 每篇普通论文一页（中文，基于 PDF 全文）
│   ├── surveys/               # 综述 / 立场论文单独归档
│   ├── concepts/              # 概念页（方向的知识地图，论文挂靠其上）
│   └── ideas/                 # 选题 / idea 页（可选）
├── report/
│   └── <YYYY-MM-DD>.md         # 每日简报：当天抓取论文的 TL;DR + 看点 + 排除清单
└── raw/                       # 原始物料（PDF 全文、架构图、元数据）
    ├── paper/  <id>.pdf
    ├── text/   <id>.txt        # PyMuPDF 抽取的全文（Wiki 页基于它，不是摘要）
    ├── figures/<id>.png        # 裁出的关键架构图，内嵌进论文页
    └── meta/   <id>.json
```

**单篇论文页的版式**（全中文，由 PDF 全文压缩而成，不是摘要翻译）：

```
---
type: paper
arxiv_id / title / authors / published / relevance_score / tags / status ...
---
# 标题
## TL;DR           一句话核心
## 摘要             方向相关的细化摘要
## 架构图           内嵌 raw/figures/ 的关键图 + 中文图注
## 问题 / 动机
## 方法（核心贡献）
## 实验与结论
## 局限与存疑
## 可借鉴点
## 资源（代码 · 数据 · benchmark）
```

**索引页**把论文按主概念分组、组内按 relevance 降序排列，每行带分数、发表日、是否含架构图，
顶部是趋势综述入口和每日简报时间线。**概念页**则是横向的知识地图，把论文按方法族/主题
组织起来并互相链接。

> 一句话效果：跑一段时间后，你得到的是一本**自己长出来的、带交叉引用的中文研究百科**，
> 外加一份每天更新的「今天值得看什么」简报。

---

## 整个流程（research-wiki 的生命周期）

分两个尺度。**每台机器一次**的安装，和**每个方向一次**的建库，之后是**每天**的增量。

```
每台机器一次
  0. setup        装依赖（uv sync：PyMuPDF + PyYAML）
  1. init-repo    建 data/ 数据仓库 + 方向注册表（registry）

每个新方向一次  ← 「采访驱动的建库流程」，每次都走，不跳
  2. 采访方向     对话式把方向问清楚（目标 / in-scope / out-of-scope / 打分 rubric /
                  锚点工作 / 检索配置 …），写进 research_direction.md
  3. new          注册方向 + 建空 vault 骨架
  4. init         冷启动回填（约 6 个月 arXiv + 综述），灌入最初一批论文

每天 / 每个方向
  5. ingest       增量更新 + 出简报   ← 这就是定时任务每天跑的那条
     query        从 Wiki 里答疑（带 [[wikilink]] 引用）
     lint         体检 vault（矛盾 / 过期 / 孤儿页 / 缺概念页）
```

**ingest 每天做的事**（定时任务自动执行）：

1. **抓取** — `arxiv_fetch.py` 按 arXiv 分类拉取最新论文，用方向 keywords 在本地做预筛
   （不把 keyword AND 进 arXiv 查询，因为 arXiv 全文索引对新论文有约一天延迟，AND 会
   把当天最新论文漏掉）。读 `state.json` 的 `last_ingest` 水位线，只取更新的。
2. **打分** — Claude 逐篇读摘要、按方向 rubric 打 0–1 分，过阈值（默认 0.6）的保留。
3. **抽取** — `pdf_extract.py` 下载 PDF 抽全文；`figure_extract.py` 裁关键架构图。
   单篇出错跳过，不中断整批。
4. **编译入库** — `librarian` 子代理基于**全文**把每篇压成一页中文 Wiki，内嵌架构图，
   更新 `index.md` / 相关 `concepts/` / `trends.md` / `log.md`。
5. **出简报** — 写当天的 `report/<日期>.md`，含每篇 TL;DR、看点、与方向的关系、以及
   被排除/低分论文清单。
6. **推水位线** — 更新 `state.json` 与 registry 的 `last_ingest`。

> **关于「为什么有时只抓到前一两天的论文」**：arXiv 的公告（announcement）本身有节奏与
> 延迟，周末不发布。如果某天上游还没出新批次，ingest 会自动用 `--no-keyword-filter` +
> 放宽时间窗复核确认「是上游未发布而非漏抓」，并把当天可得的最新一批（含之前刻意暂留的
> 边界分数层）补齐入库。这是正常行为，不是故障。

---

## 快速开始（手动跑一遍）

依赖：Python 3.12+、[`uv`](https://docs.astral.sh/uv/)。所有脚本通过 skill 自带的虚拟环境调用。

```bash
# 0. 装依赖（在 skill 目录）
cd skills/research-wiki && uv sync && cd -

# 1. 建数据仓库（每台机器一次）
skills/research-wiki/.venv/bin/python skills/research-wiki/scripts/vault_admin.py init-repo

# 1b.（可选，定时任务用）准备本地配置：复制 .env.example 为 .env 填上联系邮箱等
cp .env.example .env   # 然后编辑 ARXIV_CONTACT_EMAIL / DIRECTION / MODEL / PROXY

# 2~4. 新建一个方向：最省事的方式是直接让 Claude Code 跑 research-wiki skill —
#      它会先采访你把方向问清楚，再 new + init 冷启动。
#      （research-wiki 是一个 Claude Code skill，详见 skills/research-wiki/SKILL.md）

# 5. 之后每天的增量（也可交给定时任务，见下）
#    同样推荐通过 Claude Code 跑 skill 的 `ingest` 工作流，因为打分/编译需要模型判断。
```

> `research-wiki` 是给 **Claude Code** 用的 skill：脚本负责确定性工作（抓取 / 抽取），
> 模型负责判断工作（相关性打分 / 编译 Wiki / 写简报）。完整命令与各脚本说明见
> `skills/research-wiki/SKILL.md`。

---

## 启动每日自动化任务

`run_daily_ingest.sh` 是定时任务入口：它在无人值守下启动 headless 的 `claude -p`，
对配置好的方向跑一次 `ingest`，把结果写进本地 vault，并把整段输出记到当天日志。
脚本本身**不含任何机器相关路径**——仓库根目录由脚本自身位置推断，其余配置走 `.env`。

**1. 配置（复制 `.env.example` 到 `.env` 再改）**：`.env` 被 gitignore，不会提交。

| 变量 | 含义 |
|---|---|
| `DIRECTION` | 要每天更新的方向 slug（默认 `agent-harness`） |
| `MODEL` | 用哪个模型（`claude-opus-4-8`；想省钱换 `claude-sonnet-4-6`） |
| `ARXIV_CONTACT_EMAIL` | 写进 arXiv User-Agent 的联系邮箱（arXiv 礼仪，降低 429） |
| `PROXY` | **可选**出站代理。仅当本机直连 Anthropic API 受限时才需要；arXiv 始终直连。留空即纯直连。脚本会先探活，不通就清晰地 ABORT 并记日志 |

脚本会自动补好 `PATH` / `HOME` / `AUTORESEARCH_HOME`，因为 cron 的环境极简——
`uv`、`claude` 等必须能被找到（曾踩坑：`uv` 不在默认 PATH 上导致 `uv sync` 静默失败）。

**2. 装进 crontab**（每天早上 8:00 跑一次为例）：

```bash
crontab -e
# 加入一行（把 <repo> 换成本仓库实际所在路径）：
0 8 * * * <repo>/run_daily_ingest.sh
```

**3. 看运行结果**：每次运行在 `logs/ingest-<日期>.log` 留一份完整输出，结尾有
`ingest end (rc=0)` 表示成功；同时 vault 里多出当天的 `report/<日期>.md` 简报与新论文页。

**注意事项**

- **网络须可达**：脚本运行前会探测 `api.anthropic.com`（配了 `PROXY` 就经代理探），
  不通则直接 ABORT 并在日志写明原因，避免空跑。
- **cron 只在机器开机时触发**：若到点时机器/WSL 关着，这一跑会被跳过——但下次会从
  `state.json` 水位线继续，不会漏论文（只是简报会合并补抓）。
- **退出码**：`rc=3` 网络/代理不可达；`rc=4` 模型返回 0 但没写出当天简报（疑似空跑，
  便于 cron 监控发现）；`rc=0` 正常。

---

## 仓库结构

```
.
├── run_daily_ingest.sh        # 定时任务入口（headless ingest + 日志）
├── .env.example               # 定时任务的本地配置模板（复制为 .env，gitignore）
├── skills/research-wiki/      # research-wiki skill（脚本 + 子代理 + SKILL.md + 自带 README）
│   ├── SKILL.md               # 完整工作流与命令说明
│   ├── scripts/               # arxiv_fetch / relevance_filter / pdf_extract / figure_extract …
│   ├── agents/librarian.md    # 编写与维护 vault 的子代理
│   └── assets/                # vault「宪法」CLAUDE.md 模板 + 方向采访模板
├── shared/                    # 跨 skill 共享库（vendor 到 skill 内）
├── data/                      # 持久 vault（.gitignore，本地累积，不入库）
└── logs/                      # 每次运行一份 ingest-<日期>.log（.gitignore）
```

> `data/` 与 `logs/` 不纳入版本控制：vault 是本地有状态的产物，按用户选择手动同步、不提交。

---

## 多方向

通过 registry 支持多个互相独立的方向，每个方向一个自包含 vault。新增方向时**务必重走采访
→ `new` → `init` 流程**，不要把新话题塞进已有的无关 vault。`vault_admin.py list` 可查看
已注册方向及其状态。
