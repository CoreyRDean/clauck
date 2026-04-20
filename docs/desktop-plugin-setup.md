# clauck — Claude Desktop plugin setup

**Prerequisite:** install the clauck runtime on your Mac first. The plugin wraps the installed binary; it doesn't ship one.

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
```

This places `~/.local/bin/clauck`, the scheduler, and the LaunchAgent.

## Install the plugin

Paste this to Claude Desktop (CoWork or regular chat):

> Create a new CoWork plugin from `https://github.com/CoreyRDean/clauck`.

Done. Claude Desktop handles the rest natively.

## What you get

- **MCP server** `clauck` — 13 tools: `list_jobs`, `fire_job`, `get_logs`, `inspect_job`, `pause_job`, `resume_job`, `get_status`, `next_fires`, `marketplace_list`, `marketplace_info`, `install_job`, `run_doctor`, `run_work`.
- **Skill** `/clauck:clauck` — operational reference for authoring jobs, reading logs, pipeline composition, marketplace usage. Loaded on demand.
- **SessionStart hook** — emits a `<scheduled-jobs-system>` block listing registered jobs and their `semantic_hooks` at the top of every Desktop chat. Also self-heals runtime drift by backgrounding `install.sh` when the binary is missing or version-mismatched. Rate-limited to once per hour.

## Updating

Two sides. Update either — the plugin's SessionStart hook detects drift and prints a pointer to the other.

**CoWork plugin side:**

> Pull latest plugins/clauck/ from github.com/CoreyRDean/clauck and build a Cowork .plugin update.

**Host Mac runtime side:** re-run `install.sh` in a Mac terminal:

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
```

The installer prints the CoWork update prompt in its success banner so you can paste it directly into CoWork without looking it up.

## Uninstalling

- Plugin: Customize → Personal plugins → clauck → Remove.
- Runtime: `clauck uninstall` (keeps jobs/logs) or `clauck uninstall --wipe`.
