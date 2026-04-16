# Migrate from ~/.claude/scheduled-jobs to ~/.clauck — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all clauck-owned state out of `~/.claude/` into `~/.clauck/` to eliminate non-overridable Claude Code sandbox write-protection on `~/.claude/` paths. Resolves #26.

**Architecture:** Single root-path substitution (`~/.claude/scheduled-jobs` → `~/.clauck`) across all runtime, CLI, installer, and docs. Internal layout stays the same — only the root changes. Claude-native assets (SKILL.md, marketplace, settings.json hook entry) stay in `~/.claude/`. Installer detects legacy installs and migrates automatically.

**Tech Stack:** `/usr/bin/python3`, `/bin/zsh` (no new deps)

---

## Path Mapping

| Old path | New path | Notes |
|---|---|---|
| `~/.claude/scheduled-jobs/` | `~/.clauck/` | Root move |
| `~/.claude/scheduled-jobs/scheduler.py` | `~/.clauck/scheduler.py` | Runtime |
| `~/.claude/scheduled-jobs/run-job.sh` | `~/.clauck/run-job.sh` | Runtime |
| `~/.claude/scheduled-jobs/trigger-job.sh` | `~/.clauck/trigger-job.sh` | Runtime |
| `~/.claude/scheduled-jobs/dag-runner.py` | `~/.clauck/dag-runner.py` | Runtime |
| `~/.claude/scheduled-jobs/update-check.sh` | `~/.clauck/update-check.sh` | Runtime |
| `~/.claude/scheduled-jobs/uninstall.sh` | `~/.clauck/uninstall.sh` | Runtime |
| `~/.claude/scheduled-jobs/*.md` | `~/.clauck/*.md` | Jobs |
| `~/.claude/scheduled-jobs/<module>/` | `~/.clauck/<module>/` | Module jobs |
| `~/.claude/scheduled-jobs/.state/` | `~/.clauck/.state/` | State |
| `~/.claude/scheduled-jobs/.manifest.json` | `~/.clauck/.manifest.json` | Manifest |
| `~/.claude/scheduled-jobs/.clauck.config.json` | `~/.clauck/.clauck.config.json` | Config |
| `~/.claude/scheduled-jobs/.version` | `~/.clauck/.version` | Version |
| `~/.claude/scheduled-jobs/.build-source` | `~/.clauck/.build-source` | Build info |
| `~/.claude/scheduled-jobs/.scheduler-*.log` | `~/.clauck/.scheduler-*.log` | Scheduler logs |
| `~/.claude/scheduled-jobs/<name>-*.log` | `~/.clauck/<name>-*.log` | Job logs |
| `~/.claude/scheduled-jobs-prompt.md` | `~/.clauck/prompt.md` | Global prompt |

### Stays in ~/.claude (Claude-native assets)

| Path | Why |
|---|---|
| `~/.claude/skills/clauck/SKILL.md` | Claude skill mechanism |
| `~/.claude/skills/clauck/marketplace/` | Marketplace browsing via skill |
| `~/.claude/hooks/scheduled-jobs-notice.sh` | Claude SessionStart hook mechanism (internal paths update) |
| `~/.claude/settings.json` hook entry | Claude settings (command path stays the same) |

### Stays outside (already correct)

| Path | Notes |
|---|---|
| `~/.local/bin/clauck` | CLI binary |
| `~/Library/LaunchAgents/com.$USER.claude-scheduler.plist` | LaunchAgent (internal paths update) |

## Substitution Pattern

The migration is a mechanical substitution with three patterns:

1. **Python pathlib**: `HOME / ".claude" / "scheduled-jobs"` → `HOME / ".clauck"`
2. **Shell variables**: `$HOME/.claude/scheduled-jobs` → `$HOME/.clauck`
3. **Documentation/prose**: `~/.claude/scheduled-jobs` → `~/.clauck`
4. **Global prompt special case**: `$HOME/.claude/scheduled-jobs-prompt.md` → `$HOME/.clauck/prompt.md` and `HOME / ".claude" / "scheduled-jobs-prompt.md"` → `HOME / ".clauck" / "prompt.md"`

---

## Task 1: Python runtime path constants

**Files:**
- Modify: `lib/clauck:46` (JOBS_DIR constant)
- Modify: `lib/scheduler.py:33-40` (JOBS_DIR, GLOBAL_PROMPT constants)
- Modify: `lib/dag-runner.py:33-38` (JOBS_DIR constant)

- [ ] **Step 1: Update `lib/clauck` JOBS_DIR**

```python
# Line 46: change
JOBS_DIR = HOME / ".claude" / "scheduled-jobs"
# to
JOBS_DIR = HOME / ".clauck"
```

All downstream constants (STATE_DIR, MANIFEST, VERSION_FILE, CONFIG_FILE, TRIGGER_SCRIPT, UPDATE_SCRIPT, UNINSTALL_SCRIPT) derive from JOBS_DIR — no changes needed.

- [ ] **Step 2: Update `lib/scheduler.py` path constants**

```python
# Lines 33-35: change
JOBS_DIR = HOME / ".claude" / "scheduled-jobs"
STATE_DIR = JOBS_DIR / ".state"
GLOBAL_PROMPT = HOME / ".claude" / "scheduled-jobs-prompt.md"
# to
JOBS_DIR = HOME / ".clauck"
STATE_DIR = JOBS_DIR / ".state"
GLOBAL_PROMPT = JOBS_DIR / "prompt.md"
```

All other constants derive from JOBS_DIR — unchanged.

- [ ] **Step 3: Update `lib/dag-runner.py` path constants**

```python
# Line 33: change
JOBS_DIR = HOME / ".claude" / "scheduled-jobs"
# to
JOBS_DIR = HOME / ".clauck"
```

All other constants derive from JOBS_DIR — unchanged.

- [ ] **Step 4: Verify Python syntax**

```bash
/usr/bin/python3 -c "import ast; ast.parse(open('lib/clauck').read())"
/usr/bin/python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())"
/usr/bin/python3 -c "import ast; ast.parse(open('lib/dag-runner.py').read())"
```

Expected: all three exit 0.

- [ ] **Step 5: Commit**

```bash
git add lib/clauck lib/scheduler.py lib/dag-runner.py
git commit -m "feat: migrate Python runtime paths from ~/.claude/scheduled-jobs to ~/.clauck"
```

---

## Task 2: Shell runtime path constants

**Files:**
- Modify: `lib/run-job.sh:6,41,43`
- Modify: `lib/trigger-job.sh:5,37`
- Modify: `lib/update-check.sh:13,38,58-59,62,96-97`
- Modify: `lib/scheduled-jobs-notice.sh:12,15-16,38,69,101,106,110`
- Rename: `lib/scheduled-jobs-prompt.md` → `lib/prompt.md` (and update content)

- [ ] **Step 1: Update `lib/run-job.sh`**

```bash
# Line 6 comment: ~/.claude/scheduled-jobs/<name>.md → ~/.clauck/<name>.md
# Line 41: JOBS_DIR="$HOME/.claude/scheduled-jobs" → JOBS_DIR="$HOME/.clauck"
# Line 43: GLOBAL_PROMPT="$HOME/.claude/scheduled-jobs-prompt.md" → GLOBAL_PROMPT="$HOME/.clauck/prompt.md"
```

- [ ] **Step 2: Update `lib/trigger-job.sh`**

```bash
# Line 5 comment: ~/.claude/scheduled-jobs/.manifest.json → ~/.clauck/.manifest.json
# Line 37: exec /usr/bin/python3 "$HOME/.claude/scheduled-jobs/scheduler.py" → exec /usr/bin/python3 "$HOME/.clauck/scheduler.py"
```

- [ ] **Step 3: Update `lib/update-check.sh`**

All `$HOME/.claude/scheduled-jobs` → `$HOME/.clauck`. All `~/.claude/scheduled-jobs` in comments/strings → `~/.clauck`. Six locations (lines 13, 38, 58, 59, 62, 96-97).

- [ ] **Step 4: Update `lib/scheduled-jobs-notice.sh`**

All `~/.claude/scheduled-jobs` → `~/.clauck`. The hook script stays at `~/.claude/hooks/scheduled-jobs-notice.sh` but its internal path references change. Eight locations (lines 12, 15, 16, 38, 69, 101, 106, 110).

- [ ] **Step 5: Rename `lib/scheduled-jobs-prompt.md` → `lib/prompt.md`**

```bash
git mv lib/scheduled-jobs-prompt.md lib/prompt.md
```

Update any internal path references within the file from `~/.claude/scheduled-jobs` → `~/.clauck`.

- [ ] **Step 6: Verify shell syntax**

```bash
bash -n lib/run-job.sh
bash -n lib/trigger-job.sh
bash -n lib/update-check.sh
bash -n lib/scheduled-jobs-notice.sh
```

Expected: all four exit 0.

- [ ] **Step 7: Commit**

```bash
git add lib/run-job.sh lib/trigger-job.sh lib/update-check.sh lib/scheduled-jobs-notice.sh lib/prompt.md
git commit -m "feat: migrate shell runtime paths from ~/.claude/scheduled-jobs to ~/.clauck"
```

---

## Task 3: Installer — new paths + migration logic

**Files:**
- Modify: `install.sh` (27 occurrences across directory creation, file placement, plist generation, settings.json patching, verification, banner)

This is the highest-risk task. The installer must:
1. Create `~/.clauck/` instead of `~/.claude/scheduled-jobs/`
2. Install files to new locations
3. **Detect legacy installs** and migrate them
4. Update the LaunchAgent plist to invoke `~/.clauck/scheduler.py`
5. Update the prompt file destination
6. Keep `~/.claude/skills/clauck/` and `~/.claude/hooks/` unchanged

- [ ] **Step 1: Update directory creation**

Replace `$HOME/.claude/scheduled-jobs` with `$HOME/.clauck` in `make_dirs()`.
Keep `$HOME/.claude/skills/clauck` and `$HOME/.claude/hooks` as-is.

- [ ] **Step 2: Update `install_files()` destinations**

```bash
# Runtime scripts → ~/.clauck/
install_file "$repo/lib/scheduler.py"     "$HOME/.clauck/scheduler.py"     755
install_file "$repo/lib/run-job.sh"       "$HOME/.clauck/run-job.sh"       755
install_file "$repo/lib/trigger-job.sh"   "$HOME/.clauck/trigger-job.sh"   755
install_file "$repo/lib/update-check.sh"  "$HOME/.clauck/update-check.sh"  755
install_file "$repo/lib/dag-runner.py"    "$HOME/.clauck/dag-runner.py"    755
install_file "$repo/uninstall.sh"         "$HOME/.clauck/uninstall.sh"     755

# Prompt file → ~/.clauck/prompt.md (was scheduled-jobs-prompt.md)
install_file "$repo/lib/prompt.md"        "$HOME/.clauck/prompt.md"        644

# Hook stays in ~/.claude/hooks/ (Claude-native)
install_file "$repo/lib/scheduled-jobs-notice.sh" "$HOME/.claude/hooks/scheduled-jobs-notice.sh" 755

# CLI stays at ~/.local/bin/
install_file "$repo/lib/clauck"           "$HOME/.local/bin/clauck"        755

# Skill + marketplace stay in ~/.claude/skills/
install_file "$repo/skill/clauck/SKILL.md" "$HOME/.claude/skills/clauck/SKILL.md" 644
```

- [ ] **Step 3: Update LaunchAgent plist generation**

Change the ProgramArguments to invoke `$HOME/.clauck/scheduler.py`.
Change StandardOutPath/StandardErrorPath to `$HOME/.clauck/.scheduler-stdout.log` and `.scheduler-stderr.log`.

- [ ] **Step 4: Update version/build-source/config writes**

All `.version`, `.build-source`, `.clauck.config.json` writes target `$HOME/.clauck/`.

- [ ] **Step 5: Add legacy migration**

After `make_dirs`, before `install_files`:

```bash
migrate_legacy() {
    local legacy="$HOME/.claude/scheduled-jobs"
    local target="$HOME/.clauck"
    [ -d "$legacy" ] || return 0
    [ -d "$target" ] && [ -f "$target/.version" ] && return 0  # already migrated

    section "Migrating from ~/.claude/scheduled-jobs → ~/.clauck"

    # Copy user data: jobs, state, logs, config, version, build-source
    for f in "$legacy"/*.md "$legacy"/*.log; do
        [ -f "$f" ] && cp -p "$f" "$target/" && ok "migrated $(basename "$f")"
    done
    # Module job directories
    for d in "$legacy"/*/; do
        local name=$(basename "$d")
        case "$name" in .state|.*) continue ;; esac
        [ -f "$d/JOB.md" ] && cp -rp "$d" "$target/" && ok "migrated module $name/"
    done
    # State directory
    [ -d "$legacy/.state" ] && cp -rp "$legacy/.state" "$target/.state" && ok "migrated .state/"
    # Config files
    for f in .clauck.config.json .version .build-source; do
        [ -f "$legacy/$f" ] && cp -p "$legacy/$f" "$target/$f"
    done
    # Global prompt
    [ -f "$HOME/.claude/scheduled-jobs-prompt.md" ] && cp -p "$HOME/.claude/scheduled-jobs-prompt.md" "$target/prompt.md"

    # Leave breadcrumb
    cat > "$legacy/MIGRATED.md" <<MIGRATED
# clauck has moved

All clauck data has been migrated to \`~/.clauck/\`.

This directory is no longer used by clauck. You can safely delete it:
    rm -rf ~/.claude/scheduled-jobs

The migration happened on: $(date -u +%Y-%m-%dT%H:%M:%SZ)
MIGRATED
    ok "migration complete — legacy data preserved at $legacy with MIGRATED.md breadcrumb"
}
```

- [ ] **Step 6: Update verification paths**

Heartbeat log search: `$HOME/.clauck/heartbeat-*.log`
Trigger script: `$HOME/.clauck/trigger-job.sh`

- [ ] **Step 7: Update banner paths**

All `~/.claude/scheduled-jobs/` → `~/.clauck/` in the banner output.

- [ ] **Step 8: Update confirm_plan output**

Add migration line if legacy install detected.

- [ ] **Step 9: Verify installer syntax**

```bash
bash -n install.sh
```

- [ ] **Step 10: Commit**

```bash
git add install.sh
git commit -m "feat: installer targets ~/.clauck with legacy migration from ~/.claude/scheduled-jobs"
```

---

## Task 4: Uninstaller

**Files:**
- Modify: `uninstall.sh` (14 occurrences)

- [ ] **Step 1: Update all paths**

Change every `$HOME/.claude/scheduled-jobs` to `$HOME/.clauck`. Update the FILES array, directory cleanup paths, and the settings.json hook removal (hook stays in `~/.claude/hooks/`, that path is unchanged).

Also: update `$HOME/.claude/scheduled-jobs-prompt.md` references to `$HOME/.clauck/prompt.md`.

- [ ] **Step 2: Add legacy cleanup**

If `--wipe` is passed and `~/.claude/scheduled-jobs/` exists (legacy), remove it too.

- [ ] **Step 3: Verify syntax**

```bash
bash -n uninstall.sh
```

- [ ] **Step 4: Commit**

```bash
git add uninstall.sh
git commit -m "feat: uninstaller targets ~/.clauck with legacy cleanup"
```

---

## Task 5: Documentation — CLAUDE.md + CONTRIBUTING.md

**Files:**
- Modify: `CLAUDE.md` (12 occurrences — key paths table, architecture diagram, frontmatter schema examples)
- Modify: `CONTRIBUTING.md` (path references in development setup, testing)

- [ ] **Step 1: Update CLAUDE.md**

Replace all `~/.claude/scheduled-jobs` with `~/.clauck` in:
- Architecture ASCII diagram
- "Key paths (installed)" table
- Test commands
- Any prose references

Update `~/.claude/scheduled-jobs-prompt.md` → `~/.clauck/prompt.md`.

Keep `~/.claude/skills/clauck/` and `~/.claude/hooks/` references as-is.

- [ ] **Step 2: Update CONTRIBUTING.md**

Update any path references in development setup or testing sections.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md CONTRIBUTING.md
git commit -m "docs: update CLAUDE.md and CONTRIBUTING.md paths for ~/.clauck migration"
```

---

## Task 6: Documentation — SKILL.md (64 occurrences!)

**Files:**
- Modify: `skill/clauck/SKILL.md` (64 occurrences — the biggest single file)

- [ ] **Step 1: Bulk replace**

This file has the most references. Use replace-all on `~/.claude/scheduled-jobs` → `~/.clauck`.

Also update `~/.claude/scheduled-jobs-prompt.md` → `~/.clauck/prompt.md`.

Keep `~/.claude/skills/clauck/` references as-is.

- [ ] **Step 2: Commit**

```bash
git add skill/clauck/SKILL.md
git commit -m "docs: update SKILL.md paths for ~/.clauck migration"
```

---

## Task 7: Documentation — remaining files

**Files:**
- Modify: `README.md` (path references if any)
- Modify: `RELEASES.md` (2 occurrences)
- Modify: `SECURITY.md` (1 occurrence)
- Modify: `claude-install-prompt.md` (2 occurrences)
- Modify: `.github/ISSUE_TEMPLATE/bug_report.md` (3 occurrences)
- Modify: `.github/workflows/ci.yml` (1 occurrence — dry-run test)
- Modify: `jobs/clauck-work.md` (5 occurrences — path references in prompt)
- Modify: `marketplace/daily-verify.md`, `downloads-triage.md`, `git-commit-nudge.md`, `inbox-zero-assist.md`, `workspace-cleanup.md` (1 each)
- Modify: `lib/prompt.md` (7 occurrences — already renamed in Task 2)

- [ ] **Step 1: Bulk replace across all remaining files**

For each file, replace `~/.claude/scheduled-jobs` → `~/.clauck` and `scheduled-jobs-prompt.md` → `prompt.md` where appropriate.

- [ ] **Step 2: Verify no stale references remain**

```bash
grep -rn '\.claude/scheduled-jobs' --include='*.md' --include='*.sh' --include='*.py' --include='*.json' --include='*.yml' | grep -v '.git/' | grep -v 'MIGRATED'
```

Expected: zero results (except possibly `scheduled-jobs-notice.sh` which stays in `~/.claude/hooks/` — but its INTERNAL references should all be updated).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: update all remaining path references for ~/.clauck migration"
```

---

## Task 8: Integration test

- [ ] **Step 1: Full syntax check**

```bash
bash -n install.sh && bash -n uninstall.sh && bash -n lib/run-job.sh && bash -n lib/trigger-job.sh && bash -n lib/update-check.sh && bash -n lib/scheduled-jobs-notice.sh
/usr/bin/python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())"
/usr/bin/python3 -c "import ast; ast.parse(open('lib/dag-runner.py').read())"
/usr/bin/python3 -c "import ast; ast.parse(open('lib/clauck').read())"
/usr/bin/python3 -c "import json; json.load(open('marketplace/index.json'))"
```

- [ ] **Step 2: Dry-run install**

```bash
bash install.sh --dry-run --yes
```

Verify all paths in the plan output point to `~/.clauck/`.

- [ ] **Step 3: Stale reference audit**

```bash
grep -rn 'scheduled-jobs' --include='*.md' --include='*.sh' --include='*.py' --include='*.json' --include='*.yml' | grep -v '.git/' | grep -v 'MIGRATED' | grep -v 'scheduled-jobs-notice'
```

Expected: only the hook filename itself (`scheduled-jobs-notice.sh`) appears — no path references to `~/.claude/scheduled-jobs`.

- [ ] **Step 4: Final commit (if any fixups needed)**

---

## Execution Notes

- **Tasks 1 + 2** can run in parallel (Python and shell are independent).
- **Task 3** (installer) depends on Tasks 1+2 being done (needs to know the renamed prompt file).
- **Task 4** (uninstaller) is independent of Tasks 1-3.
- **Tasks 5, 6, 7** (docs) are independent of each other and of Tasks 1-4.
- **Task 8** (integration test) depends on everything else.

The mechanical substitution is the same everywhere — the risk is in the installer migration logic (Task 3) and in missing a reference (caught by Task 8 Step 3).
