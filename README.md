# auto-research-studio

Self-contained checkout of the **research-wiki** skill, used by a scheduled
Claude Code cloud routine that produces a daily arXiv research briefing (简报).

- `skills/research-wiki/` — the skill (scripts + agents + SKILL.md). Deps:
  `cd skills/research-wiki && uv sync` (PyMuPDF + PyYAML).
- `daily-reports/` — the routine commits one `YYYY-MM-DD-<direction>.md` Chinese
  briefing here each run. This is the durable deliverable.
- `data/` — **gitignored**. The persistent vault lives on the user's machine and
  is synced manually; the cloud agent runs against an ephemeral vault each day.

The daily routine runs at **08:00 Asia/Seoul** for the `agent-harness` direction.
