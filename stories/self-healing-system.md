# System that fixes itself

**Who:** User who doesn't want to debug cron jobs

**Intent:** "If something breaks, I don't want to find out by noticing my morning brief is missing. I want the system to detect the failure, figure out why, fix it if it can, and tell me if it can't. I should wake up to either my brief or a clear explanation of what went wrong and what I need to do."

**Context:** Background automation fails silently by nature. The user invested time setting up their workflow and trusts it to run. When it breaks — an MCP token expires, a path changes, a budget is exceeded — the failure is invisible until the user notices a missing artifact. By then, they've lost days of value. The system should be self-aware enough to detect its own failures and take action.

**Success:** The clauck-work meta job activates when a pipeline node fails. It reads the error, analyzes root cause, and either fixes it (re-enables an auto-disabled job, refreshes a stale state file, adjusts a budget that was too tight) or escalates to the user with a clear diagnostic and specific next steps. The user's trust in the system increases over time because failures are handled, not hidden.
