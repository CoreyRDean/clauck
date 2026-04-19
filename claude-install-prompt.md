# Install clauck on this machine

You are a Claude CLI session invoked by a user who wants to install the
`clauck` system on their macOS machine. Do this autonomously
and report cleanly.

## What to do

1. Run the shell installer. It handles all file placement, LaunchAgent
   registration, settings.json patching, and end-to-end verification:

   ```
   bash <(curl -fsSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh)
   ```

2. If the installer exits 0, the system is installed and has already proven
   itself working by firing a heartbeat job ad-hoc. Report the success banner
   verbatim to the user, then briefly explain:
   - Default heartbeat job is running hourly, ~$1/month.
   - SessionStart hook (shipped by the clauck plugin) will advertise the
     system to future Claude Code sessions.
   - The `/clauck:clauck` skill (also shipped by the plugin) is how they
     manage it going forward. Invoke it in any CC session.
   - **If they also use Claude Desktop**: they can integrate it there by
     pasting *"Create a new CoWork plugin from https://github.com/CoreyRDean/clauck"*
     into any Desktop chat. Desktop handles plugin creation natively.

3. If the installer exits non-zero, diagnose:
   - Check the printed error for the specific step that failed.
   - If it's a preflight failure (missing `claude` CLI, missing python3),
     tell the user exactly what to install and stop.
   - If it's the verification step (`exit_code=3`), the files are placed but
     the heartbeat didn't complete. Tail `~/.clauck/heartbeat-*.log`
     and `~/.clauck/.scheduler-stderr.log`, explain the root
     cause, and recommend a fix.

4. After success, ask the user one question: **"What would you like to
   schedule first?"** Have the `scheduled-jobs` skill loaded and be ready to
   design the job with them. Common starting points:
   - Hourly or daily digest of some external system (Slack, Jira, Gmail, GitHub)
   - File-watcher trigger (e.g., triage new PDFs in `~/Downloads`)
   - Process-triggered job (e.g., when a specific app opens)
   - Deep-chain daily verifier (a template ships in the repo's
     `templates/example-daily-verify.md.template`)

## Do not

- Do not attempt to install the files yourself by running `cp` and
  `launchctl load`. The installer is the source of truth and handles
  edge cases (USER substitution in plist, settings.json merge, etc.).
- Do not run the install twice. It is idempotent but running it twice
  wastes time.
- Do not proceed past a verification failure. The installer exits non-zero
  specifically so you stop and diagnose.

Start with step 1 now.
