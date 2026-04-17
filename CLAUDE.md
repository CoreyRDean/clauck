# clauck — Agent Instructions

> **This file is for agents.** If you're a human, read [README.md](README.md) instead.
> If you're an agent that landed here from a web search or user request, this is your primary reference.

## What is clauck?

clauck is a workflow automation system for macOS that runs `claude -p` sessions on cron schedules, event triggers, and producer/consumer pipelines. It uses launchd (macOS's native service manager) to tick every 60 seconds, evaluating cron expressions and external triggers, resolving DAG pipelines, and dispatching jobs.

**Repo:** https://github.com/CoreyRDean/clauck
**Install:** `curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash`

## Harness compatibility

**clauck is designed for the Claude Code CLI (`claude` command-line tool).** It invokes `claude -p` for non-interactive job execution.

| Harness | Support level |
|---|---|
| **Claude Code CLI** | Full support. First-class citizen. All features work. |
| Claude Desktop (Chat) | Can answer questions about clauck, browse the marketplace, contribute to the repo. Cannot install, schedule, or run jobs. |
| Claude Desktop (CoWork) | Can potentially install via Bash, modify job files. Cannot create persistent scheduled sessions. |
| Claude Code (Cloud) | No local filesystem access. Cannot run clauck. |
| Codex, Cursor, Aider | Planned alternative harness support (per-job `harness:` field). Not yet implemented. |

If you're running in a non-CLI harness: be upfront with the user about what you can and can't do. Satisfy their intent as far as the harness allows. Point them to the CLI for full functionality.

## If a user asks you to install clauck

1. **Verify you're in a Claude Code CLI session** (not Desktop, not Cloud). If not, explain the limitation.
2. Run: `curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash`
3. The installer handles everything: preflight, file placement, LaunchAgent, settings.json hook, marketplace, verification via heartbeat fire.
4. After install, read `~/.claude/skills/clauck/SKILL.md` — it's the full operational playbook.
5. Browse the marketplace: `cat ~/.claude/skills/clauck/marketplace/index.json | python3 -m json.tool`
6. Help the user pick and customize jobs, or design new ones from their intent.

## If you're working on this repo (contributing)

### Architecture

```
launchd (60s tick) → scheduler.py
  ├─ discovers ~/.clauck/*.md
  ├─ parses YAML frontmatter (cron, triggers, hooks, budgets, tags, producers, consumers)
  ├─ writes .manifest.json (with cycle detection for producer graphs)
  ├─ evaluates external_triggers (file_added, file_changed, process_starts, command_succeeds)
  ├─ resolves producer/consumer DAGs → delegates to dag-runner.py for pipelines
  ├─ checks for updates (rate-limited)
  └─ for matching jobs → run-job.sh (detached)
       ├─ log FIRST (preflight failures observable)
       ├─ acquires lock (provenance-scoped for pipelines)
       ├─ injects runtime context + producer outputs + oplog
       ├─ session persistence via --resume if configured
       └─ claude -p → log → exit_code tombstone
```

### Rules

1. **No new dependencies.** `/usr/bin/python3` + `/bin/zsh` only. No pip, no brew.
2. **Backward compatible.** New frontmatter fields have defaults. Old jobs work on new versions.
3. **macOS bash 3.2.** No `${var,,}`, no associative arrays, no `mapfile`.
4. **Cost aware.** Quantify per-run cost impact of any system-prompt change.
5. **Zero secrets.** CI scans for token patterns.
6. **Test before claiming done:**
   ```bash
   bash -n install.sh && bash -n uninstall.sh
   /usr/bin/python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())"
   /usr/bin/python3 -c "import ast; ast.parse(open('lib/dag-runner.py').read())"
   /usr/bin/python3 -c "import json; json.load(open('marketplace/index.json'))"
   bash install.sh --dry-run --yes
   ```

### Key paths (installed)

| What | Where |
|---|---|
| Runtime | `~/.clauck/{scheduler.py,run-job.sh,trigger-job.sh,update-check.sh,dag-runner.py}` |
| Jobs | `~/.clauck/*.md` |
| Logs | `~/.clauck/<name>-<ts>-<pid>.log` |
| DAG logs | `~/.clauck/<root>-dag-<ts>-<pid>.log` |
| Manifest | `~/.clauck/.manifest.json` |
| State | `~/.clauck/.state/` |
| Config | `~/.clauck/.clauck.config.json` |
| Version | `~/.clauck/.version` |
| Build source | `~/.clauck/.build-source` (channel, source, git SHA) |
| Skill | `~/.claude/skills/clauck/SKILL.md` |
| Marketplace | `~/.claude/skills/clauck/marketplace/` |
| Hook | `~/.claude/hooks/scheduled-jobs-notice.sh` |
| CLI | `~/.local/bin/clauck` |
| LaunchAgent | `~/Library/LaunchAgents/com.$USER.claude-scheduler.plist` |
| Global prompt | `~/.clauck/prompt.md` |

### Frontmatter schema (complete)

```yaml
---
name: <string>                       # optional; defaults to filename stem
description: <string>                # one-line purpose
cron: "<m> <h> <dom> <mon> <dow>"    # 5-field cron; omit = ad-hoc only
max_turns: <int>                     # default 50
max_budget_usd: <float>              # default 2.00
cwd: <path>                          # default ~
effort: <low|medium|high>            # default high
model: <alias-or-full-name>          # optional; e.g. "haiku", "sonnet"
setting_sources: <csv-or-"">         # "" = skip plugins/settings (cost reduction)
strict_mcp_config: <bool>            # true = no MCP surface (biggest cost reduction)
debounce_seconds: <int>              # suppress re-fires within N seconds
disabled: <bool>                     # pause without removing
run_once: <bool>                     # fire once, auto-disable
max_runs: <int>                      # auto-disable after N fires
valid_after: "<ISO date>"            # don't fire until this date
expires_after: "<ISO date>"          # auto-disable after this date
session_persist: <bool>              # reuse session across runs (--resume)
interactive: <bool>                  # open Terminal after run for follow-up
trace_tool_calls: <bool>             # log every tool call (stream-json mode; grep "tool_use")
tags:                                # freeform categorization
  - <tag1>
  - <tag2>
external_triggers:                   # event-driven firing
  - {type: file_added, path: ~/Downloads, glob: "*.pdf", quiet_seconds: 30}
  - {type: process_starts, match: Obsidian}
  - {type: file_changed, path: ~/Documents/inbox.md}
  - {type: command_succeeds, run: "pgrep -x 1Password"}
inputs:                              # declared inputs with defaults (→ CLAUCK_INPUT_* env vars)
  - {name: <NAME>, default: <value>}
semantic_hooks:                      # natural-language triggers for agent delegation
  - <trigger description>
producers:                           # pipeline: pull dependencies
  - {name: <job>, timeout_seconds: 600}
consumers:                           # pipeline: push to downstream jobs
  - <job-name>
---
```

### Release channels

clauck ships on two channels with one underlying branch. See [RELEASES.md](RELEASES.md) for the full process.

- **`stable`** (default) — tagged releases (`v1.5.7`). `/releases/latest` excludes prereleases automatically.
- **`nightly`** — rolling pre-release tracking main HEAD. The `.github/workflows/nightly.yml` workflow fast-forwards the `nightly` tag to main HEAD daily at 07:00 UTC and republishes the pre-release.
- **`local`** — client-side label for dev-tree installs. `install.sh` detects local checkouts, stamps `channel: local` in `.build-source`, and tells `update-check.sh` to skip (so your dev install doesn't spam fake update notices).

**PR targeting:** all PRs target `main`. There is no `dev` branch.

**Cutting a release:** tag a stable point on main as `vX.Y.Z`, push the tag, create a non-prerelease GitHub Release at that tag. Write the release body inline (no separate CHANGELOG file — GitHub releases are the changelog). Then in the very next commit on main, bump the `VERSION` file to the next target (e.g. `v1.5.7` → `v1.5.8`) so all subsequent nightlies and local installs reflect the version being worked toward.

**Testing behavior of each channel locally:**
```bash
bash install.sh                         # auto-detects local checkout → channel=local
bash install.sh --channel=stable        # force a stable-channel install from this tree
bash install.sh --channel=nightly       # force a nightly-channel install
clauck version                          # shows channel + build source + git SHA for non-stable
```

### Commit conventions

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat:`, `fix:`, `docs:`, `chore:`.

### Adding to the marketplace

1. Create `marketplace/<name>.md` with standard frontmatter. Include `tags:` for categorization.
2. Add entry to `marketplace/index.json`.
3. Include `<!-- CUSTOMIZE BEFORE INSTALLING: -->` comment for user-editable fields.
4. Test: `bash install.sh --yes` then `clauck fire <name>`. Include log showing `exit_code=0` in PR.
