# Release process

clauck ships on two channels. The branch topology is intentionally flat: one
line of history, three labels.

| Channel   | What it is                              | How it advances                               | Who should use it                        |
|-----------|-----------------------------------------|-----------------------------------------------|------------------------------------------|
| `stable`  | Tagged releases like `v1.5.7`           | Maintainer cuts a GitHub Release from main    | Everyone by default                      |
| `nightly` | Rolling pre-release tracking main HEAD  | GHA workflow force-moves the `nightly` tag    | Test users, maintainer's own machine     |
| `local`   | Built from a developer's working tree   | Installed via `bash install.sh` from checkout | You, while iterating on clauck itself    |

`local` is a client-side label — it isn't a branch or tag. When you run
`bash install.sh` from a git checkout, the installer stamps
`~/.claude/scheduled-jobs/.build-source` with `channel: local`, and
`update-check.sh` exits early so you don't get fake update notifications
against a dev tree whose version marker doesn't reflect upstream.

## Branching

- **`main`** is the only long-lived branch. All PRs target it.
- HEAD on main may contain unreleased work. That's expected — the nightly
  channel exists specifically so test users can ride main safely while the
  stable channel stays pinned to tagged commits.
- Feature branches live only for the lifetime of their PR.

Do **not** maintain a separate `dev` or `develop` branch.

## Versioning rules

- The `VERSION` file always names the version *being worked toward*, never
  the version most recently released. This is the opposite of the common
  pattern but it makes a useful invariant true: at any point in main's
  history, `VERSION` matches what nightly + local installs report and what
  the next stable release will be tagged.
- `VERSION` is bumped in the **first commit after a stable release**
  (e.g. release `v1.5.7` → next commit on main bumps `VERSION` to
  `v1.5.8`). It is not bumped repeatedly within a cycle.
- Mid-cycle tier rollovers are allowed if a significant change warrants
  jumping the next slot (e.g. major refactor mid-`v1.5.x` → bump straight
  to `v1.6.0`). Don't do this lightly. Once it's bumped, stay there until
  the next release.
- The GitHub Releases page is the changelog. There is no separate
  `CHANGELOG.md` file — that file was deleted as a maintenance/merge-
  conflict liability with low cost-vs-value.

## Cutting a stable release

1. Verify `VERSION` reads the version you want to release. It should
   already match — nightlies + local installs have been carrying it
   throughout the development cycle.
2. Tag main HEAD: `git tag -a v1.5.7 main -m "v1.5.7" && git push origin v1.5.7`
3. Create the GitHub Release from the tag. **Do not mark as prerelease.**
   GitHub's `/releases/latest` filters to non-prereleases, so stable-
   channel clients only see real releases.
4. Write the release body inline. Reference merged PRs/issues by number;
   GitHub's "Generate release notes" button does most of the work.
5. **Immediately after release:** in the next commit on main, bump
   `VERSION` to the next target (e.g. `v1.5.7` → `v1.5.8`). Stay on
   that target through the cycle.
6. Within the hour, users on the stable channel with auto-update enabled
   see the update-available notice. Users with `auto_apply: true` get it
   automatically; otherwise they run `clauck update --apply`.

## Nightly channel

Automated by `.github/workflows/nightly.yml`:

- Runs daily at 07:00 UTC plus on manual dispatch.
- Reads `VERSION` from main, generates a tag of the form
  `v{VERSION}-{unix_ts}` (e.g. `v1.5.7-1681580000`), tags main HEAD with
  it (immutable, never moved), and publishes a pre-release at that tag.
- SemVer-correct: `v1.5.7-1681580000 < v1.5.7`, so each nightly sorts
  below the stable it's targeting, and chronologically among other
  nightlies by timestamp.
- No-op refreshes (latest nightly already at main HEAD) are skipped —
  no empty releases are published.

`update-check.sh` for the nightly channel queries `/releases?per_page=20`
and picks the first `prerelease: true` entry. Tag-name inequality detects
an update.

### Opting into nightly

```sh
clauck config set auto_update.channel nightly
clauck update --apply
```

Or on a fresh machine:

```sh
curl -sSL https://raw.githubusercontent.com/CoreyRDean/clauck/main/install.sh \
  | bash -s -- --channel=nightly
```

### Moving back to stable

```sh
clauck config set auto_update.channel stable
clauck update --apply
```

The apply step will install the latest stable release over the nightly.

## Local installs (developers)

If you run `bash install.sh` from a git checkout of the repo, the
installer:

- Detects `BASH_SOURCE[0]` points at a working tree (not a piped curl).
- Stamps `~/.claude/scheduled-jobs/.build-source` with
  `channel: local`, `source: local`, and the current `HEAD` SHA (plus a
  `-dirty` suffix if the tree has uncommitted changes).
- Sets `auto_update.channel = local` in `.clauck.config.json`.

`clauck version` then prints the version with the build provenance:

```
clauck v1.5.7  [local]
  source: local checkout @ ea05d1ebcd-dirty
  note:   update checks disabled for local builds
  installed: 2026-04-15T20:15:00Z
  repo:      CoreyRDean/clauck
```

To switch a local install back to a managed channel:

```sh
clauck config set auto_update.channel stable   # or nightly
clauck update --apply                          # pulls the upstream ref
```

## Forks

Forks work identically — the installer reads `CLAUCK_REPO` and
`CLAUCK_BRANCH` env vars, and `update-check.sh` reads `repo` from
`.clauck.config.json`. To run your own nightly channel on a fork, copy
`.github/workflows/nightly.yml` to the fork unchanged; it uses
`${{ github.repository }}` so it points at the fork's own releases page.
