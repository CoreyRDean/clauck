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
for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=1 ;;
        --yes|-y)   AUTO_YES=1 ;;
        --help|-h)
            cat <<HELP
Usage: install.sh [--dry-run] [--yes]

  --dry-run   Show what would be done without writing any files.
  --yes       Accept all defaults without prompting (for automation).

Environment variables:
  CLAUCK_REPO     Git clone URL (default: $REPO_URL)
  CLAUCK_BRANCH   Branch or tag to install (default: main)
HELP
            exit 0
            ;;
    esac
done

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
        "$HOME/.claude"
        "$HOME/.claude/scheduled-jobs"
        "$HOME/.claude/scheduled-jobs/.state"
        "$HOME/.claude/skills/scheduled-jobs"
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

    install_file "$repo/lib/scheduler.py"             "$HOME/.claude/scheduled-jobs/scheduler.py"   755
    install_file "$repo/lib/run-job.sh"               "$HOME/.claude/scheduled-jobs/run-job.sh"     755
    install_file "$repo/lib/trigger-job.sh"           "$HOME/.claude/scheduled-jobs/trigger-job.sh" 755
    install_file "$repo/lib/update-check.sh"          "$HOME/.claude/scheduled-jobs/update-check.sh" 755

    # Install the clauck CLI to ~/.local/bin (same location as claude CLI).
    run mkdir -p "$HOME/.local/bin"
    install_file "$repo/lib/clauck"                   "$HOME/.local/bin/clauck"                     755
    install_file "$repo/lib/scheduled-jobs-prompt.md" "$HOME/.claude/scheduled-jobs-prompt.md"      644
    install_file "$repo/lib/scheduled-jobs-notice.sh" "$HOME/.claude/hooks/scheduled-jobs-notice.sh" 755

    # Record the installed version for the auto-updater.
    if [ -f "$repo/VERSION" ]; then
        cp "$repo/VERSION" "$HOME/.claude/scheduled-jobs/.version"
        ok "recorded version: $(cat "$HOME/.claude/scheduled-jobs/.version" | tr -d '[:space:]')"
    fi

    # Write config: respect auto-update prompt decision + persist fork URL.
    # Never overwrite an existing config — user preferences are sacrosanct.
    local cfg_dst="$HOME/.claude/scheduled-jobs/.clauck.config.json"
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
    "auto_apply": false
  }
}
CFGEOF
        fi
        ok "wrote config: $cfg_dst (auto_update.enabled=$auto_enabled, repo=$repo_short)"
    fi

    section "Installing skill"
    install_file "$repo/skill/scheduled-jobs/SKILL.md" "$HOME/.claude/skills/scheduled-jobs/SKILL.md" 644

    # Ship the library (pre-made job catalog) into the skill dir so agents can
    # browse it offline. Always overwrite — library updates are expected.
    if [ -d "$repo/library" ]; then
        local lib_dst="$HOME/.claude/skills/scheduled-jobs/library"
        rm -rf "$lib_dst"
        cp -R "$repo/library" "$lib_dst"
        ok "installed library → $lib_dst ($(ls "$lib_dst/"*/*.md 2>/dev/null | wc -l | tr -d ' ') job(s))"
    fi

    section "Installing default jobs"
    local job
    for job in "$repo/jobs/"*.md; do
        [ -f "$job" ] || continue
        local name; name="$(basename "$job")"
        local dst="$HOME/.claude/scheduled-jobs/$name"
        if [ -f "$dst" ]; then
            warn "preserving existing user job: $dst (shipped default not installed)"
        else
            install_file "$job" "$dst" 644
        fi
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
# Verification: fire heartbeat, wait for exit_code=0 in the log
# ──────────────────────────────────────────────────────────────────────────

verify() {
    section "Verifying pipeline (firing heartbeat ad-hoc)"

    local trigger="$HOME/.claude/scheduled-jobs/trigger-job.sh"
    [ -x "$trigger" ] || die "trigger-job.sh not executable at $trigger" 3

    # Snapshot existing logs so we can detect a new one.
    local before_count
    before_count=$(ls "$HOME/.claude/scheduled-jobs/"heartbeat-*.log 2>/dev/null | wc -l | tr -d ' ')

    "$trigger" heartbeat >/dev/null 2>&1 \
        || die "trigger-job.sh heartbeat failed to dispatch" 3

    # Poll for a new log to appear and complete. Up to 90s.
    local elapsed=0 interval=3 max=90 latest=""
    while [ "$elapsed" -lt "$max" ]; do
        sleep "$interval"
        elapsed=$((elapsed + interval))
        latest=$(ls -t "$HOME/.claude/scheduled-jobs/"heartbeat-*.log 2>/dev/null | head -1 || true)
        if [ -n "$latest" ]; then
            local current_count
            current_count=$(ls "$HOME/.claude/scheduled-jobs/"heartbeat-*.log 2>/dev/null | wc -l | tr -d ' ')
            if [ "$current_count" -gt "$before_count" ] && grep -q "exit_code=" "$latest"; then
                break
            fi
        fi
    done

    if [ -z "$latest" ] || ! grep -q "exit_code=" "$latest"; then
        fail "heartbeat did not complete within ${max}s"
        fail "check: $latest"
        fail "check: $HOME/.claude/scheduled-jobs/.scheduler-stderr.log"
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

  Version         $(cat "$HOME/.claude/scheduled-jobs/.version" 2>/dev/null | tr -d '[:space:]' || echo unknown)
  Scheduler       com.$USER.claude-scheduler (loaded, tick interval 60s)
  Jobs directory  ~/.claude/scheduled-jobs/
  Skill           ~/.claude/skills/scheduled-jobs/SKILL.md
  Library         ~/.claude/skills/scheduled-jobs/library/
  Hook            ~/.claude/hooks/scheduled-jobs-notice.sh
  Config          ~/.claude/scheduled-jobs/.clauck.config.json

${C_BOLD}Default job installed:${C_RESET}
  heartbeat (hourly liveness check, ~\$1/month at current Haiku pricing)

${C_BOLD}Auto-updates:${C_RESET}
  Checking GitHub Releases every hour. Detects new versions; does NOT apply
  them automatically (security-conscious default). To change, edit the config
  file above or run: ${C_BOLD}~/.claude/scheduled-jobs/update-check.sh --help${C_RESET}

${C_BOLD}What just happened:${C_RESET}
  Your Claude CLI was just launched by a launchd-spawned shell, loaded its
  tool surface, produced a "heartbeat ok" result, wrote a log file, and
  exited with code 0. That is end-to-end proof that the system works.

${C_BOLD}Next steps:${C_RESET}
  1. Open Claude Code in any terminal. A SessionStart hook will advertise
     this system and the library to your agent.
  2. Ask your session: ${C_BOLD}"What clauck jobs can I add from the library?"${C_RESET}
     The agent will read ~/.claude/skills/scheduled-jobs/library/index.json
     and install any you pick.
  3. Or just ask: ${C_BOLD}"What can I schedule?"${C_RESET} — the agent will design a
     new job with you from scratch.
  4. To inspect manually:
       cat ~/.claude/scheduled-jobs/.manifest.json | python3 -m json.tool
       ls ~/.claude/scheduled-jobs/  ~/.claude/skills/scheduled-jobs/library/
  5. To uninstall:
       bash <(curl -sSL $REPO_URL/raw/$REPO_BRANCH/uninstall.sh)

${C_DIM}Full docs: ~/.claude/skills/scheduled-jobs/SKILL.md${C_RESET}

EOF
}

# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

confirm_plan() {
    local repo="$1"
    local version=""
    [ -f "$repo/VERSION" ] && version=" ($(cat "$repo/VERSION" | tr -d '[:space:]'))"

    cat <<EOF

${C_BOLD}This installer will:${C_RESET}
  ${C_DIM}core${C_RESET}  Place scheduler + executor scripts in ~/.claude/scheduled-jobs/
  ${C_DIM}core${C_RESET}  Register a LaunchAgent (com.$USER.claude-scheduler, ticks every 60s)
  ${C_DIM}opt ${C_RESET}  Install a Claude Code skill at ~/.claude/skills/scheduled-jobs/
  ${C_DIM}opt ${C_RESET}  Install a pre-made job library at ~/.claude/skills/scheduled-jobs/library/
  ${C_DIM}opt ${C_RESET}  Register a SessionStart hook in ~/.claude/settings.json
  ${C_DIM}opt ${C_RESET}  Install the 'heartbeat' job (~\$1/month on Haiku)

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

    # If resolve_repo cloned into /tmp, register cleanup for when the installer exits.
    if [[ "$repo" == /tmp/* ]]; then
        local tmproot="${repo%/repo}"  # /tmp/clauck.XXXXX
        trap "rm -rf '$tmproot'" EXIT
    fi

    confirm_plan "$repo"
    prompt_auto_update

    make_dirs
    install_files "$repo"
    install_plist "$repo"
    patch_settings
    verify
    banner
}

main "$@"
