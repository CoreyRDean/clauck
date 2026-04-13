# open-claude-cron

Cron-scheduled `claude -p` sessions on macOS, plus event-driven triggers and an agent-discoverable manifest. A hundred lines of Python, some shell, one LaunchAgent, zero daemons. Installs in about ten seconds.

## What you get

- A launchd LaunchAgent that ticks every 60 seconds and fires `claude -p` sessions on cron schedules (`0 * * * *`, `*/5 * * * *`, etc.) drawn from Markdown files you drop into `~/.claude/scheduled-jobs/`.
- **External triggers** that fire jobs on file-system, process, and shell-command events (`file_added`, `file_changed`, `process_starts`, `command_succeeds`).
- **Semantic hooks** — natural-language descriptions of when each job is relevant, published in a manifest that other agent sessions can consult to delegate work.
- **A Claude Code skill** (`scheduled-jobs`) for natural-language management of the system: "pause my daily digest," "change cadence to every 2 hours," "add a trigger for when Obsidian opens."
- **A SessionStart hook** that advertises the system to every new agent session without polluting your `~/.claude/CLAUDE.md`.
- A cost-minimized default heartbeat job (~$1/month at current Haiku pricing) that serves as end-to-end installation proof.
- Concurrent-run protection, optional per-job debouncing, pause/resume, and a preflight-failure observable so nothing fails silently.

## Install

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh | bash
```

That's it. The installer is idempotent; re-running replays cleanly.

If you prefer to inspect before executing:

```bash
curl -fsSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh -o install.sh
less install.sh
bash install.sh
```

Or — if you want the install itself to happen inside a Claude session:

```bash
claude -p "$(curl -fsSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/claude-install-prompt.md)"
```

(This is slower and spends tokens. The shell installer is the recommended path.)

### What the installer does

1. **Preflight**: verifies macOS, `claude` CLI, `/usr/bin/python3`, `/bin/zsh`.
2. **Places files** under `~/.claude/`:
   - `scheduled-jobs/` — runtime (scheduler + per-job executor)
   - `skills/scheduled-jobs/` — the management skill
   - `hooks/scheduled-jobs-notice.sh` — the SessionStart hook
   - `scheduled-jobs-prompt.md` — global prompt appended to every job
3. **Materializes a LaunchAgent** at `~/Library/LaunchAgents/com.$USER.claude-scheduler.plist` and `launchctl load -w`s it.
4. **Registers the SessionStart hook** in `~/.claude/settings.json` (merges into existing hooks; idempotent).
5. **Installs the default heartbeat job** at `~/.claude/scheduled-jobs/heartbeat.md`. Will never overwrite a user-edited job of the same name.
6. **Verifies end-to-end**: fires the heartbeat ad-hoc, waits for `exit_code=0`, prints the result. If this step fails, the installer exits non-zero and points you at the log file for diagnosis.

At the end you'll see a banner with paths, default job, and a prompt suggesting you open Claude Code and ask "what can I schedule?"

## Adding jobs

Drop a Markdown file with YAML frontmatter into `~/.claude/scheduled-jobs/`. The scheduler re-parses every 60 seconds — no reload needed.

Minimal example:

```markdown
---
name: daily-digest
cron: "0 9 * * *"        # 09:00 UTC daily
max_turns: 15
max_budget_usd: 0.50
cwd: ~/work/notes
effort: medium
model: haiku
semantic_hooks:
  - Need a morning summary of open Jira tickets
---

Summarize my open Jira tickets into a markdown digest at
`~/work/notes/digest-$(date -u +%Y-%m-%d).md`. Skip if today's file exists.
```

Or ask your Claude session: *"I want a job that runs at 9am every weekday and emails me a summary of last night's Sentry errors"*. The agent has the `scheduled-jobs` skill loaded and will build it for you.

See [skill/scheduled-jobs/SKILL.md](skill/scheduled-jobs/SKILL.md) for the full frontmatter schema, mutation recipes, cost reality table, and diagnosis walkthroughs.

## External triggers

Jobs can fire on events, not just cron:

```yaml
external_triggers:
  - {type: file_added, path: ~/Downloads, glob: "*.pdf", quiet_seconds: 30}
  - {type: process_starts, match: Obsidian}
  - {type: file_changed, path: ~/Documents/inbox.md}
  - {type: command_succeeds, run: "curl -sf https://api.example.com/health"}
```

All four types are evaluated by the scheduler every minute with bootstrap semantics (pre-existing state doesn't fire), edge-triggering for process/command conditions, and burst-aware firing for new-file detection. Zero token cost to evaluate — these are pure shell/syscalls.

## Cost

On a machine with a rich MCP + plugin surface (~25 MCPs, ~20 plugins):

| Config | Cost per run on Haiku |
|---|---|
| Default heartbeat (`strict_mcp_config: true` + `setting_sources: ""`) | ~$0.04 |
| MCP-using job with `setting_sources: ""` | ~$0.16 |
| Full default surface | ~$0.21 |

Sonnet ~3×, Opus ~15×. Cache creation dominates cost because typical cron cadences exceed the 5-minute cache TTL.

## Uninstall

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/uninstall.sh | bash
```

By default, `uninstall.sh` preserves your job files, state, and logs. Pass `--wipe` to remove everything:

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/uninstall.sh | bash -s -- --wipe
```

## Architecture

```
launchd LaunchAgent (ticks every 60s)
   └─→ scheduler.py
         ├─ scans ~/.claude/scheduled-jobs/*.md
         ├─ parses YAML frontmatter (cron, budgets, triggers, hooks)
         ├─ writes ~/.claude/scheduled-jobs/.manifest.json
         ├─ evaluates external_triggers (file/process/command)
         └─ for each job whose cron matches OR whose trigger fires,
            fires run-job.sh <name> in a detached login shell
                └─→ run-job.sh
                      ├─ creates per-run log FIRST (preflight failures observable)
                      ├─ acquires per-job mkdir-lock (concurrent-run protection)
                      ├─ resolves claude CLI, strips frontmatter from prompt
                      ├─ composes Runtime Context (trigger, budget, paths)
                      ├─ invokes claude -p with --append-system-prompt
                      └─ appends --- exit_code=N === tombstone to log
```

One master LaunchAgent, N jobs. Adding a job is dropping a file. Removing a job is deleting a file. The whole thing is text and shell — grep is your admin tool.

## Requirements

- macOS 12+ (tested through Darwin 25)
- Bundled `/bin/zsh` and `/usr/bin/python3` (no Homebrew required)
- `claude` CLI installed and authenticated
- `git` (for `curl | bash` install; Xcode Command Line Tools provide it)

## License

MIT. See [LICENSE](LICENSE).
