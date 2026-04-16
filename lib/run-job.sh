#!/bin/zsh -l
# run-job.sh — Execute a single scheduled claude job.
#
# Normally invoked by scheduler.py with config pre-resolved into env vars:
#   CLAUDE_JOB_NAME           (required)
#   CLAUDE_JOB_PATH           (prompt .md path; default ~/.clauck/<name>.md)
#   CLAUDE_JOB_CWD            (working directory; default $HOME)
#   CLAUDE_JOB_MAX_TURNS      (default 50)
#   CLAUDE_JOB_MAX_BUDGET_USD (default 2.00)
#   CLAUDE_JOB_EFFORT         (default high)
#   CLAUDE_JOB_MODEL          (optional; passed to `claude --model` if non-empty)
#   CLAUDE_JOB_SETTING_SOURCES       (optional; passed to `claude --setting-sources`, can be "")
#   CLAUDE_JOB_SETTING_SOURCES_SET   (sentinel: "1" means setting_sources was intentionally set, even to empty)
#   CLAUDE_JOB_STRICT_MCP_CONFIG     (sentinel: "1" → pass --strict-mcp-config with an empty config file,
#                                     dropping the user's full MCP surface from the prompt)
#   CLAUDE_JOB_DEBOUNCE_SECONDS      (optional; skip this invocation if the job was last started
#                                     within the window. 0 or unset = no debounce)
#   CLAUDE_JOB_TRACE_TOOL_CALLS      (sentinel: "1" → use stream-json output so every tool
#                                     call appears in the log. Grep for "tool_use" to inspect.)
#   CLAUDE_JOB_CRON           (cron expression; informational)
#   CLAUDE_JOB_TRIGGER        ("scheduled" or "adhoc"; default "scheduled")
#   CLAUDE_JOB_FIRED_AT       (ISO8601 UTC timestamp from scheduler; informational)
#
# Also callable manually: `run-job.sh <job-name>` — resolves defaults only.
#
# Logging: the job log file is created BEFORE any pre-flight check so that
# missing-prompt, missing-claude-CLI, and unreachable-cwd failures are captured
# in the per-run log instead of vanishing into the scheduler's DEVNULL'd stdio.
#
# Log rotation: caps log files at 100 per job-name prefix. Before creating
# the new log, if 100+ matching logs already exist, deletes the oldest
# (N - 99) so this run brings the count to exactly 100.

set -u
setopt NULL_GLOB

JOB_NAME="${CLAUDE_JOB_NAME:-${1:-}}"
if [ -z "$JOB_NAME" ]; then
  echo "usage: $0 <job-name>  (or set CLAUDE_JOB_NAME)" >&2
  exit 2
fi

JOBS_DIR="$HOME/.clauck"
PROMPT_FILE="${CLAUDE_JOB_PATH:-$JOBS_DIR/${JOB_NAME}.md}"
GLOBAL_PROMPT="$HOME/.clauck/prompt.md"
JOB_CWD="${CLAUDE_JOB_CWD:-$HOME}"
MAX_TURNS="${CLAUDE_JOB_MAX_TURNS:-50}"
MAX_BUDGET_USD="${CLAUDE_JOB_MAX_BUDGET_USD:-2.00}"
EFFORT="${CLAUDE_JOB_EFFORT:-high}"
MODEL="${CLAUDE_JOB_MODEL:-}"
# stream-json when trace_tool_calls is set; tool events appear inline in the log.
OUTPUT_FORMAT="json"
[ "${CLAUDE_JOB_TRACE_TOOL_CALLS:-}" = "1" ] && OUTPUT_FORMAT="stream-json"
DEBOUNCE_SECONDS="${CLAUDE_JOB_DEBOUNCE_SECONDS:-0}"
CRON_EXPR="${CLAUDE_JOB_CRON:-}"
TRIGGER="${CLAUDE_JOB_TRIGGER:-manual}"
FIRED_AT="${CLAUDE_JOB_FIRED_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
# Append PID to disambiguate invocations that fire within the same second
# (e.g. three rapid-fire ad-hoc triggers); otherwise they'd share a filename
# and later writes would overwrite the earlier tombstone.
LOG_FILE="$JOBS_DIR/${JOB_NAME}-${TIMESTAMP}-${$}.log"

# --- Log rotation: keep at most 100 logs for this job name ---
# Pattern `<name>-[0-9]*.log` requires a digit after the dash to avoid
# matching logs for a different job whose name is a prefix of this one.
# Run BEFORE creating the new log so we don't accidentally delete it.
# Collect matching log files into an array. With NULL_GLOB set at the top
# of the script, a zero-match glob expands to an empty array — crucially, we
# must NOT pipe the bare pattern into `ls`, because with zero args ls would
# list the cwd and wildly overcount. Zsh note: ${~PATTERN} enables glob
# expansion inside parameter substitution.
# The pattern `<name>-[0-9]*.log` requires a digit after the dash to avoid
# matching logs for a different job whose name is a prefix of this one.
LOG_PATTERN="${JOBS_DIR}/${JOB_NAME}-[0-9]*.log"
EXISTING_LOGS=( ${~LOG_PATTERN} )
EXISTING_COUNT=${#EXISTING_LOGS[@]}
if [ "$EXISTING_COUNT" -ge 100 ]; then
  NEED_DELETE=$(( EXISTING_COUNT - 99 ))
  # ls -t: newest first; tail -n NEED_DELETE: the oldest NEED_DELETE entries.
  # Safe here because EXISTING_LOGS is non-empty.
  ls -t "${EXISTING_LOGS[@]}" | tail -n "$NEED_DELETE" | while IFS= read -r f; do
    rm -f -- "$f"
  done
fi

# --- Create log file FIRST so all subsequent failures are observable ---
mkdir -p "$JOBS_DIR"
{
  echo "=== scheduled-job start: $JOB_NAME @ $TIMESTAMP ==="
  echo "stage=init"
  echo "prompt_config=$PROMPT_FILE"
  echo "global_config=$GLOBAL_PROMPT"
  echo "cwd_config=$JOB_CWD"
  echo "max_turns=$MAX_TURNS max_budget_usd=$MAX_BUDGET_USD effort=$EFFORT"
  echo "existing_logs_before_rotation=$EXISTING_COUNT"
} > "$LOG_FILE"

# die <reason> <exit_code>: write a tombstone to the log and exit.
die() {
  echo "--- preflight_fail: $1 ===" >> "$LOG_FILE"
  exit "$2"
}

# skip <reason>: write a noop tombstone to the log and exit cleanly (0).
# Used for debounce / concurrent-run suppression — an expected, not a failure.
skip() {
  echo "--- noop_skip: $1 ===" >> "$LOG_FILE"
  exit 0
}

# --- Debounce: skip if the last START was within DEBOUNCE_SECONDS ---
# This fires BEFORE the concurrency lock so debounced runs don't even contend.
# Measures from last-start, so a long-running job resets debounce when it finishes.
STATE_DIR="$JOBS_DIR/.state"
mkdir -p "$STATE_DIR"
LAST_START_FILE="$STATE_DIR/${JOB_NAME}.last-start"
if [ "$DEBOUNCE_SECONDS" -gt 0 ] && [ -f "$LAST_START_FILE" ]; then
  LAST_START=$(cat "$LAST_START_FILE" 2>/dev/null || echo 0)
  NOW_EPOCH=$(date +%s)
  AGO=$(( NOW_EPOCH - LAST_START ))
  if [ "$AGO" -lt "$DEBOUNCE_SECONDS" ]; then
    echo "stage=debounce debounce_seconds=$DEBOUNCE_SECONDS last_start_ago=${AGO}s" >> "$LOG_FILE"
    skip "debounced: last start was ${AGO}s ago (< ${DEBOUNCE_SECONDS}s window)"
  fi
fi

# --- Concurrent-run guard: atomic mkdir as a self-cleaning advisory lock ---
# If another invocation of this job is already running, this one noops. Uses
# mkdir (atomic on all POSIX filesystems) so no external `flock` dependency.
# Stores owning PID; if the previous holder died without cleanup, reclaim.
LOCK_DIR="$STATE_DIR/${JOB_NAME}.lock.d"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  OLD_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "stage=concurrent_skip holder_pid=$OLD_PID" >> "$LOG_FILE"
    skip "concurrent run in progress (PID $OLD_PID)"
  fi
  # Stale lock (PID file missing or process dead): reclaim.
  echo "stage=stale_lock_cleanup old_pid=${OLD_PID:-unknown}" >> "$LOG_FILE"
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" || die "failed to reclaim stale lock dir" 7
fi
echo $$ > "$LOCK_DIR/pid"
# Release lock + record start timestamp on every exit path (success, error, signal).
trap 'rm -rf "$LOCK_DIR"' EXIT
date +%s > "$LAST_START_FILE"

[ -f "$PROMPT_FILE" ]   || die "prompt file not found: $PROMPT_FILE" 3
[ -f "$GLOBAL_PROMPT" ] || die "global prompt not found: $GLOBAL_PROMPT" 4

# --- Resolve claude binary from login-shell PATH ---
# NOTE: under launchd, zsh -lc is login but NOT interactive, so ~/.zshrc is not
# sourced. User-installed CLIs in $HOME/.local/bin or $HOME/bin are typically
# added to PATH there. Prepend them here so resolution works regardless of
# whether the invoking shell was interactive.
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
CLAUDE_BIN="$(command -v claude || true)"
[ -n "$CLAUDE_BIN" ] || die "claude CLI not on PATH: $PATH" 6
echo "stage=resolved claude=$CLAUDE_BIN" >> "$LOG_FILE"

cd "$JOB_CWD" || die "cwd unreachable: $JOB_CWD" 5
echo "stage=cwd cwd=$(pwd)" >> "$LOG_FILE"

# --- Resolve CLAUCK_OUTPUT_DIR from config (fallback: ~/Documents/clauck) ---
# Allow the caller to override by pre-setting CLAUCK_OUTPUT_DIR in the env.
if [ -z "${CLAUCK_OUTPUT_DIR:-}" ]; then
  CONFIG_FILE="$JOBS_DIR/.clauck.config.json"
  CLAUCK_OUTPUT_DIR="$(/usr/bin/python3 -c "
import json, os
try:
    data = json.loads(open('$CONFIG_FILE').read())
    print(data.get('output_dir', '~/Documents/clauck'))
except Exception:
    print('~/Documents/clauck')
" 2>/dev/null || echo "$HOME/Documents/clauck")"
  # Expand leading ~ to $HOME (Read tool and other tools do not expand tilde)
  CLAUCK_OUTPUT_DIR="${CLAUCK_OUTPUT_DIR/#\~/$HOME}"
fi
export CLAUCK_OUTPUT_DIR
mkdir -p "$CLAUCK_OUTPUT_DIR" 2>/dev/null || true
echo "stage=output_dir output_dir=$CLAUCK_OUTPUT_DIR" >> "$LOG_FILE"

# --- Strip YAML frontmatter before passing prompt to claude ---
# State machine: init → (inside between --- markers) → body.
PROMPT_BODY="$(awk '
  BEGIN { state = "init" }
  {
    if (state == "init") {
      if ($0 == "---") { state = "inside"; next }
      state = "body"; print; next
    }
    if (state == "inside") {
      if ($0 == "---") { state = "body"; next }
      next
    }
    print
  }
' "$PROMPT_FILE")"

# --- Compose per-invocation runtime context appended to the global prompt ---
# The claude CLI accepts either --append-system-prompt OR --append-system-prompt-file,
# not both, so we read the global file here and concatenate the runtime block,
# passing the combined text as a single --append-system-prompt argument.
GLOBAL_PROMPT_TEXT="$(cat "$GLOBAL_PROMPT")"
RUNTIME_CONTEXT="# Runtime Context (this invocation)

- **Job name:** ${JOB_NAME}
- **Trigger:** ${TRIGGER}$([ -n "$CRON_EXPR" ] && echo " (cron: ${CRON_EXPR})")
- **Fired at:** ${FIRED_AT}
- **Budget:** max_turns=${MAX_TURNS}, max_budget_usd=\$${MAX_BUDGET_USD}, effort=${EFFORT}
- **Working directory:** $(pwd)
- **User home:** ${HOME}
- **Local timezone:** $(date +%Z) (UTC offset: $(date +%z))
- **Log file (this run):** ${LOG_FILE}
- **Jobs directory:** ${JOBS_DIR}
- **Manifest (all jobs, with semantic_hooks and trigger_commands):** ${JOBS_DIR}/.manifest.json
- **Per-job state directory:** ${JOBS_DIR}/.state/
- **Output directory:** ${CLAUCK_OUTPUT_DIR}

Spend proportional to value. Budget is a cap, not a target. If there is nothing meaningful to do, exit cleanly with a brief note — a no-op is a legitimate outcome for a scheduled invocation.
These limits are enforced — exceeding max_budget_usd or max_turns terminates the session immediately.

## Tilde expansion (critical)

When you encounter \`~\` in any file path — in this Runtime Context, in Custom inputs, or anywhere else — expand it to the absolute home path BEFORE using it with any tool. The Read tool and other file operations do NOT expand tilde automatically.

- \`~\` or \`~/\` → \`${HOME}/\`
- Example: \`~/Downloads/file.pdf\` → \`${HOME}/Downloads/file.pdf\`

Tilde paths are a known failure mode; the expansion is your responsibility every time."

# --- Apply input defaults from frontmatter ---
# Read the job's `inputs:` declarations and set CLAUCK_INPUT_<NAME> for any
# input whose env var is not already set. This ensures every declared input
# has at least its default value available for the injection block below.
eval "$(/usr/bin/python3 -c "
import re, os, sys
try:
    text = open('$PROMPT_FILE').read()
    m = re.match(r'\A---\s*\n(.*?)\n---\s*\n?', text, re.DOTALL)
    if not m:
        sys.exit(0)
    fm_block = m.group(1)
    # Minimal parse: find 'inputs:' key, then collect list items
    lines = fm_block.splitlines()
    in_inputs = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('inputs:'):
            in_inputs = True
            continue
        if in_inputs:
            if stripped.startswith('- '):
                item = stripped[2:].strip()
                # Parse flow-style object: {name: X, default: Y, ...}
                if item.startswith('{') and item.endswith('}'):
                    inner = item[1:-1]
                    fields = {}
                    for part in inner.split(','):
                        part = part.strip()
                        if ':' in part:
                            k, _, v = part.partition(':')
                            k = k.strip()
                            v = v.strip().strip('\"').strip(\"'\")
                            fields[k] = v
                    iname = fields.get('name', '')
                    idefault = fields.get('default', '')
                    if iname:
                        env_key = 'CLAUCK_INPUT_' + iname
                        if env_key not in os.environ:
                            # Expand env vars in default value
                            expanded = os.path.expandvars(idefault)
                            # Shell-escape the value
                            safe = expanded.replace(\"'\", \"'\\\\''\" )
                            print(f\"export {env_key}='{safe}'\")
            elif not stripped.startswith('#'):
                # Hit a non-list-item, non-comment line — end of inputs block
                if stripped and not stripped.startswith('-'):
                    break
except Exception:
    pass
" 2>/dev/null)"

# Append any CLAUCK_INPUT_* env vars as custom input to the runtime context
CUSTOM_INPUTS=""
for var in $(env | grep '^CLAUCK_INPUT_' | sort); do
  key="${var%%=*}"
  val="${var#*=}"
  short_key="${key#CLAUCK_INPUT_}"
  CUSTOM_INPUTS="${CUSTOM_INPUTS}
- **${short_key}:** ${val}"
done
if [ -n "$CUSTOM_INPUTS" ]; then
  RUNTIME_CONTEXT="${RUNTIME_CONTEXT}

## Custom inputs (passed via trigger)
${CUSTOM_INPUTS}"
fi

# --- Inject producer outputs if this job was invoked as part of a pipeline ---
PRODUCER_OUTPUTS=""
# Find the most recent producer-outputs file for this job (left by dag-runner.py)
PRODUCER_FILE=$(ls -t "$STATE_DIR/${JOB_NAME}.producer-outputs-"*.json 2>/dev/null | head -1)
if [ -n "$PRODUCER_FILE" ] && [ -f "$PRODUCER_FILE" ]; then
  PRODUCER_OUTPUTS=$(/usr/bin/python3 -c "
import json, sys
try:
    data = json.load(open('$PRODUCER_FILE'))
    parts = []

    # Producer outputs section
    producers = data.get('producers', {})
    if producers:
        parts.append('## Producer outputs\n')
        for name, info in producers.items():
            exit_code = info.get('exit_code', '?')
            cost = info.get('cost', '?')
            result = info.get('result', '')
            parts.append(f'### {name} (exit {exit_code}, \${cost})')
            parts.append(result)
            parts.append('')

    # Oplog section
    oplog = data.get('oplog', [])
    if oplog:
        parts.append('## Execution chain (oplog)\n')
        for entry in oplog:
            ts = entry.get('ts', '?')
            job = entry.get('job', '?')
            event = entry.get('event', '?')
            extra = ''
            if 'exit_code' in entry:
                extra = f' exit={entry[\"exit_code\"]}'
            if 'cost' in entry:
                extra += f' \${entry[\"cost\"]}'
            parts.append(f'- {ts} {job} {event}{extra}')

    print('\n'.join(parts))
except Exception as e:
    print(f'[producer output parse error: {e}]', file=sys.stderr)
" 2>/dev/null)

  # Clean up the producer file after reading (one-time delivery)
  rm -f "$PRODUCER_FILE"

  if [ -n "$PRODUCER_OUTPUTS" ]; then
    echo "stage=pipeline_inputs producer_file=$(basename $PRODUCER_FILE)" >> "$LOG_FILE"
  fi
fi

APPENDED_SYSTEM_PROMPT="${GLOBAL_PROMPT_TEXT}

---

${RUNTIME_CONTEXT}"

if [ -n "$PRODUCER_OUTPUTS" ]; then
  APPENDED_SYSTEM_PROMPT="${APPENDED_SYSTEM_PROMPT}

---

${PRODUCER_OUTPUTS}"
fi

echo "stage=run" >> "$LOG_FILE"
echo "--- runtime_context ---" >> "$LOG_FILE"
echo "$RUNTIME_CONTEXT" >> "$LOG_FILE"
echo "--- prompt body (claude -p stdout follows) ---" >> "$LOG_FILE"

# Assemble optional flags. --model is only added if the job specified one.
CLAUDE_ARGS=(
  -p "$PROMPT_BODY"
  --append-system-prompt "$APPENDED_SYSTEM_PROMPT"
  --dangerously-skip-permissions
  --effort "$EFFORT"
  --max-turns "$MAX_TURNS"
  --max-budget-usd "$MAX_BUDGET_USD"
  --output-format "$OUTPUT_FORMAT"
)
[ -n "$MODEL" ] && CLAUDE_ARGS+=(--model "$MODEL")
# Only add --setting-sources if the job explicitly opted in (including setting it
# to the empty string to disable plugins/settings and dramatically reduce cache
# creation cost). Absent → claude's default behavior.
[ -n "${CLAUDE_JOB_SETTING_SOURCES_SET:-}" ] && CLAUDE_ARGS+=(--setting-sources "${CLAUDE_JOB_SETTING_SOURCES:-}")
# If the job opted into strict MCP config, write a single-use empty config and
# point claude at it. Strips the ~170k-token user MCP surface for jobs that
# don't need tool access — biggest single cache-creation cost reduction.
if [ "${CLAUDE_JOB_STRICT_MCP_CONFIG:-}" = "1" ]; then
  EMPTY_MCP_CONFIG="${JOBS_DIR}/.state/.empty-mcp-config.json"
  [ -f "$EMPTY_MCP_CONFIG" ] || echo '{"mcpServers":{}}' > "$EMPTY_MCP_CONFIG"
  CLAUDE_ARGS+=(--strict-mcp-config --mcp-config "$EMPTY_MCP_CONFIG")
fi

# --- Session persistence: reuse the same session across runs ---
# On first run, we capture session_id from the JSON output and store it.
# On subsequent runs, we pass --resume <session_id> so claude has context
# from all prior runs of this job.
SESSION_ID_FILE="$STATE_DIR/${JOB_NAME}.session-id"
if [ "${CLAUDE_JOB_SESSION_PERSIST:-}" = "1" ] && [ -f "$SESSION_ID_FILE" ]; then
  STORED_SID="$(cat "$SESSION_ID_FILE" 2>/dev/null | tr -d '[:space:]')"
  if [ -n "$STORED_SID" ]; then
    CLAUDE_ARGS+=(--resume "$STORED_SID")
    echo "stage=session_resume session_id=$STORED_SID" >> "$LOG_FILE"
  fi
fi

"$CLAUDE_BIN" "${CLAUDE_ARGS[@]}" >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

# --- Stale session-ID retry: if --resume failed, retry without it ---
# If exit was non-zero, session persistence was active, and the error looks
# session-related, drop the stale session-id and retry once from scratch.
if [ "$EXIT_CODE" -ne 0 ] && [ "${CLAUDE_JOB_SESSION_PERSIST:-}" = "1" ] && [ -f "$SESSION_ID_FILE" ]; then
  # Check last ~40 lines of log for session/resume-related error text
  if tail -40 "$LOG_FILE" 2>/dev/null | grep -qi -e "session" -e "resume"; then
    echo "stage=session_retry stale_session_id=$(cat "$SESSION_ID_FILE" 2>/dev/null | tr -d '[:space:]')" >> "$LOG_FILE"
    echo "--- retrying without --resume (stale session) ---" >> "$LOG_FILE"
    rm -f "$SESSION_ID_FILE"
    # Rebuild CLAUDE_ARGS without --resume
    CLAUDE_ARGS=(
      -p "$PROMPT_BODY"
      --append-system-prompt "$APPENDED_SYSTEM_PROMPT"
      --dangerously-skip-permissions
      --effort "$EFFORT"
      --max-turns "$MAX_TURNS"
      --max-budget-usd "$MAX_BUDGET_USD"
      --output-format "$OUTPUT_FORMAT"
    )
    [ -n "$MODEL" ] && CLAUDE_ARGS+=(--model "$MODEL")
    [ -n "${CLAUDE_JOB_SETTING_SOURCES_SET:-}" ] && CLAUDE_ARGS+=(--setting-sources "${CLAUDE_JOB_SETTING_SOURCES:-}")
    if [ "${CLAUDE_JOB_STRICT_MCP_CONFIG:-}" = "1" ]; then
      CLAUDE_ARGS+=(--strict-mcp-config --mcp-config "$EMPTY_MCP_CONFIG")
    fi
    "$CLAUDE_BIN" "${CLAUDE_ARGS[@]}" >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
  fi
fi

# Capture session_id for future runs (session persistence).
if [ "${CLAUDE_JOB_SESSION_PERSIST:-}" = "1" ]; then
  NEW_SID="$(grep -o '"session_id":"[^"]*"' "$LOG_FILE" 2>/dev/null | tail -1 | sed 's/"session_id":"//;s/"$//')"
  if [ -n "$NEW_SID" ]; then
    echo "$NEW_SID" > "$SESSION_ID_FILE"
  fi
fi

# --- Interactive follow-up: open Terminal for the user to continue ---
if [ "${CLAUDE_JOB_INTERACTIVE:-}" = "1" ] && [ "$EXIT_CODE" -eq 0 ]; then
  RESUME_SID=""
  if [ -f "$SESSION_ID_FILE" ]; then
    RESUME_SID="$(cat "$SESSION_ID_FILE" 2>/dev/null | tr -d '[:space:]')"
  else
    RESUME_SID="$(grep -o '"session_id":"[^"]*"' "$LOG_FILE" 2>/dev/null | tail -1 | sed 's/"session_id":"//;s/"$//')"
  fi
  if [ -n "$RESUME_SID" ]; then
    # Open a new Terminal window with an interactive claude session resuming
    # the just-completed run. The user sees the output and can iterate.
    osascript -e "tell application \"Terminal\" to do script \"claude --resume $RESUME_SID\"" 2>/dev/null || true
    echo "stage=interactive_opened session_id=$RESUME_SID" >> "$LOG_FILE"
  fi
fi

echo "--- exit_code=$EXIT_CODE ===" >> "$LOG_FILE"
exit $EXIT_CODE
