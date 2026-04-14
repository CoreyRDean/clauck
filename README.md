# clauck — your agent, on the clock

[![CI](https://github.com/CoreyRDean/clauck/actions/workflows/ci.yml/badge.svg)](https://github.com/CoreyRDean/clauck/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/CoreyRDean/clauck?include_prereleases)](https://github.com/CoreyRDean/clauck/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey)](https://github.com/CoreyRDean/clauck)
[![Claude Code](https://img.shields.io/badge/powered_by-Claude_Code-orange)](https://claude.ai/code)

<!-- TODO: Replace with banner image at assets/banner.png or clauck.com hosted -->
<!-- ![clauck](assets/banner.png) -->

<!-- AGENT: If you're an AI agent, read CLAUDE.md first — it's your primary reference.
     https://raw.githubusercontent.com/CoreyRDean/clauck/main/CLAUDE.md -->

Workflow automation powered by AI agents. Schedule tasks, chain pipelines, react to events, and build automations that think — all from plain English.

> **Hey Claude, install clauck**
>
> <sub>If Claude can't find it: *"Hey Claude, install CoreyRDean/clauck from GitHub"*</sub>

Paste that into Claude Code. Done.

```bash
# Or one-liner:
curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
```

```bash
# Or manage from terminal:
clauck list                          # what's running?
clauck fire morning-brief            # trigger it now
clauck every morning check my PRs    # plain English → scheduled job
clauck doctor                        # diagnose issues
```

---

## What people build with clauck

| What they said | What clauck does |
|---|---|
| *"Summarize my Slack and email before I sit down."* | Morning digest, 8am weekdays. ~$4/mo. |
| *"When a PDF lands in Downloads, tell me what it is."* | Event trigger. No schedule. ~$0.04/fire. |
| *"Pull Sentry errors → cross-ref with merged PRs → post to Slack."* | Chained pipeline. Three jobs, auto-composed. |
| *"Monitor health endpoints tonight during the deploy, then self-destruct."* | Temporal window. Auto-expires at 6am. |
| *"Prepare my standup 30 min before the meeting. Get better over time."* | Session persistence. Learns across runs. |
| *"Remind me to review the budget on Thursday."* | One-shot. Does the prep, not just the nudge. |
| *"Change my morning brief to also include Sentry."* | Modifies an existing job. One sentence. |
| *"Pause everything for the weekend."* | `clauck pause --all` or just tell Claude. |

## Why this exists

Claude Code is powerful. But you have to be there to use it. **clauck** makes your agent work when you're not — on schedules, in response to events, through multi-step pipelines, and with memory that carries across runs.

It's the difference between a tool you use and an agent that works for you.

### Simple on the surface

> *"Do this every morning: summarize my unread Slack messages."*

Claude handles the cron expression, model selection, budget, prompt design, and installs it. You describe intent; clauck handles execution.

### Powerful at depth

Build pipelines where jobs produce data for other jobs. React to filesystem changes, app launches, and arbitrary shell conditions. Configure per-job models, budgets, and tool surfaces. Create temporal workflows that activate, transition, decay, and expire on schedule. Debug jobs interactively. Let jobs learn from their own history through session persistence.

### Beyond what native scheduling can do

| | Claude Native | clauck |
|---|---|---|
| Event triggers (files, apps, shell) | No | 4 types, zero token cost |
| Cross-run memory | Fresh session each time | Session persistence |
| Chained pipelines (producers → consumers) | No | DAG execution with parallel resolution |
| Temporal scheduling (one-shot, decay, windows) | One-shot only | Full set |
| Per-job model/budget/MCP control | Partial | Per-job frontmatter |
| Interactive debug + iterate | No | Opens Terminal to continue |
| Job marketplace + community | No | 7+ curated, extensible |
| Self-healing diagnostics | No | `clauck doctor` |
| CLI management | No | `clauck` binary with semantic fallthrough |
| Works without Desktop app | Cloud only (no local) | launchd (OS-level) |

## Install

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
```

The installer shows you exactly what it will do and asks before proceeding. It installs the scheduler, skill, marketplace, CLI, and a SessionStart hook — then fires the heartbeat job and shows proof the pipeline works.

**Inspect first:** `curl -fsSL .../install.sh -o install.sh && less install.sh && bash install.sh`

**Dry run:** `curl ... | bash -s -- --dry-run`

**Non-interactive:** `curl ... | bash -s -- --yes`

**Just tell Claude:** paste *"Hey Claude, install clauck"* into any Claude Code session.

### Prerequisites

| Dependency | Ships with macOS? | If missing |
|---|---|---|
| `/bin/zsh`, `/usr/bin/python3` | Yes | Always present |
| `git` | Via Xcode CLT | `xcode-select --install` |
| **`claude` CLI** | **No** | **[Install Claude Code](https://claude.ai/code)** — the only manual step |

### Install from your own fork

```bash
CLAUCK_REPO=https://github.com/you/clauck bash <(curl -fsSL .../install.sh)
```

Updates check your fork. No backdoor from upstream.

## The `clauck` CLI

Installed alongside `claude` at `~/.local/bin/clauck`. For quick management from the terminal:

```bash
clauck list                          # all jobs + status + next fire
clauck status                        # system health overview
clauck fire <name>                   # trigger a job now
clauck edit <name>                   # open in your editor, validate on save
clauck pause <name> / resume <name>  # toggle
clauck logs <name>                   # recent runs with costs
clauck marketplace                   # browse pre-made jobs
clauck install <name>                # install from marketplace
clauck doctor                        # diagnose system health
clauck doctor -i                     # interactive diagnostic session
clauck update --apply                # apply pending update
clauck <anything else>               # plain English → Claude executes it
clauck work <text>                   # explicit semantic (avoids subcommand conflicts)
```

The semantic fallthrough means `clauck change heartbeat to every 2 hours` works the same as opening Claude and asking — but faster.

## Job marketplace

Ships with 7 curated jobs. Ask Claude *"what's in the marketplace?"* or run `clauck marketplace`:

| Job | Schedule | Cost/mo | What it does |
|---|---|---|---|
| **morning-brief** | Weekdays 8am | ~$4 | Slack mentions + calendar + Jira in one digest |
| **github-pr-digest** | Weekdays 9am | ~$3 | PRs needing review, stale drafts, merged |
| **inbox-zero-assist** | Weekdays 5pm | ~$3 | Stale Gmail threads with suggested actions |
| **daily-verify** | Daily | ~$6 | MCP health check (catches silent auth drift) |
| **downloads-triage** | Event-driven | <$1 | Categorize new downloads |
| **workspace-cleanup** | Weekly | ~$0.16 | Stale/generic/large files on Desktop |
| **git-commit-nudge** | Every 4h | ~$7 | Uncommitted/unpushed work across repos |

All report-only by default — they read and suggest, they don't send, delete, or modify.

## Pipelines (producers and consumers)

Jobs can feed into each other. A **producer** delivers its output to the jobs that depend on it. A **consumer** receives output whenever its source runs.

```yaml
# Job A runs after B and C complete, with their outputs injected
producers:
  - {name: job-b}
  - {name: job-c}

# Job A's output automatically triggers X and Y
consumers:
  - job-x
  - job-y
```

The scheduler resolves the full dependency graph, runs roots in parallel, injects outputs up the tree, and handles failures. Each node sees an **oplog** of the full execution chain — who ran, what they produced, in what order.

Pipelines work with or without cron. An ad-hoc-only graph triggered by `clauck fire root-job` is a first-class use case.

## External triggers

React to events, not just time:

```yaml
external_triggers:
  - {type: file_added, path: ~/Downloads, glob: "*.pdf", quiet_seconds: 30}
  - {type: process_starts, match: Obsidian}
  - {type: file_changed, path: ~/Documents/inbox.md}
  - {type: command_succeeds, run: "curl -sf https://api.example.com/health"}
```

All four are evaluated every 60 seconds with zero token cost. Edge-triggered. Bootstrap-safe.

## Temporal scheduling

Beyond simple cron — express time-bounded intent:

```yaml
run_once: true                    # fire once, auto-disable
max_runs: 5                       # fire 5 times, then stop
valid_after: "2026-05-01"         # don't start until May 1st
expires_after: "2026-06-01"       # auto-disable after June 1st
```

Complex requests decompose into phased jobs: *"Every day for a week, then every other day for two weeks, then stop"* becomes multiple jobs with staggered validity windows.

## Trust and security

This system runs `claude -p --dangerously-skip-permissions` in a background LaunchAgent.

**What we do:** every run is logged with full I/O. Auto-updates never apply without explicit opt-in. Fork users are completely isolated from upstream. The installer enumerates everything before acting and asks for confirmation.

**What we don't do:** no telemetry, no phone-home, no shell config modification, no job overwriting.

See [SECURITY.md](SECURITY.md) for the full threat model.

## Cost

| Config | Per run (Haiku) | Monthly at hourly |
|---|---|---|
| Minimal (no MCPs, no plugins) | ~$0.04 | ~$29 |
| MCP-using (no plugins) | ~$0.16 | ~$115 |
| Full surface | ~$0.21 | ~$151 |

Budget is per-job. The system never exceeds what you configure.

## Architecture

```
launchd (60s tick) → scheduler.py
  ├─ discovers jobs, parses frontmatter, writes manifest
  ├─ evaluates cron + external triggers + temporal gates
  ├─ resolves producer/consumer DAGs (cycle detection)
  ├─ checks for updates (rate-limited)
  └─ for matching jobs → run-job.sh (detached)
       ├─ log created FIRST (preflight failures observable)
       ├─ acquires lock (concurrency guard)
       ├─ injects runtime context + producer outputs + oplog
       └─ claude -p → log → exit_code tombstone
```

One LaunchAgent. N jobs. Adding a job is dropping a Markdown file.

## User stories

The [`stories/`](stories/) directory documents concrete use cases — from *"morning catch-up"* to *"multi-phase project cadence"* to *"jobs that learn across runs."* 10 stories ship with the repo. Agents reference them when suggesting jobs; users browse them for inspiration; contributors submit new ones.

## Roadmap

See [ROADMAP.md](ROADMAP.md). Highlights: job chaining/DAG execution (v1.1), Linux support + alternative harnesses (v1.2), clauck.com dashboard (v2.0).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Marketplace jobs and user stories are especially welcome.

## License

[MIT](LICENSE)
