---
name: github-pr-digest
description: Weekday digest of PRs needing your attention — reviews requested, your stale drafts, and recently merged.
cron: "0 14 * * 1-5"
max_turns: 8
max_budget_usd: 0.25
cwd: ~
effort: low
model: haiku
setting_sources: ""
tags:
  - productivity
  - github
  - pull-requests
  - digest
  - daily
  - code-review
semantic_hooks:
  - Want a summary of GitHub PRs that need my attention
  - Need to check for stale PRs or pending review requests
  - Looking for a PR review digest
---

**Important:** Replace any `~/` paths below with the absolute path using the `User home` value from your Runtime Context (e.g., `/Users/<username>/Downloads` not `~/Downloads`). The Read tool does not expand tilde.

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Replace the Slack channel TODO with your DM channel ID, or switch to local file.
2. Optionally narrow to specific GitHub orgs/repos.
-->

Build a GitHub PR digest and post to Slack self-DM (channel `<TODO: your channel ID>`). Thread under a root titled `PR digest`; search first, create if missing.

**Sections:**

**1. Reviews requested from you**
Search GitHub for open PRs where your review is requested. For each: repo, PR title, author, age in days.

**2. Your open PRs (not merged)**
Search for PRs you authored that are still open. For each: repo, title, age, CI status if available. Flag any older than 7 days as stale.

**3. Recently merged (last 24h)**
Search for PRs you authored that merged in the last 24 hours. For each: repo, title, merge time.

**Format:**

```
PR digest — <date>

👀 Reviews requested (N)
• org/repo#123 — "Title" by @author (3d old)
• ...

📝 Your open PRs (N, M stale)
• org/repo#456 — "Title" (12d, CI passing) ⚠️ stale
• ...

✅ Merged last 24h (N)
• org/repo#789 — "Title" (merged 6h ago)
```

If no PRs in any section: `PR digest — <date>: all clear` and exit.
