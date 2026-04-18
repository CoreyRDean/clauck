# INTENT

**Version:** v2
**Status:** Adopted
**Scope:** Binds the `CoreyRDean/clauck` upstream repository. Revised only by PR amending this file.

This document is the intent contract for clauck. It is the first thing to consult when proposing a change, reviewing a PR, or deciding whether something belongs in clauck at all. When this contract conflicts with other documentation, this contract wins until it is amended.

---

## 1. Identity

**clauck is a local agent runtime for macOS.**

It is the substrate that agent workflows execute on — the way Node.js is a runtime for JavaScript or Docker is a runtime for containers. Everything else — the scheduler, the CLI, the marketplace, the semantic interpreter, the doctor — is a layer on the runtime.

The runtime does six things:

1. **Accepts intent** — from English, from YAML, from the marketplace, from agents.
2. **Compiles intent to durable work** — file-backed Markdown jobs as source of truth.
3. **Executes with full user-level trust** — no sandbox, no permission gate, no cloud.
4. **Observes execution** — logs, manifest, oplog, dispatch log, state.
5. **Persists state across executions** — session persistence, durable state files, cross-run memory.
6. **Orchestrates dependencies** — DAGs, pipelines, consumers, temporal gates, external triggers, events.

Every capability in clauck must serve one of these six primitives. Capabilities that don't either belong in a layer above, or not at all.

---

## 2. Operators

clauck serves two kinds of operator in equal standing.

### The human operator

A technical user who:

- Understands `--dangerously-skip-permissions` and chooses it deliberately
- Values logs over guardrails
- Would rather fork than wait for upstream to fix something
- Already runs multiple agent sessions and wants them to coordinate
- Measures agent work in cost and outcomes, not turn counts

clauck is **not** designed for users who want a GUI, need cloud execution, want someone else to manage security, or don't know what launchd is. This exclusion is calibration, not gatekeeping — every feature that tries to serve both this user and a sandboxed-agent user under-serves both.

### The agent operator

A first-class operator alongside the human. The canonical first interaction is *"Hey Claude, install clauck."* Agents install, configure, author, fire, inspect, pause, resume, compose, and report through the same surfaces humans use.

Every agent-facing surface — the skill file, the SessionStart hook, the semantic CLI fallthrough, `clauck mcp`, the frontmatter schema, the marketplace package format — is a **protocol**. Versioned, deprecated with lifecycle, never broken silently. Third parties can build agents, libraries, and tools against these interfaces with the same stability guarantees as the human-facing CLI.

Humans drive through agents more often than through files. The contract honors that.

---

## 3. Non-negotiables

These are decided. When they conflict with feature requests, the non-negotiables win. When they conflict with each other, the debate is explicit and visible, not buried.

| # | Non-negotiable | What it means | What it rules out |
|---|---|---|---|
| 1 | **Local sovereignty** | Runs as the user, on the user's machine, with the user's permissions. | Cloud execution, remote agents, sandboxed VMs, permission-gated runtimes. |
| 2 | **Inspectability over restriction** | Every execution is logged. Every state change is visible. Every intent is traceable. | Opaque execution paths, silent failures, untracked mutations. |
| 3 | **Minimal dependencies** | `/usr/bin/python3` and `/bin/zsh` at runtime. Nothing else. | pip installs, homebrew requirements, compiled binaries, language runtimes. Install-time tools (git, xcode CLT) and dev-time tools (gh, shellcheck) are outside this constraint. |
| 4 | **Cost as first-class surface** | Every job declares budget. Every run logs cost. Every feature quantifies cost impact. | Hidden costs, unbudgeted agent execution, cost surprises. |
| 5 | **Backward compatibility** | Jobs written for version N work on version N+1 without edits. | Breaking frontmatter changes, silent semantic shifts, required migrations. |
| 6 | **Trust via proof** | Every install verifies. Every update is opt-in. Every action is auditable. | Trust-us patterns, magic updates, hidden mutations, telemetry. |
| 7 | **File-backed source of truth** | Jobs are Markdown files. State is text files. Logs are plaintext. | Databases as authoritative state, binary formats, opaque serialization. |
| 8 | **Extensibility via stable interfaces** | Frontmatter schema, CLI surface, MCP tool surface, marketplace package format, semantic hooks, and event names are versioned and subject to the deprecation lifecycle. | Silent interface churn, undocumented surfaces that third parties depend on, breaking changes without deprecation windows. |
| 9 | **Evolvability** | This contract is revised by explicit PR amending this file. | Silent drift. Features that violate the contract without first revising it. |

---

## 4. Architectural properties

Four properties emerge from the primitives. Naming them makes them checkable — a PR can be evaluated against whether it preserves or extends these, not only against whether it serves a primitive.

### Composability

Every primitive composes with every other. DAGs compose jobs. The oplog composes observation across a pipeline. The event bus composes reaction. The marketplace composes packages via dependency resolution. New primitives must compose with existing ones, not replace them. **A feature that requires disabling another primitive to work is a failed design.**

### Self-observation feeds back

`clauck doctor` inspects the runtime. `clauck report` mines user intent into structured issues. Autonomous issue reporting lets jobs, doctor, and utility agents compose draft tickets when they notice problems. The system watches itself and turns findings into durable artifacts — logs, reports, issues, ideas. This is not a nice-to-have; it is a distinguishing property. A runtime that cannot observe and describe its own failures is opaque in a way that violates non-negotiable #2.

### Intent as first-class artifact

Every job carries traceable provenance — a `source:` block tracking where the intent came from (human, agent, marketplace, autogenerated). The oplog preserves the chain: who ran, what they produced, in what order. Drift between expressed intent and executing job is a bug, not a feature. `clauck history` / `clauck trace <invocation-id>` promotes this from convention to primitive.

### Cost transparency

Non-negotiable #4 says cost is a first-class surface. This property specifies *how*. Every Claude session clauck runs — doctor invocations, scheduled jobs (flat, module-anchor, module-stage), marketplace-installed jobs — derives its sizing (`model`, `effort`, `max_turns`, `max_budget_usd`) from a single shared formula keyed on a declared **complexity scale**, not from ad-hoc guessing at each site. The formula is visible in one file (`lib/sizing.py`), configurable per-user (`~/.clauck/.clauck.config.json` under `doctor`), introspectable by humans and agents (`clauck size <scale>`, `clauck inspect <job>`), and self-correcting (doctor bumps `scale_skew` on budget truncation, decays on clean runs). Clamps are visibly surfaced, not silent. A feature that does its own sizing math outside this pipeline, hides cost from the user, or sets a budget the user cannot audit violates this property. Parallel cost/sizing logic anywhere else in the codebase is a red flag — either the formula is wrong (fix the formula) or the feature shouldn't exist.

**Scope of compliance at v2 adoption**: doctor, scheduler, CLI surfaces (`clauck size`, `clauck validate`, `clauck inspect`), and all marketplace jobs are fully compliant. The natural-language semantic interpreter (`clauck <anything>`, `clauck work <text>`) still emits its own stage-2 execution params directly — a known compliance gap tracked for follow-up. Job-creation guidance inside the semantic path already directs Claude to emit `complexity:` in any new job frontmatter, so the gap is only at the interpreter's own stage-2 sizing, not in the jobs it creates. This does not retroactively reshape the property — the claim above stands for all sites named in it — but the semantic path must be migrated before v3.

---

## 5. Decision filter

For every proposed capability, apply these three questions in order:

**1. Does this require a local agent runtime, or could it run in a sandbox?**

If it could run in a sandbox (Cowork, Routines, cloud tasks), it doesn't strengthen clauck's position. Build it only if the integration with the runtime adds value — not because the feature itself is useful.

**2. Does this serve one of the six runtime primitives?**

Accept intent, compile, execute, observe, persist, orchestrate. If the feature doesn't clearly map to one, it probably belongs in a layer above the runtime, or not in clauck at all.

**3. Does this preserve the non-negotiables and architectural properties?**

A feature that requires a new runtime dependency, cloud mediation, a hidden execution path, an unstable interface, or breaks composability is a red flag. Either the feature needs redesign, or the contract needs explicit revision first.

**Scoring:**

- Passes three: build it.
- Fails one: reshape it.
- Fails two: defer it.
- Fails three: reject it.

---

## 6. Scope boundaries

Some capabilities live **in the runtime**. Others live **in layers above** that consume the runtime. Others are **deferred**. Others are explicitly **out of scope**. Mixing these wastes design effort.

| Layer | What belongs here | Examples |
|---|---|---|
| **In the runtime** | Anything that serves one of the six primitives and passes the decision filter. | scheduler, dag-runner, external trigger evaluation, oplog, session persistence, `clauck mcp` stdio server, frontmatter schema, cost logging, doctor. |
| **In layers above** | Anything consuming the runtime's stable interfaces (CLI, MCP, frontmatter, marketplace format) to build higher experiences. Not clauck, but clauck commits to supporting them. | Third-party GUIs, menu-bar apps, web dashboards, mobile notifiers, IDE integrations, analytical tools over the oplog, **agents in any harness driving clauck via MCP**. |
| **Deferred (eventually, not now)** | Capabilities consistent with the contract but not prioritized. Not promises; not rejections. Revisited when concrete need exists. | Cross-harness execution (per-job `harness:` field for Codex, Cursor, Aider as **job runners**, not as clients). |
| **Out of scope — explicit non-goals** | Capabilities that violate a non-negotiable or belong to a different product in the ecosystem. | Cloud execution (Routines owns that), sandboxed agents (Cowork owns that), cross-platform support, GUI shipped with the runtime, non-technical user onboarding, telemetry, managed hosting. |

A capability that seems valuable but violates a non-negotiable is a signal that it belongs in a layer above (if consumable via stable interface) or in a different product (if not). It is not a signal to revise the non-negotiables.

**Note on harness portability.** Two independent axes: (a) agents in other harnesses talking to clauck via the MCP interface — that is in layers above, supported now. (b) clauck running jobs on a non-Claude harness — that is deferred. Exposing MCP does not enable (b); (b) requires a separate per-job `harness:` field and multi-harness execution plumbing, and is not a priority at the cost of shipping functionality.

---

## 7. Chosen policies

Where earlier design docs leave decisions open, these are the settled answers. Implemented reality, written down.

| Policy | Setting |
|---|---|
| **Concurrency** | Parallel execution with per-provenance locks. Jobs run concurrently; DAG pipelines and same-lineage runs serialize via lock files. Not Serial. Not unbounded parallel. |
| **Cost** | Declare + derive + log. Jobs declare a **complexity scale** (`complexity: 0.0–1.0`) in frontmatter; the shared formula in `lib/sizing.py` derives `model`/`effort`/`max_turns`/`max_budget_usd` at run time. Explicit fields are accepted as per-field overrides for legacy jobs and intentional pins. Harness enforces the derived budget. Cost is logged per run. Doctor auto-skews on truncation. No mid-run throttling, no multi-threshold escalation policy. |
| **Platform** | macOS only. Cross-platform is an explicit non-goal. launchd, zsh, `/usr/bin/python3`, BSD utilities may be assumed. A Linux port is a fork, not a port. |
| **UI** | CLI only, from the runtime. Runtime provides no graphical surface. Third parties may build GUIs on top of the stable CLI + MCP + frontmatter interfaces — those layers are not clauck. |
| **Execution harness** | Claude CLI (`claude -p`) is the only supported job runner at v1. Alternative harnesses are deferred, not rejected. |
| **Marketplace role** | First-class distribution channel. Package-manager semantics (install, version, depend, compose, third-party sources) are committed direction. **No commerce** — paid packages, monetization, and revenue sharing are explicit non-goals. |
| **API stability** | Frontmatter, CLI, MCP tool surface, marketplace package format, skill file, SessionStart hook output follow the deprecation lifecycle: notice → parallel support → migration guide → sunset. Pre-1.0: frontmatter and CLI stability is guaranteed; other surfaces are best-effort. Post-1.0: 2-release or 6-month transition window, whichever is longer. |

---

## 8. How this contract evolves

This contract is a living artifact. It is revised by explicit PR that amends `INTENT.md`.

**Amending process.** A PR that changes runtime behavior in a way inconsistent with this contract must either (a) reshape the change to fit, or (b) first amend the contract, with reviewer sign-off on the amendment before the behavioral change merges. Silent drift is a bug. Drift that earns its place revises the contract first.

**Versioning.** This file carries a version at the top (`v1`, `v2`, …). Each amendment bumps it. Commits and issues cite the version they were written against so intent is unambiguous across time.

**Review discipline.** Every non-trivial PR description should cite which primitives, non-negotiables, or architectural properties it serves — or explicitly declare itself as a contract amendment. Reviewers enforce.

**Scope of authority.** This contract binds the `CoreyRDean/clauck` upstream repository. Forks are free to amend their own copy; the upstream contract applies to upstream decisions only. Third-party extensions (marketplace packages, layer-above tools) are bound only by the stable interfaces they consume, not by the contract itself.

---

## How to use this contract

**Read it when** you are about to make a decision and want to know what has already been decided.

**When evaluating a feature request:** run the decision filter (§5). If it passes, build it. If it fails, reshape or defer it.

**When writing docs or the README:** lead with the identity. Support with features. Never lead with features.

**When a contributor proposes something that doesn't fit:** point at this contract. If they make a case for revising it, that's a real conversation — amend the contract first. If they're simply not aligned with what clauck is, that's a clarification, not a compromise.

**When checking for drift:** compare what has been built against the non-negotiables, the six primitives, and the four architectural properties. Drift is when features accumulate that don't serve them. Drift is fixable if caught early.
