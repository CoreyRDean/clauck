---
name: release-monitor
description: Bounded post-release monitor — watches a GitHub repo for new issues during a release window, then auto-disables.
cron: "0 */6 * * *"
max_turns: 6
max_budget_usd: 0.12
cwd: ~
effort: low
model: haiku
valid_after: "TODO: YYYY-MM-DD"
expires_after: "TODO: YYYY-MM-DD"
max_runs: 28
tags:
  - monitoring
  - github
  - temporal
  - release
  - bounded
semantic_hooks:
  - Monitor GitHub issues after a release or launch
  - Watch for problems during the first week after shipping
  - Temporary bounded monitoring job
---

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Set REPO to the GitHub repo to monitor (owner/repo format).
   Example: REPO=CoreyRDean/clauck
2. Set valid_after to your release date (YYYY-MM-DD).
3. Set expires_after to 7 days after release (YYYY-MM-DD).
4. Adjust OUTPUT_FILE path if desired.
5. max_runs=28 = 4 runs/day × 7 days. Adjust with the window.

This job auto-disables when expires_after passes OR max_runs is exhausted —
whichever comes first. No manual cleanup needed.
-->

REPO=TODO:owner/repo
OUTPUT_FILE=~/.clauck/release-monitor-feed.md

You are monitoring **REPO** during its release window. This job fires every 6 hours and auto-disables when the window closes.

**Each run:**

1. Run `gh issue list --repo REPO --state open --json number,title,labels,createdAt` and filter for issues created in the last 6 hours. If `gh` is unavailable, note it and skip.

2. Categorize:
   - **Bugs/blockers**: issues labeled `bug`, `critical`, `regression`, or containing "broken", "crash", "fails", "error" in title
   - **Feedback**: labeled `enhancement`, `question`, or "feature request" in title
   - **Other**: everything else

3. Append to OUTPUT_FILE:

```
## YYYY-MM-DD HH:MM UTC — release-monitor (REPO)
Bugs/blockers (N): #123 short title, #456 short title
Feedback (N): #789 short title
Other (N): #012 short title
Nothing new since last check.
```

If no new issues: write a single `## YYYY-MM-DD HH:MM UTC — nothing new` line and exit.

One issue per line max. Titles truncated to 60 chars. This is a log, not a report.
