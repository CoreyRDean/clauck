# Chained analysis pipeline

**Who:** Data-aware developer or analyst

**Intent:** "Every Monday morning: (1) pull last week's Sentry error counts by category, (2) cross-reference with the PRs that were merged last week, (3) generate a correlation report showing which merges likely introduced which error spikes, (4) post the report to the team's Slack channel."

**Context:** Each step depends on the prior step's output. Step 1 produces error data. Step 2 enriches it with PR context. Step 3 synthesizes. Step 4 delivers. Running these as independent jobs means manually piping data between them or writing one monolithic prompt that hits budget limits. The user wants a pipeline where each stage is a focused, cheap job that passes its output to the next.

**Success:** Four jobs configured as a chain. Each runs after the previous completes successfully. Each job's prompt receives the prior job's result as context. Total cost is lower than one large job because each stage uses only the MCP surface it needs. If step 2 fails, step 3 and 4 don't run (no wasted spend). The user debugs at the stage level, not the pipeline level.
