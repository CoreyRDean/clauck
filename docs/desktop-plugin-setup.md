# clauck — Claude Desktop plugin setup

Claude Desktop doesn't have the `claude plugin marketplace add` / `claude plugin install` CLI that Claude Code does, so Desktop install requires one of two paths:

- **Option A (recommended)**: hand Claude Desktop a short prompt and have it build a custom personal plugin from this repo's resources.
- **Option B (fallback)**: step through the Customize → Personal plugins UI yourself.

Either way, **install the clauck runtime on your Mac first** — the plugin wraps an already-installed binary, it doesn't ship one:

```bash
curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
```

This places `~/.local/bin/clauck`, the scheduler, and the LaunchAgent. Without it, the plugin's MCP server can't start — the launcher shim points at that path.

---

## Option A — ask Claude to build a custom plugin

Paste this message to Claude Desktop:

> Please create a new custom personal plugin in Claude Desktop called `clauck`.
>
> Mirror the structure from this repository's plugin, which lives at `plugins/clauck/`: https://github.com/CoreyRDean/clauck/tree/main/plugins/clauck
>
> Specifically, your custom plugin should include:
>
> - **Skill** — copy the content of `plugins/clauck/skills/clauck/SKILL.md` into a skill inside your plugin.
> - **Hook** — replicate `plugins/clauck/hooks/hooks.json` (a SessionStart hook) and the `plugins/clauck/hooks/sessionstart.sh` script it invokes.
> - **MCP server config** — replicate `plugins/clauck/.mcp.json`. The command should be `${CLAUDE_PLUGIN_ROOT}/bin/clauck-mcp-launcher`, and you'll need to include the `plugins/clauck/bin/clauck-mcp-launcher` shell script itself (it execs `$HOME/.local/bin/clauck mcp`).
> - Make sure `hooks/sessionstart.sh` and `bin/clauck-mcp-launcher` are executable (chmod +x).
>
> Once the plugin is assembled, enable it. Then attempt to call one of the clauck MCP tools (`get_status` is simplest — no arguments) and report the output verbatim. If any step fails, tell me which step and what the error was. If you need to walk me through any manual click in the Customize UI to complete the install, ask one question at a time.

Claude Desktop will read the four files from the repo, create a new personal plugin in its Customize panel, copy those artifacts in, enable the plugin, and try it. If its `get_status` call returns live runtime data, you're done. If any step fails, Claude will tell you which one so we can iterate.

**Restart Claude Desktop** afterward if the plugin doesn't activate immediately in the current session.

---

## Option B — manual UI walkthrough (deterministic fallback)

If Option A stalls, use the UI directly. Takes ~45 seconds:

1. Click **Customize** in the left-hand menu.
2. Click the **`+`** next to **Personal plugins**.
3. Click **Create plugin**.
4. Click **Add Marketplace**.
5. Type `CoreyRDean/clauck` and confirm.
6. Click the **`+`** next to **Personal plugins** again.
7. Click **Browse Plugins**.
8. Click the **Personal** tab.
9. Click the **clauck** marketplace.
10. Click the **clauck** plugin.
11. Click **Install**.
12. Restart Claude Desktop if the plugin doesn't activate immediately.

This path goes through Claude Desktop's marketplace integration rather than building a custom personal plugin — the end result is the same.

---

## What you get after install

The plugin ships three Claude-facing surfaces:

- **MCP server**: `clauck` — exposes the following tools: `list_jobs`, `fire_job`, `get_logs`, `inspect_job`, `pause_job`, `resume_job`, `get_status`, `next_fires`, `marketplace_list`, `marketplace_info`, `install_job`, `run_doctor`, `run_work`.
- **Skill**: `/clauck:clauck` — the full operational reference for authoring jobs, reading logs, pipeline composition, marketplace usage. Loaded on demand.
- **SessionStart hook**: emits a `<scheduled-jobs-system>` block listing registered jobs, their `semantic_hooks`, and example `trigger_command` invocations at the top of every Desktop chat. Also **self-heals**: if the clauck binary is missing or version-drifted, the hook backgrounds `install.sh` via `nohup` and prints a one-line notice. Rate-limited to once per hour so failed installs don't spam.

---

## Verification

Quick smoke test after install:

- Open a new Desktop chat. You should see a `<scheduled-jobs-system>` block at the top listing your registered jobs.
- Ask: *"Use the clauck MCP get_status tool and show me the output."*
- Should return something like:
  ```
  clauck v1.5.7
    scheduler: running
    jobs: 6
    logs: 985
    …
  ```

---

## Updating

Plugin and runtime versions are coupled via the repo's `VERSION` file.

- **Plugin side**: Option A users — re-run the Option A prompt; Claude rebuilds the custom plugin from the latest repo contents. Option B users — Desktop picks up marketplace updates on restart.
- **Runtime side**: re-run `install.sh` on your Mac, or let the SessionStart hook's drift-reconciler background-install the matching version on the next Desktop session.

---

## Uninstalling

- **Plugin**: Customize → Personal plugins → clauck → Disable or Remove.
- **Runtime**: `clauck uninstall` (preserves jobs/state/logs) or `clauck uninstall --wipe` (removes everything under `~/.clauck/`).

---

## Troubleshooting

**"clauck binary not found" when the MCP server tries to start.** The runtime wasn't installed, or `~/.local/bin/clauck` isn't accessible to the subprocess. Run `curl … install.sh | bash` and verify `~/.local/bin/clauck version` works in a terminal.

**Plugin installs but nothing happens in new chats.** Restart Claude Desktop. Some versions require a restart to load newly-added Personal plugins.

**`get_status` MCP call fails with "tool not found".** The MCP server didn't register. Check the launcher is executable (`chmod +x` on the bin script) and that the hooks/skill files are where the plugin manifest expects them. Disable and re-enable the plugin in Customize.

**SessionStart hook shows "clauck runtime missing" on every session.** The self-heal is running install.sh in the background but it's failing. Check `~/.clauck/.state/.plugin-install.log` for the install.sh output and errors.
