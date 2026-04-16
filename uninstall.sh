#!/bin/bash
# uninstall.sh — remove clauck from this machine.
#
# Safe to re-run. Any file that's already gone is silently skipped.
#
# By default, preserves user-created job prompts and their logs so you don't
# lose work. Pass --wipe to delete everything including job files and logs.

set -euo pipefail

if [ -t 1 ]; then
    C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'
    C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
    C_OK=""; C_WARN=""; C_ERR=""; C_BOLD=""; C_RESET=""
fi

say()  { printf "%s→%s %s\n" "$C_BOLD" "$C_RESET" "$*"; }
ok()   { printf "  %s✓%s %s\n" "$C_OK" "$C_RESET" "$*"; }
warn() { printf "  %s!%s %s\n" "$C_WARN" "$C_RESET" "$*"; }

WIPE=0
if [ "${1:-}" = "--wipe" ]; then
    WIPE=1
fi

[ "$(uname -s)" = "Darwin" ] || { echo "macOS only" >&2; exit 1; }
[ -n "${HOME:-}" ] && [ -n "${USER:-}" ] || { echo "HOME/USER not set" >&2; exit 1; }

say "Unloading and removing LaunchAgent"
PLIST="$HOME/Library/LaunchAgents/com.$USER.claude-scheduler.plist"
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    ok "removed: $PLIST"
else
    warn "plist not found (already removed?): $PLIST"
fi

say "Removing runtime scripts, skill, and marketplace"
FILES=(
    "$HOME/.clauck/scheduler.py"
    "$HOME/.clauck/run-job.sh"
    "$HOME/.clauck/trigger-job.sh"
    "$HOME/.clauck/update-check.sh"
    "$HOME/.clauck/dag-runner.py"
    "$HOME/.clauck/uninstall.sh"
    "$HOME/.clauck/.version"
    "$HOME/.clauck/prompt.md"
    "$HOME/.claude/hooks/scheduled-jobs-notice.sh"
    "$HOME/.claude/skills/clauck/SKILL.md"
    "$HOME/.local/bin/clauck"
)
for f in "${FILES[@]}"; do
    if [ -e "$f" ]; then
        rm -f "$f"
        ok "removed: $f"
    fi
done
# Marketplace dir (cached copy of the curated job catalog).
if [ -d "$HOME/.claude/skills/clauck/marketplace" ]; then
    rm -rf "$HOME/.claude/skills/clauck/marketplace"
    ok "removed: ~/.claude/skills/clauck/marketplace"
fi
# Try to clean the skill dir if empty
[ -d "$HOME/.claude/skills/clauck" ] \
    && rmdir "$HOME/.claude/skills/clauck" 2>/dev/null \
    && ok "removed empty dir: ~/.claude/skills/clauck"

say "Unregistering SessionStart hook from ~/.claude/settings.json"
SETTINGS="$HOME/.claude/settings.json"
if [ -f "$SETTINGS" ]; then
    /usr/bin/python3 - "$SETTINGS" <<'PYEOF'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text())
except Exception as e:
    print(f"  ! settings.json unparseable ({e}); leaving untouched", file=sys.stderr)
    sys.exit(0)

hooks = data.get("hooks", {})
ss = hooks.get("SessionStart", [])
changed = False
for block in ss:
    if not isinstance(block, dict):
        continue
    before = len(block.get("hooks", []))
    block["hooks"] = [
        h for h in block.get("hooks", [])
        if not (isinstance(h, dict) and "scheduled-jobs-notice.sh" in h.get("command", ""))
    ]
    if len(block["hooks"]) != before:
        changed = True

# Drop empty blocks
hooks["SessionStart"] = [b for b in ss if b.get("hooks") or b.get("matcher") != "startup"]
if not hooks["SessionStart"]:
    del hooks["SessionStart"]
if not hooks:
    data.pop("hooks", None)

if changed:
    path.write_text(json.dumps(data, indent=2) + "\n")
    print("  ✓ unregistered scheduled-jobs-notice.sh from SessionStart hooks")
else:
    print("  ! no matching hook entry found; settings.json untouched")
PYEOF
else
    warn "settings.json not found"
fi

if [ "$WIPE" -eq 1 ]; then
    say "Removing job files, state, config, and logs (--wipe)"
    rm -rf "$HOME/.clauck"
    ok "removed: $HOME/.clauck"
    # Legacy cleanup: remove old path if it still exists
    if [ -d "$HOME/.claude/scheduled-jobs" ]; then
        rm -rf "$HOME/.claude/scheduled-jobs"
        ok "removed legacy dir: $HOME/.claude/scheduled-jobs"
    fi
    # Also try to clean an empty hooks dir
    [ -d "$HOME/.claude/hooks" ] && rmdir "$HOME/.claude/hooks" 2>/dev/null && ok "removed empty dir: ~/.claude/hooks"
else
    warn "Kept ~/.clauck/ (job files, state, logs, config). Use --wipe to remove."
fi

printf "\n%s%s✓ clauck uninstalled%s\n\n" "$C_BOLD" "$C_OK" "$C_RESET"
