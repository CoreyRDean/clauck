#!/bin/bash
# install.sh — clauck installer for macOS
#
# Idempotent. Re-running skips steps already done.
#
# Supports two invocation modes:
#   1. Directly from a checked-out repo: `bash install.sh`
#   2. Piped from curl: `curl -sSL .../install.sh | bash`
#      (the script auto-clones the repo into a tempdir)
#
# Exit codes:
#   0  success
#   1  prerequisite missing
#   2  install failed
#   3  verification failed (installed but pipeline didn't prove out)

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────
# Config — edit REPO_URL when forking, or set env var at install time
# ──────────────────────────────────────────────────────────────────────────

REPO_URL="${CLAUCK_REPO:-https://github.com/CoreyRDean/clauck}"
REPO_BRANCH="${CLAUCK_BRANCH:-main}"

# ──────────────────────────────────────────────────────────────────────────
# Flags (parsed from args)
# ──────────────────────────────────────────────────────────────────────────

DRY_RUN=0
AUTO_YES=0
NO_MCP=0
# Channel: stable (default), nightly, or local. When installing from a local
# checkout, auto-overridden to "local" unless the user explicitly passed one.
# "local" installs don't participate in the auto-update flow — treating a
# dev-tree install as a tagged release would produce confusing "up-to-date"
# or "update-available" signals depending on the fork's head position.
CHANNEL=""
CHANNEL_EXPLICIT=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=1 ;;
        --yes|-y)   AUTO_YES=1 ;;
        --no-mcp)   NO_MCP=1 ;;
        --channel=*)
            CHANNEL="${arg#--channel=}"
            CHANNEL_EXPLICIT=1
            ;;
        --channel)
            echo "--channel requires a value (stable|nightly|local). Use --channel=<value>." >&2
            exit 2
            ;;
        --help|-h)
            cat <<HELP
Usage: install.sh [--dry-run] [--yes] [--channel=stable|nightly|local] [--no-mcp]

  --dry-run          Show what would be done without writing any files.
  --yes              Accept all defaults without prompting (for automation).
  --channel=<name>   Update channel: stable (default), nightly, or local.
                     When installing from a local checkout, defaults to "local"
                     unless this flag is explicitly set.
  --no-mcp           Skip auto-registering the MCP server in Claude Desktop and
                     Claude Code. Persisted in config; use 'clauck mcp --install'
                     to register manually later.

Environment variables:
  CLAUCK_REPO     Git clone URL (default: $REPO_URL)
  CLAUCK_BRANCH   Branch or tag to install (default: main)
HELP
            exit 0
            ;;
    esac
done

case "$CHANNEL" in
    ""|stable|nightly|local) ;;
    *)
        echo "invalid --channel: $CHANNEL (valid: stable, nightly, local)" >&2
        exit 2
        ;;
esac

# ──────────────────────────────────────────────────────────────────────────
# Output helpers
# ──────────────────────────────────────────────────────────────────────────

if [ -t 1 ]; then
    C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'
    C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
    C_OK=""; C_WARN=""; C_ERR=""; C_DIM=""; C_BOLD=""; C_RESET=""
fi

say()      { printf "%s→%s %s\n" "$C_BOLD" "$C_RESET" "$*"; }
ok()       { printf "  %s✓%s %s\n" "$C_OK" "$C_RESET" "$*"; }
warn()     { printf "  %s!%s %s\n" "$C_WARN" "$C_RESET" "$*"; }
fail()     { printf "  %s✗%s %s\n" "$C_ERR" "$C_RESET" "$*" >&2; }
die()      { fail "$*"; exit "${2:-2}"; }
section()  { printf "\n%s%s%s\n" "$C_BOLD" "$*" "$C_RESET"; }

# prompt <message> <default y|n> → returns 0 for yes, 1 for no.
# Reads from /dev/tty so it works under curl | bash (stdin is the pipe).
prompt() {
    local msg="$1" default="${2:-y}"
    if [ "$AUTO_YES" -eq 1 ]; then return 0; fi
    if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
    local hint="[Y/n]"
    [ "$default" = "n" ] && hint="[y/N]"
    printf "\n  %s %s " "$msg" "$hint"
    local resp
    if read -r resp </dev/tty 2>/dev/null; then
        resp="${resp:-$default}"
    else
        resp="$default"
    fi
    # Portable lowercase (bash 3.2 on macOS doesn't support ${var,,}).
    resp="$(printf '%s' "$resp" | tr '[:upper:]' '[:lower:]')"
    case "$resp" in
        y|yes) return 0 ;;
        *)     return 1 ;;
    esac
}

# dry-run wrapper: if DRY_RUN, print what would happen; otherwise execute.
run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf "  %s[dry-run]%s would run: %s\n" "$C_DIM" "$C_RESET" "$*"
        return 0
    fi
    "$@"
}

# ──────────────────────────────────────────────────────────────────────────
# Locate the repo: if script runs from a checked-out tree, use it;
# otherwise clone into a tempdir.
# ──────────────────────────────────────────────────────────────────────────

resolve_repo() {
    # NOTE: this function is called inside a command substitution — it runs in
    # a subshell. Do NOT set EXIT traps here (they fire when the subshell exits,
    # deleting files before the parent can use them). Cleanup is handled in main().
    local script_dir=""
    if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "bash" ]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
    fi
    if [ -n "$script_dir" ] && [ -f "$script_dir/lib/scheduler.py" ]; then
        echo "$script_dir"
        return 0
    fi
    # Piped install → clone into a temp dir.
    if ! command -v git >/dev/null 2>&1; then
        fail "git not found. Install Xcode Command Line Tools:" >&2
        fail "  xcode-select --install" >&2
        fail "Then re-run this installer." >&2
        return 1
    fi
    local tmp
    tmp="$(mktemp -d /tmp/clauck.XXXXXX)"
    say "Cloning $REPO_URL (branch $REPO_BRANCH) → $tmp" >&2
    if ! git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$tmp/repo" >/dev/null 2>&1; then
        fail "failed to clone $REPO_URL (branch $REPO_BRANCH)" >&2
        return 1
    fi
    echo "$tmp/repo"
}

# ──────────────────────────────────────────────────────────────────────────
# Preflight checks
# ──────────────────────────────────────────────────────────────────────────

preflight() {
    section "Preflight checks"

    [ "$(uname -s)" = "Darwin" ] || die "this installer only supports macOS (Darwin); got $(uname -s)" 1
    ok "macOS ($(uname -s) $(uname -r))"

    [ -x /bin/zsh ] || die "/bin/zsh not found — required by run-job.sh and the LaunchAgent" 1
    ok "zsh at /bin/zsh"

    [ -x /usr/bin/python3 ] || die "/usr/bin/python3 not found — Apple's bundled python3 is required" 1
    ok "python3 at /usr/bin/python3 ($("/usr/bin/python3" --version 2>&1))"

    if command -v claude >/dev/null 2>&1; then
        ok "claude CLI at $(command -v claude) ($(claude --version 2>/dev/null | head -1 || echo 'version check failed'))"
    else
        warn "claude CLI not on PATH — install from https://docs.claude.com/en/docs/claude-code then re-run this script"
        die "claude CLI required" 1
    fi

    [ -n "${HOME:-}" ] || die "\$HOME is not set" 1
    [ -d "$HOME" ] || die "\$HOME ($HOME) is not a directory" 1
    ok "HOME=$HOME"

    [ -n "${USER:-}" ] || die "\$USER is not set (needed for LaunchAgent label)" 1
    # Guard against weird characters in USER (launchd label restrictions)
    [[ "$USER" =~ ^[a-zA-Z0-9._-]+$ ]] || die "\$USER contains unsupported characters: $USER" 1
    ok "USER=$USER"
}

# ──────────────────────────────────────────────────────────────────────────
# Directory layout
# ──────────────────────────────────────────────────────────────────────────

make_dirs() {
    section "Creating directory layout"
    local dirs=(
        "$HOME/.clauck"
        "$HOME/.clauck/.state"
        "$HOME/.claude"
        "$HOME/.claude/skills/clauck"
        "$HOME/.claude/hooks"
        "$HOME/Library/LaunchAgents"
    )
    local d
    for d in "${dirs[@]}"; do
        if [ -d "$d" ]; then
            ok "exists: $d"
        else
            mkdir -p "$d" && ok "created: $d"
        fi
    done
}

# ──────────────────────────────────────────────────────────────────────────
# Legacy migration: ~/.claude/scheduled-jobs → ~/.clauck
# ──────────────────────────────────────────────────────────────────────────

migrate_legacy() {
    local legacy="$HOME/.claude/scheduled-jobs"
    local target="$HOME/.clauck"

    # Only migrate if the legacy directory exists and the new one doesn't
    # have a version file yet (avoids re-migrating on idempotent re-runs).
    [ -d "$legacy" ] || return 0
    [ -f "$target/.version" ] && return 0

    section "Migrating from ~/.claude/scheduled-jobs → ~/.clauck"

    # User job files (flat .md)
    for f in "$legacy"/*.md; do
        [ -f "$f" ] || continue
        local name; name="$(basename "$f")"
        cp -p "$f" "$target/$name" && ok "migrated job: $name"
    done

    # Module job directories (contain JOB.md)
    for d in "$legacy"/*/; do
        [ -d "$d" ] || continue
        local name; name="$(basename "$d")"
        # Skip hidden dirs (.state, etc.)
        case "$name" in .*) continue ;; esac
        [ -f "$d/JOB.md" ] || continue
        cp -rp "$d" "$target/$name" && ok "migrated module: $name/"
    done

    # State directory
    [ -d "$legacy/.state" ] && cp -rp "$legacy/.state" "$target/.state" && ok "migrated .state/"

    # Config + metadata files
    local meta
    for meta in .clauck.config.json .version .build-source; do
        [ -f "$legacy/$meta" ] && cp -p "$legacy/$meta" "$target/$meta"
    done

    # Job logs
    for f in "$legacy"/*-[0-9]*.log; do
        [ -f "$f" ] || continue
        cp -p "$f" "$target/$(basename "$f")"
    done

    # Global prompt (was at a separate path)
    [ -f "$HOME/.claude/scheduled-jobs-prompt.md" ] && \
        cp -p "$HOME/.claude/scheduled-jobs-prompt.md" "$target/prompt.md"

    # Scheduler logs
    for f in "$legacy"/.scheduler-*.log; do
        [ -f "$f" ] || continue
        cp -p "$f" "$target/$(basename "$f")"
    done

    # Leave breadcrumb
    cat > "$legacy/MIGRATED.md" <<MIGEOF
# clauck has moved

All clauck data has been migrated to \`~/.clauck/\`.

This directory is no longer used. You can safely delete it:

    rm -rf ~/.claude/scheduled-jobs

Migration date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
MIGEOF
    ok "migration complete — legacy data preserved with breadcrumb"
}

# ──────────────────────────────────────────────────────────────────────────
# File installation (never clobber user-edited job prompts)
# ──────────────────────────────────────────────────────────────────────────

install_files() {
    local repo="$1"
    section "Installing runtime scripts and prompt"

    install_file() {
        local src="$1"
        local dst="$2"
        local mode="${3:-}"
        run cp "$src" "$dst"
        [ -n "$mode" ] && run chmod "$mode" "$dst"
        ok "installed: $dst"
    }

    install_file "$repo/lib/scheduler.py"             "$HOME/.clauck/scheduler.py"   755
    install_file "$repo/lib/run-job.sh"               "$HOME/.clauck/run-job.sh"     755
    install_file "$repo/lib/trigger-job.sh"           "$HOME/.clauck/trigger-job.sh" 755
    install_file "$repo/lib/update-check.sh"          "$HOME/.clauck/update-check.sh" 755

    # Install the clauck CLI to ~/.local/bin (same location as claude CLI).
    run mkdir -p "$HOME/.local/bin"
    install_file "$repo/lib/clauck"                   "$HOME/.local/bin/clauck"                     755
    install_file "$repo/lib/dag-runner.py"            "$HOME/.clauck/dag-runner.py"  755
    install_file "$repo/lib/clauck-mcp"               "$HOME/.clauck/clauck-mcp"     755
    install_file "$repo/lib/prompt.md"                "$HOME/.clauck/prompt.md"      644
    install_file "$repo/lib/scheduled-jobs-notice.sh" "$HOME/.claude/hooks/scheduled-jobs-notice.sh" 755
    # Ship uninstall.sh alongside the runtime so `clauck uninstall` always has
    # a local, version-matched copy to invoke. Running the remote latest
    # against an older local install can leave orphaned files behind.
    install_file "$repo/uninstall.sh"                 "$HOME/.clauck/uninstall.sh"   755

    # Record the installed version for the auto-updater.
    #
    # The recorded value should be the actual tag this install came from,
    # not just the contents of the VERSION file. This matters for nightlies:
    # a nightly cut from main HEAD has VERSION = "v1.5.7" but the tag is
    # "v1.5.7-1681580000". Update-check compares .version to the latest
    # nightly tag, so .version must hold the timestamped form for nightly
    # installs to detect successive nightlies.
    #
    # Precedence: CLAUCK_BRANCH (if it looks like a tag) > VERSION file.
    local recorded_version=""
    case "$REPO_BRANCH" in
        v[0-9]*) recorded_version="$REPO_BRANCH" ;;
    esac
    if [ -z "$recorded_version" ] && [ -f "$repo/VERSION" ]; then
        recorded_version="$(cat "$repo/VERSION" | tr -d '[:space:]')"
    fi
    if [ -n "$recorded_version" ]; then
        if [ "$DRY_RUN" -eq 0 ]; then
            printf '%s\n' "$recorded_version" > "$HOME/.clauck/.version"
        fi
        ok "recorded version: $recorded_version"
    fi

    # Record the build source so `clauck version` and update-check can tell
    # a local-tree install from a release install, and so update-check picks
    # the right channel (stable release tag vs rolling nightly tag).
    local source_type="release"
    local git_sha="null"
    # $2 is install source from caller: "local" or "clone"; default to clone.
    if [ "${2:-clone}" = "local" ]; then
        source_type="local"
        # Try to capture the git SHA from the working tree for traceability.
        if command -v git >/dev/null 2>&1 && [ -d "$repo/.git" ]; then
            git_sha="\"$(cd "$repo" && git rev-parse HEAD 2>/dev/null || echo unknown)\""
            local dirty
            dirty="$(cd "$repo" && git status --porcelain 2>/dev/null | head -1 || true)"
            if [ -n "$dirty" ]; then
                git_sha="\"$(cd "$repo" && git rev-parse HEAD 2>/dev/null || echo unknown)-dirty\""
            fi
        fi
    elif [ "$CHANNEL" = "nightly" ] || [ "$REPO_BRANCH" = "nightly" ]; then
        source_type="nightly"
        if command -v git >/dev/null 2>&1 && [ -d "$repo/.git" ]; then
            git_sha="\"$(cd "$repo" && git rev-parse HEAD 2>/dev/null || echo unknown)\""
        fi
    fi

    # Resolve the effective channel at this point. If the user didn't pass
    # --channel explicitly, infer from the source type (local → local,
    # nightly → nightly, release → stable).
    local effective_channel="$CHANNEL"
    if [ -z "$effective_channel" ]; then
        case "$source_type" in
            local)   effective_channel="local" ;;
            nightly) effective_channel="nightly" ;;
            *)       effective_channel="stable" ;;
        esac
    fi

    local bs_dst="$HOME/.clauck/.build-source"
    if [ "$DRY_RUN" -eq 0 ]; then
        local bs_ts
        bs_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        cat > "$bs_dst" <<BSEOF
{
  "channel": "$effective_channel",
  "source": "$source_type",
  "git_sha": $git_sha,
  "installed_at": "$bs_ts",
  "repo": "$(echo "$REPO_URL" | sed 's|.*github\.com/||; s|\.git$||')",
  "branch": "$REPO_BRANCH"
}
BSEOF
    fi
    ok "recorded build source: channel=$effective_channel, source=$source_type"

    # Write config: respect auto-update prompt decision + persist fork URL.
    # Never overwrite an existing config — user preferences are sacrosanct.
    local cfg_dst="$HOME/.clauck/.clauck.config.json"
    if [ -f "$cfg_dst" ]; then
        ok "preserving existing config: $cfg_dst"
    else
        # Derive the short owner/repo form for the config file.
        local repo_short
        repo_short="$(echo "$REPO_URL" | sed 's|.*github\.com/||; s|\.git$||')"
        local auto_enabled="true"
        [ "${ENABLE_AUTO_UPDATE:-1}" -eq 0 ] && auto_enabled="false"
        if [ "$DRY_RUN" -eq 0 ]; then
            cat > "$cfg_dst" <<CFGEOF
{
  "repo": "$repo_short",
  "auto_update": {
    "enabled": $auto_enabled,
    "check_interval_seconds": 3600,
    "auto_apply": false,
    "channel": "$effective_channel"
  }
}
CFGEOF
        fi
        ok "wrote config: $cfg_dst (auto_update.enabled=$auto_enabled, channel=$effective_channel, repo=$repo_short)"
    fi

    section "Installing skill"
    # Clean up old skill dir name if upgrading from pre-v1.2
    [ -d "$HOME/.claude/skills/scheduled-jobs" ] && rm -rf "$HOME/.claude/skills/scheduled-jobs" && ok "migrated old skill dir"
    run mkdir -p "$HOME/.claude/skills/clauck"
    install_file "$repo/skill/clauck/SKILL.md" "$HOME/.claude/skills/clauck/SKILL.md" 644

    # Ship the marketplace (pre-made job catalog) into the skill dir so agents can
    # browse it offline. Always overwrite — marketplace updates are expected.
    if [ -d "$repo/marketplace" ]; then
        local mkt_dst="$HOME/.claude/skills/clauck/marketplace"
        rm -rf "$mkt_dst"
        cp -R "$repo/marketplace" "$mkt_dst"
        ok "installed marketplace → $mkt_dst ($(ls "$mkt_dst/"*.md 2>/dev/null | wc -l | tr -d ' ') job(s))"
    fi

    section "Installing default jobs"
    local job
    for job in "$repo/jobs/"*.md; do
        [ -f "$job" ] || continue
        local name; name="$(basename "$job")"
        local dst="$HOME/.clauck/$name"
        if [ ! -f "$dst" ]; then
            install_file "$job" "$dst" 644
            continue
        fi
        # Compare content — if identical, skip silently.
        if diff -q "$job" "$dst" >/dev/null 2>&1; then
            ok "up-to-date: $dst"
            continue
        fi
        # Content differs. Back up user's version, overwrite with shipped default.
        # Rationale: default jobs (heartbeat, clauck-work) are infrastructure —
        # upgrades should propagate. User customizations are preserved as .backup.
        local backup="${dst}.backup-$(date -u +%Y%m%dT%H%M%SZ)"
        cp "$dst" "$backup"
        install_file "$job" "$dst" 644
        warn "updated default job: $dst (your previous copy saved to: $backup)"
    done
}

# ──────────────────────────────────────────────────────────────────────────
# LaunchAgent (per-user plist with substitutions)
# ──────────────────────────────────────────────────────────────────────────

install_plist() {
    local repo="$1"
    section "Installing LaunchAgent"

    local plist_src="$repo/templates/com.USERNAME.claude-scheduler.plist"
    local plist_dst="$HOME/Library/LaunchAgents/com.$USER.claude-scheduler.plist"

    # Substitute USERNAME + HOME using Python (robust against sed quoting issues)
    /usr/bin/python3 - <<EOF
import os, pathlib
src = pathlib.Path("$plist_src").read_text()
out = src.replace("__USERNAME__", os.environ["USER"]).replace("__HOME__", os.environ["HOME"])
pathlib.Path("$plist_dst").write_text(out)
EOF
    ok "wrote: $plist_dst"

    # Unload any prior instance before loading (idempotent re-install).
    if launchctl list 2>/dev/null | grep -q "com.$USER.claude-scheduler"; then
        launchctl unload "$plist_dst" >/dev/null 2>&1 || true
        ok "unloaded prior instance"
    fi
    launchctl load -w "$plist_dst" \
        || die "launchctl load failed — inspect $plist_dst" 2
    ok "loaded: com.$USER.claude-scheduler"
}

# ──────────────────────────────────────────────────────────────────────────
# settings.json — register SessionStart hook idempotently
# ──────────────────────────────────────────────────────────────────────────

patch_settings() {
    section "Registering SessionStart hook in ~/.claude/settings.json"

    local settings="$HOME/.claude/settings.json"
    local hook_cmd="bash $HOME/.claude/hooks/scheduled-jobs-notice.sh"

    /usr/bin/python3 - "$settings" "$hook_cmd" <<'EOF'
import json, sys, pathlib

path = pathlib.Path(sys.argv[1])
cmd  = sys.argv[2]

data = {}
if path.exists():
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print(f"  ! existing settings.json could not be parsed ({e}); refusing to overwrite", file=sys.stderr)
        sys.exit(2)

hooks = data.setdefault("hooks", {})
session_start = hooks.setdefault("SessionStart", [])

# Find or create the "startup" matcher block.
startup_block = None
for block in session_start:
    if isinstance(block, dict) and block.get("matcher") == "startup":
        startup_block = block
        break
if startup_block is None:
    startup_block = {"matcher": "startup", "hooks": []}
    session_start.append(startup_block)

# Check if our hook is already registered (by command string).
existing = startup_block.setdefault("hooks", [])
already = any(isinstance(h, dict) and h.get("command") == cmd for h in existing)
if already:
    print("  ✓ hook already registered; leaving untouched")
else:
    existing.append({"type": "command", "command": cmd})
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  ✓ registered SessionStart hook → {cmd}")
EOF
}

# ──────────────────────────────────────────────────────────────────────────
# MCP server registration (Claude Desktop + Claude Code)
# ──────────────────────────────────────────────────────────────────────────

install_mcp() {
    section "Registering MCP server"

    local clauck_bin="$HOME/.local/bin/clauck"
    if [ ! -x "$clauck_bin" ]; then
        warn "clauck CLI not found at $clauck_bin — skipping MCP registration"
        return 0
    fi

    if [ "$NO_MCP" -eq 1 ]; then
        # Persist the opt-out so update-check.sh --apply (which re-runs install.sh)
        # also skips it on future updates.
        local cfg_dst="$HOME/.clauck/.clauck.config.json"
        if [ "$DRY_RUN" -eq 0 ] && [ -f "$cfg_dst" ]; then
            /usr/bin/python3 - "$cfg_dst" <<'EOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text()) if p.exists() else {}
d["no_mcp_install"] = True
p.write_text(json.dumps(d, indent=2) + "\n")
EOF
        fi
        ok "MCP registration skipped (--no-mcp); use 'clauck mcp --install' to register later"
        return 0
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        ok "[dry-run] would run: clauck mcp --install"
        return 0
    fi

    "$clauck_bin" mcp --install 2>&1 | sed 's/^/  /' || warn "MCP install step reported an error (non-fatal)"
}

# ──────────────────────────────────────────────────────────────────────────
# Verification: fire heartbeat, wait for exit_code=0 in the log
# ──────────────────────────────────────────────────────────────────────────

verify() {
    section "Verifying pipeline (firing heartbeat ad-hoc)"

    local trigger="$HOME/.clauck/trigger-job.sh"
    [ -x "$trigger" ] || die "trigger-job.sh not executable at $trigger" 3

    # Snapshot existing logs so we can detect a new one.
    local before_count
    before_count=$(ls "$HOME/.clauck/"heartbeat-*.log 2>/dev/null | wc -l | tr -d ' ')

    "$trigger" heartbeat >/dev/null 2>&1 \
        || die "trigger-job.sh heartbeat failed to dispatch" 3

    # Poll for a new log to appear and complete. Up to 90s.
    local elapsed=0 interval=3 max=90 latest=""
    while [ "$elapsed" -lt "$max" ]; do
        sleep "$interval"
        elapsed=$((elapsed + interval))
        latest=$(ls -t "$HOME/.clauck/"heartbeat-*.log 2>/dev/null | head -1 || true)
        if [ -n "$latest" ]; then
            local current_count
            current_count=$(ls "$HOME/.clauck/"heartbeat-*.log 2>/dev/null | wc -l | tr -d ' ')
            if [ "$current_count" -gt "$before_count" ] && grep -q "exit_code=" "$latest"; then
                break
            fi
        fi
    done

    if [ -z "$latest" ] || ! grep -q "exit_code=" "$latest"; then
        fail "heartbeat did not complete within ${max}s"
        fail "check: $latest"
        fail "check: $HOME/.clauck/.scheduler-stderr.log"
        die "verification failed" 3
    fi

    local exit_line
    exit_line=$(grep "exit_code=" "$latest" | tail -1)
    case "$exit_line" in
        *"exit_code=0"*)
            ok "heartbeat completed: $exit_line"
            ok "log: $latest"
            local result
            result=$(grep -o '"result":"[^"]*"' "$latest" 2>/dev/null | head -1 | sed 's/"result":"//;s/"$//')
            [ -n "$result" ] && ok "result: $result"
            ;;
        *)
            fail "heartbeat exit code non-zero: $exit_line"
            fail "log tail:"
            tail -20 "$latest" | sed 's/^/    /'
            die "verification failed" 3
            ;;
    esac
}

# ──────────────────────────────────────────────────────────────────────────
# Success banner
# ──────────────────────────────────────────────────────────────────────────

banner() {
    cat <<EOF

${C_BOLD}═══════════════════════════════════════════════════════════════${C_RESET}
${C_OK}${C_BOLD}✓ clauck installed and verified${C_RESET}
${C_BOLD}═══════════════════════════════════════════════════════════════${C_RESET}

  Version         $(cat "$HOME/.clauck/.version" 2>/dev/null | tr -d '[:space:]' || echo unknown)
  Scheduler       com.$USER.claude-scheduler (loaded, tick interval 60s)
  Jobs directory  ~/.clauck/
  Skill           ~/.claude/skills/clauck/SKILL.md
  Marketplace     ~/.claude/skills/clauck/marketplace/
  Hook            ~/.claude/hooks/scheduled-jobs-notice.sh
  Config          ~/.clauck/.clauck.config.json

${C_BOLD}Default job installed:${C_RESET}
  heartbeat (hourly liveness check, ~\$1/month at current Haiku pricing)

${C_BOLD}Auto-updates:${C_RESET}
  Checking GitHub Releases every hour. Detects new versions; does NOT apply
  them automatically (security-conscious default). To change, edit the config
  file above or run: ${C_BOLD}~/.clauck/update-check.sh --help${C_RESET}

${C_BOLD}What just happened:${C_RESET}
  Your Claude CLI was just launched by a launchd-spawned shell, loaded its
  tool surface, produced a "heartbeat ok" result, wrote a log file, and
  exited with code 0. That is end-to-end proof that the system works.

${C_BOLD}Get started (through Claude):${C_RESET}
  Open Claude Code in any terminal. A SessionStart hook will tell your
  agent about clauck and the marketplace automatically.
  ${C_BOLD}"What clauck jobs can I add from the marketplace?"${C_RESET}
  ${C_BOLD}"Schedule a job to summarize my Slack every morning"${C_RESET}
  ${C_BOLD}"What's running? Anything fail recently?"${C_RESET}

${C_BOLD}Get started (through the clauck CLI):${C_RESET}
  clauck is also a standalone CLI at ~/.local/bin/clauck. Each command
  launches a specialized Claude session with injected instructions tuned
  for that task — often better results than asking through a general
  session.

  ${C_BOLD}clauck list${C_RESET}                          ${C_DIM}# all jobs, status, next fire time${C_RESET}
  ${C_BOLD}clauck marketplace${C_RESET}                   ${C_DIM}# browse + install pre-made jobs${C_RESET}
  ${C_BOLD}clauck fire <name>${C_RESET}                   ${C_DIM}# trigger any job right now${C_RESET}
  ${C_BOLD}clauck doctor${C_RESET}                        ${C_DIM}# diagnose system health (specialized agent)${C_RESET}
  ${C_BOLD}clauck logs <name>${C_RESET}                   ${C_DIM}# recent runs with costs${C_RESET}
  ${C_BOLD}clauck <anything>${C_RESET}                    ${C_DIM}# plain English — uses a specialized agent${C_RESET}

  That last one is powerful: ${C_BOLD}clauck change heartbeat to every 2 hours${C_RESET}
  works because clauck routes natural language through an interpreter
  with full context about your jobs, schedules, and system state.

  ${C_DIM}To uninstall:${C_RESET}
  ${C_BOLD}clauck uninstall${C_RESET}                     ${C_DIM}# preserves jobs, state, and logs${C_RESET}
  ${C_BOLD}clauck uninstall --wipe${C_RESET}              ${C_DIM}# also removes ~/.clauck${C_RESET}

${C_DIM}Full docs: ~/.claude/skills/clauck/SKILL.md${C_RESET}

EOF
}

star_prompt() {
    if [ "$AUTO_YES" -eq 1 ] || [ "$DRY_RUN" -eq 1 ]; then return 0; fi

    # Derive the short owner/repo form for starring
    local repo_short
    repo_short="$(echo "$REPO_URL" | sed 's|.*github\.com/||; s|\.git$||')"

    if prompt "Star $repo_short on GitHub? (helps others discover clauck)" "y"; then
        # Try gh CLI first (most likely to work if user has it)
        if command -v gh >/dev/null 2>&1; then
            if gh repo star "$repo_short" >/dev/null 2>&1; then
                ok "starred $repo_short"
                return 0
            fi
        fi
        # Fallback: open the repo page in the browser
        if command -v open >/dev/null 2>&1; then
            open "https://github.com/$repo_short" 2>/dev/null
            say "Opened the repo in your browser — click the star button if you'd like"
        else
            say "Star it here: https://github.com/$repo_short"
        fi
    fi
}

# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

confirm_plan() {
    local repo="$1"
    local version=""
    [ -f "$repo/VERSION" ] && version=" ($(cat "$repo/VERSION" | tr -d '[:space:]'))"

    local legacy_note=""
    if [ -d "$HOME/.claude/scheduled-jobs" ] && [ ! -f "$HOME/.clauck/.version" ]; then
        legacy_note="
  ${C_BOLD}${C_WARN}migrate${C_RESET}  Migrate jobs, state, and logs from ~/.claude/scheduled-jobs → ~/.clauck"
    fi

    cat <<EOF

${C_BOLD}This installer will:${C_RESET}
  ${C_DIM}core${C_RESET}  Place scheduler + executor scripts in ~/.clauck/
  ${C_DIM}core${C_RESET}  Register a LaunchAgent (com.$USER.claude-scheduler, ticks every 60s)
  ${C_DIM}opt ${C_RESET}  Install a Claude Code skill at ~/.claude/skills/clauck/
  ${C_DIM}opt ${C_RESET}  Install a pre-made job marketplace at ~/.claude/skills/clauck/marketplace/
  ${C_DIM}opt ${C_RESET}  Register a SessionStart hook in ~/.claude/settings.json
  ${C_DIM}opt ${C_RESET}  Register the MCP server in Claude Desktop and Claude Code (skip with --no-mcp)
  ${C_DIM}opt ${C_RESET}  Install the 'heartbeat' job (~\$1/month on Haiku)${legacy_note}

  Source: ${REPO_URL}${version}

EOF
    prompt "Proceed with installation?" "y" || { say "Cancelled."; exit 0; }
}

prompt_auto_update() {
    ENABLE_AUTO_UPDATE=1

    if [ "$AUTO_YES" -eq 1 ] || [ "$DRY_RUN" -eq 1 ]; then
        return 0
    fi

    cat <<EOF

${C_BOLD}Auto-updates${C_RESET}
  The scheduler can check GitHub Releases hourly for new versions.
  It ${C_BOLD}never${C_RESET} applies updates automatically — it only notifies you.
  (You can enable auto-apply later in the config file if you choose.)

EOF
    if ! prompt "Enable hourly update checks?" "y"; then
        ENABLE_AUTO_UPDATE=0
        ok "auto-updates disabled — you can re-enable in the config file anytime"
    fi
}

main() {
    printf "%sclauck installer%s\n" "$C_BOLD" "$C_RESET"
    [ "$DRY_RUN" -eq 1 ] && printf "  %s[DRY RUN — no files will be written]%s\n" "$C_WARN" "$C_RESET"

    preflight

    local repo
    repo="$(resolve_repo)" || die "could not locate repo source" 1
    ok "source: $repo"

    # Classify the install source. A /tmp/clauck.* path came from resolve_repo's
    # clone path (curl | bash). Anything else is a local checkout — the user ran
    # `bash install.sh` from their own working tree.
    local install_source="clone"
    if [[ "$repo" != /tmp/clauck.* ]]; then
        install_source="local"
    fi

    # If resolve_repo cloned into /tmp, register cleanup for when the installer exits.
    if [[ "$repo" == /tmp/* ]]; then
        local tmproot="${repo%/repo}"  # /tmp/clauck.XXXXX
        trap "rm -rf '$tmproot'" EXIT
    fi

    confirm_plan "$repo"
    prompt_auto_update

    make_dirs
    migrate_legacy
    install_files "$repo" "$install_source"
    install_plist "$repo"
    patch_settings
    install_mcp
    verify
    banner
    star_prompt
}

main "$@"
