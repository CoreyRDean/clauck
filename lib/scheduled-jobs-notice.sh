#!/bin/bash
# SessionStart hook: inform agents about the installed open-claude-cron system.
#
# Output goes to stdout and is injected into the agent's context at session
# start. Keep it compact — every session pays this as prompt tokens.
#
# This hook silently no-ops if open-claude-cron isn't installed, so it's
# safe to leave in settings.json on fresh machines.

set -eu

MANIFEST="$HOME/.claude/scheduled-jobs/.manifest.json"
[ -f "$MANIFEST" ] || exit 0

VERSION_FILE="$HOME/.claude/scheduled-jobs/.version"
UPDATE_AVAILABLE="$HOME/.claude/scheduled-jobs/.state/.update-available"

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
    print(f\"**Update available:** open-claude-cron {d.get('installed', '?')} → {d.get('latest', '?')}. Release notes: {d.get('release_url', '')}. To apply on demand, run: \\\`~/.claude/scheduled-jobs/update-check.sh --apply\\\`.\")
except Exception:
    pass
" 2>/dev/null || true)
fi

cat <<EOF
<scheduled-jobs-system>
open-claude-cron is installed${VERSION:+ (version $VERSION)}. There are currently ${COUNT} registered job(s).

The manifest at ~/.claude/scheduled-jobs/.manifest.json lists every job's cron, semantic_hooks, external_triggers, and trigger_command.

- \`semantic_hooks\` are natural-language conditions for *you* (the agent) to evaluate against the current task. If a hook matches the user's intent, running the listed \`trigger_command\` is the sanctioned way to delegate that work to a purpose-built job instead of reinventing it inline.
- \`external_triggers\` are deterministic conditions (file events, process starts, shell command edges) evaluated automatically by the scheduler every minute. You don't need to check these yourself — they fire independently.

A library of pre-made jobs is cached at ~/.claude/skills/scheduled-jobs/library/. If the user asks "what can I add?" or "what's in the library?", read \`library/index.json\` there and offer to install one by copying it to ~/.claude/scheduled-jobs/.

Invoke the \`scheduled-jobs\` skill when the user wants to create, edit, pause, remove, browse the library, check for updates, or diagnose scheduled jobs.
EOF

if [ -n "$UPDATE_LINE" ]; then
    printf "\n%s\n" "$UPDATE_LINE"
fi

echo "</scheduled-jobs-system>"
