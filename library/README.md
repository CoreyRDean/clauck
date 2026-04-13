# Library of pre-made scheduled jobs

Curated job prompts you can install into your own `open-claude-cron` setup. The install script copies the library into `~/.claude/skills/scheduled-jobs/library/` so any Claude session can browse and copy-install them without cloning the repo.

## Browsing from a Claude session

Ask your Claude session something like:

> "What library jobs are available in open-claude-cron?"
> "Show me library jobs for file organization."
> "Install the daily-verify library job."

The `scheduled-jobs` skill teaches Claude to read `library/index.json`, filter by category/tags, show a summary, and (on confirmation) copy the chosen job to `~/.claude/scheduled-jobs/<name>.md`, prompting for any required customizations.

## Categories

| Category | Purpose |
|---|---|
| `verification/` | Jobs that exercise the pipeline or check health (catch silent drift). |
| `organization/` | Jobs that react to filesystem events and help keep things tidy. |

More categories land as the library grows.

## Adding to the library

1. Create your job file at `library/<category>/<name>.md` with standard YAML frontmatter plus a `<!-- CUSTOMIZE BEFORE INSTALLING: -->` comment describing what users must edit.
2. Add a matching entry to `library/index.json` (pick existing schema; see the two shipped examples).
3. Open a PR against the `main` branch.
4. The maintainer cuts a GitHub Release to propagate the new job to all installed users (subject to their auto-update settings).

## Entry schema

Each entry in `index.json` has:

- `name` — filename stem; becomes the scheduled-job name on install.
- `path` — relative path under `library/` to the `.md` file.
- `category` — directory name; used for filtering.
- `tags` — array of searchable keywords.
- `one_line` — a single-sentence description shown when browsing.
- `schedule` — plain-English schedule (e.g., "daily at 14:00 UTC", "event-driven").
- `cost_per_run_usd_approx`, `runs_per_month_approx`, `monthly_cost_usd_approx` — rough cost expectations on Haiku.
- `requires.mcps` — free-form text about required MCP integrations.
- `requires.setup` — array of plain-English steps the user must complete before the job is useful.
