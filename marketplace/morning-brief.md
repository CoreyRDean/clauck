---
name: morning-brief
description: Weekday morning digest — unread Slack mentions, today's calendar, and open tickets in one threaded post.
cron: "0 13 * * 1-5"
max_turns: 12
max_budget_usd: 0.35
cwd: ~
effort: low
model: haiku
setting_sources: ""
tags:
  - productivity
  - digest
  - daily
  - slack
  - calendar
  - jira
  - standup
semantic_hooks:
  - Want a morning summary of overnight activity across Slack, calendar, and tickets
  - Need to catch up on what happened while I was asleep
  - Looking for a daily standup digest
---

**Important:** Replace any `~/` paths below with the absolute path using the `User home` value from your Runtime Context (e.g., `/Users/<username>/Downloads` not `~/Downloads`). The Read tool does not expand tilde.

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Pick your notification channel. Replace the TODO below with your Slack DM
   channel ID (e.g. D0XXXXXX), or switch to Gmail/local file.
2. Optionally narrow the Jira/Atlassian search to a specific project.
3. Adjust the cron time (default: 13:00 UTC = 8am ET / 6am PT).
-->

Build a morning briefing and post it to Slack self-DM (channel `<TODO: your channel ID>`). Thread under a root message titled `Morning brief`; search for it first, create if missing.

**Sections to include (skip any section where the MCP is unavailable or returns nothing):**

**1. Slack mentions (last 12 hours)**
Search Slack for messages mentioning you in the last 12 hours. For each, show: channel name, sender, one-line preview. Cap at 10.

**2. Today's calendar**
Fetch today's events from Google Calendar. For each: time, title, attendees count. Flag conflicts.

**3. Open tickets assigned to you**
Search Jira/Atlassian for issues assigned to you that are not Done. Show: key, title, status, priority. Cap at 10. Sort by priority.

**Format:**

```
Morning brief — <today's date>

📨 Slack (N unread mentions)
• #channel — @sender: preview text
• ...

📅 Calendar (N events today)
• 09:00–09:30 — Weekly standup (4 attendees)
• ...

🎫 Open tickets (N)
• PROJ-123 — Fix login timeout [In Progress, High]
• ...
```

If ALL three sections are empty: post `Morning brief — <date>: inbox zero ✓` and exit.

Keep it tight. No commentary, no suggestions, no action items. Just the facts.
