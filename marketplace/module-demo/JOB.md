---
name: module-demo
version: "1.0.0"
description: Reference module-format marketplace job. Demonstrates the <name>/JOB.md directory shape for multi-file jobs.
complexity: 0.05      # minimum example — trivial work
max_turns: 1          # override: pedagogical minimum, tighter than derived
max_budget_usd: 0.02  # override: pedagogical minimum, below min_budget floor
cwd: ~
setting_sources: ""
strict_mcp_config: true
tags:
  - example
  - module
  - reference
semantic_hooks:
  - Show me what a module-format clauck job looks like
  - I want a reference module I can copy when building multi-file jobs
---

<!--
CUSTOMIZE BEFORE INSTALLING (optional):
- Add your own stage files to this directory as <stage-name>.md with frontmatter.
  They become reachable via producers/consumers declared on this JOB.md anchor.
- Drop supporting assets (prompts, fixtures, docs) next to JOB.md. Non-.md files
  and dotfiles are ignored by the scheduler.
-->

This is the entry point for a module-format job. Print a single line confirming
the module ran, then exit:

```
echo "module-demo: ok"
```

That's it — this job exists to validate that module-format installs work end to
end. See `README.txt` in this directory for the full module-format reference.
