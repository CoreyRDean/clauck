# open-claude-cron

**Give Claude a schedule.** Drop a Markdown file, set a cron expression, and Claude runs it automatically — hourly digests, file-watcher reactions, daily health checks, whatever you need on repeat. One LaunchAgent, zero daemons, ten-second install.

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh | bash
```

The installer walks you through what it will do, asks for confirmation, verifies the pipeline end-to-end, and prints proof it's working.

---

## Why

Claude Code is powerful in a terminal. But you have to be there to use it. open-claude-cron runs Claude when you're not — on a schedule, in response to file changes, when an app opens, or when a shell condition flips. Your agent works while you sleep.

**Casual users:** "Summarize my Slack overnight, every morning at 8am" is a single Markdown file.

**Power users:** External triggers, semantic hook manifests for cross-agent delegation, per-job model/budget/MCP-surface tuning, concurrent-run guards, burst-aware file watchers, and a pre-made job library you can extend or fork.

## What you get

| Feature | What it does |
|---|---|
| **Cron scheduling** | Standard 5-field cron expressions. `*/5 * * * *`, `0 9 * * 1-5`, etc. |
| **External triggers** | Fire jobs on filesystem events, process launches, or shell command edges. No polling tokens — pure syscalls. |
| **Job library** | Curated pre-made jobs you can browse and install from any Claude session. |
| **Natural-language management** | "Pause my daily digest." "Change it to every 2 hours." "What's in the library?" Claude has a skill for this. |
| **Semantic hooks** | Jobs publish natural-language descriptions of when they're relevant. Other agent sessions read the manifest and delegate. |
| **Auto-updates** | Checks GitHub Releases hourly. Notifies you; never auto-applies unless you explicitly opt in. |
| **Cost controls** | Per-job `model`, `max_budget_usd`, `setting_sources`, `strict_mcp_config`. A minimal job costs ~$0.04/run on Haiku. |
| **Concurrency guard** | If a job is already running, re-fires noop instead of double-billing you. |
| **Debouncing** | Optional `debounce_seconds` to suppress rapid re-triggers. |
| **Fork-first design** | Install from your fork. Updates check your fork. No backdoor from upstream. |

## Install

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh | bash
```

**What the installer does** (it tells you all this before asking for confirmation):

1. Checks prerequisites: macOS, `claude` CLI, `/usr/bin/python3`, `/bin/zsh`.
2. Creates `~/.claude/scheduled-jobs/` and supporting directories.
3. Places the scheduler, executor, trigger scripts, skill, library, and SessionStart hook.
4. Asks whether to enable hourly update checks (default: yes, notify-only).
5. Registers a LaunchAgent that ticks every 60 seconds.
6. Fires the default `heartbeat` job ad-hoc and waits for `exit_code=0` as proof the pipeline works.

**Inspect before running:**

```bash
curl -fsSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh -o install.sh
less install.sh   # read every line
bash install.sh
```

**Dry run** (shows what would happen, writes nothing):

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh | bash -s -- --dry-run
```

**Non-interactive** (accepts defaults, for automation):

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/install.sh | bash -s -- --yes
```

**Or just tell Claude** — paste this into any Claude Code session:

> Install open-claude-cron from github.com/CoreyRDean/open-claude-cron. Read the repo's CLAUDE.md for instructions, then run the installer and help me pick jobs from the library.

Claude will fetch the repo's CLAUDE.md, follow the install instructions, and walk you through the library.

### Prerequisites

The installer checks for these and tells you exactly what's missing:

| Dependency | Ships with macOS? | If missing |
|---|---|---|
| `/bin/zsh` | Yes | Always present on macOS |
| `/usr/bin/python3` | Yes (since macOS 12) | Always present on modern macOS |
| `git` | Yes (via Xcode CLT) | `xcode-select --install` |
| **`claude` CLI** | **No** | **[Install Claude Code](https://claude.ai/code)** — the only manual step |

`claude` is the only dependency you need to install yourself. Everything else is bundled with macOS.

### Install from your own fork

Fork the repo, then install with your fork as the source and update channel:

```bash
OPEN_CLAUDE_CRON_REPO=https://github.com/youruser/open-claude-cron \
  bash <(curl -fsSL https://raw.githubusercontent.com/youruser/open-claude-cron/main/install.sh)
```

The installer writes your fork URL into the local config. Future update checks target your fork exclusively — the upstream repo has no mechanism to push anything to your machine. You review and merge upstream changes on your own terms.

## Adding a scheduled job

### The easy way: just tell Claude

Open any Claude Code session and describe what you want:

> "Every weekday at 8am, summarize my unread Slack messages and email me the digest."

The `scheduled-jobs` skill handles everything: cron expression, model selection, budget, prompt design, frontmatter. It writes the `.md` file, fires it ad-hoc to verify, and reports the expected monthly cost.

### The manual way: drop a Markdown file

Create `~/.claude/scheduled-jobs/my-job.md`:

```yaml
---
name: my-job
cron: "0 8 * * 1-5"
max_turns: 10
max_budget_usd: 0.30
model: haiku
---

Summarize my unread Slack messages from the last 12 hours.
Post the summary to my Slack DM (channel D0XXXXXX).
If nothing unread, reply "inbox zero" and exit.
```

The scheduler discovers it within 60 seconds. No reload, no restart.

### Browse the library

Ask Claude: *"What open-claude-cron jobs are in the library?"*

Ships with 7 curated jobs across 4 categories:

| Job | What it does | Schedule | Cost/mo |
|---|---|---|---|
| **morning-brief** | Slack mentions + calendar + Jira tickets in one digest | Weekdays 8am | ~$4 |
| **github-pr-digest** | PRs needing review, stale drafts, recently merged | Weekdays 9am | ~$3 |
| **inbox-zero-assist** | Gmail threads unread 48h+ with suggested actions | Weekdays 5pm | ~$3 |
| **daily-verify** | MCP-surface health check (catch silent auth drift) | Daily | ~$6 |
| **downloads-triage** | Categorize new files in ~/Downloads | Event-driven | <$1 |
| **workspace-cleanup** | Find stale/generic/large files on Desktop | Weekly | ~$0.16 |
| **git-commit-nudge** | Uncommitted changes and unpushed commits across repos | Every 4h | ~$7 |

All library jobs are report-only by default — they read and summarize, they don't send, delete, or modify.

## External triggers

Jobs can fire on events, not just time:

```yaml
external_triggers:
  - {type: file_added, path: ~/Downloads, glob: "*.pdf", quiet_seconds: 30}
  - {type: process_starts, match: Obsidian}
  - {type: file_changed, path: ~/Documents/inbox.md}
  - {type: command_succeeds, run: "curl -sf https://api.example.com/health"}
```

| Trigger | Fires when | Semantics |
|---|---|---|
| `file_added` | New files match the glob after a quiet period | Burst-aware: 10 files in 5 seconds = one fire |
| `file_changed` | File mtime moves forward | Every change fires |
| `process_starts` | Process transitions from not-running to running | Edge-triggered; already-running at install = no fire |
| `command_succeeds` | Shell command exit code transitions from non-zero to zero | Edge-triggered |

All four are evaluated by the scheduler every 60 seconds with zero token cost (pure Python/shell syscalls). Bootstrap-safe: pre-existing conditions at install time don't fire.

## Cost

Every `claude -p` invocation pays a cache-creation cost for the system prompt surface. On a machine with ~25 MCPs and ~20 plugins:

| Job config | Cost per run (Haiku) | Monthly at hourly |
|---|---|---|
| Minimal (`strict_mcp_config` + `setting_sources: ""`) | ~$0.04 | ~$29 |
| MCP-using (`setting_sources: ""`) | ~$0.16 | ~$115 |
| Full default surface | ~$0.21 | ~$151 |

Sonnet is ~3x; Opus is ~15x. The default heartbeat job uses the minimal config: **~$1/month**.

Budget is a hard cap, not a target. Set `max_budget_usd` per job to control spend. The system never exceeds what you configure.

## Trust and security

This system runs `claude -p --dangerously-skip-permissions` in a background LaunchAgent. That's a significant trust surface. Here's how we handle it:

**What we run:**
- A Python scheduler (`scheduler.py`) that reads Markdown files and evaluates cron expressions. It does not invoke Claude itself — it delegates to `run-job.sh`.
- A shell executor (`run-job.sh`) that invokes `claude -p` with your job's prompt. Each invocation is logged with full input/output.
- An optional update checker that makes one HTTPS request per hour to `api.github.com` to compare your installed version against the latest Release.

**What we don't do:**
- **Never auto-apply updates** unless you explicitly set `auto_apply: true` in the config file. The default is notify-only.
- **Never phone home.** No telemetry, no analytics, no tracking. The only outbound request is the opt-in update check against public GitHub API.
- **Never touch your shell config** (`~/.zshrc`, `~/.zprofile`, etc.). We register a hook in `~/.claude/settings.json` and a plist in `~/Library/LaunchAgents/` — both reversible, both enumerated before installation.
- **Never overwrite your jobs.** The installer skips any `.md` file that already exists in your scheduled-jobs directory.

**What you can verify:**
- Every job run produces a timestamped log at `~/.claude/scheduled-jobs/<name>-<ts>.log` with the full `claude -p` JSON envelope. Grep for `exit_code`, `total_cost_usd`, or `result` to audit.
- The manifest at `~/.claude/scheduled-jobs/.manifest.json` shows every registered job, its cron, triggers, and hooks — at a glance.
- `launchctl list | grep claude-scheduler` confirms the LaunchAgent state.

**If you don't trust upstream:**
- Fork the repo.
- Install from your fork: `OPEN_CLAUDE_CRON_REPO=https://github.com/you/open-claude-cron bash install.sh`.
- Update checks target your fork. Upstream merges happen on your terms.

See [SECURITY.md](SECURITY.md) for the full threat model and vulnerability reporting process.

## Architecture

```
launchd (ticks every 60s)
  └─ scheduler.py
       ├─ discovers ~/.claude/scheduled-jobs/*.md
       ├─ parses YAML frontmatter (cron, triggers, hooks, budgets)
       ├─ writes .manifest.json
       ├─ evaluates external_triggers (file/process/command)
       ├─ checks for updates (rate-limited)
       └─ for matching jobs → detached run-job.sh
            ├─ creates log FIRST (preflight failures observable)
            ├─ acquires per-job mkdir-lock (concurrency guard)
            ├─ resolves claude CLI, strips frontmatter
            ├─ composes Runtime Context (trigger, budget, paths)
            └─ claude -p → log → exit_code tombstone
```

One LaunchAgent. N jobs. Adding a job is dropping a file. Removing is deleting it. The whole system is text and shell — `grep` is your admin tool.

## Common operations

```bash
# What's running?
cat ~/.claude/scheduled-jobs/.manifest.json | python3 -m json.tool

# Latest log for a job:
ls -t ~/.claude/scheduled-jobs/<name>-*.log | head -1 | xargs tail

# Ad-hoc fire:
~/.claude/scheduled-jobs/trigger-job.sh <name>

# Check for updates:
~/.claude/scheduled-jobs/update-check.sh

# Apply an update:
~/.claude/scheduled-jobs/update-check.sh --apply

# Scheduler status:
launchctl list | grep claude-scheduler

# Uninstall (preserves your jobs):
bash <(curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/uninstall.sh)

# Full removal including jobs:
bash <(curl -sSL https://raw.githubusercontent.com/CoreyRDean/open-claude-cron/main/uninstall.sh) --wipe
```

## Requirements

- macOS 12+ (tested through Darwin 25)
- `/bin/zsh` and `/usr/bin/python3` (bundled with macOS; no Homebrew needed)
- `claude` CLI installed and authenticated
- `git` (for `curl | bash` install; Xcode Command Line Tools provide it)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Library job contributions are especially welcome — the library grows with the community.

## License

[MIT](LICENSE)
