# 研究方向：{title}

> 这是整个 Wiki 最重要的一份文件。每一次相关性打分、每一篇论文的取舍、每日简报的视角，
> 都以此为准绳。请尽量具体——具体到目标论文、目标问题、目标方法层级。
> 助手在 `new` 阶段应当**逐项采访用户**把下面每个小节填满，不要留占位符。

## 一句话定义
<用一两句话精确描述这个方向研究什么。坏例子：「Agent 相关」。好例子：
「面向 LLM agent 的 harness/scaffolding 工程：上下文管理、工具调用编排、
自我改进与 agentic 系统的自动化设计——不含纯模型预训练。」>

## 背景与目标（为什么追这个方向）
- 我做这个 Wiki 的目的：<选题找 gap / 工程落地选型 / 写综述 / 持续追踪 SOTA / 教学……>
- 我目前的水平与已知：<已经熟悉哪些工作，避免重复收录常识性内容>
- 我最想从每日简报里得到什么：<新方法？工程技巧？可复现的 benchmark？开源实现？理论结果？>

## 我关注什么（in-scope，越细越好）
- 子主题 1：<要收录哪类论文/贡献，给 1-2 个典型例子>
- 子主题 2：<…>
- 子主题 3：<…>

## 我不关注什么（out-of-scope，明确排除）
- <明确排除项 1，例如：纯预训练/微调技巧、与本方向无关的垂直应用（医疗/法律 demo）>
- <明确排除项 2，例如：纯 prompt engineering trick、无方法贡献的应用报告>

## 关注的具体问题 / 方法 / Benchmark
- 核心问题：<这个方向想解决的 3-5 个具体问题>
- 关键方法族：<例如 ReAct 类、reflection/self-refine、自动化 agent 设计、记忆机制……>
- 关注的 benchmark / 数据集：<例如 SWE-bench、GAIA、WebArena……（用于判断论文成色）>

## 判定准则（relevance 打分 rubric，给打分用）
> 打分区间的语义要写清楚，便于每天稳定复用。
- **0.85–1.0（必收）**：<满足什么条件——例如直接提出新的 agent harness/scaffolding 方法并有实验>
- **0.6–0.85（收录）**：<相关且有增量贡献，但不是核心——例如改进某一子模块>
- **0.4–0.6（边缘，默认排除）**：<沾边但贡献在别处>
- **<0.4（排除）**：<明确属于 out-of-scope>
- 阈值（threshold）：默认 0.6。

## 锚点工作（种子 / 校准用，3–8 个）
<代表性论文/方法名，既用来给打分做参照系，也作为 citation 雪球（bootstrap_seed）的种子。
例如：ReAct、Reflexion、Voyager、ADAS、AutoGen……>

## 检索配置（给 arxiv_fetch 用）
- arXiv categories：<例如 cs.AI cs.CL cs.LG cs.MA cs.SE>
- keywords（含同义词/缩写）：<例如 "agent harness"、"agent scaffolding"、"self-improving agent"、
  "agentic workflow"、"LLM agent framework"、"orchestration"……同义词越全，召回越好>

## 节奏与规模（给 init / ingest 用）
- bootstrap 回溯月数：<冷启动回填多少个月，默认 6；新兴方向可设 12–14>
- 每次最多收录（--max-papers）：<冷启动的成本闸门，例如 60>
- 每日抓取节奏：<每天 / 每周；触发时间>
