---
name: downloads-triage
description: When new files land in ~/Downloads, categorize them and log a brief summary. Demonstrates file_added external triggers.
max_turns: 6
max_budget_usd: 0.15
cwd: ~
effort: low
model: haiku
setting_sources: ""
strict_mcp_config: true
debounce_seconds: 300
external_triggers:
  - {type: file_added, path: ~/Downloads, quiet_seconds: 60}
semantic_hooks:
  - Want to triage or categorize newly downloaded files
  - Need a summary of recent downloads
---

<!--
CUSTOMIZE BEFORE INSTALLING (optional):
- Change the `path` in external_triggers if you want to watch a different folder.
- Change `quiet_seconds` to tune how long after a download burst this fires.
- Adjust `debounce_seconds` to cap how often this fires no matter what.
-->

List files added to ~/Downloads in the last 30 minutes that you haven't already categorized. For each:

1. Note the filename and extension.
2. Make a one-line guess at what it is (screenshot, installer, PDF paper, media, etc.) based on the name and extension alone. Do not open the file.
3. Optionally suggest a destination folder if the category is obvious (e.g. images → ~/Pictures, installers → /Applications after install, academic PDFs → ~/Documents/papers).

Append your report to ~/.claude/scheduled-jobs/downloads-triage-feed.md in this format:

```
## <ISO8601 UTC>

- `<filename>` — <one-line guess>; suggest: <destination or "none">
- ...
```

Do not move or modify any files. Do not open any files. Exit after writing the report.

If you see zero new downloads since the last run, write a single-line no-op note and exit.
