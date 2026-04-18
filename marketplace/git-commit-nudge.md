---
name: git-commit-nudge
version: "1.0.0"
description: Every 4 hours, check for uncommitted changes or unpushed commits across your repos. Nudge via local feed file.
cron: "0 */4 * * *"
complexity: 0.10   # scan configured repos for uncommitted state
cwd: ~
setting_sources: ""
strict_mcp_config: true
tags:
  - monitoring
  - git
  - uncommitted
  - unpushed
  - nudge
  - developer
semantic_hooks:
  - Want to check if I have uncommitted or unpushed work in any repo
  - Need a reminder about stale git working directories
---

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Change REPOS_ROOT below to the parent directory containing your git repos.
   Default: ~/Documents/GitHub. The scan is one level deep (each subdir is checked).
-->

Scan all git repos under `~/Documents/GitHub` (each immediate subdirectory that contains a `.git/`):

For each repo, run:
1. `git -C <repo> status --porcelain` — any output means uncommitted changes.
2. `git -C <repo> log @{u}.. --oneline 2>/dev/null` — any output means unpushed commits. If no upstream is set, skip this check.

Collect results. If ANY repo has uncommitted or unpushed work, append to `$CLAUCK_OUTPUT_DIR/git-nudge-feed.md` (this path is in your Runtime Context under **Output directory**):

```
## <ISO8601 UTC>

⚠️ Uncommitted changes:
- ~/Documents/GitHub/my-project — 3 files modified, 1 untracked
- ...

⬆️ Unpushed commits:
- ~/Documents/GitHub/other-repo — 2 commits ahead of origin/main
- ...
```

If all repos are clean: write `## <UTC>: all repos clean` to the same feed file and exit.

**Do not commit, push, stash, or modify any repo.** Report only.
