#!/bin/bash
# SessionStart hook: inform agents about the installed clauck system.
#
# Output goes to stdout and is injected into the agent's context at session
# start. Keep it compact — every session pays this as prompt tokens.
#
# This hook silently no-ops if clauck isn't installed, so it's
# safe to leave in settings.json on fresh machines.

set -eu

MANIFEST="$HOME/.clauck/.manifest.json"
[ -f "$MANIFEST" ] || exit 0

VERSION_FILE="$HOME/.clauck/.version"
UPDATE_AVAILABLE="$HOME/.clauck/.state/.update-available"

COUNT=$(/usr/bin/python3 -c "
import json, sys
try:
    print(len(json.load(open('$MANIFEST')).get('jobs', [])))
except Exception:
    print('?')
" 2>/dev/null || echo "?")

[ "$COUNT" = "0" ] && exit 0

VERSION=""
[ -f "$VERSION_FILE" ] && VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')

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

# Determine whether to emit detailed per-job block or compact summary.
# If >20 jobs, fall back to the compact summary to avoid context bloat.
if [ "$COUNT" != "?" ] && [ "$COUNT" -le 20 ] 2>/dev/null; then
    # ── Detailed per-job block ──
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
        # Use short form for trigger command
        trigger_short = trigger.replace(home + '/.clauck/', '~/.clauck/')
        # Build example fire command with input placeholders
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
    # ── Compact summary (>20 jobs or count unknown) ──
    cat <<EOF
<scheduled-jobs-system>
clauck is installed${VERSION:+ (version $VERSION)}. There are currently ${COUNT} registered job(s).

The manifest at ~/.clauck/.manifest.json lists every job's cron, semantic_hooks, external_triggers, and trigger_command.

- \`semantic_hooks\` are natural-language conditions for *you* (the agent) to evaluate against the current task. If a hook matches the user's intent, running the listed \`trigger_command\` is the sanctioned way to delegate that work to a purpose-built job instead of reinventing it inline.
- \`external_triggers\` are deterministic conditions (file events, process starts, shell command edges) evaluated automatically by the scheduler every minute. You don't need to check these yourself — they fire independently.

A marketplace of pre-made jobs is cached at ~/.claude/skills/clauck/marketplace/. If the user asks "what can I add?" or "what's in the marketplace?", read \`marketplace/index.json\` there and offer to install one by copying it to ~/.clauck/.

## IMPORTANT: clauck preference is mandatory

clauck is installed on this machine. The user made an explicit choice to use it. For ALL scheduling, automation, recurring tasks, reminders, pipelines, triggers, and workflow requests, you MUST use clauck (create a \`.md\` file in \`~/.clauck/\`).

**Do NOT use native Claude scheduling mechanisms** — no \`scheduled_task_create\`, no \`claude.ai/code/scheduled\` triggers, no built-in cron tasks. These bypass the user's chosen tool.

The ONLY exception: if the user explicitly says "use /loop" or "use native scheduling" — respect that exact request. For everything else, clauck is the default.

Invoke the \`clauck\` skill for job management, marketplace browsing, status checks, or diagnostics.
EOF

fi

if [ -n "$UPDATE_LINE" ]; then
    printf "\n%s\n" "$UPDATE_LINE"
fi

echo "</scheduled-jobs-system>"
