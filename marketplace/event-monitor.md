---
name: event-monitor
version: "1.0.0"
description: Time-bounded health checker. Runs every 15 minutes inside a configurable window, posts alerts on failure, and auto-expires when the window closes. No cleanup needed.
cron: "*/15 * * * *"
valid_after: "2026-01-01T00:00:00"
expires_after: "2026-01-01T06:00:00"
max_turns: 5
max_budget_usd: 0.10
cwd: ~
effort: low
model: haiku
setting_sources: ""
inputs:
  - {name: HEALTH_URL, default: "https://example.com/health"}
  - {name: ALERT_CHANNEL, default: ""}
tags:
  - monitoring
  - health-check
  - temporary
  - on-call
  - deployment
  - event
  - time-bounded
semantic_hooks:
  - Monitor a deployment or migration health endpoint for a limited window
  - Set up temporary monitoring that auto-disables after an event
  - Watch a health endpoint overnight and alert on failure
---

<!--
CUSTOMIZE BEFORE INSTALLING:
1. Set `valid_after` to the start of your monitoring window (ISO 8601, local or UTC).
   Example: "2026-04-18T00:00:00" to start at midnight tonight.
2. Set `expires_after` to the end of your window. The job auto-disables when it passes
   — no cleanup required.
3. Set `HEALTH_URL` input default to your actual endpoint.
   Or leave the default and pass it at fire-time: `clauck fire event-monitor HEALTH_URL=https://...`
4. Optionally set `ALERT_CHANNEL` to a Slack channel or DM ID (e.g. D0XXXXXX) to receive
   failure alerts via Slack. Leave empty to write alerts to a local file instead.
5. Optionally adjust the `cron` interval. `*/15 * * * *` fires every 15 minutes.
   Use `*/5 * * * *` for a tighter watch, `0 * * * *` for hourly.
6. Rename the job before installing if you have multiple monitors running in parallel.
-->

You are a health monitor for a time-bounded event window. Your only job is to check the health endpoint and alert on failure. Be fast and terse — no commentary, no summaries, just the check and any alert.

**Health endpoint:** `$CLAUCK_INPUT_HEALTH_URL`
**Alert channel:** `$CLAUCK_INPUT_ALERT_CHANNEL` (empty = local file)

## Steps

1. Fetch `$CLAUCK_INPUT_HEALTH_URL` using WebFetch.
   - If the fetch fails (connection refused, timeout, DNS error): treat as UNHEALTHY.
   - If the HTTP status is 2xx: treat as HEALTHY.
   - If the HTTP status is 4xx or 5xx: treat as UNHEALTHY.
   - If the response body contains a `status` field that is not `"ok"`, `"healthy"`, or `"up"` (case-insensitive): treat as UNHEALTHY.

2. If HEALTHY: exit immediately. Write nothing, post nothing. Silence is the all-clear.

3. If UNHEALTHY:
   - Compose a brief alert:
     ```
     ⚠️ event-monitor UNHEALTHY — <timestamp UTC>
     URL: <HEALTH_URL>
     Reason: <one-line: HTTP <status>, connection refused, or body: <excerpt>]>
     ```
   - **If `$CLAUCK_INPUT_ALERT_CHANNEL` is set:** post the alert to that Slack channel using the Slack MCP. Thread under a root message titled `event-monitor alerts`; search for an existing thread first.
   - **If `$CLAUCK_INPUT_ALERT_CHANNEL` is empty:** append the alert to `~/event-monitor-alerts.log` with a newline separator.

4. Exit. Do not retry, do not sleep, do not attempt remediation.
