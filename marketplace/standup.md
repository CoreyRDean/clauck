---
name: standup
description: Weekday standup generator — pulls git activity via standup-gather pipeline, writes a formatted standup note.
cron: "0 13 * * 1-5"
max_turns: 6
max_budget_usd: 0.08
cwd: ~
effort: low
model: haiku
setting_sources: ""
strict_mcp_config: true
producers:
  - {name: standup-gather, timeout_seconds: 120}
tags:
  - productivity
  - developer
  - pipeline
  - standup
semantic_hooks:
  - Write my daily standup from git commits
  - Generate a standup report from recent code activity
  - Create a standup note from yesterday's work
---

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Set OUTPUT_FILE to where you want standups written.
   Default writes to ~/standup.md — change to match your workflow.
2. Adjust cron time to your standup time (default: 13:00 UTC = 8am ET).
3. Install standup-gather.md alongside this job.

This job uses standup-gather as a producer (pipeline pattern):
  standup-gather runs first → collects git data → output injected here
  standup formats the data → appends to OUTPUT_FILE
-->

OUTPUT_FILE=~/standup.md

Read the `## Producer outputs` section in your runtime context — it contains JSON output from standup-gather with today's git activity.

Parse the JSON and format a concise standup. Append to OUTPUT_FILE (never overwrite):

```
## YYYY-MM-DD standup
Yesterday:
- [repo-name]: brief summary of work from commit messages (N commits)
- [repo-name]: ...
Today: continuing [inferred area from commit patterns] / (leave blank if unclear)
Blockers: none
```

Rules:
- One bullet per repo. Summarize from commit messages — don't just list them.
- "Today" line: infer from patterns if obvious, otherwise omit it.
- "Blockers": always include — say "none" if no evidence of blockers in commits.
- If total_commits is 0: append `## YYYY-MM-DD — no commits to report`.
- If producer output is missing or malformed: append `## YYYY-MM-DD — standup-gather produced no output`.
