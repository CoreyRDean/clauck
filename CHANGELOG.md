# Changelog

All notable changes to clauck are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [v0.1.0] — 2026-04-13

### Added

- **Scheduler core:** launchd LaunchAgent ticking every 60s, `scheduler.py` for job discovery + cron evaluation + dispatch, `run-job.sh` for per-job execution with `claude -p`.
- **Frontmatter schema:** `name`, `description`, `cron`, `max_turns`, `max_budget_usd`, `cwd`, `effort`, `model`, `setting_sources`, `strict_mcp_config`, `debounce_seconds`, `disabled`, `external_triggers`, `semantic_hooks`.
- **External triggers:** `file_added` (burst-aware, quiet-period-gated), `file_changed` (mtime), `process_starts` (edge-triggered), `command_succeeds` (edge-triggered). All evaluated every tick by scheduler.py with zero token cost.
- **Concurrent-run protection:** mkdir-based advisory lock per job. Rapid re-fires noop with `noop_skip: concurrent run in progress` tombstones.
- **Optional per-job debouncing** via `debounce_seconds` frontmatter field.
- **Job pausing** via `disabled: true` frontmatter field (ad-hoc triggers still work).
- **Manifest** at `~/.claude/scheduled-jobs/.manifest.json` — regenerated every tick with all jobs, their cron, semantic hooks, external triggers, and ad-hoc `trigger_command`.
- **Runtime Context** block dynamically appended to every job's system prompt: trigger source, budget, paths, timestamps.
- **Preflight-failure observability:** log file created before any preflight check; failures produce `--- preflight_fail: <reason> ===` tombstones instead of vanishing into DEVNULL.
- **Log rotation:** caps at 100 log files per job name.
- **Minimal YAML parser** supporting flat scalars, string lists, and flow-style object lists (no PyYAML dependency).
- **SessionStart hook** (`scheduled-jobs-notice.sh`) registered in `~/.claude/settings.json`; advertises the system and library to every new agent session without polluting CLAUDE.md.
- **Claude Code skill** (`scheduled-jobs`) with comprehensive docs: architecture, frontmatter schema, install recipe, common mutations, external triggers, concurrency/debounce, cost reality table, diagnosis flowchart, library browsing, update management.
- **Pre-made job library** with curated jobs cached locally for offline browsing:
  - `verification/daily-verify.md` — daily MCP-surface health check.
  - `organization/downloads-triage.md` — file_added trigger on `~/Downloads`.
- **Auto-update system:** checks GitHub Releases hourly (configurable via `~/.claude/scheduled-jobs/.clauck.config.json`); notify-only by default; opt-in auto-apply.
- **Default heartbeat job:** hourly, Haiku, minimal surface (`strict_mcp_config: true` + `setting_sources: ""`), ~$0.04/run (~$1/month).
- **Idempotent installer** (`install.sh`) with preflight checks, interactive confirmation, end-to-end verification via heartbeat fire, and a success banner with next steps.
- **Clean uninstaller** (`uninstall.sh`) that preserves user job files by default; `--wipe` for full removal.
- **Alternative Claude-native install path** (`claude-install-prompt.md`).

### Security

- `--dangerously-skip-permissions` is set on all scheduled jobs because they run non-interactively. Only install on machines where the user account is trusted.
- Auto-update defaults to notify-only. Auto-apply requires explicit opt-in.
- Source of truth for updates: GitHub Releases only. Pushes to `main` never trigger updates.
- Fork users install from their fork's URL and update checks target their fork — no backdoor from the upstream repo.

[Unreleased]: https://github.com/CoreyRDean/clauck/compare/v0.1.0...HEAD
[v0.1.0]: https://github.com/CoreyRDean/clauck/releases/tag/v0.1.0
