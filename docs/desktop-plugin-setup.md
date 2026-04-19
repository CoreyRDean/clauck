# clauck — Claude Desktop plugin setup

> **For Desktop users.** Claude Desktop has no `/plugin` CLI command (unlike Claude Code). Two install paths below — the **self-build recipe** is the zero-friction one (tell Claude to read this doc; it does the rest). The **UI walkthrough** is the deterministic fallback when the recipe can't reach some step.
>
> **Both paths require the clauck runtime binary installed first.** If `~/.local/bin/clauck` doesn't exist on your Mac, run this in a terminal first:
>
> ```bash
> curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash
> ```
>
> The installer places the scheduler, LaunchAgent, and CLI. It will also attempt Claude Code plugin registration (no effect on Desktop directly, but it populates the shared `~/.claude/plugins/` store that Desktop also reads).

---

## Option A — self-build recipe (recommended)

Paste this to Claude Desktop:

> Please read this page and set up the clauck plugin for Claude Desktop by following the **"Recipe for Claude Desktop"** section verbatim: https://github.com/CoreyRDean/clauck/blob/main/docs/desktop-plugin-setup.md
>
> When you're done, tell me what you did and whether any step failed. If Filesystem or Shell MCP is not available to you, stop and tell me which steps I need to run manually.

Claude Desktop fetches this file, finds the recipe below, and executes it end-to-end. Assumes Filesystem MCP or Shell/Bash MCP is available.

---

## Recipe for Claude Desktop

**Claude: execute these steps in order. Stop on the first failure and report it verbatim.**

### Step 0 — prerequisites

Run this shell command:

```bash
test -x "$HOME/.local/bin/clauck" && echo "runtime-ok" || echo "runtime-missing"
```

- If output is `runtime-ok`: continue to Step 1.
- If output is `runtime-missing`: run
  ```bash
  curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh | bash -s -- --yes --no-mcp
  ```
  The `--no-mcp` flag skips plugin registration on the Code side (we handle the Desktop-aware registration in Step 2). The `--yes` flag suppresses interactive prompts. After this completes, re-run Step 0's check. If still `runtime-missing`, stop and report the install.sh output to the user.

### Step 1 — verify the shared plugin store

The user-scope plugin store is `~/.claude/plugins/`. Both Claude Code and Claude Desktop read from it. Verify the store exists:

```bash
mkdir -p "$HOME/.claude/plugins/marketplaces" "$HOME/.claude/plugins/cache"
test -f "$HOME/.claude/plugins/known_marketplaces.json" || echo '{}' > "$HOME/.claude/plugins/known_marketplaces.json"
test -f "$HOME/.claude/plugins/installed_plugins.json" || echo '{"version":2,"plugins":{}}' > "$HOME/.claude/plugins/installed_plugins.json"
echo "store-ready"
```

### Step 2 — register the marketplace and install the plugin

**If `claude` CLI is on PATH** (check with `command -v claude`): use the CLI, which handles everything idempotently. This is the preferred path — Claude Code's plugin subcommands also register entries in the shared store that Desktop reads.

```bash
claude plugin marketplace add CoreyRDean/clauck 2>&1 || true
claude plugin install clauck@clauck --scope user 2>&1 || true
```

**If `claude` CLI is NOT on PATH** (Desktop-only install, no Code CLI present): fall back to direct filesystem registration.

1. Clone the clauck repo into the marketplaces dir:
   ```bash
   rm -rf "$HOME/.claude/plugins/marketplaces/clauck"
   git clone --depth 1 https://github.com/CoreyRDean/clauck.git "$HOME/.claude/plugins/marketplaces/clauck"
   ```

2. Register the marketplace. Use Filesystem MCP (or `python3 -c`) to merge into `~/.claude/plugins/known_marketplaces.json`:
   ```python
   import json, pathlib, datetime
   p = pathlib.Path.home() / ".claude/plugins/known_marketplaces.json"
   d = json.loads(p.read_text()) if p.exists() else {}
   d["clauck"] = {
       "source": {"source": "github", "repo": "CoreyRDean/clauck"},
       "installLocation": str(pathlib.Path.home() / ".claude/plugins/marketplaces/clauck"),
       "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
   }
   p.write_text(json.dumps(d, indent=2) + "\n")
   ```

3. Read the plugin version from the cloned marketplace manifest and copy the plugin contents into the cache:
   ```bash
   VERSION=$(python3 -c "import json; print(json.load(open('$HOME/.claude/plugins/marketplaces/clauck/plugins/clauck/.claude-plugin/plugin.json'))['version'])")
   CACHE="$HOME/.claude/plugins/cache/clauck/clauck/$VERSION"
   rm -rf "$CACHE"
   mkdir -p "$CACHE"
   cp -R "$HOME/.claude/plugins/marketplaces/clauck/plugins/clauck/." "$CACHE/"
   chmod +x "$CACHE/hooks/sessionstart.sh" "$CACHE/bin/clauck-mcp-launcher"
   ```

4. Register the plugin as installed. Merge into `~/.claude/plugins/installed_plugins.json`:
   ```python
   import json, pathlib, datetime
   version = "PASTE_VERSION_FROM_STEP_ABOVE"
   cache = str(pathlib.Path.home() / f".claude/plugins/cache/clauck/clauck/{version}")
   now = datetime.datetime.utcnow().isoformat() + "Z"
   p = pathlib.Path.home() / ".claude/plugins/installed_plugins.json"
   d = json.loads(p.read_text()) if p.exists() else {"version": 2, "plugins": {}}
   d.setdefault("plugins", {})["clauck@clauck"] = [{
       "scope": "user",
       "installPath": cache,
       "version": version,
       "installedAt": now,
       "lastUpdated": now,
   }]
   p.write_text(json.dumps(d, indent=2) + "\n")
   ```

### Step 3 — verify the install

```bash
ls "$HOME/.claude/plugins/cache/clauck/clauck/"*/
cat "$HOME/.claude/plugins/installed_plugins.json" | python3 -c "import json,sys; d=json.load(sys.stdin); print([k for k in d.get('plugins',{}) if 'clauck' in k])"
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}' | "$HOME/.local/bin/clauck" mcp 2>&1 | head -1
```

Expected:
- `ls` shows the plugin cache contents (`plugin.json`, `hooks/`, `skills/`, `bin/`, `.mcp.json`).
- The `installed_plugins.json` check prints `['clauck@clauck']`.
- The MCP initialize returns a JSON response with `"serverInfo":{"name":"clauck",...}`.

### Step 4 — activate in Claude Desktop

Tell the user:

> Installation complete. To activate, **restart Claude Desktop** (quit and re-open). When you start a new chat, you should see a `<scheduled-jobs-system>` block injected at the top by the clauck plugin's SessionStart hook. You can also invoke the skill as `/clauck:clauck` or ask me to use any of the clauck MCP tools (list_jobs, fire_job, get_status, etc.).
>
> If after restart you don't see the plugin: open Claude Desktop → Customize → Personal plugins. The clauck marketplace and plugin should be listed; click clauck to verify it's enabled.

---

## Option B — manual UI walkthrough (deterministic fallback)

If the recipe fails on any step or you don't have MCP access set up, use the UI:

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

To trigger this from chat: paste the above 12 steps into the message ("Please help me install the clauck plugin by walking me through these 12 steps, one at a time...") and Claude Desktop will coach you through them.

---

## What you get

The plugin ships three Claude-facing surfaces:

- **MCP server**: `clauck` — exposes `list_jobs`, `fire_job`, `get_logs`, `inspect_job`, `pause_job`, `resume_job`, `get_status`, `marketplace_list`, `install_job`, `next_fires`, `run_doctor`, `run_work`, `marketplace_info` as MCP tools.
- **Skill**: `/clauck:clauck` — full reference for authoring jobs, reading logs, pipeline composition, marketplace usage. Loaded on demand.
- **SessionStart hook**: emits a `<scheduled-jobs-system>` block listing registered jobs, their `semantic_hooks`, and example `trigger_command` invocations at the top of every Desktop chat. This is what lets Claude match user intent against the right pre-built job.

The SessionStart hook also **self-heals**: if the clauck runtime is missing from `~/.local/bin/clauck` (plugin installed but user skipped `install.sh`) or if the binary version doesn't match the plugin version (plugin auto-updated but binary didn't, or vice versa), the hook spawns `install.sh` in the background and prints a one-line notice. Rate-limited to once per hour so failed installs don't spam.

---

## Updating

When clauck ships a new release:

- **Claude Code side** (if you also use CC): `claude plugin update clauck` — or just re-run `install.sh`.
- **Desktop side**: the plugin cache at `~/.claude/plugins/cache/clauck/clauck/<version>/` is version-scoped. Desktop picks up the new version after the marketplace re-sync (restart Desktop or trigger a marketplace update).
- **Runtime side**: either re-run `install.sh` manually, or let the SessionStart hook's drift-reconciler background-install the matching version on the next Desktop session.

Plugin version and runtime version are coupled via the same `VERSION` file in the repo, so they match once reconciled.

---

## Uninstalling

### Via claude CLI (if installed)
```bash
claude plugin uninstall clauck@clauck -s user
claude plugin marketplace remove clauck     # optional — only if not reusing
clauck uninstall                            # or `clauck uninstall --wipe`
```

### Manual
```bash
# Plugin cache + registry
rm -rf "$HOME/.claude/plugins/cache/clauck"
rm -rf "$HOME/.claude/plugins/marketplaces/clauck"
python3 -c "
import json, pathlib
for name in ('installed_plugins.json', 'known_marketplaces.json'):
    p = pathlib.Path.home() / '.claude/plugins' / name
    if not p.exists(): continue
    d = json.loads(p.read_text())
    if name == 'installed_plugins.json':
        d.get('plugins', {}).pop('clauck@clauck', None)
    else:
        d.pop('clauck', None)
    p.write_text(json.dumps(d, indent=2) + '\n')
"

# Runtime
clauck uninstall
# or: clauck uninstall --wipe
```

Restart Claude Desktop to pick up the removal.

---

## Troubleshooting

**Recipe Step 2 (fallback) — `python3` not found.** macOS ships `/usr/bin/python3` via Xcode CLT. Install Xcode CLT: `xcode-select --install`. Then re-run.

**Recipe Step 3 — MCP initialize returns nothing or an error.** The clauck runtime isn't on PATH for the subprocess. Verify: `test -x "$HOME/.local/bin/clauck" && "$HOME/.local/bin/clauck" version`. If the binary is missing, re-run install.sh.

**After restart, Desktop doesn't show the plugin.** Check `~/.claude/plugins/installed_plugins.json` — does `clauck@clauck` appear under `.plugins`? If yes but Desktop ignores it, the Desktop UI may need the marketplace registered via its own flow; fall back to Option B (UI walkthrough).

**SessionStart hook prints "clauck runtime missing" every session.** The self-heal is running install.sh in the background but it's failing. Check `~/.clauck/.state/.plugin-install.log` for errors. Rate-limited to one attempt per hour.
