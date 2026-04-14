# Job that learns across runs

**Who:** Power user who wants a job to get better over time

**Intent:** "My email triage job should learn my patterns. If I keep archiving suggestions it made about GitHub notification emails, it should stop suggesting 'reply' for those and start defaulting to 'archive.' I don't want to edit the prompt every time — I want the job to observe my reactions and adjust."

**Context:** With session persistence, each run has context from all prior runs. The job can be prompted to maintain a running set of learned rules: "When I see notifications from GitHub, suggest archive. When I see emails from my manager, always suggest reply." These rules accumulate in the session context and inform future triage.

**Success:** After a few weeks, the triage job's suggestions match the user's actual behavior >90% of the time. The user's only interaction is skimming the report and occasionally correcting a suggestion (by editing the feed file or telling Claude in an interactive session). The job feels like it understands the user's inbox preferences.
