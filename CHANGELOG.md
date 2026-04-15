# Changelog

All notable changes to clauck are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [v1.3.0] — 2026-04-14

### Added

- **Module format:** folders with `JOB.md` discovered as modular jobs; internal `.md` files invisible to manifest.
- **`clauck add`:** import job files with optional `--name` rename and `--when` natural-language cron via Haiku.
- **`clauck doctor <text>`:** natural-language context appended to diagnostic prompt.
- **Issue reporting guidance:** agents instructed to offer `gh issue create` when hitting limitations.

## [v1.2.0] — 2026-04-14

### Added

- **Custom inputs:** `trigger-job.sh` accepts `KEY=VALUE` args, injected as `## Custom inputs` in Runtime Context.
- **`clauck peek`:** live-tail unified log stream across scheduler and all job logs.
- **Runtime Context fields:** `User home`, `Local timezone`, budget enforcement note.
- **Tilde path warning** in global prompt (Read tool does not expand `~`).

### Changed

- Skill renamed from `scheduled-jobs` to `clauck`; description rewritten as trigger-match for wider activation.
- SessionStart hook references `clauck` skill and prefers it over native scheduling.

## [v1.1.0] — 2026-04-14

### Added

- **Tags:** `tags:` field parsed from frontmatter, included in manifest; 33 searchable tags across 7 marketplace jobs.
- **Agent landing page:** `CLAUDE.md` rewritten as agent-first reference with harness compatibility table.

### Changed

- Library renamed to **marketplace**; category subdirectories flattened to single root.
- `clauck marketplace` shows jobs grouped by first tag; `clauck marketplace <tag>` filters.

### Removed

- `ROADMAP.md` (stale, unmaintained).

## [v1.0.0] — 2026-04-14

### Added

- **Producer/consumer pipeline engine** (`dag-runner.py`): topological sort, parallel layer execution, output injection, provenance-scoped locks, abort-on-fail.
- **Cycle detection** at manifest-write time with errors surfaced in `.manifest.json`.
- **Oplog:** append-only execution chain injected into every pipeline node's context.
- **`clauck-work` meta job:** session-persistent diagnostic agent for self-healing on pipeline failures.

### Changed

- `scheduler.py` delegates to `dag-runner.py` when a job has producers (tick, external trigger, and ad-hoc paths).
- `run-job.sh` reads and injects `## Producer outputs` and `## Execution chain` into system prompt.

## [v0.7.0] — 2026-04-14

### Changed

- README fully rewritten for three audiences (casual, power, architect) with pipeline architecture docs.
- Project positioning elevated to "Workflow automation powered by AI agents."

### Added

- Star prompt after successful install (gh CLI with browser fallback).

## [v0.6.0] — 2026-04-14

### Added

- **`clauck doctor [-i]`:** spawns diagnostic session; interactive mode opens resume session for collaborative debugging.
- **`clauck work <text>`:** explicit alias for semantic fallthrough.
- **User stories** (`stories/`): 10 stories from simple to complex.
- README badges (CI, release, license, platform).

## [v0.5.0] — 2026-04-14

### Added

- **`clauck edit <name>`:** opens job in `$EDITOR`, validates frontmatter on close.
- **Semantic fallthrough:** `clauck <any text>` spawns background `claude -p` scoped to clauck operations.
- **User stories** (`stories/`): 10 intent-documentation stories.

### Changed

- Skill guidance: clauck CLI is for humans, agents should use direct filesystem access.

## [v0.4.0] — 2026-04-14

### Added

- **CLI tool** (`lib/clauck`): `list`, `status`, `fire`, `pause`, `resume`, `logs`, `next`, `library`, `install`, `update`, `config`, `version`.
- `ROADMAP.md` with v1.0 through v2.0 milestones.

### Changed

- Project renamed from `open-claude-cron` to **clauck**; all references updated (URLs, env vars, config file).

## [v0.3.0] — 2026-04-13

### Added

- **Session persistence** (`session_persist: true`): stores `session_id`, subsequent runs pass `--resume` for cross-run context.
- **Interactive mode** (`interactive: true`): opens macOS Terminal with `claude --resume` after background run completes.
- Temporal scheduling gates: `valid_after`, `expires_after`, `run_once`, `max_runs` with auto-disable via state files.

### Changed

- Skill UX overhaul: intent-signal detection, default word association, status queries, modification detection.

## [v0.2.0] — 2026-04-13

### Added

- **Temporal scheduling:** `run_once`, `max_runs`, `valid_after`, `expires_after` frontmatter fields.
- Auto-disable via `.state/<name>.auto-disabled` (reversible without editing `.md`).
- Runs-remaining counter at `.state/<name>.runs-remaining`.
- Proactive job suggestions guidance in skill docs.
- Third-party job crafting: turn any URL or pasted text into a scheduled job.

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
- **SessionStart hook** (`scheduled-jobs-notice.sh`) registered in `~/.claude/settings.json`; advertises the system and marketplace to every new agent session without polluting CLAUDE.md.
- **Claude Code skill** (`scheduled-jobs`) with comprehensive docs: architecture, frontmatter schema, install recipe, common mutations, external triggers, concurrency/debounce, cost reality table, diagnosis flowchart, marketplace browsing, update management.
- **Pre-made job marketplace** with curated jobs cached locally for offline browsing:
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

[Unreleased]: https://github.com/CoreyRDean/clauck/compare/v1.3.0...HEAD
[v1.3.0]: https://github.com/CoreyRDean/clauck/compare/v1.2.0...v1.3.0
[v1.2.0]: https://github.com/CoreyRDean/clauck/compare/v1.1.0...v1.2.0
[v1.1.0]: https://github.com/CoreyRDean/clauck/compare/v1.0.0...v1.1.0
[v1.0.0]: https://github.com/CoreyRDean/clauck/compare/v0.7.0...v1.0.0
[v0.7.0]: https://github.com/CoreyRDean/clauck/compare/v0.6.0...v0.7.0
[v0.6.0]: https://github.com/CoreyRDean/clauck/compare/v0.5.0...v0.6.0
[v0.5.0]: https://github.com/CoreyRDean/clauck/compare/v0.4.0...v0.5.0
[v0.4.0]: https://github.com/CoreyRDean/clauck/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/CoreyRDean/clauck/compare/v0.2.0...v0.3.0
[v0.2.0]: https://github.com/CoreyRDean/clauck/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/CoreyRDean/clauck/releases/tag/v0.1.0
