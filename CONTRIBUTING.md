# Contributing to clauck

Thanks for considering contributing. This project is young and benefits from improvements to the scheduler, new marketplace jobs, documentation, and bug reports.

## Quick links

- [Open an issue](https://github.com/CoreyRDean/clauck/issues/new/choose) for bugs, feature requests, or questions.
- [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
- [Marketplace contribution guide](#adding-a-job-to-the-marketplace) below for submitting pre-made jobs.

## Development setup

```bash
git clone https://github.com/CoreyRDean/clauck.git
cd clauck
bash install.sh   # installs from local checkout (detects the repo tree)
```

The installer uses the local `lib/`, `jobs/`, and `skill/` directories when it detects it's running from a checked-out repo. No network clone happens.

## Branch and commit conventions

- **`main`** is the single long-lived branch. All PRs target `main`. HEAD on `main` may contain unreleased work — this is intentional. The nightly channel ([RELEASES.md](RELEASES.md)) exists so test users can track main HEAD safely; the stable channel pins to tagged commits.
- Feature branches live only for the lifetime of their PR. Do not maintain a long-lived `dev` or `develop` branch.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format:
  ```
  feat: add file_changed external trigger type
  fix: prevent rotation count inflation when NULL_GLOB is set
  docs: add cost reality table to SKILL.md
  chore: update marketplace index with new job
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
- [ ] No secrets, API keys, or personal paths committed

## Adding a job to the marketplace

The marketplace lives at `marketplace/` in the repo. When users install or update clauck, the marketplace is cached locally at `~/.claude/skills/clauck/marketplace/` so Claude can browse and install jobs offline.

### Requirements for marketplace jobs

1. **Self-contained.** A marketplace job is a single `.md` file with standard YAML frontmatter. No external dependencies beyond the MCPs it declares.
2. **Customization-friendly.** Include a `<!-- CUSTOMIZE BEFORE INSTALLING: -->` HTML comment block in the prompt body listing what the user must edit (channel IDs, paths, ticket keys, etc.). The Claude skill walks users through these during install.
3. **Cost-documented.** Include realistic `max_budget_usd` and `model` values. Users trust the marketplace when costs are transparent.
4. **Tested.** Ad-hoc fire your job (`trigger-job.sh <name>`) and confirm it completes with `exit_code=0` before submitting.
5. **Idempotent.** Jobs run repeatedly. The prompt should tell the LLM how to detect and skip already-completed work.

### Steps to contribute a marketplace job

1. Choose a category for your job. Current categories (used as tags):

   | Category tag | Purpose |
   |---|---|
   | `verification` | Pipeline health checks, MCP drift detection |
   | `organization` | File management, inbox triage, cleanup |
   | `productivity` | Digests, summaries, reminders |
   | `monitoring` | Service health, error alerting |

   New categories are welcome if existing ones don't fit. Categories are expressed as the first entry in the `tags` array.

2. Create `marketplace/<name>.md` with standard frontmatter. Use an existing marketplace job as a template.

3. Add an entry to `marketplace/index.json`:
   ```json
   {
     "name": "<name>",
     "path": "<name>.md",
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

### What makes a great marketplace job

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

See [RELEASES.md](RELEASES.md) for the full release channel architecture (stable / nightly / local) and why branch topology is intentionally flat.

**Stable release (maintainer only):**

1. Verify `VERSION` is the version you want to release (it should already match — `VERSION` is bumped in the *first* commit after the previous release, so by the time you cut the next one it's been carrying the target value through the whole development cycle).
2. Tag the stable point: `git tag -a vX.Y.Z main -m "vX.Y.Z" && git push origin vX.Y.Z`
3. `gh release create vX.Y.Z --title "vX.Y.Z — <tagline>" --notes "..."` — **not** a prerelease. GitHub's `/releases/latest` API excludes prereleases, so stable-channel users only see non-prerelease tags.
4. Write the release body inline. The GitHub Releases page is the changelog of record.
5. **Immediately after release:** in the next commit on main, bump `VERSION` to the next target (e.g. `v1.5.7` → `v1.5.8`). Mid-cycle tier bumps (significant feature warranting `v1.6.0`) are allowed but should not happen multiple times per cycle.

**Nightly release:** automated by `.github/workflows/nightly.yml`. Tags main HEAD as `v{VERSION}-{unix_ts}` (e.g. `v1.5.7-1681580000`) daily at 07:00 UTC and publishes a pre-release. SemVer-correct: `v1.5.7-anything < v1.5.7`, so nightlies sort below the stable they're tracking, and chronologically among each other by timestamp. No-op refreshes (unchanged main) are skipped. No manual action required.

Pushes to `main` without a stable tag never trigger stable-channel updates. They do feed the nightly channel on the next scheduled GHA run (or immediate `workflow_dispatch`).

## Code of conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.
