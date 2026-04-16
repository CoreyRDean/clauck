---
name: standup-gather
description: Pipeline stage — collects git commits from the last 24h across repos. Output consumed by the standup job.
cron: ""
max_turns: 4
max_budget_usd: 0.05
cwd: ~
effort: low
model: haiku
setting_sources: ""
strict_mcp_config: true
tags:
  - developer
  - pipeline
  - standup
  - pipeline-stage
---

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Set REPOS_ROOT to your repos parent directory.
2. Install standup.md alongside this job — it uses standup-gather as a producer.
-->

REPOS_ROOT=~/code

Scan REPOS_ROOT for git activity from the last 24 hours. For each direct subdirectory:
- Check if it is a git repo: `git -C <dir> rev-parse --git-dir 2>/dev/null`
- If yes: run `git -C <dir> log --since="24 hours ago" --oneline --all`
- Collect: repo name, commit count, up to 3 one-line summaries

Output ONLY this JSON block (no preamble, no explanation):

```json
{
  "repos": [
    {"name": "repo-name", "commits": 3, "summaries": ["fix auth bug", "add tests", "bump version"]}
  ],
  "total_commits": 3,
  "repos_root": "REPOS_ROOT"
}
```

If no repos have activity, output `{"repos": [], "total_commits": 0, "repos_root": "REPOS_ROOT"}`.
If REPOS_ROOT does not exist or is not a directory, output `{"repos": [], "total_commits": 0, "repos_root": "REPOS_ROOT", "error": "REPOS_ROOT not found"}`.
