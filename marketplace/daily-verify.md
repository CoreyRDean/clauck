---
name: daily-verify
description: Daily deep-chain verification. Exercises full launchd → claude → MCP → external-tool chain so silent MCP drift is caught within 24h.
cron: "0 14 * * *"
max_turns: 5
max_budget_usd: 0.40
cwd: ~
effort: low
model: haiku
setting_sources: ""
tags:
  - verification
  - health-check
  - daily
  - mcp
  - notification
semantic_hooks:
  - Need to verify MCP servers are loading correctly under launchd-driven claude sessions
  - Suspect silent MCP auth drift (OAuth tokens expired, claude.ai integration glitched)
  - Want a deep-chain health check of the scheduled-job pipeline
  - Investigating why a specific scheduled job that needs MCP tools is failing
---

<!--
CUSTOMIZE BEFORE INSTALLING:
Pick ONE destination for the daily post and edit the prompt below accordingly.
Common choices: Slack DM, Discord DM, Jira comment, Gmail self-send, local file.
-->

Post a daily verification message via one of your configured MCPs.

**Where to post** (pick ONE and edit this prompt):

- **Slack DM to yourself:** call `slack_send_message` with `channel_id=<TODO: your Slack DM channel ID, e.g. D0XXXXXX>`. Thread under a root message titled `Scheduled daily-verify — launchd`; search for it first, create it if missing.
- **Discord DM:** use the Discord MCP.
- **Jira ticket:** append a comment to `<TODO: ticket key>`.
- **Email:** use the Gmail MCP to send to yourself with subject `clauck daily-verify`.
- **Local file only:** append to `~/.clauck/daily-verify-feed.md`. No MCP needed; you lose external visibility but removes the MCP-surface cost floor (drops to ~$0.04 like heartbeat).

**Post body (one line per bullet, no preamble, no trailing text):**

```
<ISO8601 UTC> · claude <version>
• MCPs connected: <count> (names: <comma-separated>)
• MCPs need-auth: <count> (names: <comma-separated>, or "none")
• MCPs failed: <count> (names: <comma-separated>, or "none")
• Post: OK (this message)
• Verdict: <OK | DEGRADED: brief reason>
```

**How to enumerate MCPs:**
Run `claude mcp list` via Bash to get CLI-scope MCPs. For additional claude.ai-integrated MCPs, enumerate by scanning distinct `mcp__<server>__` tool-name prefixes visible via `ToolSearch` with query `+mcp`. Do NOT rely on initial tool-surface enumeration as authoritative; if you think a server is absent, confirm with a `ToolSearch` call.

**Verdict rules:**
- `OK` — post succeeded AND zero MCPs in the "failed" bucket.
- `DEGRADED` — any failed MCP, OR any MCP you couldn't enumerate. Include a one-line reason.

**Failure handling:**
If the post itself fails, do not retry more than once. Write the verbatim error to stdout and exit. The log file's `--- exit_code=N ===` tombstone is the fallback evidence surface.

Don't do anything else. This job is the canary, not the fix.
