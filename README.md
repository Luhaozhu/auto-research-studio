# auto-research-studio

Home of the **research-wiki** skill plus a local daily-ingest automation.

- `skills/research-wiki/` — the skill (scripts + agents + SKILL.md + README).
  Deps: `cd skills/research-wiki && uv sync` (PyMuPDF + PyYAML).
- `run_daily_ingest.sh` — the local cron entry point. Launches headless
  `claude -p` to run the research-wiki `ingest` workflow against the **local
  persistent vault**, so the full cross-linked wiki + daily 简报 accumulate on
  this machine. No git push involved.
- `data/` — **gitignored**. The persistent vault lives here locally.
- `logs/` — gitignored; one `ingest-<date>.log` per run.

## Daily automation (local cron)
Runs every day at **08:00 Asia/Seoul**:

```cron
0 8 * * * /mnt/c/Users/Aaron/Desktop/SynologyDrive/Claude/auto-idea/run_daily_ingest.sh
```

The job writes the day's papers into `data/vaults/agent-harness/` (wiki pages,
concepts, trends) and a briefing to `data/vaults/agent-harness/report/<date>.md`.
Inspect a run via `logs/ingest-<date>.log`.

> Caveat: cron only fires while WSL is running. If the machine/WSL is off at
> 08:00, the run is skipped (it resumes from `state.json`'s watermark next time).
