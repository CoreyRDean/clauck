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
# Config file (JSON) at: ~/.clauck/.clauck.config.json
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
_CONFIG_CHANNEL=""
_CFG="$HOME/.clauck/.clauck.config.json"
if [ -f "$_CFG" ]; then
    _CONFIG_REPO=$(/usr/bin/python3 -c "
import json, sys
try: print(json.load(open('$_CFG')).get('repo',''))
except: pass
" 2>/dev/null || true)
    _CONFIG_CHANNEL=$(/usr/bin/python3 -c "
import json, sys
try:
    d = json.load(open('$_CFG'))
    print(d.get('auto_update', {}).get('channel', ''))
except: pass
" 2>/dev/null || true)
fi
REPO="${CLAUCK_REPO:-${_CONFIG_REPO:-CoreyRDean/clauck}}"
# Channel: stable (default), nightly, or local. local = dev tree install,
# skip update checks entirely.
CHANNEL="${CLAUCK_CHANNEL:-${_CONFIG_CHANNEL:-stable}}"

STATE_DIR="$HOME/.clauck/.state"
VERSION_FILE="$HOME/.clauck/.version"
AVAILABLE_FILE="$STATE_DIR/.update-available"
LAST_CHECK_FILE="$STATE_DIR/.update-last-check"
CONFIG_FILE="$HOME/.clauck/.clauck.config.json"

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

[ -d "$HOME/.clauck" ] \
    || { err "clauck is not installed at ~/.clauck"; exit 2; }
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
# Channel gate
# ──────────────────────────────────────────────────────────────────────────
# local-channel installs were built from a developer's working tree. We
# can't meaningfully compare against published releases — the tag on disk
# bears no relation to what's on GitHub. Skip the check entirely so we
# don't spam fake "update available" markers.

if [ "$CHANNEL" = "local" ]; then
    rm -f "$AVAILABLE_FILE"
    date +%s > "$LAST_CHECK_FILE"
    log "✓ local build — update check skipped ($INSTALLED)"
    log "  (this install was built from a local checkout; update via your repo instead)"
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────────
# Fetch latest tag for the selected channel
# Uses unauthenticated GitHub API (60 req/hr/IP — far more than we'd ever use).
# Falls back to `gh` if available and curl fails.
#
# Channel → endpoint:
#   stable  → /releases/latest    (GitHub auto-filters prereleases out)
#   nightly → /releases (paged)   (we pick the first prerelease=true entry,
#                                  which is the newest by published_at desc)
#
# Nightly tags are immutable and timestamped: v{VERSION}-{unix_ts}.
# We treat the tag name itself as the comparison key — newer nightlies have
# strictly greater timestamps, so simple string inequality detects an update.
# ──────────────────────────────────────────────────────────────────────────

LATEST_TAG=""
LATEST_SHA=""
if [ "$CHANNEL" = "stable" ]; then
    API_URL="https://api.github.com/repos/$REPO/releases/latest"
else
    API_URL="https://api.github.com/repos/$REPO/releases?per_page=20"
fi

if [ "$CHANNEL" != "stable" ] && [ "$CHANNEL" != "nightly" ]; then
    err "unknown channel: $CHANNEL (valid: stable, nightly, local)"
    exit 2
fi

if command -v curl >/dev/null 2>&1; then
    RESPONSE="$(curl -fsSL --max-time 10 -H 'Accept: application/vnd.github+json' "$API_URL" 2>/dev/null || true)"
    if [ -n "$RESPONSE" ]; then
        if [ "$CHANNEL" = "stable" ]; then
            LATEST_TAG="$(/usr/bin/python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get("tag_name", ""))
except Exception:
    print("")
' <<<"$RESPONSE")"
        else
            # Find newest prerelease in the page. The /releases endpoint
            # returns sorted by created_at desc, so the first prerelease
            # entry is what we want.
            read -r LATEST_TAG LATEST_SHA <<<"$(/usr/bin/python3 -c '
import json, sys
try:
    arr = json.loads(sys.stdin.read())
    if not isinstance(arr, list):
        arr = []
    for r in arr:
        if r.get("prerelease"):
            tag = r.get("tag_name", "")
            sha = r.get("target_commitish", "") or r.get("published_at", "")
            print(f"{tag} {sha}")
            break
    else:
        print(" ")
except Exception:
    print(" ")
' <<<"$RESPONSE")"
        fi
    fi
fi

if [ -z "$LATEST_TAG" ] && command -v gh >/dev/null 2>&1; then
    # gh is authenticated and provides a nicer interface; try as fallback.
    if [ "$CHANNEL" = "stable" ]; then
        LATEST_TAG="$(gh release view --repo "$REPO" --json tagName --jq .tagName 2>/dev/null || true)"
    else
        # gh release list returns most recent first; filter to prereleases.
        LATEST_TAG="$(gh release list --repo "$REPO" --limit 20 --json tagName,isPrerelease \
            --jq 'map(select(.isPrerelease))[0].tagName' 2>/dev/null || true)"
    fi
fi

date +%s > "$LAST_CHECK_FILE"

if [ -z "$LATEST_TAG" ]; then
    err "could not fetch latest $CHANNEL release from https://github.com/$REPO"
    err "(this is usually transient — check your network, or see if the repo has a '$CHANNEL' release yet)"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────
# Compare
# ──────────────────────────────────────────────────────────────────────────
# Stable: simple tag equality (v1.5.6 vs v1.5.7).
# Nightly: tag names are timestamped (v1.5.7-1681580000) and immutable, so
#   simple inequality detects an update. We still compare to the installed
#   tag stored in .version (which is rewritten on every install/apply to
#   the actual tag pulled, not the VERSION-file value).

if [ "$INSTALLED" = "$LATEST_TAG" ]; then
    rm -f "$AVAILABLE_FILE"
    log "✓ up-to-date on $CHANNEL ($INSTALLED)"
    exit 0
fi

# Write the "update available" marker so the SessionStart hook can mention it.
cat > "$AVAILABLE_FILE" <<EOF
{
  "installed": "$INSTALLED",
  "latest": "$LATEST_TAG",
  "channel": "$CHANNEL",
  "latest_sha": "$LATEST_SHA",
  "detected_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "release_url": "https://github.com/$REPO/releases/tag/$LATEST_TAG"
}
EOF

if [ "$CHANNEL" = "nightly" ]; then
    log "nightly update available ($INSTALLED @ $CURRENT_NIGHTLY_SHA → @ $LATEST_SHA)"
else
    log "update available: $INSTALLED → $LATEST_TAG"
fi
log "release notes:    https://github.com/$REPO/releases/tag/$LATEST_TAG"

if [ "$APPLY" -eq 0 ]; then
    log ""
    log "To install this release now, run:"
    log "  clauck update --apply"
    log ""
    log "To enable auto-apply (applies new releases automatically), edit:"
    log "  $CONFIG_FILE"
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────────
# Apply: run install.sh from the target ref (release tag for stable,
# nightly tag for nightly channel).
# ──────────────────────────────────────────────────────────────────────────

log "applying $CHANNEL update $INSTALLED → $LATEST_TAG ..."
# Fetch install.sh from main HEAD — it always has the latest bug fixes for
# the install process itself. CLAUCK_BRANCH tells the installer which ref
# to clone for the payload files.
INSTALLER_URL="https://raw.githubusercontent.com/$REPO/main/install.sh"
TMP_INSTALLER="$(mktemp /tmp/clauck-install.XXXXXX.sh)"
trap 'rm -f "$TMP_INSTALLER"' EXIT

if ! curl -fsSL --max-time 30 "$INSTALLER_URL" -o "$TMP_INSTALLER"; then
    err "failed to download installer from $INSTALLER_URL"
    exit 3
fi

# For stable, use the release tag. For nightly, use the nightly tag itself
# (GitHub resolves it to the current main HEAD at apply time).
if CLAUCK_BRANCH="$LATEST_TAG" bash "$TMP_INSTALLER" --yes --channel="$CHANNEL"; then
    rm -f "$AVAILABLE_FILE"
    log "✓ $CHANNEL update applied; now on $LATEST_TAG"
    exit 0
else
    err "installer exited non-zero; your prior install should still be intact"
    err "see installer output above; no state files were changed"
    exit 3
fi
