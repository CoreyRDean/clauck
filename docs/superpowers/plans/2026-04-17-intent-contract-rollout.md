# INTENT Contract Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the newly-committed `INTENT.md` into the repo so it is discoverable by agents and humans, authoritative in architectural debates, and cited in PRs that affect the contract.

**Architecture:** Purely documentation edits. Five independent, atomic changes across four files. No code, no tests, no migrations. Each change is a self-contained commit so any subset can be reverted independently if reviewer taste diverges.

**Tech Stack:** Markdown. Git. No build, lint, or CI gates touched.

---

## File Structure

Files modified by this plan (no new files created):

| File | Responsibility | Why it changes |
|---|---|---|
| `CLAUDE.md` | Agent-facing operating instructions for this repo. Agents read this first. | Must reference `INTENT.md` as authority; must align identity framing with `INTENT.md §1`; must clarify harness-compatibility per `INTENT.md §6`'s two-axes model. |
| `README.md` | Human-facing entry point. Sets first-impression framing. | Currently leads with "Workflow automation powered by AI agents." Per `INTENT.md §1`, must lead with runtime identity. Must link `INTENT.md`. |
| `CONTRIBUTING.md` | Contributor expectations. | Needs a short "Design discipline" section pointing PR authors at `INTENT.md` and the decision filter. Light touch, not gatekeeping. |
| `.github/PULL_REQUEST_TEMPLATE.md` | Default PR body. | Needs one optional prompt asking authors to cite the primitive / non-negotiable / property their change serves, or flag it as a contract amendment. |

`INTENT.md` is already committed at repo root (`1a8d5ef`). This plan does not modify it.

---

## Scope check

Single cohesive rollout: "make `INTENT.md` load-bearing in repo workflow." Five tasks, all doc-only. Does not require decomposition into sub-plans.

---

## Task 1: Reference INTENT.md at the top of CLAUDE.md

**Files:**
- Modify: `CLAUDE.md:1-12`

- [ ] **Step 1: Read the current CLAUDE.md header**

Run: verify lines 1–12 match the expected pre-state.

Expected pre-state (lines 1–12):

```markdown
# clauck — Agent Instructions

> **This file is for agents.** If you're a human, read [README.md](README.md) instead.
> If you're an agent that landed here from a web search or user request, this is your primary reference.

## What is clauck?

clauck is a workflow automation system for macOS that runs `claude -p` sessions on cron schedules, event triggers, and producer/consumer pipelines. It uses launchd (macOS's native service manager) to tick every 60 seconds, evaluating cron expressions and external triggers, resolving DAG pipelines, and dispatching jobs.

**Repo:** https://github.com/CoreyRDean/clauck
**Install:** `curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash`
```

- [ ] **Step 2: Apply the edit**

Use the Edit tool with this exact `old_string`:

```markdown
# clauck — Agent Instructions

> **This file is for agents.** If you're a human, read [README.md](README.md) instead.
> If you're an agent that landed here from a web search or user request, this is your primary reference.

## What is clauck?

clauck is a workflow automation system for macOS that runs `claude -p` sessions on cron schedules, event triggers, and producer/consumer pipelines. It uses launchd (macOS's native service manager) to tick every 60 seconds, evaluating cron expressions and external triggers, resolving DAG pipelines, and dispatching jobs.

**Repo:** https://github.com/CoreyRDean/clauck
**Install:** `curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash`
```

And this exact `new_string`:

```markdown
# clauck — Agent Instructions

> **This file is for agents.** If you're a human, read [README.md](README.md) instead.
> If you're an agent that landed here from a web search or user request, this is your primary reference.

> **Before making architectural decisions or proposing changes, read [INTENT.md](INTENT.md).** It is the intent contract for clauck — identity, non-negotiables, architectural properties, decision filter, scope boundaries, chosen policies. This file (CLAUDE.md) is the operational playbook; `INTENT.md` is the authority the playbook serves.

## What is clauck?

**clauck is a local agent runtime for macOS.** It is the substrate that agent workflows execute on — the way Node.js is a runtime for JavaScript or Docker is a runtime for containers. The runtime accepts intent, compiles it to durable Markdown jobs, executes with full user-level trust, observes execution, persists state across runs, and orchestrates dependencies (cron schedules, event triggers, DAG pipelines). See `INTENT.md §1` for the full six-primitive definition.

**Repo:** https://github.com/CoreyRDean/clauck
**Install:** `curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash`
```

- [ ] **Step 3: Verify the edit**

Run: `head -20 CLAUDE.md`
Expected: the new header with the INTENT.md callout and runtime framing appears.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md — reference INTENT.md as authority, align identity framing

Agents read CLAUDE.md first; it must point them at INTENT.md before
architectural decisions. Also replaces the "workflow automation system"
framing with the "local agent runtime" identity per INTENT.md §1.

Cites: INTENT v1 §1 (Identity), §9 (Evolvability — contract-first authority).
EOF
)"
```

---

## Task 2: Update CLAUDE.md harness compatibility per INTENT.md §6

The current harness-compatibility table lumps "Codex, Cursor, Aider" under "Planned alternative harness support (per-job `harness:` field)." `INTENT.md §6` clarifies two independent axes: (a) agents-in-other-harnesses talking to clauck via MCP is supported now (via `clauck mcp`), (b) clauck running jobs on a non-Claude harness is deferred. The table should reflect this.

**Files:**
- Modify: `CLAUDE.md:13-25`

- [ ] **Step 1: Read the current harness section**

Run: verify lines 13–25 match the expected pre-state.

Expected pre-state (lines 13–25):

```markdown
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
```

- [ ] **Step 2: Apply the edit**

Use the Edit tool with this exact `old_string`:

```markdown
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
```

And this exact `new_string`:

```markdown
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
```

- [ ] **Step 3: Verify the edit**

Run: `grep -n "Axis 1" CLAUDE.md && grep -n "Axis 2" CLAUDE.md`
Expected: both lines present; no stray references to the old "Planned alternative harness support" phrasing.

Also run: `grep -n "Planned alternative harness" CLAUDE.md`
Expected: no output (0 matches).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md — separate two harness-compatibility axes per INTENT v1 §6

Axis 1 (which harness runs clauck jobs) — Claude CLI only at v1,
alternatives deferred.
Axis 2 (which harness agents are in when driving clauck) — any
MCP-capable or shell-capable harness, supported now.

Previous single table conflated the two, making roadmap (#34 clauck mcp)
look like it enables Codex-as-job-runner. It does not; that is a
separate, deferred axis.

Cites: INTENT v1 §6 (Scope boundaries — harness portability note).
EOF
)"
```

---

## Task 3: Rewrite README opener + "Why this exists" section

The current README leads with *"Workflow automation powered by AI agents."* Per `INTENT.md §1`, it should lead with runtime identity. Keep the rest of the README (job marketplace, pipelines, external triggers, temporal scheduling, etc.) unchanged — those are correct and work as progressive disclosure.

**Files:**
- Modify: `README.md:15-57`

- [ ] **Step 1: Read the current opener and "Why this exists" section**

Run: `sed -n '15,57p' README.md`

Expected pre-state (lines 15 through the end of the "Beyond what native scheduling can do" table, approximately line 80 — verify with `grep -n "Beyond what native scheduling can do" README.md` before editing):

```markdown
Workflow automation powered by AI agents. Schedule tasks, chain pipelines, react to events, and build automations that think — all from plain English.

> **Hey Claude, install clauck**
```

(followed by the quickstart block, the "What people build with clauck" table, and the "Why this exists" section)

- [ ] **Step 2: Apply the opener edit**

Use the Edit tool with this exact `old_string`:

```markdown
Workflow automation powered by AI agents. Schedule tasks, chain pipelines, react to events, and build automations that think — all from plain English.
```

And this exact `new_string`:

```markdown
**clauck is a local agent runtime for macOS.** Schedule agent work, react to events, chain pipelines, and build automations that think — all from plain English. Runs as you, on your Mac, with your permissions. No cloud. No sandbox. No permission-gated runtime.

The contract that governs this project lives in [INTENT.md](INTENT.md).
```

- [ ] **Step 3: Apply the "Why this exists" edit**

Use the Edit tool with this exact `old_string`:

```markdown
## Why this exists

Claude Code is powerful. But you have to be there to use it. **clauck** makes your agent work when you're not — on schedules, in response to events, through multi-step pipelines, and with memory that carries across runs.

It's the difference between a tool you use and an agent that works for you.
```

And this exact `new_string`:

```markdown
## Why this exists

Claude Code is powerful. But you have to be there to use it. **clauck** makes your agent work when you're not — on schedules, in response to events, through multi-step pipelines, and with memory that carries across runs.

It's the difference between a tool you use and an agent that works for you.

**The permission model is the wedge.** clauck runs as you, on your machine, with your permissions. Every competitor runs sandboxed. That's the reason clauck exists and the reason you'd pick it over alternatives. Logs over guardrails. Trust earned via inspectability — every execution logged, every state change visible, every intent traceable. If you don't understand `--dangerously-skip-permissions`, clauck is not for you. If you do, it's designed for you.
```

- [ ] **Step 4: Verify both edits**

Run: `grep -n "local agent runtime for macOS" README.md`
Expected: one match at the top of the README body (around line 15).

Run: `grep -n "permission model is the wedge" README.md`
Expected: one match in the "Why this exists" section.

Run: `grep -n "INTENT.md" README.md`
Expected: at least one match linking to `INTENT.md`.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: README — lead with runtime identity and permission model

Replaces the "workflow automation powered by AI agents" opener with
the runtime-first identity from INTENT.md §1. Adds a "permission model
is the wedge" paragraph to "Why this exists" — the market positioning
that distinguishes clauck from Cowork (sandboxed) and Routines (cloud).

Links INTENT.md at the top so new contributors and agents discover
the contract immediately.

Cites: INTENT v1 §1 (Identity), §2 (Operators — target user), §3 #1 (Local
sovereignty), §3 #2 (Inspectability over restriction).
EOF
)"
```

---

## Task 4: Add "Design discipline" section to CONTRIBUTING.md

**Files:**
- Modify: `CONTRIBUTING.md` — insert a new section between "Quick links" and "Development setup"

- [ ] **Step 1: Read CONTRIBUTING.md to locate the insertion point**

Run: `grep -n "^## " CONTRIBUTING.md`
Expected: the section headers including `## Quick links` and `## Development setup`.

Expected pre-state around the insertion point:

```markdown
## Quick links

- [Open an issue](https://github.com/CoreyRDean/clauck/issues/new/choose) for bugs, feature requests, or questions.
- [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
- [Marketplace contribution guide](#adding-a-job-to-the-marketplace) below for submitting pre-made jobs.

## Development setup
```

- [ ] **Step 2: Apply the edit**

Use the Edit tool with this exact `old_string`:

```markdown
## Quick links

- [Open an issue](https://github.com/CoreyRDean/clauck/issues/new/choose) for bugs, feature requests, or questions.
- [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
- [Marketplace contribution guide](#adding-a-job-to-the-marketplace) below for submitting pre-made jobs.

## Development setup
```

And this exact `new_string`:

```markdown
## Quick links

- [Open an issue](https://github.com/CoreyRDean/clauck/issues/new/choose) for bugs, feature requests, or questions.
- [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
- [Marketplace contribution guide](#adding-a-job-to-the-marketplace) below for submitting pre-made jobs.

## Design discipline

Before proposing a non-trivial change, read [INTENT.md](INTENT.md). It defines what clauck is, what it's not, and the decision filter every new capability should pass:

1. **Does this require a local agent runtime, or could it run in a sandbox?** If it could run in a sandbox, it probably belongs somewhere else.
2. **Does this serve one of the six runtime primitives?** (Accept intent, compile, execute, observe, persist, orchestrate.)
3. **Does this preserve the non-negotiables and architectural properties?**

PRs that change runtime behavior in ways inconsistent with the contract must either reshape to fit or amend the contract first (see `INTENT.md §8`). Non-trivial PR descriptions should cite which primitive, non-negotiable, or property the change serves — reviewers check this.

Simple bug fixes, marketplace jobs, docs corrections, and typo fixes do not require a citation. Architectural changes do.

## Development setup
```

- [ ] **Step 3: Verify the edit**

Run: `grep -n "Design discipline" CONTRIBUTING.md`
Expected: one match at the new section header.

Run: `grep -n "decision filter" CONTRIBUTING.md`
Expected: one match inside the new section.

- [ ] **Step 4: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "$(cat <<'EOF'
docs: CONTRIBUTING — add Design discipline section referencing INTENT.md

Points new contributors at the intent contract before architectural
work. Names the three-question decision filter inline so the barrier
to reading it is low. Explicitly exempts simple bug fixes, marketplace
jobs, and docs from requiring citations — only architectural changes
need them.

Cites: INTENT v1 §5 (Decision filter), §8 (Evolution — review discipline).
EOF
)"
```

---

## Task 5: Add contract citation prompt to PR template

**Files:**
- Modify: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Read the current PR template**

Run: `cat .github/PULL_REQUEST_TEMPLATE.md`

Expected pre-state (full file content):

```markdown
## What changed and why

<!-- Brief description of the change. Link to an issue if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Marketplace job (new or updated)
- [ ] Documentation
- [ ] Refactoring (no behavior change)

## Checklist

- [ ] `bash -n install.sh && bash -n uninstall.sh` passes
- [ ] `python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())"` passes
- [ ] Tested `install.sh` on a clean-ish environment (or `--dry-run`)
- [ ] No secrets, personal paths, or API keys committed
```

- [ ] **Step 2: Apply the edit**

Use the Edit tool with this exact `old_string`:

```markdown
## What changed and why

<!-- Brief description of the change. Link to an issue if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Marketplace job (new or updated)
- [ ] Documentation
- [ ] Refactoring (no behavior change)
```

And this exact `new_string`:

```markdown
## What changed and why

<!-- Brief description of the change. Link to an issue if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Marketplace job (new or updated)
- [ ] Documentation
- [ ] Refactoring (no behavior change)
- [ ] INTENT.md amendment (contract change)

## Intent contract alignment

<!--
Optional but recommended for architectural changes. Cite which part of
INTENT.md this change serves:

- Primitive served: accept / compile / execute / observe / persist / orchestrate
- Non-negotiable preserved (or explicitly amended): §3 #N
- Architectural property extended: composability / self-observation / intent-as-artifact
- Decision filter pass: questions 1, 2, 3

Skip this section for simple bug fixes, marketplace jobs, docs, and typo fixes.
-->
```

- [ ] **Step 3: Verify the edit**

Run: `grep -n "INTENT.md amendment" .github/PULL_REQUEST_TEMPLATE.md`
Expected: one match in the "Type of change" block.

Run: `grep -n "Intent contract alignment" .github/PULL_REQUEST_TEMPLATE.md`
Expected: one match as a new section header.

- [ ] **Step 4: Commit**

```bash
git add .github/PULL_REQUEST_TEMPLATE.md
git commit -m "$(cat <<'EOF'
docs: PR template — add optional INTENT contract alignment section

Adds an "INTENT.md amendment" check under "Type of change" so explicit
contract changes are flagged, and a new optional "Intent contract
alignment" section prompting citations for architectural PRs.

Explicitly scoped as optional, with guidance to skip for simple bug
fixes, marketplace jobs, docs, and typo fixes — keeps overhead low.

Cites: INTENT v1 §8 (Evolution — review discipline, amending process).
EOF
)"
```

---

## Self-review notes

**Spec coverage:** The rollout targets five concrete touchpoints surfaced during brainstorming (CLAUDE.md identity + cross-link, CLAUDE.md harness clarification, README opener + permission-model wedge, CONTRIBUTING.md design discipline, PR template citation prompt). No remaining rollout gaps.

**Placeholder scan:** Each task contains complete `old_string` / `new_string` content, exact grep verifications, and complete commit messages. No TBDs.

**Type consistency:** Not applicable — docs only. Cross-document references all point to `INTENT.md` (one canonical location) with section numbers consistent with the committed `INTENT.md v1`.

**Not in scope:**

- Issue grooming (reviewing open issues against the contract) is a separate, higher-judgment activity — worth doing as a follow-up session but not a doc-edit task.
- Bumping `INTENT.md` to `v2` for rollout wording tweaks — this plan does not amend the contract.
- Updating `skill/` or `~/.claude/skills/clauck/SKILL.md` templates — the skill is user-installable and regenerated from `skill/` on install; leave alone unless a contract-level statement belongs there.
