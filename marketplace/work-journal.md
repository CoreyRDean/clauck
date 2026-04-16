---
name: work-journal
description: Session-persistent daily work journal — accumulates context across runs to surface patterns and track momentum over time.
cron: "0 22 * * 1-5"
max_turns: 8
max_budget_usd: 0.08
cwd: ~
effort: low
model: haiku
session_persist: true
setting_sources: ""
strict_mcp_config: true
tags:
  - productivity
  - journal
  - developer
  - session-persist
semantic_hooks:
  - Write a daily summary of work completed today
  - Build a running work journal from git activity
  - Log what I worked on today
---

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Set REPOS_ROOT to the parent directory containing your git repos.
   Example: REPOS_ROOT=~/Projects  or  REPOS_ROOT=~/code
2. Set OUTPUT_FILE to where you want the journal written.
3. Adjust cron time to your end-of-workday (default: 22:00 UTC / 5pm ET).
-->

REPOS_ROOT=~/code
OUTPUT_FILE=~/.clauck/work-journal.md

You are maintaining a running work journal across multiple sessions. Because session_persist is enabled, you have full context from every prior run of this job. Use that history to notice patterns.

**Step 1 — Gather today's git activity.**
For each direct subdirectory of REPOS_ROOT: check if it's a git repo (`git -C <dir> rev-parse --git-dir 2>/dev/null`). If yes, run `git -C <dir> log --since="24 hours ago" --oneline --all`. Collect: repo name, commit count, up to 3 commit summaries. Skip repos with no activity.

**Step 2 — Write today's entry.**
Append to OUTPUT_FILE (never overwrite):

```
## YYYY-MM-DD
- [repo-name] N commits — summary of work (e.g., "fixed auth bug, added tests")
- [repo-name] ...
↑ [optional 1-line pattern note if you see something recurring across sessions]
```

If no git activity anywhere: append `## YYYY-MM-DD — no commits`.

Terse. One bullet per repo. The optional pattern note fires only when you notice something meaningful spanning multiple days — skip it if nothing stands out.
