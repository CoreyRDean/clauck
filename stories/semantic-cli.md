# Managing jobs from the terminal in plain English

**Who:** Developer who lives in the terminal

**Intent:** "I don't want to open a Claude session to manage my jobs. I want to type `clauck every morning check my PRs and post to slack` and have it just work. Or `clauck pause everything for the weekend` or `clauck what ran today`. One command, plain English, immediate result."

**Context:** The full Claude session is powerful but heavyweight for quick management tasks. The user wants the speed of a CLI with the understanding of natural language. They shouldn't need to know frontmatter, cron syntax, or file paths for common operations.

**Success:** Any text after `clauck` that doesn't match a built-in command gets interpreted as a natural-language instruction. Claude handles it in the background: creates jobs, edits schedules, pauses things, shows status — and the output comes back to the terminal as if it were a normal CLI response. The user never sees "Claude is thinking." They just see the result.
