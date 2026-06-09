#!/usr/bin/env bash
# Daily local research-wiki ingest, driven by headless Claude Code.
# Scheduled via cron (see `crontab -l`). Runs against the LOCAL persistent vault,
# so the full cross-linked wiki accumulates on this machine — no git involved.
#
# Config is env-overridable; put overrides in .env (gitignored) so this script
# stays machine-agnostic:
#   DIRECTION  research-direction slug to update    (default: agent-harness)
#   MODEL      model id                             (default: claude-opus-4-8)
#   PROXY      outbound proxy for the Anthropic API (default: empty = direct)
set -uo pipefail

# Repo root = the directory this script lives in (override with $PROJ if needed).
PROJ="${PROJ:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# cron runs with a minimal environment — set HOME and make `claude` + `uv`
# discoverable on PATH (this once bit us: `uv` off PATH made `uv sync` no-op).
export HOME="${HOME:-$(eval echo "~$(id -un)")}"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export AUTORESEARCH_HOME="${AUTORESEARCH_HOME:-$PROJ}"  # vault home = repo root (holds data/)

# Load local config (.env) — ARXIV_CONTACT_EMAIL, DIRECTION, MODEL, PROXY, …
# `set -a` exports every assignment so the headless `claude -p` + python inherit it.
if [ -f "$PROJ/.env" ]; then set -a; . "$PROJ/.env"; set +a; fi

DIRECTION="${DIRECTION:-agent-harness}"
MODEL="${MODEL:-claude-opus-4-8}"   # set MODEL=claude-sonnet-4-6 in .env to cut cost
PROXY="${PROXY:-}"                  # optional outbound proxy for the Anthropic leg

mkdir -p "$PROJ/logs"
LOG="$PROJ/logs/ingest-$(date +%F).log"

# Outbound routing. When $PROXY is set, the Anthropic API goes through it while
# arXiv stays DIRECT: the shared proxy exit IP gets collectively rate-limited by
# arXiv (1 req / 3s PER IP) -> chronic 429, whereas a direct connection earns its
# own per-IP budget. arXiv hosts are pinned into NO_PROXY for that reason. Leave
# PROXY empty for a plain direct setup. Either way we preflight the API so a dead
# network ABORTs with a clear log line instead of burning a run.
if [ -n "$PROXY" ]; then
  export HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY" https_proxy="$PROXY" http_proxy="$PROXY"
  export NO_PROXY="127.0.0.1,localhost,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16,export.arxiv.org,arxiv.org"
  export no_proxy="$NO_PROXY"
  if ! curl -s -o /dev/null --max-time 8 -x "$PROXY" https://api.anthropic.com/ ; then
    echo "$(date '+%F %T %Z') ABORT: proxy $PROXY unreachable (is it running?)" >> "$LOG"
    exit 3
  fi
else
  if ! curl -s -o /dev/null --max-time 8 https://api.anthropic.com/ ; then
    echo "$(date '+%F %T %Z') ABORT: api.anthropic.com unreachable" >> "$LOG"
    exit 3
  fi
fi

cd "$PROJ" || { echo "cannot cd $PROJ" >&2; exit 1; }

# ensure deps (idempotent; cheap if already synced)
( cd "$PROJ/skills/research-wiki" && uv sync ) >>"$LOG" 2>&1 || true

PROMPT="按 skills/research-wiki/SKILL.md 的 \`ingest\`（每日增量）工作流，对 direction=${DIRECTION} 做今天的增量更新：\
【重要·headless 约束】你运行在一次性 \`claude -p\` 进程里，没有交互事件循环——绝对不要把抓取/任何步骤丢到后台（run_in_background）然后『等通知再继续』，那样进程会直接退出导致空跑。所有步骤一律前台阻塞执行、跑完再进行下一步；arXiv 的 3s 冷却/退避也在前台同步等待。\
用 .venv/bin/python 调脚本；抓取最新 arXiv（用 state.json 的 last_ingest 水位线）；\
务必遵守 SKILL 的 Fetch correctness 提示——若 0/低产，先用 --no-keyword-filter 并放宽 --since 复核再下结论；\
你来做相关性打分（阈值见 registry）；pdf_extract 抽全文、figure_extract 裁架构图；\
按 librarian 职责把保留论文编译进 vault（基于全文不是摘要，全部中文），更新 index.md / concepts / trends.md / log.md；\
写当日 report/<YYYY-MM-DD>.md 简报；推进 state.json 水位线与 registry 的 last_ingest。\
健壮性优先：单篇出错跳过不要中断整批。结束时简要汇报：抓取/保留多少篇、报告路径。"

echo "===== $(date '+%F %T %Z') ingest start: ${DIRECTION} =====" >>"$LOG"
claude -p "$PROMPT" \
  --model "$MODEL" \
  --permission-mode bypassPermissions \
  >>"$LOG" 2>&1
RC=$?

# Empty-run guard: a healthy ingest ALWAYS writes today's report (even a 0-paper
# day writes one with the fetch-correctness reasoning). If claude returned 0 but
# no report exists, the agent bailed early (e.g. backgrounded the fetch and quit)
# -> a silent no-op. Force a non-zero rc so cron/monitoring sees the failure.
REPORT="$PROJ/data/vaults/${DIRECTION}/report/$(date +%F).md"
if [ "$RC" -eq 0 ] && [ ! -f "$REPORT" ]; then
  echo "$(date '+%F %T %Z') WARN: rc=0 but no report at $REPORT -> treating as empty/no-op run" >>"$LOG"
  RC=4
fi

echo "===== $(date '+%F %T %Z') ingest end (rc=$RC) =====" >>"$LOG"
exit $RC
