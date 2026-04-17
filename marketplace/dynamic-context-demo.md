---
name: dynamic-context-demo
description: Demonstrates {{cmd:}} inline bash templating — injects live date and git state into the prompt body at dispatch time, before the model receives it.
cron: ""
max_turns: 3
max_budget_usd: 0.05
effort: low
strict_mcp_config: true
setting_sources: ""
tags:
  - demo
  - templating
  - example
  - marketplace
---

<!-- CUSTOMIZE BEFORE INSTALLING:
     Change ~/Documents/repos/clauck below to any git repo you want to inspect.
     Add more {{cmd:}} markers to inject other live shell context as needed. -->

Today is **{{cmd: date '+%A, %B %-d, %Y at %H:%M %Z'}}**.

Recent commits in my tracked repo:
{{cmd: git -C ~/Documents/repos/clauck log --oneline -5 2>/dev/null || echo "(repo not found or git unavailable)"}}

Pending local changes:
{{cmd: git -C ~/Documents/repos/clauck status --short 2>/dev/null | head -10 | sed 's/^/  /' || echo "  (none)"}}

In one sentence, summarize the recent activity shown above. If git data is unavailable, just say so and suggest customizing the repo path.
