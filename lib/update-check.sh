#!/bin/bash
# update-check.sh — check clauck for a newer release, optionally apply.
#
# Invoked:
#   • Ad-hoc by user or agent (no args)                  → report only
#   • By scheduler.py on its periodic update-check tick  → may apply if configured
#   • Explicit self-update request: `--apply`            → force apply the latest release
#
# Source of truth: the `tag_name` of the latest GitHub Release on the configured
# repo. A push to main does NOT trigger an update — someone has to explicitly cut
# a Release for downstream machines to see the new version.
#
# Config file (JSON) at: ~/.claude/scheduled-jobs/.clauck.config.json
#   {
#     "auto_update": {
#       "enabled": true,                   # auto-check enabled
#       "check_interval_seconds": 3600,    # how often scheduler.py checks
#       "auto_apply": false                # whether to auto-install new releases
#     }
#   }
#
# Exit codes:
#   0  up-to-date, OR report succeeded (no action needed), OR apply succeeded
#   1  network / API error
#   2  misconfig / missing install
#   3  apply failed

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────
# Config — edit REPO when forking
# ──────────────────────────────────────────────────────────────────────────

# Repo defaults to whatever was set during installation (persisted in config file).
# Env var override takes precedence for ad-hoc testing.
_CONFIG_REPO=""
_CFG="$HOME/.claude/scheduled-jobs/.clauck.config.json"
if [ -f "$_CFG" ]; then
    _CONFIG_REPO=$(/usr/bin/python3 -c "
import json, sys
try: print(json.load(open('$_CFG')).get('repo',''))
except: pass
" 2>/dev/null || true)
fi
REPO="${CLAUCK_REPO:-${_CONFIG_REPO:-CoreyRDean/clauck}}"

STATE_DIR="$HOME/.claude/scheduled-jobs/.state"
VERSION_FILE="$HOME/.claude/scheduled-jobs/.version"
AVAILABLE_FILE="$STATE_DIR/.update-available"
LAST_CHECK_FILE="$STATE_DIR/.update-last-check"
CONFIG_FILE="$HOME/.claude/scheduled-jobs/.clauck.config.json"

APPLY=0
QUIET=0
for arg in "$@"; do
    case "$arg" in
        --apply) APPLY=1 ;;
        --quiet) QUIET=1 ;;
        --help|-h)
            cat <<HELP
update-check.sh — check clauck for a newer release.

Usage:
  update-check.sh              Check. Write state files. Print status.
  update-check.sh --apply      Check. If newer release available, install it.
  update-check.sh --quiet      Check. Update state files. Print nothing unless apply fails.

Configuration lives at:
  $CONFIG_FILE

Installed version:
  $VERSION_FILE

Update-available flag (written when a newer release is detected):
  $AVAILABLE_FILE
HELP
            exit 0
            ;;
    esac
done

log() { [ "$QUIET" -eq 0 ] && printf "%s\n" "$*"; }
err() { printf "%s\n" "$*" >&2; }

[ -d "$HOME/.claude/scheduled-jobs" ] \
    || { err "clauck is not installed at ~/.claude/scheduled-jobs"; exit 2; }
mkdir -p "$STATE_DIR"

# ──────────────────────────────────────────────────────────────────────────
# Installed version
# ──────────────────────────────────────────────────────────────────────────

if [ -f "$VERSION_FILE" ]; then
    INSTALLED="$(cat "$VERSION_FILE" | tr -d '[:space:]')"
else
    INSTALLED="unknown"
fi

# ──────────────────────────────────────────────────────────────────────────
# Fetch latest release tag
# Uses unauthenticated GitHub API (60 req/hr/IP — far more than we'd ever use).
# Falls back to `gh` if available and curl fails.
# ──────────────────────────────────────────────────────────────────────────

LATEST_TAG=""
API_URL="https://api.github.com/repos/$REPO/releases/latest"

if command -v curl >/dev/null 2>&1; then
    RESPONSE="$(curl -fsSL --max-time 10 -H 'Accept: application/vnd.github+json' "$API_URL" 2>/dev/null || true)"
    if [ -n "$RESPONSE" ]; then
        LATEST_TAG="$(/usr/bin/python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get("tag_name", ""))
except Exception:
    print("")
' <<<"$RESPONSE")"
    fi
fi

if [ -z "$LATEST_TAG" ] && command -v gh >/dev/null 2>&1; then
    # gh is authenticated and provides a nicer interface; try as fallback.
    LATEST_TAG="$(gh release view --repo "$REPO" --json tagName --jq .tagName 2>/dev/null || true)"
fi

date +%s > "$LAST_CHECK_FILE"

if [ -z "$LATEST_TAG" ]; then
    err "could not fetch latest release from https://github.com/$REPO"
    err "(this is usually transient — check your network, or see if the repo has any releases yet)"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────
# Compare
# ──────────────────────────────────────────────────────────────────────────

if [ "$INSTALLED" = "$LATEST_TAG" ]; then
    rm -f "$AVAILABLE_FILE"
    log "✓ up-to-date ($INSTALLED)"
    exit 0
fi

# Write the "update available" marker so the SessionStart hook can mention it.
cat > "$AVAILABLE_FILE" <<EOF
{
  "installed": "$INSTALLED",
  "latest": "$LATEST_TAG",
  "detected_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "release_url": "https://github.com/$REPO/releases/tag/$LATEST_TAG"
}
EOF

log "update available: $INSTALLED → $LATEST_TAG"
log "release notes:    https://github.com/$REPO/releases/tag/$LATEST_TAG"

if [ "$APPLY" -eq 0 ]; then
    log ""
    log "To install this release now, run:"
    log "  bash <(curl -fsSL https://raw.githubusercontent.com/$REPO/$LATEST_TAG/install.sh)"
    log ""
    log "To enable auto-apply (applies new releases automatically), edit:"
    log "  $CONFIG_FILE"
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────────
# Apply: run install.sh from the new release tag
# ──────────────────────────────────────────────────────────────────────────

log "applying update $INSTALLED → $LATEST_TAG ..."
# Fetch install.sh from main HEAD (always has the latest bug fixes for the
# install process itself). The CLAUCK_BRANCH env var tells the
# installer to clone the release TAG for the actual payload files.
INSTALLER_URL="https://raw.githubusercontent.com/$REPO/main/install.sh"
TMP_INSTALLER="$(mktemp /tmp/clauck-install.XXXXXX.sh)"
trap 'rm -f "$TMP_INSTALLER"' EXIT

if ! curl -fsSL --max-time 30 "$INSTALLER_URL" -o "$TMP_INSTALLER"; then
    err "failed to download installer from $INSTALLER_URL"
    exit 3
fi

# Pass --yes so the installer doesn't prompt (we're non-interactive),
# and the branch env var so it clones the release tag, not main.
if CLAUCK_BRANCH="$LATEST_TAG" bash "$TMP_INSTALLER" --yes; then
    rm -f "$AVAILABLE_FILE"
    log "✓ update applied; now on $LATEST_TAG"
    exit 0
else
    err "installer exited non-zero; your prior install should still be intact"
    err "see installer output above; no state files were changed"
    exit 3
fi
