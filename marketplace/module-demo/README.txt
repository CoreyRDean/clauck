module-demo — reference module-format Clauck Cycle
==================================================

This directory demonstrates the module format for marketplace Cycles. Use it as
a copy-paste starting point when building Cycles that need more than one file.

Shape
-----

    module-demo/
      JOB.md         # required — the anchor / entry point
      README.txt     # optional — docs, ignored by the scheduler
      <stage>.md     # optional — additional stages (see below)
      <assets>       # optional — prompts, fixtures, snippets (non-.md)

The marketplace index.json points at the directory (with a trailing slash),
and `clauck install module-demo` copies the whole directory to
~/.clauck/module-demo/.

Stages
------

Any `*.md` file next to JOB.md (other than dotfiles) is registered by the
scheduler as a stage. Stages are not fired directly on their own cron — they
are only reachable through producers/consumers declared on JOB.md. This lets a
single installed module encapsulate a multi-step pipeline.

This demo intentionally has no stages to keep the install path easy to verify.

Removal
-------

    clauck remove module-demo

removes the entire directory and its state (same command used for flat jobs).
