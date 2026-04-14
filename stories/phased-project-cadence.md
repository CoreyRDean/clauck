# Multi-phase project cadence

**Who:** Project lead managing a multi-week initiative

**Intent:** "I have a 6-week project. Week 1-2 I need daily status checks on CI and blockers. Week 3-4 switch to monitoring integration test results every 12 hours. Week 5 is code freeze — I want hourly checks. Week 6 is launch — I want real-time monitoring that fires on every deploy. After launch, drop to daily for a month, then weekly forever."

**Context:** Project cadences change as the work evolves. Manually adjusting cron schedules or creating new monitoring jobs at each phase transition is busywork. The user wants to describe the full cadence arc upfront and have the system handle phase transitions automatically.

**Success:** The user describes the full arc in natural language. Multiple jobs are created with staggered `valid_after` / `expires_after` windows so each phase activates and deactivates on schedule. No manual intervention at phase boundaries. The system handles the complexity; the user just reviews the output at each phase's cadence.
