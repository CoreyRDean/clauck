# Debug a job interactively then save the result

**Who:** User whose scheduled job isn't producing the right output

**Intent:** "My morning-brief job is including too many Slack channels and the calendar section is formatted wrong. I want to see it run live, tell Claude what to change mid-execution, iterate until it looks right, and then say 'save it this way from now on.'"

**Context:** Editing a job prompt blindly and waiting for the next cron fire to see the result is a slow feedback loop. The user wants to see the execution, intervene, iterate, and lock in the changes — all in one session. The job becomes the starting point for a conversation, not a write-and-pray artifact.

**Success:** The user triggers the job with `interactive: true` or via `clauck fire <name> --interactive`. A Terminal window opens showing Claude executing the job's prompt. The user watches the output, then types corrections: "don't include #random channel" or "put calendar events in a table." Claude adjusts. When the user says "save this version," Claude rewrites the job's `.md` file with the updated prompt. The next scheduled run uses the improved version.
