# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| Latest release | Yes |
| Older releases | Best-effort only |

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, use [GitHub's private security advisory feature](https://github.com/CoreyRDean/open-claude-cron/security/advisories/new) to report the vulnerability. You'll receive a response within 72 hours.

If you're unable to use GitHub advisories, email the maintainer directly (see the GitHub profile for contact info).

## Threat model

open-claude-cron runs `claude -p` sessions with `--dangerously-skip-permissions` under a launchd LaunchAgent. This means:

- **Job prompts have full CLI access** to everything the installing user's account can reach. A malicious or poorly-written job prompt can read, write, or delete files, make network requests, and interact with any MCP the user has configured.
- **The scheduler runs every 60 seconds.** A compromised `scheduler.py` or `run-job.sh` executes on that cadence.
- **The auto-updater checks GitHub Releases.** If `auto_apply` is enabled and the upstream repo is compromised, malicious code could be pulled and installed automatically. This is why `auto_apply` defaults to `false` and users are prompted about auto-updates during installation.

### What we do to mitigate

- **Auto-apply is off by default.** The auto-updater notifies about new versions but never applies them unless the user has explicitly opted in.
- **Releases are the update gate.** Pushes to `main` never trigger updates. Only GitHub Releases do.
- **Fork-first design.** Users can install from their own fork and the update channel points exclusively at that fork. No mechanism exists for the upstream repo to push anything to a fork-installed user.
- **Installer prompts before acting.** The installer enumerates exactly what it will do and requires confirmation before writing any files.
- **No secrets in job prompts.** The system uses the user's existing MCP surface (which they've already authenticated) rather than storing credentials in job files.
- **Pre-flight failures are observable.** Every job run produces a log file before any work begins. Silent failures are architecturally prevented.

### What users should do

- **Review job prompts before installing them.** Library jobs are curated but user-submitted. Read the `.md` file before copying it into your scheduled-jobs directory.
- **Prefer notify-only auto-updates** (`auto_apply: false`, the default). When a new version is available, review the release notes before applying.
- **Fork if you need full control.** Installing from your own fork means you review every change before it reaches your machine.
- **Monitor logs.** `~/.claude/scheduled-jobs/<name>-*.log` files show exactly what each job did. Review periodically.

## Scope

This policy covers the open-claude-cron codebase (`install.sh`, `scheduler.py`, `run-job.sh`, `trigger-job.sh`, `update-check.sh`, the skill, and the library). It does not cover the Claude CLI itself, Claude's model behavior, or MCP server implementations.
