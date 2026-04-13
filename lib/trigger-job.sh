#!/bin/zsh -l
# trigger-job.sh — ad-hoc fire a scheduled job by name, bypassing cron.
#
# Intended for agent nodes that matched a semantic hook (see
# ~/.claude/scheduled-jobs/.manifest.json) and want to execute the
# corresponding job now. Also fine for manual human invocation.
#
# Usage:  trigger-job.sh <job-name>

set -u

NAME="${1:-}"
if [ -z "$NAME" ]; then
  echo "usage: $0 <job-name>" >&2
  exit 2
fi

exec /usr/bin/python3 "$HOME/.claude/scheduled-jobs/scheduler.py" --trigger "$NAME"
