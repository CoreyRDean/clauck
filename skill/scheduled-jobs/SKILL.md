---
name: scheduled-jobs
description: Manage clauck — a launchd-driven scheduler that runs cron-style `claude -p` jobs on macOS with event triggers and a pre-made job marketplace. Use this skill to add/remove/edit/pause jobs, browse and install from the marketplace, check for updates, inspect run logs, diagnose failures, or answer questions about how the system works.
---

# clauck (macOS launchd → `claude -p`)

A minimal system that runs Claude Code prompts on a cron schedule under macOS launchd. Useful for hourly heartbeats, daily digests, periodic inbox triage, scheduled reminders, async monitoring — anything you'd want Claude to do on a cadence without a human in the loop.

## How to respond to common user requests

When the user asks something in this list, follow the playbook — don't improvise from scratch. These are the sanctioned patterns; they set user expectations and keep the UX consistent.

| User intent | Playbook |
|---|---|
| "What's installed / what jobs do I have?" | `cat ~/.claude/scheduled-jobs/.manifest.json \| python3 -m json.tool`. Summarize each job in one line (name, cron/triggers, purpose). Also note the installed version from `~/.claude/scheduled-jobs/.version`. |
| "What can I add?" / "Show me the marketplace" | Read `~/.claude/skills/scheduled-jobs/marketplace/index.json`. Present jobs as a compact list: `<name> (<category>) — <one_line>. Costs ~$X/mo. Requires: <mcps>`. If user mentions a category/tag, filter first. |
| "Install [marketplace job]" | See **Installing from the marketplace** below. Copy the `.md`, walk the user through any `CUSTOMIZE BEFORE INSTALLING` blocks, then ad-hoc fire to verify. |
| "Add a new scheduled job for …" | See **Designing a new job** below. Elicit cron/trigger, budget, destination, then write the `.md`, ad-hoc fire, confirm. |
| "Make this job depend on / use output from [other job]" | Add `producers: [{name: other-job}]` to frontmatter. Check manifest for cycle errors within 60s. See **Pipelines** below. |
| "When this job runs, also trigger [other job]" | Add `consumers: [other-job]` to frontmatter. Consumer fires after each run with the producer's output injected. |
| "Build a pipeline that does A then B then C" | Create 3 jobs. B has `producers: [{name: A}]`, C has `producers: [{name: B}]`. Fire A → automatic cascade. See **Pipelines**. |
| "Fix this" / "Something's broken" / "Debug my job" | Run `clauck doctor` or invoke the `clauck-work` meta job. See **Self-healing**. |
| "Pause / resume job X" | Edit frontmatter: set `disabled: true` (pause) or remove (resume). Effective within 60s. |
| "Change job X to run every N …" | Edit `cron:` field. Show them the new cron string and what it means in plain English. |
| "Check for updates" / "Is there a new version?" | Run `~/.claude/scheduled-jobs/update-check.sh`. Report the result (up-to-date, or new version with release URL). |
| "Apply the update" | Run `~/.claude/scheduled-jobs/update-check.sh --apply`. The installer re-runs against the release tag; verify the heartbeat still fires after. |
| "Disable auto-updates" / "Change update frequency" | Edit `~/.claude/scheduled-jobs/.clauck.config.json`. See **Auto-update configuration** below. |
| "Why isn't job X firing?" / "It broke" | See **Diagnosing failures** section. Walk the hierarchy: launchd loaded? last-run state? preflight log? JSON envelope. |
| "Do this once at [time]" / "Run this tomorrow at 9am" | Set `cron` to match the target time + `run_once: true`. Explain it fires once then auto-disables. |
| "Do this for the next N days/times" | Set `cron` + `max_runs: N`. Or `cron` + `expires_after: <date>`. Pick whichever is more natural for the request. |
| "Start this after [date]" | Set `valid_after: "<ISO date>"`. Scheduler silently skips until then. |
| "Do this until [date]" | Set `expires_after: "<ISO date>"`. Auto-disables after that. |
| Complex multi-phase temporal request | Decompose into multiple jobs with staggered `valid_after`/`expires_after` windows. See **Temporal scheduling** section. |
| "Turn this URL into a scheduled job" | Fetch the URL, identify the repeatable intent, design the prompt. See **Crafting jobs from external sources**. |
| "Remove job X" | `rm ~/.claude/scheduled-jobs/<name>.md` + clean state. Ask first — this is destructive. |
| "Uninstall the whole thing" | Point them at the uninstall.sh one-liner. Note that jobs/logs are preserved by default (use `--wipe` for full removal). Ask before running. |

**Style rules for this skill:**
- Be terse. Users running scheduled jobs don't want essays about scheduled jobs.
- Show the cron expression translated to plain English on every mutation (e.g., `0 */2 * * *` → "every 2 hours on the hour").
- Echo the skill's own cost table when designing a new job. Tell the user the expected monthly cost before they commit.
- If a marketplace job matches what the user asked for, surface it before offering to write a new one. Ship-of-Theseus principle: use what exists.
- **Default word association:** when the user says "remind me", "set a reminder", "schedule this", "do this every [time]", "recurring task", "notification", or similar scheduling-adjacent language, default to solving it with clauck unless the context clearly refers to a different system (e.g., "show my Reminders app" is about Apple Reminders, not cron jobs). When ambiguous, lean toward offering a scheduled-job solution.
- When proactively suggesting, don't just suggest new jobs — watch for signals that an existing job should be **modified**: "this brief is too verbose", "I don't need the calendar section anymore", "can we add Sentry to the morning report?" These are modification intents, not creation intents. Suggest editing the existing job's prompt.

### The `clauck` CLI — a human tool, not an agent tool

The `clauck` binary at `~/.local/bin/clauck` is a lightweight CLI for humans to manage jobs from the terminal. It's convenient for quick status checks, pausing jobs, browsing the marketplace, and editing prompts.

**As an agent, you should NOT use `clauck` CLI commands.** You have direct access to the filesystem, state files, and manifest — use those for more control and granularity. The CLI is a convenience wrapper around the same files you can read/write directly. Using it would add a subprocess hop and limit your ability to handle edge cases.

**However, educate the user about `clauck` when relevant.** When they ask how to manage jobs from the terminal, show them the CLI commands. When they want to do something quickly without opening a Claude session, point them to `clauck`. Key commands to teach:
- `clauck list` — quick overview
- `clauck edit <name>` — open job prompt in their editor
- `clauck fire <name>` — test a job immediately
- `clauck logs <name>` — recent run history
- `clauck <anything>` — semantic fallthrough (Claude interprets natural language as a clauck operation)

The semantic fallthrough (`clauck every morning check my PRs`) uses `claude -p` behind the scenes, but the user sees only the result — like a normal CLI command. It's the bridge between the CLI's speed and Claude's understanding.

## User stories

The `stories/` directory in the repo contains documented use cases that clauck is designed to support — from simple ("remind me to review this on Thursday") to complex ("multi-phase project cadence with automatic transitions"). Agents should reference these when suggesting jobs to ground recommendations in concrete, validated patterns. Users can browse them for inspiration.

## Status queries and diagnostics

When the user asks about the state of their jobs, give rich, skimmable output:

**"What's running?" / "Show my jobs"** — For each job: name, schedule (translated to English), next expected fire time, status (active/paused/expired/runs-remaining). If temporal fields are set, show them: `valid_after`, `expires_after`, `max_runs` with remaining count, `run_once` status. Read the manifest + `.state/` files.

**"When does [job] run next?"** — Calculate from the cron expression + current time. Show both UTC and the user's local timezone if detectable.

**"How many runs are left?"** — Read `.state/<name>.runs-remaining`. If not set, say "unlimited (no max_runs configured)."

**"Show me the last run of [job]"** — `ls -t ~/.claude/scheduled-jobs/<name>-*.log | head -1 | xargs tail`. Parse the JSON envelope for: exit code, cost, duration, result excerpt.

**"Show run history for [job]"** — List the last N log files by date. For each: timestamp, exit code, cost. Present as a compact table.

**"Why didn't [job] fire?"** — Walk the diagnosis tree: Is it disabled? Auto-disabled? valid_after in the future? expires_after in the past? max_runs exhausted? Debounced? Cron doesn't match? External trigger didn't fire? Last-run already set for this minute?

## Installing from the marketplace

The marketplace at `~/.claude/skills/scheduled-jobs/marketplace/` ships curated job prompts. Workflow:

1. Read `marketplace/index.json` to list/filter candidates.
2. Show the user a compact summary of matching jobs with their `one_line`, `cost_per_run_usd_approx`, `requires.mcps`, and `schedule`.
3. When the user picks one, **read the source `.md` file** and look for a `<!-- CUSTOMIZE BEFORE INSTALLING: -->` comment block. Walk the user through each customization (ask for the specific channel ID / path / etc.), and edit the copy in memory.
4. Copy the customized content to `~/.claude/scheduled-jobs/<name>.md`. **Never overwrite an existing job of the same name without asking first.**
5. Wait ~60s for the scheduler to pick up the new job (`.manifest.json` will regenerate), then ad-hoc fire it to verify: `~/.claude/scheduled-jobs/trigger-job.sh <name>`.
6. Tail the resulting log. If exit_code=0 and the expected side-effect happened (Slack post / file written / etc.), report success with the expected schedule and cost.
7. If it failed, show the user the log excerpt and propose a fix.

## Designing a new job (interactive)

When the user wants a new job that isn't in the marketplace, elicit these in order:

1. **Trigger:** cron? external trigger (file/process/command)? Both?
2. **What it should do:** in one sentence. If multiple actions, ask them to narrow — scheduled jobs should do one thing well.
3. **Where output goes:** durable surface (Slack/Jira/local file/etc.). Scheduled jobs that only produce transient output are usually a mistake.
4. **Cost tolerance:** does this need full MCP access or can it run minimal? Use the cost table to ground the conversation. Haiku + minimal surface = ~$0.04/run; MCP-using job = ~$0.20/run.
5. **Idempotency plan:** what happens if the job runs twice? The global prompt enforces "check durable state before acting" but the job-specific prompt should make the check concrete.

Once collected, write `~/.claude/scheduled-jobs/<name>.md`, ad-hoc fire to verify, and report.

## Auto-update configuration

Config file: `~/.claude/scheduled-jobs/.clauck.config.json`

Default:

```json
{
  "auto_update": {
    "enabled": true,
    "check_interval_seconds": 3600,
    "auto_apply": false
  }
}
```

| Key | Effect |
|---|---|
| `enabled: false` | Scheduler never checks for updates. The user can still run `update-check.sh` manually. |
| `check_interval_seconds: N` | How often (in seconds) the scheduler runs the update check. 3600 = hourly. 86400 = daily. |
| `auto_apply: true` | When a new release is detected, automatically run install.sh from the new tag. Requires network, may interrupt running jobs during the install. Security-conscious default is `false` (notify-only). |

**Source of truth:** the `tag_name` of the latest GitHub Release at `https://github.com/CoreyRDean/clauck/releases/latest`. Pushes to `main` never trigger an auto-update — a maintainer must explicitly cut a Release.

**Ad-hoc check:** `~/.claude/scheduled-jobs/update-check.sh` (report only) or `--apply` (install).

When an update is detected, the SessionStart hook surfaces this at the top of future Claude sessions, so the user sees the notification without having to check manually.

## Crafting jobs from external sources (3rd-party URLs, raw intent)

When the user says something like *"Claude, install this as a job: https://example.com/my-workflow"* or *"Claude, turn this into a daily job: [paste of raw text]"*:

1. **Fetch/read the source material.** Use WebFetch for URLs, or read pasted text directly.
2. **Identify the repeatable intent.** What is the core action that should happen each run? Strip the one-time setup instructions, keep the recurring work.
3. **Design the prompt** using the same principles as "Designing a new job": cron/trigger, output destination, cost tier, idempotency plan. Aim for the minimum turns + tokens that accomplish the intent.
4. **Write the `.md` file**, ad-hoc fire to verify, report cost and schedule.

The user does NOT need to understand frontmatter or cron. They provide intent + source material; you produce an optimized job.

## Proactive job suggestions

**You should actively look for opportunities to suggest scheduled jobs during normal conversation.** This is not a passive skill — it triggers whenever you detect intent that maps to recurring, deferred, or event-driven automation.

The goal is not to suggest jobs mechanically. It's to understand the user's underlying needs well enough that the right suggestion feels obvious to them — like the system read their mind. You're looking for the *hidden intent behind the surface behavior*.

### Intent signals → job suggestions

These signals aren't a lookup table. They're patterns that indicate the user would likely accept a suggestion. Use judgment — if the signal is weak or the context doesn't fit, don't suggest.

**Repetition signals** — the user does something that is inherently recurring:
- Searches for time-varying information (news, prices, social feeds, repo activity, weather)
- Summarizes a channel, inbox, feed, or dashboard
- Does manual triage, cleanup, review, or categorization
- Checks on the status of something (CI, deploy, PR, service health, server uptime)
- Prepares for a meeting that recurs (standup, retro, 1:1, sprint planning)

**Deferral signals** — the user describes future intent:
- "Remind me to...", "Don't let me forget...", "I need to do this by..."
- "Next Tuesday I need to...", "When X happens, I should..."
- "After the launch, I'll want to monitor..."
- "For the next few days, check..."

**Frustration signals** — the user is annoyed at manual repetition:
- "I keep having to check this manually"
- "Every morning I have to open 5 tabs and..."
- "I wish I had a summary of..."
- Doing the same file management, email triage, or notification cleanup repeatedly

**Modification signals** — an existing job should change, not a new one created:
- "This is too verbose / too detailed / not enough"
- "Can we add [source] to the brief?"
- "I don't need the [section] anymore"
- "Can it run at [different time] instead?"
- "Make it also check [additional thing]"
- Implicit: user asks you to do something a job already does differently → suggest modifying the job

### How to suggest

- **One sentence, as a question.** Match the energy of the conversation. Don't lecture about clauck or frontmatter.
- **Include the cadence and rough cost.** *"Want me to do this every weekday morning? ~$0.20/day on Haiku."*
- **For modifications**, name the existing job: *"Your morning-brief already runs at 8am — want me to add Sentry to it?"*
- **If they say yes**, immediately design/modify and install. Don't ask more questions unless you genuinely need a decision (output destination, specific channel, etc.).
- **If they ignore or decline**, drop it. One offer per pattern per session.
- **For deferral signals**, suggest one-shot or temporal scheduling naturally: *"I can set that up as a one-time job for Tuesday at 9am."*

## Temporal scheduling (one-shot, decay, delayed-start, expiry)

The scheduler supports several temporal patterns beyond simple cron repetition, all via frontmatter fields:

### `run_once: true` — fire once, then auto-disable

```yaml
---
name: birthday-reminder
cron: "0 9 17 4 *"
run_once: true
---
Send a birthday message to the team Slack channel.
```

After firing once, the scheduler writes a `.auto-disabled` state file. The job stays in the manifest but won't fire again. User can re-enable by deleting `~/.claude/scheduled-jobs/.state/<name>.auto-disabled`.

### `max_runs: N` — fire N times, then auto-disable

```yaml
---
name: onboarding-check
cron: "0 9 * * *"
max_runs: 5
---
Check if the new hire completed each onboarding step. Post progress to Slack.
```

Counter tracked at `~/.claude/scheduled-jobs/.state/<name>.runs-remaining`. Decrements on each fire. At zero, auto-disabled.

### `valid_after: "<ISO date>"` — don't fire until this date

```yaml
---
name: post-launch-monitor
cron: "0 */2 * * *"
valid_after: "2026-05-01"
---
Check production metrics every 2 hours after the May 1st launch.
```

Scheduler silently skips this job until the system clock passes the date. Combine with `expires_after` for a bounded window.

### `expires_after: "<ISO date>"` — auto-disable after this date

```yaml
---
name: conference-prep
cron: "0 8 * * *"
valid_after: "2026-06-01"
expires_after: "2026-06-05"
---
Daily conference schedule digest during the event.
```

### Decomposing complex temporal requests

Users will say things like: *"Do this every day for a week, then switch to every other day for two weeks, then stop."*

Decompose into multiple jobs with staggered `valid_after` / `expires_after` windows:

| Phase | Job name | Cron | valid_after | expires_after |
|---|---|---|---|---|
| Week 1: daily | `task-phase1` | `0 9 * * *` | (now) | 7 days from now |
| Week 2-3: every other day | `task-phase2` | `0 9 */2 * *` | 7 days from now | 21 days from now |

Create both jobs at once. Phase 1 runs immediately; phase 2 activates when phase 1 expires.

For truly complex requests the user might describe, decompose as far as the system allows. If any requirement can't be expressed in the available frontmatter fields, be transparent: explain what you CAN do, do that, and suggest the user file a feature request at https://github.com/CoreyRDean/clauck/issues for the missing capability.

## Artifact delivery — where job outputs live

Jobs that produce durable artifacts (digests, reports, triage suggestions) need a clear delivery model. The system does NOT prescribe a default — it's part of the job's prompt. But guide users toward good patterns:

### Delivery surfaces (pick per job)

| Surface | When to use | Tradeoff |
|---|---|---|
| **Slack/Discord DM** | User wants push notification + searchable history | Requires MCP; ~$0.15/run cost floor |
| **Local Markdown file** | User wants zero-MCP cost | No push notification; user must check the file |
| **Jira/Linear comment** | Artifact is tied to a specific ticket or project | Requires MCP |
| **Email (Gmail)** | User wants delivery to an inbox they already check | Requires MCP |
| **Clipboard** (via `pbcopy`) | Ephemeral; user wants to paste somewhere specific | No history; gone after next copy |

### Accumulation pattern

Each job's prompt should specify:
- **Append** (default for feed-style jobs): each run adds a new section with a timestamp header. History accumulates. Capped implicitly by log rotation (100 files) or the user's own cleanup.
- **Overwrite** (for "latest status" dashboards): each run replaces the file entirely. Only the most recent state matters.
- **Thread** (for Slack/Discord): each run is a reply in a thread. History is the thread. Root message is created on first run, discovered on subsequent runs.

When designing a job for the user, ask which pattern they want if the intent is ambiguous. Default to append for digests/reports, overwrite for status dashboards, and thread for chat-based delivery.

### Discoverability

If a job writes to a local file, tell the user exactly where it is after installation. When proactively suggesting a job, mention the output path as part of the pitch: *"I'd write a morning brief to `~/.claude/scheduled-jobs/morning-brief-feed.md` — want me to set it up?"*

## Pipelines (producers and consumers)

Jobs can be wired into DAGs where one job's output feeds into another job's input.

### Producers (pull — "I need this before I can run")

```yaml
producers:
  - {name: job-b}
  - {name: job-c, timeout_seconds: 300}
```

When a job with producers triggers (cron, event, or ad-hoc), the scheduler delegates to `dag-runner.py` which:
1. Resolves the full dependency tree recursively
2. Finds roots (jobs with no producers) and runs them in parallel
3. As each layer completes, injects outputs into the next layer
4. Each node receives a `## Producer outputs` section in its runtime context with the results from its producers
5. Each node also sees an **oplog** — the full execution chain showing what ran, when, and whether it succeeded

### Consumers (push — "My output goes to these after I run")

```yaml
consumers:
  - job-x
  - job-y
```

After a job completes (regardless of how it was triggered), its output is delivered to each consumer and the consumer is fired. This is unconditional and non-blocking.

### Cycle suppression

When a producer completes inside an invocation tree and would deliver to its registered consumers, it skips any consumer that is already a member of the current invocation tree. This prevents ping-pong loops in double-linked jobs (A produces for B, B consumes from A).

**When designing pipelines, ALWAYS check for cycles.** The scheduler detects them at manifest-write time (every 60s) and logs errors. But the best practice is to never create them. Before adding a producer or consumer link, trace the graph mentally: can you get from any job back to itself by following producer/consumer edges?

### Designing a pipeline for the user

When a user describes a multi-step workflow:

1. **Identify the stages.** Each distinct data-transformation step is a job.
2. **Wire producers.** Each stage lists its input stages as producers.
3. **Keep stages focused.** One job = one transformation. Cheaper per-job budgets, better debuggability.
4. **Set the root's trigger.** The root (final stage) has the cron or external trigger. Upstream jobs are ad-hoc-only (`cron: ""`).
5. **Consumer links are for fan-out.** Use them when a job's output should trigger independent downstream work that isn't part of the linear pipeline.
6. **Report total cost.** Sum all jobs' `max_budget_usd` in the pipeline. This is the theoretical max per trigger.

Example — a 3-stage pipeline:

```
Job: sentry-pull (cron: "", producers: none)
  → pulls last 24h of Sentry errors

Job: pr-correlate (cron: "", producers: [{name: sentry-pull}])
  → cross-references errors with merged PRs from last week

Job: weekly-report (cron: "0 10 * * 1", producers: [{name: pr-correlate}])
  → synthesizes correlation report, posts to Slack
  → consumers: [team-channel-notify]
```

User says: *"Every Monday, pull Sentry errors, cross-reference with merged PRs, and post a correlation report."* You create these 3 jobs + the consumer. Total cost: ~$0.50/week.

### Pipelines without scheduling

Producer/consumer DAGs work independently of cron. A graph of ad-hoc-only jobs triggered by `clauck fire root-job` is a first-class use case. This makes clauck a general-purpose workflow engine, not just a scheduler.

## Self-healing (clauck-work)

The `clauck-work` meta job is a session-persistent diagnostic agent. It's invoked:
- Automatically when a pipeline node fails (abort-on-fail behavior)
- Via `clauck doctor` for manual diagnostics
- Via `clauck doctor -i` for interactive diagnostic sessions

It scores fixes on cost:value × confidence:impact before acting. High-confidence low-risk fixes are applied automatically. Uncertain or high-risk issues are surfaced to the user with options.

Because it has `session_persist: true`, it accumulates knowledge about recurring issues across invocations — it gets better at diagnosing your specific installation over time.

## Architecture

```
launchd LaunchAgent (ticks every 60s)
   └─→ scheduler.py
         ├─ scans ~/.claude/scheduled-jobs/*.md for job prompts
         ├─ parses YAML frontmatter (cron, budgets, semantic_hooks, …)
         ├─ writes ~/.claude/scheduled-jobs/.manifest.json
         └─ for each job whose cron matches the current minute,
            fires run-job.sh <name> in a detached login shell
                └─→ run-job.sh
                      ├─ creates per-run log FIRST (so preflight failures are captured)
                      ├─ resolves claude CLI, strips frontmatter from prompt
                      ├─ composes runtime-context block (trigger, budget, paths)
                      ├─ invokes `claude -p <prompt> --append-system-prompt <global+runtime>
                      │                  --dangerously-skip-permissions --effort … --max-turns … --max-budget-usd …
                      │                  --output-format json`
                      └─ appends `--- exit_code=N ===` tombstone to log
```

One master LaunchAgent, N jobs. Adding a job is dropping a Markdown file.

## File layout (canonical paths)

| Path | Purpose |
|---|---|
| `~/.claude/scheduled-jobs/scheduler.py` | Discovery + dispatch. Runs every 60s. |
| `~/.claude/scheduled-jobs/run-job.sh` | Per-job executor (log, preflight, compose runtime context, run claude). |
| `~/.claude/scheduled-jobs/trigger-job.sh` | Ad-hoc-fire wrapper. Used by other agents that match a semantic hook. |
| `~/.claude/scheduled-jobs/<name>.md` | A job: YAML frontmatter + prompt body. |
| `~/.claude/scheduled-jobs-prompt.md` | Global system prompt appended to every job. |
| `~/.claude/scheduled-jobs/.manifest.json` | Regenerated every tick. All jobs with their `cron`, `semantic_hooks`, and `trigger_command`. |
| `~/.claude/scheduled-jobs/.state/<name>.last-run` | Per-job last-fire epoch (cron-duplication guard). |
| `~/.claude/scheduled-jobs/<name>-<utc-ts>.log` | Per-run log. Rotated at 100 per job. |
| `~/.claude/scheduled-jobs/.scheduler-stdout.log` | Master scheduler stdout (one line per fire). |
| `~/.claude/scheduled-jobs/.scheduler-stderr.log` | Master scheduler stderr (bad crons, etc). |
| `~/Library/LaunchAgents/com.<username>.claude-scheduler.plist` | The LaunchAgent. |

## Frontmatter schema (the job contract)

```yaml
---
name: <string>                      # optional; defaults to filename stem
description: <string>               # one-line purpose; shown in the manifest
cron: "<m> <h> <dom> <mon> <dow>"   # 5-field cron; omit/blank = ad-hoc-only
max_turns: <int>                    # default 50
max_budget_usd: <float>             # default 2.00
cwd: <path>                         # default ~; supports ~ and $HOME-relative
effort: <low|medium|high>           # default high
model: <alias-or-full-name>         # optional; e.g. "haiku", "sonnet", "opus",
                                    #   or full "claude-haiku-4-5-20251001".
                                    # Absent = claude's default.
setting_sources: <csv-or-"">        # optional; maps to --setting-sources.
                                    # Empty string = skip plugins/settings (big
                                    # cache-creation savings for simple jobs).
                                    # Absent = claude's default (load user+project+local).
strict_mcp_config: <bool>           # optional, default false. If true, the
                                    # executor passes --strict-mcp-config with
                                    # an empty MCP config, stripping the user's
                                    # entire MCP surface from the prompt. The
                                    # single largest cache-creation reduction
                                    # available; use for jobs that don't need
                                    # any tool access.
debounce_seconds: <int>             # optional, default 0 (off). If >0, a new
                                    # invocation within this window of the last
                                    # START is suppressed (noop, exit 0, logged
                                    # as `noop_skip: debounced`).
disabled: <bool>                    # optional, default false. If true, scheduler
                                    # skips cron firings of this job but keeps
                                    # it in the manifest so other agents can
                                    # still ad-hoc trigger it.
run_once: <bool>                    # optional. Fire once, then auto-disable.
                                    # State: .state/<name>.auto-disabled
max_runs: <int>                     # optional, 0=unlimited. Auto-disable after
                                    # N fires. State: .state/<name>.runs-remaining
valid_after: "<ISO date>"           # optional. Scheduler skips until now >= this.
                                    # "2026-05-01" or "2026-05-01T09:00:00"
expires_after: "<ISO date>"         # optional. Scheduler auto-disables once
                                    # now > this. Combine with valid_after for
                                    # bounded windows.
session_persist: <bool>             # optional. If true, reuse the same claude
                                    # session across runs (--resume). Each run
                                    # has context from all prior runs. Session ID
                                    # stored at .state/<name>.session-id.
interactive: <bool>                 # optional. If true, after the background run
                                    # completes, open a Terminal window with an
                                    # interactive claude session resuming the
                                    # just-completed run. User can see output and
                                    # iterate. Useful for debugging or iterative jobs.
external_triggers:                  # optional. List of conditions that fire
                                    # the job between cron slots. Evaluated each
                                    # 60s tick. See "External triggers" section.
  - {type: file_added, path: ~/Downloads, glob: "*.pdf", quiet_seconds: 30}
  - {type: process_starts, match: Obsidian}
  - {type: file_changed, path: ~/Documents/inbox.md}
  - {type: command_succeeds, run: "pgrep -x 1Password"}
semantic_hooks:                     # natural-language triggers for ad-hoc firing
  - <trigger 1>
  - <trigger 2>
---
(prompt body — YAML is stripped before being passed to claude -p)
```

**Cron syntax supported:** standard 5-field form. Each field supports `*`, `*/N`, `N`, `A,B,C`, `A-B`. Day-of-week: `0=Sun..6=Sat` (7=Sun tolerated).

**Omitting `cron`** makes a job ad-hoc-only (still appears in the manifest with a `trigger_command`, but is never fired by the scheduler). Useful for jobs that only other agents should invoke via semantic hooks.

## What each job sees

A running job receives three stacked prompts:

1. **User prompt** (`-p <body>`): the job's own `<name>.md` with YAML frontmatter stripped.
2. **Appended system prompt**: the global `scheduled-jobs-prompt.md` concatenated with a **Runtime Context** block the executor composes per invocation. Runtime Context includes: job name, trigger source (`scheduled` or `adhoc`) plus cron expression, fire-at timestamp, budget (max_turns / max_budget_usd / effort), cwd, the exact log-file path for this run, the jobs directory, and the manifest path.
3. **Claude's own defaults** (tools, MCP surface, memory).

Everything is resolved via `zsh -l` so PATH / nvm / keychain mirror the user's Terminal. MCPs auto-load from the user's configured MCP surface.

## Key behavioral guarantees (baked into the code)

- **Preflight failures are observable.** `run-job.sh` creates the log file *before* any preflight check. Missing prompt, missing claude CLI, unreachable cwd all write a `--- preflight_fail: <reason> ===` tombstone. Stdout/stderr of the dispatched subprocess are DEVNULL'd, so this is the only record — it has to land in the log.
- **PATH quirks under launchd are handled.** launchd-spawned `zsh -lc` is login but not interactive; `~/.zshrc` does not load. `run-job.sh` explicitly prepends `$HOME/.local/bin:$HOME/bin` to PATH so user-installed CLIs resolve.
- **Cron-duplicate guard.** Each job's `last-run` state file is written *before* the detached process is spawned. If a tick is slow, the next tick sees last-run == current-minute and skips.
- **Log rotation.** Caps at 100 files matching `<name>-[0-9]*.log`. The digit anchor prevents accidental cross-job matches (e.g. `heart` wouldn't match `heartbeat-*`).
- **Ad-hoc trigger marks itself.** Runtime Context distinguishes `scheduled` vs `adhoc` triggers so jobs can gate behavior (e.g. skip expensive work on ad-hoc probes).

## Install from scratch on a new machine

Prerequisites: macOS, `zsh` (default), `/usr/bin/python3`, `claude` CLI installed and authenticated (test with `claude --version`).

### Step 1: Create the directory layout

```bash
mkdir -p ~/.claude/scheduled-jobs/.state
mkdir -p ~/Library/LaunchAgents
```

### Step 2: Install the three scripts and global prompt

Clone the repo and run the installer — it handles all file placement, LaunchAgent registration, and settings.json patching:

```bash
git clone https://github.com/CoreyRDean/clauck /tmp/clauck-install
bash /tmp/clauck-install/install.sh
```

Or use the one-liner from the README:

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
```

The installer places scripts in `~/.claude/scheduled-jobs/`, the skill in `~/.claude/skills/scheduled-jobs/`, the hook in `~/.claude/hooks/`, and the LaunchAgent in `~/Library/LaunchAgents/`. After install, consider editing `~/.claude/scheduled-jobs-prompt.md` to add environment-specific durable-state guidance if useful for your jobs.

### Step 3: Install the LaunchAgent

Create `~/Library/LaunchAgents/com.<username>.claude-scheduler.plist` (replace `<username>` with the current user) with this content — adjust paths only if the user's home is non-standard:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.<username>.claude-scheduler</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-lc</string>
        <string>/usr/bin/python3 "$HOME/.claude/scheduled-jobs/scheduler.py"</string>
    </array>

    <key>StartInterval</key>
    <integer>60</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>ProcessType</key>
    <string>Background</string>

    <key>StandardOutPath</key>
    <string>/Users/<username>/.claude/scheduled-jobs/.scheduler-stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/<username>/.claude/scheduled-jobs/.scheduler-stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/<username></string>
    </dict>
</dict>
</plist>
```

### Step 4: Load it

```bash
launchctl load -w ~/Library/LaunchAgents/com.<username>.claude-scheduler.plist
launchctl list | grep claude-scheduler
# Expect: <pid>  0  com.<username>.claude-scheduler
```

### Step 5: Verify with a disposable job

Drop a one-shot verification job at `~/.claude/scheduled-jobs/probe.md`:

```yaml
---
name: probe
description: Installation verification
cron: ""
max_turns: 2
max_budget_usd: 0.05
effort: low
---

Reply with one line: `probe ok <ISO8601 UTC>`. No preamble.
```

Fire it ad-hoc:

```bash
~/.claude/scheduled-jobs/trigger-job.sh probe
# Wait ~10 seconds, then:
ls -t ~/.claude/scheduled-jobs/probe-*.log | head -1 | xargs tail
# Expect: "--- exit_code=0 ===" and a JSON envelope whose `result` contains "probe ok <timestamp>"
```

Delete the probe when done: `rm ~/.claude/scheduled-jobs/probe.md ~/.claude/scheduled-jobs/probe-*.log`.

## Adding a job

1. Create `~/.claude/scheduled-jobs/<name>.md` with the frontmatter schema above and a prompt body describing exactly what this invocation should do.
2. The scheduler regenerates the manifest within 60 seconds. No `launchctl reload` needed.
3. Verify with `~/.claude/scheduled-jobs/trigger-job.sh <name>` before waiting for the first cron fire.

**Prompt writing tips** for scheduled jobs (different from interactive prompts):

- **No human clarification.** Phrase the task so there's only one reasonable interpretation, or give explicit tiebreakers.
- **Idempotency.** The same job runs many times. Tell it how to detect and skip work already done (check a durable-state surface: a chat thread, a ticket, a file, a manifest).
- **Token efficiency.** Invocation cost pays every time. Be terse. Skip restating intent. Say what output you want and stop.
- **MCP tool attempts.** MCP tools (Slack, Jira, Gmail, etc.) may not appear in the LLM's initial tool-surface enumeration — they're often lazy-loaded. Instruct jobs to *attempt* the call when needed rather than preemptively declaring a tool unavailable. (This is already in the global prompt; don't repeat it per-job.)
- **Budget appropriately.** Budget caps are a hard kill-switch, not a target. A health-check: `max_turns: 2-4`, `max_budget_usd: 0.25-0.35`, `effort: low`, `model: haiku`. A multi-step triage: `max_turns: 20`, `max_budget_usd: 1.00`, `effort: medium`. A deep investigation: higher.
- **Durable state.** Tell the job the canonical place to persist state and read state from prior invocations. This is job-specific (a chat channel, a ticket tracker, a filesystem marker, etc.) — the global prompt only tells jobs *that* durable state matters, not *where* it lives.

### Cost reality check for frequent jobs

Every invocation pays the **cache-creation cost** of Claude's system prompt surface, because the prompt cache has a ~5-minute TTL and most cron cadences are longer than that. Each run starts cold.

Empirical measurements on a machine with a rich MCP + plugin inventory (~25 MCP servers, ~20 plugins installed):

| Configuration | Cache-creation tokens | Cost per run (Haiku) |
|---|---|---|
| Default (full MCP + plugins) | ~170k | ~$0.21 |
| `setting_sources: ""` (no plugins, full MCPs) | ~124k | ~$0.16 |
| `--strict-mcp-config` + empty MCP config (no MCPs, plugins intact) | ~47k | ~$0.06 |
| Both (no plugins, no MCPs) | ~30k | ~$0.04 |

Corollaries:
- If a job needs any MCP tool (Slack, Jira, etc.) it pays the MCP-surface floor (~$0.15-0.20 on Haiku per run). There is no way around this without replacing `claude -p` with something else (e.g., a direct API call for the specific tool).
- Sonnet is ~3× more expensive; Opus is ~15× more expensive. For jobs that only need to decide one small thing and do it, Haiku is the right default.
- Budget must exceed the floor or the job dies during cache creation without performing any work. Set `max_budget_usd` at least ~30% above the measured floor for margin.
- High-frequency low-value jobs are inherently expensive on a rich plugin/MCP setup. Consider: (a) larger cadence, (b) an out-of-claude implementation (curl + a webhook for heartbeat-style pings), or (c) `setting_sources: ""` and a minimal MCP config for jobs that don't need the full tool surface.

## Common operations

### Inspect the system

```bash
# All discovered jobs + semantic hooks + trigger commands:
cat ~/.claude/scheduled-jobs/.manifest.json | python3 -m json.tool

# Is the scheduler running?
launchctl list | grep claude-scheduler

# Recent fires:
tail -f ~/.claude/scheduled-jobs/.scheduler-stdout.log

# Latest run for a specific job:
ls -t ~/.claude/scheduled-jobs/<name>-*.log | head -1 | xargs tail

# Dry-run discovery without firing:
/usr/bin/python3 ~/.claude/scheduled-jobs/scheduler.py --list
```

### Ad-hoc fire a job

```bash
~/.claude/scheduled-jobs/trigger-job.sh <name>
```

Runtime Context will report `Trigger: adhoc` so the job can distinguish this from a cron fire.

### Edit a job

Edit `~/.claude/scheduled-jobs/<name>.md`. Changes take effect on the next tick (the scheduler re-parses frontmatter every minute).

### Remove a job

```bash
rm ~/.claude/scheduled-jobs/<name>.md
# Optionally clean up:
rm -f ~/.claude/scheduled-jobs/.state/<name>.last-run
rm -f ~/.claude/scheduled-jobs/<name>-*.log
```

### Stop the scheduler (e.g., during maintenance)

```bash
launchctl unload ~/Library/LaunchAgents/com.<username>.claude-scheduler.plist
```

### Resume

```bash
launchctl load -w ~/Library/LaunchAgents/com.<username>.claude-scheduler.plist
```

### Reset a job's cron-duplicate guard (force the next matching minute to fire)

```bash
rm -f ~/.claude/scheduled-jobs/.state/<name>.last-run
```

## Common mutations (recipes)

Natural-language asks like "change my daily job to run every 2 days" or "pause all jobs" map to these recipes. Scheduler re-reads frontmatter on every minute tick, so edits take effect within 60 seconds — no reload needed.

### Pause a single job (keep manifest + ad-hoc trigger, just stop cron)

Add `disabled: true` to the frontmatter:

```yaml
---
name: my-job
cron: "0 * * * *"
disabled: true        # ← add this
...
---
```

The scheduler skips disabled jobs entirely. The manifest still lists it (with `"disabled": true`) so other agents can still ad-hoc trigger it via `trigger-job.sh`. Remove the `disabled` line to resume.

### Pause ALL scheduled firings

Unload the LaunchAgent (the master scheduler):

```bash
launchctl unload ~/Library/LaunchAgents/com.<username>.claude-scheduler.plist
```

No jobs will fire on cron. Ad-hoc `trigger-job.sh` still works (it doesn't require the scheduler). To resume: `launchctl load -w …`.

### Change a job's cadence

Edit the `cron:` field in frontmatter. Common patterns:

| Natural language | Cron |
|---|---|
| Every minute | `* * * * *` |
| Every 5 minutes | `*/5 * * * *` |
| Every 30 minutes | `*/30 * * * *` |
| Every hour on the hour | `0 * * * *` |
| Every 2 hours | `0 */2 * * *` |
| Every day at 09:00 UTC | `0 9 * * *` |
| Every 2 days at 09:00 UTC | `0 9 */2 * *` |
| Every Monday at 14:00 UTC | `0 14 * * 1` |
| Every weekday at 08:30 UTC | `30 8 * * 1-5` |
| First of every month at midnight UTC | `0 0 1 * *` |

Note: times are UTC because `launchd` and `date -u` are UTC. Convert from local if needed.

### Change model or budget

Edit `model:`, `max_turns:`, `max_budget_usd:`, or `effort:` in frontmatter. Effective on next tick.

### Change cost behavior (for jobs that need less tool surface)

- Add `setting_sources: ""` to skip plugin/settings surface (~30% cache-creation reduction)
- Add `strict_mcp_config: true` to skip the MCP surface entirely (largest single reduction, ~80%)
- Combine both for jobs that just need claude to respond (~$0.04/run on Haiku)

### Add or change semantic hooks

Edit the `semantic_hooks:` list in frontmatter. Agents reading `.manifest.json` at session start will see the updated hooks within 60 seconds.

### Rename a job

```bash
mv ~/.claude/scheduled-jobs/<old>.md ~/.claude/scheduled-jobs/<new>.md
rm -f ~/.claude/scheduled-jobs/.state/<old>.*
# Optionally archive/remove old logs:
rm -f ~/.claude/scheduled-jobs/<old>-*.log
```

Also update the `name:` field inside the frontmatter if set, otherwise the filename stem is authoritative.

## Concurrency and debouncing

### Concurrent-run protection (automatic)

If a job is already running and another invocation fires (cron + ad-hoc collide, rapid repeated triggers, etc.), the new invocation **noops** with a tombstone:

```
stage=concurrent_skip holder_pid=12345
--- noop_skip: concurrent run in progress (PID 12345) ===
--- exit_code=0 ===
```

Implementation: `mkdir` on a state directory at `~/.claude/scheduled-jobs/.state/<name>.lock.d`. The PID of the current holder is stored inside; if the holder process dies without cleanup, a later invocation reclaims the lock.

This is always on — no frontmatter field. The design avoids the surprise of multiple concurrent claude-p processes running the same job, which would be billed twice and could produce duplicate side effects.

### Debouncing rapid re-triggers

Add `debounce_seconds: N` to frontmatter. If a new invocation fires within N seconds of this job's last START time, it noops:

```yaml
---
name: noisy-triggered-job
debounce_seconds: 60      # ignore re-fires within 60s of last start
---
```

Useful when an external trigger (e.g., file-system watcher) fires in bursts and you only want to act once per burst.

### What if I want queueing instead of noop?

Not implemented. If a job is busy, subsequent triggers are dropped, not queued. Adding a queue would require a separate runner loop and adds nontrivial complexity; most use cases are better served by idempotent jobs that don't care if a trigger is dropped. Revisit if you have a real case.

## External triggers (fire on events, not just cron)

A job can fire in response to external events — new files in a directory, a specific app starting, a watched file changing, a shell command succeeding. This is how you wire "do X when Y happens" into the scheduler without running a separate daemon.

Add an `external_triggers:` list to frontmatter. Each trigger is a flow-style object with a `type` and type-specific parameters. All triggers are evaluated every 60 seconds (alongside cron) by `scheduler.py`. If any trigger fires, the job is dispatched with Runtime Context `Trigger: external`.

### Supported trigger types

#### `file_added` — burst-aware new-file detector

```yaml
external_triggers:
  - {type: file_added, path: ~/Downloads, glob: "*.pdf", quiet_seconds: 30}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `path` | yes | — | Directory to watch. `~` expanded. Non-recursive. |
| `glob` | no | `*` | Shell-style pattern applied to filenames (not paths). |
| `quiet_seconds` | no | `30` | After new files appear, wait this long with no further additions before firing. Set to `0` to fire immediately on any new file. |

**Semantics:** Fires **once per burst** of new files. A burst is any series of new-file events followed by `quiet_seconds` of no new matching files. Downloading 10 PDFs in 5 seconds fires once, not ten times.

**Bootstrap:** on first evaluation (no state file), the current directory contents are recorded as the baseline. Only files added *after* bootstrap can trigger the job — installing a trigger does not fire on pre-existing files.

**Re-adding a deleted file re-fires.** The evaluator drops filenames that are no longer present from the seen set, so a re-created file counts as a new addition.

#### `file_changed` — mtime-based change detector

```yaml
external_triggers:
  - {type: file_changed, path: ~/Documents/inbox.md}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `path` | yes | — | File to watch. `~` expanded. |

**Semantics:** Fires every time the file's mtime moves forward since the last evaluation.

**Bootstrap:** on first evaluation, the current mtime is recorded; the trigger does not fire.

#### `process_starts` — edge-triggered process detector

```yaml
external_triggers:
  - {type: process_starts, match: Obsidian}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `match` | yes | — | Case-insensitive substring of the full command line. Under the hood: `pgrep -if <match>`. |

**Semantics:** Fires on the **not-running → running** transition only. If the matched process is already running when the trigger is installed, it does NOT fire — it waits for the process to stop and then start.

Use `match: "Obsidian.app"` to target the specific app bundle path if you need to disambiguate from unrelated processes named similarly.

#### `command_succeeds` — edge-triggered shell command

```yaml
external_triggers:
  - {type: command_succeeds, run: "test -f /tmp/ready.flag"}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `run` | yes | — | Shell command. Runs under `zsh -lc` with `~/.local/bin:~/bin:$PATH`. Stdout/stderr discarded. |

**Semantics:** Fires on the **non-zero-exit → zero-exit** transition only. While the command keeps succeeding on every tick, no additional fires happen.

Use this as an escape hatch for anything the built-in trigger types don't cover: HTTP checks via `curl -sf`, custom monitoring scripts, API probes. The command runs in the same login-shell environment as jobs themselves, so user-installed CLIs resolve identically.

### Interactions with other behaviors

- **Minute-level dedup:** if external triggers fire a job, the cron evaluator for the same job is skipped in that minute. No double-fire.
- **Concurrent-run guard:** if a job is still running when a trigger fires, the new invocation noops as usual (logged as `concurrent_skip`).
- **Debounce:** stacks on top of triggers. A burst-firing trigger + `debounce_seconds: 300` means "fire at most once per 5 minutes regardless of burst frequency."
- **`disabled: true`:** skips all firing, including external triggers.

### Per-trigger state files

Each trigger's state lives at `~/.claude/scheduled-jobs/.state/<job>.trigger-<index>.json` (index is the position in the `external_triggers` list, starting at 0). Deleting the state file re-bootstraps that trigger on the next tick — useful if you want to reset it.

Trigger evaluation errors (missing path, invalid config) are logged to `~/.claude/scheduled-jobs/.scheduler-stderr.log` and do not block other triggers or other jobs.

### Ad-hoc delegation via external triggers vs. semantic_hooks

- **`semantic_hooks`** are natural-language conditions for *other agent sessions* to read the manifest and decide to ad-hoc fire a job. Evaluated by an LLM based on user intent.
- **`external_triggers`** are concrete deterministic conditions evaluated by `scheduler.py` every minute. No LLM involvement, zero token cost for evaluation.

The two are complementary. A job can have both.

## Behavior when the machine is off or sleeping

launchd with `StartInterval=60` **does not** attempt to catch up missed intervals. If the machine is off or asleep for a day:

- No ticks fire while the machine is off.
- When the machine wakes, launchd schedules the next tick from wake time (approximately a minute later).
- On that tick, `scheduler.py` evaluates each job's cron against the current minute only. Missed scheduled slots are **not** fired retroactively.

Example: heartbeat cron `0 * * * *`. Machine is off 23 hours, wakes at `15:47`. Scheduler first ticks around `15:48`; cron doesn't match (minute 48 ≠ 0). Heartbeat next runs at `16:00` — exactly one invocation for the `16:00` slot, not 23 catch-up invocations for all the missed hours.

This is the intended design. It trades retroactive execution for predictability: scheduled jobs are alarms for specific wall-clock moments, not a queue of deferred work. If you need "run at least once per day even if the machine missed the slot," encode that in the job itself (e.g., check a last-run timestamp in durable state and no-op if already run today).

## Diagnosing failures

1. **Nothing fires at all.**
   - `launchctl list | grep claude-scheduler` — is it loaded? Is exit code `0`?
   - `tail ~/.claude/scheduled-jobs/.scheduler-stderr.log` — Python errors?
   - `/usr/bin/python3 ~/.claude/scheduled-jobs/scheduler.py --list` — does discovery work at all?

2. **Job fires but produces no log file.**
   - This shouldn't happen — `run-job.sh` creates the log before any preflight. If you see this, the script itself failed to start. Check `.scheduler-stderr.log` and re-check `chmod +x` on `run-job.sh`.

3. **Log exists but claims `preflight_fail`.**
   - Read the tombstone: it states the reason (missing prompt, claude CLI not on PATH, cwd unreachable).
   - PATH issues: user's `claude` probably lives somewhere not in the default launchd PATH. Add its directory to the PATH export near the top of `run-job.sh`.

4. **Claude ran but exited non-zero.**
   - Inspect the JSON envelope in the log — `claude -p --output-format json` reports its own errors. Common causes: budget exhausted (`max_turns`/`max_budget_usd` hit), MCP auth expired, permission denial despite the bypass flag.

5. **Job completes but the work it was supposed to do didn't happen.**
   - Check the `result` field in the JSON envelope. Did it attempt the tool call? If it reported a tool as "unavailable," re-read the prompt — it may need to be more explicit about attempting calls regardless of tool-surface enumeration.

6. **Double-fire in a single minute.**
   - Shouldn't happen — last-run guard prevents it. If you see two logs with timestamps in the same minute, the guard file wasn't writable. Check `~/.claude/scheduled-jobs/.state/` permissions.

## Other agents using this system

Other agent sessions (interactive Claude Code, different long-running sessions, etc.) can delegate work to purpose-built jobs via semantic hooks:

1. At session start, read `~/.claude/scheduled-jobs/.manifest.json`.
2. Compare each job's `semantic_hooks` against the current task.
3. If a hook matches, run the job's `trigger_command` and let it log asynchronously rather than reinventing the work inline.

### Making agents aware of this system at session start (no CLAUDE.md pollution)

The cleanest way to advertise scheduled-job hooks to every agent session without adding content to `~/.claude/CLAUDE.md` (which some users rewrite regularly) is a **SessionStart hook** in `~/.claude/settings.json`. The hook runs a shell script whose stdout is injected into the agent's context at session start.

The installer registers a hook script at `~/.claude/hooks/scheduled-jobs-notice.sh` and adds it to `~/.claude/settings.json`. The registered entry looks like:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          { "type": "command", "command": "bash /Users/<username>/.claude/hooks/scheduled-jobs-notice.sh" }
        ]
      }
    ]
  }
}
```

The notice script silently no-ops if the scheduled-jobs system isn't installed, so it's safe to ship in a portable `settings.json`. It counts jobs from the manifest and emits a compact `<scheduled-jobs-system>` block telling the agent where to look.

Since `settings.json` is separate from `CLAUDE.md`, it survives CLAUDE.md rewrites.

### Concurrency protection is automatic

If an agent ad-hoc-triggers a job that's already running, the second invocation noops (logged as `concurrent_skip`). No coordination is needed on the calling side — it's safe to call `trigger-job.sh <name>` from anywhere at any time.

## Portability and security notes

- The system assumes macOS + launchd. Linux equivalent would swap the LaunchAgent for a systemd user unit with `OnCalendar=` or a user crontab; `scheduler.py` and `run-job.sh` port as-is.
- `--dangerously-skip-permissions` is set because scheduled jobs can't answer permission prompts. Only enable this on a machine where the account is trusted and the jobs are authored by the account owner.
- Secrets: don't put credentials in job prompts. Use the MCP surface (which the user has already authenticated for their interactive sessions) or environment variables set in the LaunchAgent plist's `EnvironmentVariables`.
- Logs can accumulate sensitive output (MCP responses, tool results). The rotation cap is 100 per job; consider a lower cap or a sanitizing wrapper for jobs that touch sensitive data.
