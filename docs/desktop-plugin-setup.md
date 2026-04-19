# clauck — Claude Desktop plugin setup

> **Claude Desktop does not have a CLI for plugin management.** Unlike Claude Code (where `claude plugin marketplace add` and `claude plugin install` work headlessly from the shell), Desktop requires a short manual walkthrough in its Customize panel. Two options below.
>
> **Prerequisites:** the clauck runtime must be installed first. Run:
>
> ```bash
> curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
> ```
>
> This places the `clauck` binary at `~/.local/bin/clauck`, installs the LaunchAgent, and provisions `~/.clauck/`. The Desktop plugin is a Claude-facing wrapper around that runtime; it does not install the runtime itself.

---

## Option A — manual UI walkthrough (works today, guaranteed)

Works in both **Claude Desktop (Code)** and **CoWork**. Takes ~45 seconds.

1. Click **Customize** in the left-hand menu of Claude Desktop.
2. Click the **`+`** next to **Personal plugins**.
3. Click **Create plugin**.
4. Click **Add Marketplace**.
5. Type (or paste): `CoreyRDean/clauck`
6. Click the **`+`** next to **Personal plugins** again.
7. Click **Browse Plugins**.
8. Click the **Personal** tab.
9. Click the **clauck** marketplace.
10. Click the **clauck** plugin.
11. Click **Install**.
12. If the plugin does not activate immediately, restart Claude Desktop.

After activation, starting any new Claude Desktop chat will fire the plugin's `SessionStart` hook, which surfaces the installed clauck jobs and semantic hooks into the conversation context.

---

## Option B — ask Claude to walk you through it

Paste this message to Claude Desktop:

> Please help me install the clauck plugin by walking me through these 12 steps, one at a time, waiting for me to confirm each step before moving on:
>
> 1. Click Customize in the left-hand menu.
> 2. Click the + next to Personal plugins.
> 3. Click Create plugin.
> 4. Click Add Marketplace.
> 5. Type `CoreyRDean/clauck`.
> 6. Click the + next to Personal plugins again.
> 7. Click Browse Plugins.
> 8. Click the Personal tab.
> 9. Click the clauck marketplace.
> 10. Click the clauck plugin.
> 11. Click Install.
> 12. Restart Claude Desktop if the plugin doesn't activate immediately.
>
> If something in my UI looks different, tell me what you see and adapt. If any step fails, help me troubleshoot.

The steps are inlined (not referenced by URL) because Claude Desktop can't reliably fetch external URLs unless you have WebFetch enabled. This removes the cognitive load of figuring out what to click without requiring any specific tool access on Desktop's side.

Alternative (requires WebFetch enabled): *"Please help me install the clauck plugin. Read https://github.com/CoreyRDean/clauck/blob/main/docs/desktop-plugin-setup.md and walk me through the Option A steps interactively."*

---

## What you get after install

The plugin ships three Claude-facing surfaces:

- **MCP server**: `clauck` — exposes `list_jobs`, `fire_job`, `get_logs`, `inspect_job`, `pause_job`, `resume_job`, `get_status`, `marketplace_list` as MCP tools.
- **Skill**: `/clauck:clauck` — full reference for authoring jobs, reading logs, pipeline composition, marketplace usage. Loaded on demand.
- **SessionStart hook**: emits a `<scheduled-jobs-system>` block listing registered jobs, their `semantic_hooks`, and example `trigger_command` invocations at the top of every Desktop session. This is what lets Claude match user intent against the right pre-built job instead of reinventing functionality inline.

The SessionStart hook also **self-heals**: if the clauck runtime is missing from `~/.local/bin/clauck` (plugin installed but user forgot `install.sh`) or if the binary version doesn't match the plugin version (plugin auto-updated but binary didn't, or vice versa), the hook spawns `install.sh` in the background and prints a one-line notice. Subsequent sessions see the reconciled state.

---

## Updating

When clauck ships a new release:

- **Plugin side** (Desktop): Desktop checks for marketplace updates automatically at launch. If a new plugin version is available, you'll see it offered in the Customize panel. Click Update. If unprompted, use **Browse Plugins** → **Personal** → **clauck** → **Update**.
- **Runtime side** (binary): either re-run `curl install.sh | bash` manually, or rely on the SessionStart hook's drift-reconciler to background-install the matching version on the next Desktop session.

Plugin version and runtime version are coupled via the same `VERSION` file in the repo, so version numbers will match once both sides have reconciled.

---

## Uninstalling

1. Customize → Personal plugins → **clauck** → **Uninstall**.
2. (Optional) Customize → Personal plugins → the marketplace entry → **Remove marketplace**.
3. Remove the runtime with `clauck uninstall` (or `clauck uninstall --wipe` to also delete `~/.clauck/`).

The runtime and plugin are separate concerns — uninstalling one does not uninstall the other. Do both if you want a clean removal.

---

## Troubleshooting

**Plugin installs but nothing happens in new chats.** Restart Claude Desktop. Some versions require a restart to load newly-installed Personal plugins.

**MCP server shows as failed to connect.** The plugin's `.mcp.json` invokes `clauck` from `PATH`. If `~/.local/bin` isn't on your `PATH` when Desktop launches subprocesses, the command can't be found. Check with: `which clauck` in a terminal. Fix by either adding `~/.local/bin` to your shell's PATH (and restarting Desktop so it picks up the new environment) or re-running `install.sh` which also writes a plist that prepends `~/.local/bin` to the LaunchAgent's PATH.

**SessionStart hook shows "clauck runtime missing" every session.** The self-heal is running install.sh in the background but it's failing. Check `~/.clauck/.state/.plugin-install.log` for errors.

**Plugin version doesn't match what's in GitHub.** Desktop caches marketplace data. Force a refresh: Customize → Personal plugins → the marketplace entry → click through it to trigger a re-fetch. Or remove and re-add the marketplace.
