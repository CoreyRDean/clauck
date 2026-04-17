## What changed and why

<!-- Brief description of the change. Link to an issue if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Marketplace job (new or updated)
- [ ] Documentation
- [ ] Refactoring (no behavior change)
- [ ] INTENT.md amendment (contract change)

## Intent contract alignment

<!--
Optional but recommended for architectural changes. Cite which part of
INTENT.md this change serves:

- Primitive served: accept / compile / execute / observe / persist / orchestrate
- Non-negotiable preserved (or explicitly amended): §3 #N
- Architectural property extended: composability / self-observation / intent-as-artifact
- Decision filter pass: questions 1, 2, 3

Skip this section for simple bug fixes, marketplace jobs, docs, and typo fixes.
-->

## Checklist

- [ ] `bash -n install.sh && bash -n uninstall.sh` passes
- [ ] `python3 -c "import ast; ast.parse(open('lib/scheduler.py').read())"` passes
- [ ] Tested `install.sh` on a clean-ish environment (or `--dry-run`)
- [ ] No secrets, personal paths, or API keys committed
