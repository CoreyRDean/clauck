# Temporary monitoring for a time-bound event

**Who:** On-call engineer or event coordinator

**Intent:** "We're deploying a critical migration tonight. I want a job that checks the health endpoint every 15 minutes from midnight to 6am, posts any failures to Slack immediately, and then deletes itself when the window closes. I don't want to remember to clean it up."

**Context:** Monitoring for a specific event is temporary by nature. Setting up permanent monitoring for a 6-hour window creates zombie jobs. The user wants to express the intent once, have it execute for the bounded window, and clean up automatically. No orphaned jobs, no "what is this old thing" six months later.

**Success:** A single natural-language request creates a job with `cron: "*/15 * * * *"`, `valid_after` for midnight tonight, `expires_after` for 6am tomorrow. The job fires every 15 minutes during the window, posts any issues, and auto-disables when the window closes. The user wakes up to either silence (all clear) or a thread of alerts with timestamps.
