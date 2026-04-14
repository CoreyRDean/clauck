## What changed and why

<!-- Brief description of the change. Link to an issue if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Library job (new or updated)
- [ ] Documentation
- [ ] Refactoring (no behavior change)

## Checklist

- [ ] `bash -n install.sh && bash -n uninstall.sh` passes
- [ ] `python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())"` passes
- [ ] Tested `install.sh` on a clean-ish environment (or `--dry-run`)
- [ ] CHANGELOG.md updated under `[Unreleased]` (if user-facing)
- [ ] No secrets, personal paths, or API keys committed
