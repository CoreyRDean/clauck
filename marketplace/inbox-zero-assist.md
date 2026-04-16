---
name: inbox-zero-assist
version: "1.0.0"
description: End-of-day scan of unread Gmail threads older than 48h. Suggests actions (reply, archive, delegate) in a local file. Never sends.
cron: "0 22 * * 1-5"
max_turns: 8
max_budget_usd: 0.25
cwd: ~
effort: low
model: haiku
setting_sources: ""
tags:
  - productivity
  - gmail
  - email
  - triage
  - inbox-zero
  - daily
semantic_hooks:
  - Want help triaging my email inbox
  - Need to identify old unread emails I should deal with
  - Looking for an inbox-zero assistant
---

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Adjust the cron time (default: 22:00 UTC = 5pm ET end of workday).
2. Optionally narrow to specific Gmail labels.
3. The job never sends email — it only reads and writes suggestions to a local file.
-->

Search Gmail for unread threads older than 48 hours. For each (cap at 15):

1. Note: sender, subject, age, snippet.
2. Suggest ONE action: `reply` (draft a one-liner), `archive` (not actionable), `delegate` (forward to someone), `schedule` (needs attention but not now).

Append to `~/.clauck/inbox-assist-feed.md`:

```
## <ISO8601 UTC>

| # | From | Subject | Age | Suggested action |
|---|---|---|---|---|
| 1 | sender@example.com | "Re: Q3 planning" | 3d | reply — "Confirming I'll review by Friday" |
| 2 | notifications@github.com | "PR #456 merged" | 5d | archive |
| ... | | | | |

Unread threads older than 48h: N total, N shown above.
```

**Do not send, archive, label, or modify any email.** Read-only + local suggestions.

If no unread threads older than 48h: write `## <UTC>: inbox zero ✓` and exit.
