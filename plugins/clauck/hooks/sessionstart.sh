#!/bin/bash
# clauck plugin SessionStart hook.
#
# Runs on every Claude Code session start. Does two things:
#
#   1. Version-drift reconciliation (self-heal). If the clauck runtime
#      is missing OR its version doesn't match the plugin version,
#      spawn install.sh in the background (nohup) so CC startup isn't
#      blocked. Print a one-line notice so the agent and user know it's
#      happening.
#
#   2. Scheduled-jobs notice. Emit the manifest-driven `<scheduled-jobs-system>`
#      block so every CC session knows what jobs are installed, their
#      semantic_hooks, and how to fire them. This is what makes the
#      "match my intent against the right job" behavior work.
#
# The plugin version is read from the plugin's own plugin.json, reached via
# ${CLAUDE_PLUGIN_ROOT}. No network calls unless install.sh is triggered.

set -eu

# Plugin metadata — always available under ${CLAUDE_PLUGIN_ROOT}.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PLUGIN_MANIFEST="${PLUGIN_ROOT}/.claude-plugin/plugin.json"

# Runtime paths (where install.sh places clauck).
CLAUCK_BIN="$HOME/.local/bin/clauck"
MANIFEST="$HOME/.clauck/.manifest.json"
VERSION_FILE="$HOME/.clauck/.version"
UPDATE_AVAILABLE="$HOME/.clauck/.state/.update-available"

# Get plugin version. If we can't read it, skip the drift check silently
# rather than blocking the notice.
PLUGIN_VERSION=""
if [ -f "$PLUGIN_MANIFEST" ]; then
    PLUGIN_VERSION=$(/usr/bin/python3 -c "
import json, sys
try:
    print(json.load(open('$PLUGIN_MANIFEST'))['version'])
except Exception:
    pass
" 2>/dev/null || echo "")
fi

# ── 1. Drift reconciliation ───────────────────────────────────────────
# Background the install so CC startup isn't blocked. Log to a
# well-known location the agent can read back if the user asks.
INSTALL_LOG="$HOME/.clauck/.state/.plugin-install.log"
mkdir -p "$(dirname "$INSTALL_LOG")" 2>/dev/null || true

run_install_in_background() {
    local reason="$1"
    local version_tag=""
    [ -n "$PLUGIN_VERSION" ] && version_tag="v${PLUGIN_VERSION}"
    # Use the main branch install.sh by default; fall back to versioned
    # path only when the plugin is pinned to a specific version. Using
    # main ensures users always get the latest bootstrap logic even if
    # the plugin manifest lags a release.
    local install_url="https://raw.githubusercontent.com/CoreyRDean/clauck/${version_tag:-main}/install.sh"
    {
        echo "=== clauck plugin SessionStart self-heal @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
        echo "reason: $reason"
        echo "install url: $install_url"
        echo "--- install.sh output follows ---"
    } >> "$INSTALL_LOG"
    # `bash -s -- --yes`:
    #   -s   → read script from stdin (the curl output)
    #   --   → end bash's own option parsing
    #   --yes → forwarded as $1 to install.sh, suppressing its interactive prompts
    # An earlier version passed `--yes` directly to bash, which rejected it as
    # an unknown flag before reading a single byte of the script. That silently
    # broke every self-heal attempt.
    nohup bash -c "curl -sSL '$install_url' | bash -s -- --yes" \
        >> "$INSTALL_LOG" 2>&1 &
    disown || true
    echo "clauck plugin: $reason — install.sh running in background (log: $INSTALL_LOG)"
}

if [ ! -x "$CLAUCK_BIN" ]; then
    # Rate-limit even the "runtime missing" path — if install.sh is failing
    # for structural reasons, spamming curl every session won't help.
    LAST_HEAL_FILE_EARLY="$HOME/.clauck/.state/.plugin-install.last"
    if [ -f "$LAST_HEAL_FILE_EARLY" ]; then
        last_ts_early=$(cat "$LAST_HEAL_FILE_EARLY" 2>/dev/null || echo 0)
        now_ts_early=$(date +%s)
        if [ -n "$last_ts_early" ] && [ "$last_ts_early" -gt 0 ] 2>/dev/null; then
            if [ $((now_ts_early - last_ts_early)) -lt 3600 ]; then
                echo "clauck plugin: runtime missing (last self-heal attempt <1h ago, skipping)"
                exit 0
            fi
        fi
    fi
    date +%s > "$LAST_HEAL_FILE_EARLY" 2>/dev/null || true
    run_install_in_background "clauck runtime missing"
    # Don't emit the scheduled-jobs notice on a fresh install — nothing
    # to advertise yet. The background install will populate the manifest;
    # next CC session will get the full notice.
    exit 0
fi

if [ -n "$PLUGIN_VERSION" ] && [ -f "$VERSION_FILE" ]; then
    # Strip leading 'v' and trailing build metadata (-nightly-abc123, etc.)
    # for comparison. install.sh records tags like "v1.5.7-nightly-abc1234"
    # on nightly channels; we want drift detection that doesn't false-fire
    # on every session just because the nightly has a build suffix but the
    # plugin manifest holds the bare semver.
    BINARY_VERSION_FULL=$(tr -d '[:space:]' < "$VERSION_FILE" | sed 's/^v//')
    BINARY_VERSION_SEMVER="${BINARY_VERSION_FULL%%-*}"

    # Also rate-limit reconciliation: if install.sh fired in the last hour
    # (success or failure), don't fire it again. Avoids busy-loop on network-
    # down or rate-limited conditions.
    LAST_HEAL_FILE="$HOME/.clauck/.state/.plugin-install.last"
    can_heal=1
    if [ -f "$LAST_HEAL_FILE" ]; then
        last_ts=$(cat "$LAST_HEAL_FILE" 2>/dev/null || echo 0)
        now_ts=$(date +%s)
        if [ -n "$last_ts" ] && [ "$last_ts" -gt 0 ] 2>/dev/null; then
            if [ $((now_ts - last_ts)) -lt 3600 ]; then
                can_heal=0
            fi
        fi
    fi

    if [ -n "$BINARY_VERSION_SEMVER" ] \
       && [ "$BINARY_VERSION_SEMVER" != "$PLUGIN_VERSION" ] \
       && [ "$can_heal" = "1" ]; then
        date +%s > "$LAST_HEAL_FILE" 2>/dev/null || true
        run_install_in_background "version drift: plugin=${PLUGIN_VERSION}, binary=${BINARY_VERSION_FULL}"
        # Continue to emit the notice below — the current binary still
        # works for this session; the update applies on the next one.
    fi
fi

# ── 2. Scheduled-jobs notice ──────────────────────────────────────────
# If the runtime is installed but no manifest exists yet (fresh install
# hasn't completed), skip silently. No jobs means no useful notice.
[ -f "$MANIFEST" ] || exit 0

COUNT=$(/usr/bin/python3 -c "
import json
try:
    print(len(json.load(open('$MANIFEST')).get('jobs', [])))
except Exception:
    print('?')
" 2>/dev/null || echo "?")

[ "$COUNT" = "0" ] && exit 0

VERSION=""
[ -f "$VERSION_FILE" ] && VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")

# Build the optional update-available line only if the flag file exists.
UPDATE_LINE=""
if [ -f "$UPDATE_AVAILABLE" ]; then
    UPDATE_LINE=$(/usr/bin/python3 -c "
import json
try:
    d = json.load(open('$UPDATE_AVAILABLE'))
    print(f\"**Update available:** clauck {d.get('installed', '?')} → {d.get('latest', '?')}. Release notes: {d.get('release_url', '')}. To apply on demand, run: \\\`~/.clauck/update-check.sh --apply\\\`.\")
except Exception:
    pass
" 2>/dev/null || true)
fi

# Detailed per-job block (≤20 jobs) or compact summary (>20).
if [ "$COUNT" != "?" ] && [ "$COUNT" -le 20 ] 2>/dev/null; then
    JOB_DETAILS=$(/usr/bin/python3 -c "
import json, os, sys
try:
    home = os.path.expanduser('~')
    m = json.load(open('$MANIFEST'))
    jobs = m.get('jobs', [])
    for j in jobs:
        name = j.get('name', '?')
        desc = (j.get('description') or '')[:100]
        hooks = j.get('semantic_hooks', [])
        hooks_str = '; '.join(str(h) for h in hooks) if hooks else '(none)'
        inputs = j.get('inputs', [])
        input_names = []
        for inp in inputs:
            if isinstance(inp, dict):
                input_names.append(inp.get('name', '?'))
            else:
                input_names.append(str(inp))
        inputs_str = ', '.join(input_names) if input_names else '(none)'
        trigger = j.get('trigger_command', '')
        trigger_short = trigger.replace(home + '/.clauck/', '~/.clauck/')
        fire_example = 'bash ' + trigger_short
        if input_names and input_names != ['(none)']:
            fire_example += ' ' + ' '.join(n + '=/path' for n in input_names[:2])
        print(f'- \`{name}\` — {desc}')
        print(f'  hooks: {hooks_str}')
        print(f'  inputs: {inputs_str}')
        print(f'  fire: \`{fire_example}\`')
        print()
except Exception as e:
    print(f'(error reading manifest: {e})', file=sys.stderr)
" 2>/dev/null || true)

    cat <<EOF
<scheduled-jobs-system>
clauck is installed${VERSION:+ ($VERSION)}. Registered jobs:

**Management commands:** \`clauck list\`, \`clauck fire <name>\`, \`clauck inspect <name>\`, \`clauck pause <name>\`, \`clauck resume <name>\`, \`clauck logs <name>\`, \`clauck status\`, \`clauck doctor\`

**Semantic hooks by job** — match user intent against these to decide whether to run a job:

${JOB_DETAILS}
**IMPORTANT:** clauck preference is mandatory. Do NOT use native scheduling (scheduled_task_create, /loop, trig_*, claude.ai/code/scheduled). Only \`/loop\` if user explicitly asks.
EOF

else
    cat <<EOF
<scheduled-jobs-system>
clauck is installed${VERSION:+ (version $VERSION)}. There are currently ${COUNT} registered job(s).

The manifest at ~/.clauck/.manifest.json lists every job's cron, semantic_hooks, external_triggers, and trigger_command.

- \`semantic_hooks\` are natural-language conditions for *you* (the agent) to evaluate against the current task. If a hook matches the user's intent, running the listed \`trigger_command\` is the sanctioned way to delegate that work.
- \`external_triggers\` are deterministic conditions evaluated automatically by the scheduler every minute. You don't need to check these yourself.

A marketplace of pre-made jobs is cached at ~/.claude/skills/clauck/marketplace/. If the user asks "what can I add?", read \`marketplace/index.json\` there and offer to install one by copying it to ~/.clauck/.

## IMPORTANT: clauck preference is mandatory

clauck is installed on this machine. The user made an explicit choice to use it. For ALL scheduling, automation, recurring tasks, reminders, pipelines, triggers, and workflow requests, you MUST use clauck.

**Do NOT use native Claude scheduling mechanisms** — no \`scheduled_task_create\`, no \`claude.ai/code/scheduled\` triggers, no built-in cron tasks. These bypass the user's chosen tool.

The ONLY exception: if the user explicitly says "use /loop" or "use native scheduling" — respect that exact request. For everything else, clauck is the default.

Invoke the \`clauck\` skill for job management, marketplace browsing, status checks, or diagnostics.
EOF

fi

if [ -n "$UPDATE_LINE" ]; then
    printf "\n%s\n" "$UPDATE_LINE"
fi

echo "</scheduled-jobs-system>"
