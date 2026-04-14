# Contributing to open-claude-cron

Thanks for considering contributing. This project is young and benefits from improvements to the scheduler, new library jobs, documentation, and bug reports.

## Quick links

- [Open an issue](https://github.com/CoreyRDean/open-claude-cron/issues/new/choose) for bugs, feature requests, or questions.
- [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
- [Library contribution guide](#adding-a-job-to-the-library) below for submitting pre-made jobs.

## Development setup

```bash
git clone https://github.com/CoreyRDean/open-claude-cron.git
cd open-claude-cron
bash install.sh   # installs from local checkout (detects the repo tree)
```

The installer uses the local `lib/`, `jobs/`, and `skill/` directories when it detects it's running from a checked-out repo. No network clone happens.

## Branch and commit conventions

- **`main`** is the stable branch. All PRs target `main`.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format:
  ```
  feat: add file_changed external trigger type
  fix: prevent rotation count inflation when NULL_GLOB is set
  docs: add cost reality table to SKILL.md
  chore: update library index with new job
  ```
- Keep commits atomic — one logical change per commit.

## Pull requests

1. Fork the repo and create a feature branch from `main`.
2. Make your changes. Run the installer from your checkout to verify.
3. If you touched `scheduler.py`, run the parser + evaluator tests:
   ```bash
   /usr/bin/python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())" && echo OK
   ```
4. If you touched `install.sh` or `uninstall.sh`, syntax-check:
   ```bash
   bash -n install.sh && bash -n uninstall.sh && echo OK
   ```
5. Open a PR against `main`. Describe what changed and why.

### PR checklist

- [ ] `install.sh` still installs cleanly on a fresh system (test with `HOME=/tmp/test-install`)
- [ ] Existing jobs aren't broken by the change
- [ ] CHANGELOG.md updated under `[Unreleased]` if user-facing
- [ ] No secrets, API keys, or personal paths committed

## Adding a job to the library

The library lives at `library/` in the repo. When users install or update open-claude-cron, the library is cached locally at `~/.claude/skills/scheduled-jobs/library/` so Claude can browse and install jobs offline.

### Requirements for library jobs

1. **Self-contained.** A library job is a single `.md` file with standard YAML frontmatter. No external dependencies beyond the MCPs it declares.
2. **Customization-friendly.** Include a `<!-- CUSTOMIZE BEFORE INSTALLING: -->` HTML comment block in the prompt body listing what the user must edit (channel IDs, paths, ticket keys, etc.). The Claude skill walks users through these during install.
3. **Cost-documented.** Include realistic `max_budget_usd` and `model` values. Users trust the library when costs are transparent.
4. **Tested.** Ad-hoc fire your job (`trigger-job.sh <name>`) and confirm it completes with `exit_code=0` before submitting.
5. **Idempotent.** Jobs run repeatedly. The prompt should tell the LLM how to detect and skip already-completed work.

### Steps to contribute a library job

1. Choose or create a category directory under `library/`. Current categories:

   | Category | Purpose |
   |---|---|
   | `verification/` | Pipeline health checks, MCP drift detection |
   | `organization/` | File management, inbox triage, cleanup |
   | `productivity/` | Digests, summaries, reminders |
   | `monitoring/` | Service health, error alerting |

   New categories are welcome if existing ones don't fit.

2. Create `library/<category>/<name>.md` with standard frontmatter. Use an existing library job as a template.

3. Add an entry to `library/index.json`:
   ```json
   {
     "name": "<name>",
     "path": "<category>/<name>.md",
     "category": "<category>",
     "tags": ["<tag1>", "<tag2>"],
     "one_line": "<single sentence: what it does, when it fires>",
     "schedule": "<plain English: 'daily at 09:00 UTC' or 'event-driven (file_added)'>",
     "cost_per_run_usd_approx": 0.04,
     "runs_per_month_approx": 30,
     "monthly_cost_usd_approx": 1.20,
     "requires": {
       "mcps": "<free-form: 'Slack' or 'none' or 'any chat MCP'>",
       "setup": ["<step 1>", "<step 2>"]
     }
   }
   ```

4. Open a PR against `main` with the new job + index entry. The PR description should include the ad-hoc fire log showing `exit_code=0`.

### What makes a great library job

- **Solves a real problem** that many Claude users have.
- **Minimal cost** for maximum value — prefer Haiku + `setting_sources: ""` unless MCP access is genuinely needed.
- **Demonstrates a feature** newcomers might not discover on their own (external triggers, semantic hooks, debouncing).
- **Clear prompt** that the LLM can execute in 1-5 turns with no ambiguity.

## Modifying the core system

Changes to `scheduler.py`, `run-job.sh`, `trigger-job.sh`, `install.sh`, or `uninstall.sh` affect every user on their next update. These PRs get extra scrutiny:

- **Backward compatibility.** New frontmatter fields must have defaults that preserve existing behavior. Jobs without the new field should work identically to before.
- **No new dependencies.** The system runs on `/usr/bin/python3` (Apple-bundled, no pip) and `/bin/zsh`. Don't introduce `pip install`, `brew`, or compiled binaries.
- **Minimal YAML parser.** We ship a ~60-line subset parser, not PyYAML. If your feature needs a new YAML construct, extend the parser minimally and test the edge cases.
- **Cost awareness.** If a change increases cache-creation tokens (adding new system prompt text, enabling more MCP surface, etc.), quantify the per-run cost impact in the PR.

## Releases

Only the maintainer cuts releases. The process:

1. Move `[Unreleased]` items in CHANGELOG.md to a new dated section.
2. Update `VERSION` file.
3. Commit: `chore: release vX.Y.Z`
4. Push to `main`.
5. `gh release create vX.Y.Z --title "vX.Y.Z — <tagline>" --notes-file CHANGELOG_EXCERPT.md`

Releases are how the auto-updater discovers new versions. Pushes to `main` alone never trigger user updates.

## Code of conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.
