---
name: workspace-cleanup
version: "1.0.0"
description: Weekly scan of Desktop and Documents for stale files, generic names, and clutter. Report only — never deletes.
cron: "0 17 * * 0"
complexity: 0.15   # weekly ls-and-categorize on two directories
cwd: ~
setting_sources: ""
strict_mcp_config: true
tags:
  - organization
  - desktop
  - files
  - cleanup
  - stale
  - weekly
semantic_hooks:
  - Want to clean up stale files on my Desktop or Documents
  - Need to find old screenshots or unnamed files cluttering my workspace
---

<!--
CUSTOMIZE BEFORE INSTALLING (optional):
- Change the scanned directories (default: ~/Desktop and ~/Documents, non-recursive).
- Adjust the staleness threshold (default: 30 days since last access).
-->

Scan `~/Desktop` and `~/Documents` (top-level only, not recursive) for:

1. **Stale files** — not accessed in 30+ days. Use `stat -f '%a %N'` (macOS) to get access time.
2. **Generic names** — files matching patterns like `Screenshot*`, `Untitled*`, `New Document*`, `Screen Recording*`, `IMG_*`, `image*`.
3. **Large files** — anything over 100MB. Use `stat -f '%z %N'` to get size.

Write the report to `~/.clauck/workspace-cleanup-feed.md`, appending:

```
## <ISO8601 UTC>

### Stale (N files, not accessed in 30+ days)
- `filename.ext` — last accessed <date>, <size>
- ...

### Generic names (N files)
- `Screenshot 2025-01-15 at 10.23.45.png` — <size>, <age>
- ...

### Large files (N files, >100MB)
- `recording.mov` — 2.1GB, last accessed <date>
- ...
```

**Do not delete, move, or modify any files.** Report only.

If nothing found in any category: write `## <UTC>: workspace clean` and exit.
