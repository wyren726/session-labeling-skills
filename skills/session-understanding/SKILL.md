---
name: session-understanding
description: Normalize native session JSONL and recover canonical turns, Episodes, user goals, requirements, and requirement evolution. Use when a raw session must become the canonical upstream contract; do not make final quality-selection decisions.
---

# Session Understanding

Use `session-labeling normalize` for deterministic ingestion, then the model-assisted understanding phase in `session-labeling run` when Episode recovery is required. Preserve source hashes, physical lines, stable event/turn IDs, parent chains, tool-call/result links, unknown records, and parsing limitations.

Episode boundaries must reference real turn IDs. Discovery uses overlapping windows; ambiguous clipped candidates receive a targeted cross-window reconciliation call. Preserve candidate-window provenance. If reconciliation cannot establish one boundary, retain the candidates with an explicit unresolved limitation instead of silently merging or splitting them. Understanding checkpoints are reusable only after schema, source snapshot, pipeline version, and ID checks pass.
