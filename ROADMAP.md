# Roadmap

Planned features and directions for clauck. Items are rough priorities, not commitments.

## v1.0 — Production-ready

- [ ] **Job templating / parameterization** — same prompt template, different arguments per instance. Avoids duplicate jobs for similar tasks.
- [ ] **Job groups / tags** — `tags: [monitoring, daily]` in frontmatter. Batch operations: `clauck pause --tag monitoring`.
- [ ] **Per-job dry-run** — `dry_run: true` frontmatter. Claude sees the prompt but tools are blocked. Lets users validate a job's behavior before going live.
- [ ] **System-level cost budget** — monthly cap across all jobs. Scheduler pauses non-essential jobs when budget approaches the limit.
- [ ] **Sigstore artifact signing** — GitHub Actions signs releases for verifiable provenance.

## v1.1 — Automation pipelines

- [ ] **Job chaining / DAG** — `depends_on: [job-a, job-b]` in frontmatter. Job fires only after dependencies complete successfully. Enables multi-step workflows.
- [ ] **Output piping** — job A's result feeds into job B's prompt as context. Composable automation.
- [ ] **Webhook triggers** — a lightweight local HTTP endpoint that fires a job on POST. Integrates with GitHub webhooks, Zapier, IFTTT, etc.
- [ ] **Conditional execution** — `run_if: "exit_code of last run == 0"` or similar. Most conditions are better handled in the prompt itself, but structural conditions (prior job failed) need scheduler support.

## v1.2 — Multi-platform

- [ ] **Linux native support** — replace launchd LaunchAgent with systemd user unit (`systemd --user`). `scheduler.py` and `run-job.sh` are already platform-agnostic; only the install/uninstall scripts and the tick mechanism need Linux variants.
- [ ] **Alternative agent harnesses** — per-job `harness` field in frontmatter:
  ```yaml
  harness: codex      # or: cursor, aider, claude (default)
  ```
  Claude is the first-class citizen. Alternative harnesses get basic support (cron fire, log capture, concurrency guard) but may not support all features (session persistence, MCP integration, interactive mode, skill-driven management).
  Planned harnesses: Codex CLI, Cursor CLI, Aider, any `<command> -p <prompt>` compatible tool.
- [ ] **Job versioning / rollback** — git-backed version history for job prompts. `clauck rollback <name>` to revert to a previous prompt version.

## v2.0 — Platform

- [ ] **clauck.com** — web dashboard showing job status, run history, cost tracking across machines. Optional; the system remains fully local-first.
- [ ] **Shared job registries** — `clauck install author/repo-name/job-name` fetches a job from any GitHub repo, not just the built-in library.
- [ ] **Team coordination** — multiple machines running clauck can coordinate via a shared state backend (e.g., a GitHub repo as a job registry + state store).
- [ ] **MCP server interface** — expose clauck operations (list, fire, pause, status) as an MCP server so any MCP-capable agent can manage jobs without the Claude-specific skill.

## Design principles

- **Local-first.** Everything works on a single machine with no network except the optional auto-updater. Cloud features are always opt-in additions.
- **No new dependencies.** `/usr/bin/python3` + `/bin/zsh` on macOS, standard python3 + bash on Linux. No pip, no brew, no compiled binaries.
- **Harness-agnostic where possible.** The scheduler, triggers, and state management don't care which LLM runs the prompt. Only features that depend on a specific CLI's flags (session persistence, MCP integration) are harness-specific.
- **Backward compatible.** Jobs written for v0.1 work on v2.0. New frontmatter fields always have defaults.
