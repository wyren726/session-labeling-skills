---
name: session-evidence-analysis
description: Analyze canonical sessions to connect user requirements, agent actions, tool results, outcomes, and exact evidence references. Use after session understanding and before final labeling; do not treat tool calls or agent claims as proof of success.
---

# Session Evidence Analysis

Consume normalized sessions and canonical Episodes through the pipeline. Quotes must be continuous substrings of the cited event body and are revalidated programmatically. Keep agent-claimed completion separate from evidence-verified outcome, and keep requirement outcome separate from taxonomy support. Tool calls prove attempts, not success.

Long Episodes are analyzed in bounded chunks and reduced with model-call provenance. Write one schema-validated assessment checkpoint after quote validation; resume may reuse it only when assessment/session/Episode/source IDs join and all expected artifacts validate.
