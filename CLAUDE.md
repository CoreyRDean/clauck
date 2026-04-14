# open-claude-cron — Agent Instructions

You are working inside the `open-claude-cron` repository. This is a macOS launchd-based system that runs `claude -p` sessions on cron schedules and event triggers. Users install it via a one-liner shell command.

## What this repo contains

- `install.sh` / `uninstall.sh` — idempotent installer and clean uninstaller
- `lib/` — runtime scripts installed to `~/.claude/scheduled-jobs/`
  - `scheduler.py` — master scheduler (discovery, cron eval, trigger eval, dispatch)
  - `run-job.sh` — per-job executor (log, preflight, concurrency guard, invoke claude)
  - `trigger-job.sh` — ad-hoc fire wrapper
  - `update-check.sh` — version check against GitHub Releases
  - `scheduled-jobs-prompt.md` — global system prompt appended to every job
  - `scheduled-jobs-notice.sh` — SessionStart hook for agent awareness
- `jobs/` — default jobs shipped with every install (currently: heartbeat)
- `library/` — curated pre-made jobs users can browse and install via Claude
- `skill/scheduled-jobs/SKILL.md` — the Claude Code skill that teaches agents how to manage the system
- `templates/` — LaunchAgent plist template with substitution placeholders
- `VERSION` — single source of truth for installed version

## Architecture in 30 seconds

```
launchd (60s tick) → scheduler.py
  → discovers ~/.claude/scheduled-jobs/*.md
  → parses YAML frontmatter (cron, triggers, hooks, budgets)
  → writes .manifest.json
  → evaluates external_triggers (file_added, file_changed, process_starts, command_succeeds)
  → for matching jobs → detached run-job.sh → claude -p → log file
```

## Rules for working in this repo

1. **No new dependencies.** Runtime uses only `/usr/bin/python3` (Apple-bundled) and `/bin/zsh`. No pip, no brew, no compiled binaries. The YAML parser is hand-rolled (~80 lines) specifically to avoid PyYAML.

2. **Backward compatibility.** New frontmatter fields MUST have defaults that preserve existing behavior. Jobs written for v0.1.0 must work on v0.2.0 without edits.

3. **macOS bash 3.2 compatibility.** `install.sh` and `uninstall.sh` run under `/bin/bash` which is bash 3.2 on macOS. No `${var,,}`, no `${var^^}`, no associative arrays, no `mapfile`. Use `tr` for case conversion, regular arrays only.

4. **Cost awareness.** Every change to system-prompt text or MCP surface usage affects per-run cost. Quantify impact in your PR.

5. **Secrets: zero tolerance.** No API keys, OAuth tokens, Slack channel IDs, personal paths, or email addresses in any file. The CI pipeline scans for common patterns.

6. **Test before claiming done.** At minimum:
   ```bash
   bash -n install.sh && bash -n uninstall.sh  # syntax
   /usr/bin/python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())"  # parse
   /usr/bin/python3 -c "import json; json.load(open('library/index.json'))"  # JSON
   bash install.sh --dry-run --yes  # dry-run
   ```

## How to add a library job

1. Create `library/<category>/<name>.md` with standard frontmatter.
2. Include a `<!-- CUSTOMIZE BEFORE INSTALLING: -->` comment listing what users must edit.
3. Add an entry to `library/index.json` following the existing schema.
4. Test: `bash install.sh --yes` to install, then `~/.claude/scheduled-jobs/trigger-job.sh <name>` to fire it.
5. Include the log output showing `exit_code=0` in your PR.

## How to install the system (for testing your changes)

```bash
bash install.sh  # detects local repo, uses these files directly
```

This runs the installer against YOUR local checkout — no network clone. Changes to `lib/`, `jobs/`, `library/`, and `skill/` take effect immediately.

## How to help a user install this system

If a user asks you to install open-claude-cron:

1. Run the installer: `curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh | bash`
2. The installer handles everything: preflight, file placement, LaunchAgent, settings.json hook, verification.
3. After install, read `~/.claude/skills/scheduled-jobs/SKILL.md` for the full management playbook.
4. Browse the library: `cat ~/.claude/skills/scheduled-jobs/library/index.json | python3 -m json.tool`
5. Help the user pick and customize jobs from the library, or design new ones.

## Commit conventions

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat:`, `fix:`, `docs:`, `chore:`, etc. See CONTRIBUTING.md.

## Key paths when installed on a user's machine

| What | Where |
|---|---|
| Runtime scripts | `~/.claude/scheduled-jobs/{scheduler.py,run-job.sh,trigger-job.sh,update-check.sh}` |
| Job prompts | `~/.claude/scheduled-jobs/*.md` |
| Per-run logs | `~/.claude/scheduled-jobs/<name>-<utc-ts>-<pid>.log` |
| Manifest | `~/.claude/scheduled-jobs/.manifest.json` |
| State dir | `~/.claude/scheduled-jobs/.state/` |
| Config | `~/.claude/scheduled-jobs/.open-claude-cron.config.json` |
| Version | `~/.claude/scheduled-jobs/.version` |
| Skill | `~/.claude/skills/scheduled-jobs/SKILL.md` |
| Library | `~/.claude/skills/scheduled-jobs/library/` |
| Hook | `~/.claude/hooks/scheduled-jobs-notice.sh` |
| LaunchAgent | `~/Library/LaunchAgents/com.$USER.claude-scheduler.plist` |
| Global prompt | `~/.claude/scheduled-jobs-prompt.md` |
