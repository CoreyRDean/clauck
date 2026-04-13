---
name: heartbeat
description: Hourly pipeline liveness check. Minimal-token smoke test; log file is the evidence surface.
cron: "0 * * * *"
max_turns: 1
max_budget_usd: 0.10
cwd: ~
effort: low
model: haiku
# Cost-minimization: disable plugin/settings surface AND the MCP surface. This
# heartbeat doesn't need any tools — it just needs claude to respond at all.
# The log file (written by run-job.sh regardless of claude's output) is the
# evidence that the launchd → shell → claude chain is alive.
setting_sources: ""
strict_mcp_config: true
semantic_hooks:
  - Scheduled pipeline appears unhealthy or heartbeat log is missing for an hour or more
  - Need to verify launchd-driven claude sessions are firing
  - Investigating whether permissions bypass is working under launchd
  - Debugging why scheduled jobs are silently failing
---

Reply with exactly one line in this format, no preamble, no trailing text:

`heartbeat ok <current UTC time in ISO8601>`

That's the entire job. Exit.
