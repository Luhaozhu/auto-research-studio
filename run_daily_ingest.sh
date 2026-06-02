#!/usr/bin/env bash
# Daily local research-wiki ingest, driven by headless Claude Code.
# Scheduled via cron (see `crontab -l`). Runs against the LOCAL persistent vault,
# so the full cross-linked wiki accumulates on this machine — no git involved.
set -uo pipefail

PROJ="/mnt/c/Users/Aaron/Desktop/SynologyDrive/Claude/auto-idea"
DIRECTION="agent-harness"
MODEL="claude-opus-4-8"            # change to claude-sonnet-4-6 to cut cost

# cron has a minimal environment — make claude + uv discoverable, set HOME.
export HOME="/home/aaron"
export PATH="/home/aaron/.local/bin:/home/aaron/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
export AUTORESEARCH_HOME="$PROJ"  # vault home = repo root (holds data/)

mkdir -p "$PROJ/logs"
LOG="$PROJ/logs/ingest-$(date +%F).log"

cd "$PROJ" || { echo "cannot cd $PROJ" >&2; exit 1; }

# ensure deps (idempotent; cheap if already synced)
( cd "$PROJ/skills/research-wiki" && uv sync ) >>"$LOG" 2>&1 || true

PROMPT="按 skills/research-wiki/SKILL.md 的 \`ingest\`（每日增量）工作流，对 direction=${DIRECTION} 做今天的增量更新：\
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
echo "===== $(date '+%F %T %Z') ingest end (rc=$RC) =====" >>"$LOG"
exit $RC
