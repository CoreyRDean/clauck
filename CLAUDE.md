# clauck — Agent Instructions

> **This file is for agents.** If you're a human, read [README.md](README.md) instead.
> If you're an agent that landed here from a web search or user request, this is your primary reference.

> **Before making architectural decisions or proposing changes, read [INTENT.md](INTENT.md).** It is the intent contract for clauck — identity, non-negotiables, architectural properties, decision filter, scope boundaries, chosen policies. This file (CLAUDE.md) is the operational playbook; `INTENT.md` is the authority the playbook serves.

## What is clauck?

**clauck is a local agent runtime for macOS.** It is the substrate that agent workflows execute on — the way Node.js is a runtime for JavaScript or Docker is a runtime for containers. The runtime accepts intent, compiles it to durable Markdown jobs, executes with full user-level trust, observes execution, persists state across runs, and orchestrates dependencies (cron schedules, event triggers, DAG pipelines). See `INTENT.md §1` for the full six-primitive definition.

**Repo:** https://github.com/CoreyRDean/clauck
**Install:** `curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash`

## Harness compatibility

There are two independent axes here, often confused. `INTENT.md §6` covers both.

**Axis 1 — which harness runs *clauck jobs*.** At v1, Claude CLI (`claude -p`) is the only supported job runner. Alternative runners (Codex, Cursor, Aider via a per-job `harness:` field) are **deferred** — consistent with the contract, not prioritized, revisited when a concrete second-harness need exists. Not a promise; not a rejection.

**Axis 2 — which harness an *agent* is running in when they interact with clauck.** This is unrelated to Axis 1. Any harness that can speak MCP (via `clauck mcp`) or shell out to the CLI can drive clauck. This is supported now and is a stable interface per `INTENT.md §3` non-negotiable #8.

| Harness | Can agents in this harness drive clauck? (Axis 2) |
|---|---|
| **Claude Code CLI** | Yes. Full support. Primary interaction surface. |
| Claude Desktop (Chat) | Partial. Can answer questions, browse marketplace, contribute to repo. Cannot fire jobs without Bash-capable context. |
| Claude Desktop (CoWork) | Partial. Can install via Bash, modify job files. Cannot establish a persistent scheduler on the user's Mac. |
| Claude Code (Cloud) | No. Lacks local filesystem and launchd access. |
| Codex, Cursor, Aider, any MCP-capable agent | Yes once `clauck mcp` (#34) is stable. Today, only via CLI shell-out. |

If you're running in a non-CLI harness: be upfront with the user about what you can and can't do. Satisfy their intent as far as the harness allows. Point them to the CLI for full functionality.

## If a user asks you to install clauck

### Claude Code (CLI) — one command

1. **Verify you're in a Claude Code CLI session** (not Desktop, not Cloud). If not, see the Desktop flow below.
2. Run: `curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash`
3. The installer handles everything: runtime placement, LaunchAgent, job marketplace cache, heartbeat verification, **AND** registers the clauck plugin with Claude Code (`claude plugin marketplace add CoreyRDean/clauck` + `claude plugin install clauck@clauck --scope user`). The plugin delivers the skill (`/clauck:clauck`), the SessionStart hook, and the MCP server.
4. After install, invoke the skill in any CC session: `/clauck:clauck` — it's the full operational playbook.
5. Browse the job marketplace: `cat ~/.claude/skills/clauck/marketplace/index.json | python3 -m json.tool`
6. Help the user pick and customize jobs, or design new ones from their intent.

### Claude Desktop — manual plugin setup

Desktop has no `/plugin` CLI, so install has two steps:

1. User runs the install.sh above to place the runtime (scheduler, LaunchAgent, `~/.local/bin/clauck`). This is a no-op for the plugin side on Desktop — only the runtime lands.
2. User follows `docs/desktop-plugin-setup.md` to add the marketplace and install the plugin via Desktop's Customize → Personal plugins UI (12 steps). The plugin's SessionStart hook then self-heals any version drift on subsequent sessions.

Point users at `docs/desktop-plugin-setup.md` for the step-by-step.

### How the two sides stay in sync

- Plugin and runtime versions are coupled via the same `VERSION` file in this repo, so release tags produce matched plugin+runtime versions.
- Runtime update (user re-runs install.sh) → install.sh detects plugin version drift and runs `claude plugin update clauck`.
- Plugin update (CC auto-fetches from marketplace) → SessionStart hook detects runtime drift on next session and backgrounds `install.sh` via `nohup`.
- Either direction converges; both no-op if already in sync.

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
   /usr/bin/python3 -c "import ast; ast.parse(open('lib/clauck').read())"
   /usr/bin/python3 -c "import ast; ast.parse(open('lib/sizing.py').read())"
   /usr/bin/python3 -c "import json; json.load(open('marketplace/index.json'))"
   claude plugin validate ./plugins/clauck
   claude plugin validate ./.claude-plugin/marketplace.json
   bash -n plugins/clauck/hooks/sessionstart.sh
   bash install.sh --dry-run --yes
   ```

### Key paths (installed)

| What | Where |
|---|---|
| Runtime | `~/.clauck/{scheduler.py,run-job.sh,trigger-job.sh,update-check.sh,dag-runner.py,clauck-mcp}` |
| Jobs | `~/.clauck/*.md` |
| Logs | `~/.clauck/<name>-<ts>-<pid>.log` |
| DAG logs | `~/.clauck/<root>-dag-<ts>-<pid>.log` |
| Manifest | `~/.clauck/.manifest.json` |
| State | `~/.clauck/.state/` |
| Config | `~/.clauck/.clauck.config.json` |
| Version | `~/.clauck/.version` |
| Build source | `~/.clauck/.build-source` (channel, source, git SHA) |
| Plugin source (in repo) | `plugins/clauck/` — manifest, skill, hooks, `.mcp.json` |
| Plugin (installed by CC) | managed by `claude plugin install`; path is CC-internal |
| Skill | `plugins/clauck/skills/clauck/SKILL.md` (source); delivered to CC via the plugin, loaded on demand as `/clauck:clauck` |
| SessionStart hook | `plugins/clauck/hooks/sessionstart.sh` (source); delivered via the plugin |
| Job marketplace | `~/.claude/skills/clauck/marketplace/` (pre-made job catalog — separate from the Claude plugin marketplace) |
| CLI | `~/.local/bin/clauck` |
| LaunchAgent | `~/Library/LaunchAgents/com.$USER.claude-scheduler.plist` |
| Global prompt | `~/.clauck/prompt.md` |

### Cost policy

Cost is a first-class transparent policy per `INTENT.md §3` non-negotiable #4 and §4 architectural property "Cost transparency." Every sizing decision — doctor invocations, scheduled job firings, natural-language-created jobs — flows through a single formula in `lib/sizing.py`. Knobs live in `~/.clauck/.clauck.config.json` under the `doctor` key; view/edit via `clauck config doctor`.

**The complexity scale (0.0–1.0)** is the canonical way to declare a job's sizing. `lib/sizing.py` maps scale → `(model, effort, max_turns, max_budget_usd)` at run time via a banded lookup table (SCALE_PARAMS) and a context-growth-aware budget formula. Inspect what any scale derives with `clauck size <scale>`.

**Per-field overrides** — if frontmatter includes `complexity: X` plus one or more of `max_turns` / `max_budget_usd` / `effort` / `model`, each explicit value wins over its derived counterpart for that field only. Use only when pinning a specific value is genuinely required; don't duplicate what the formula would derive.

**Legacy compat** — jobs without `complexity:` continue to use explicit `max_turns`/`max_budget_usd`/`effort`/`model` fields, falling back to LEGACY_DEFAULTS (50 turns, $2.00, high effort, default model) if none are set. No existing job is forced to migrate.

**Auto-skew** — doctor tracks a `scale_skew` offset in config. When a doctor run hits its budget ceiling, the skew bumps (default +0.05, capped at +0.30); on clean runs it decays. Self-balancing safety net so the formula self-tunes to the user's real workloads without intervention.

**MCP auto-promote** — empirical hard rule: if the user's full MCP surface loads (frontmatter does NOT set `strict_mcp_config: true`, or doctor stage-2 which always loads MCP), haiku auto-promotes to sonnet. The MCP surface (~150k tokens of tool descriptions) regularly approaches haiku's effective working context and triggers compaction loops that burn budget without progress. The promotion is surfaced in the sizing explanation string and via `clauck size <scale>`'s `strict_mcp:` line. To run a job on haiku, either set `strict_mcp_config: true` in frontmatter (the job won't have MCP tools available) or accept the sonnet bump.

*Migration note:* installed jobs that previously derived haiku under MCP were silently truncating on the compaction loop; they now correctly route to sonnet. Per-run cost rises ~3–4× on those jobs, but runs actually complete. Jobs that explicitly strip MCP (`strict_mcp_config: true` in frontmatter) keep their prior haiku pricing unchanged.

**Source of truth** — `lib/sizing.py` is the single implementation. `scheduler.py` and the CLI import from it. Do not introduce parallel cost/sizing logic anywhere else; if you need a different curve, edit `SCALE_PARAMS` or add knobs, don't bypass.

### Frontmatter schema (complete)

```yaml
---
name: <string>                       # optional; defaults to filename stem
description: <string>                # one-line purpose
cron: "<m> <h> <dom> <mon> <dow>"    # 5-field cron; omit = ad-hoc only
complexity: <float>                  # 0.0–1.0 scale; derives the four sizing
                                     # fields below. Preferred over setting
                                     # them directly. See Cost policy above.
max_turns: <int>                     # default 50; override when set
max_budget_usd: <float>              # default 2.00; override when set
cwd: <path>                          # default ~
effort: <low|medium|high>            # default high; override when set
model: <alias-or-full-name>          # optional; e.g. "haiku", "sonnet". override when set
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

### Brand terminology

**"Cycle" / "Clauck Cycles"** is the marketing/brand name for a clauck job. The name echoes "clock cycles" — the right pronunciation cue for "clauck."

**Use "Cycle" in:** README landing copy, marketplace human-readable descriptions, release notes, external-facing docs. Example: "Install the morning-brief Cycle."

**Use "job" in:** CLI verbs (`clauck fire`, `clauck list`), code identifiers, frontmatter field names, MCP tool schemas, agent-facing contracts, error messages, and all technical documentation. Example: "the `name:` field", "the job fires at 9am."

The two terms name the same primitive. The distinction is register only — marketing vs. technical.
