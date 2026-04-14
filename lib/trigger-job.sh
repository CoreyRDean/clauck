#!/bin/zsh -l
# trigger-job.sh — ad-hoc fire a scheduled job by name, bypassing cron.
#
# Intended for agent nodes that matched a semantic hook (see
# ~/.claude/scheduled-jobs/.manifest.json) and want to execute the
# corresponding job now. Also fine for manual human invocation.
#
# Usage:
#   trigger-job.sh <job-name> [KEY=VALUE ...]
#
# Any KEY=VALUE pairs after the job name are exported as env vars prefixed
# with CLAUCK_INPUT_ and available to the job via the runtime context.
# Example:
#   trigger-job.sh my-job FILE_PATH=/tmp/data.json MODE=verbose
#   → sets CLAUCK_INPUT_FILE_PATH=/tmp/data.json, CLAUCK_INPUT_MODE=verbose

set -u

NAME="${1:-}"
if [ -z "$NAME" ]; then
  echo "usage: $0 <job-name> [KEY=VALUE ...]" >&2
  exit 2
fi
shift

# Export any KEY=VALUE args as CLAUCK_INPUT_* env vars
for arg in "$@"; do
  case "$arg" in
    *=*)
      key="${arg%%=*}"
      val="${arg#*=}"
      export "CLAUCK_INPUT_${key}=${val}"
      ;;
  esac
done

exec /usr/bin/python3 "$HOME/.claude/scheduled-jobs/scheduler.py" --trigger "$NAME"
