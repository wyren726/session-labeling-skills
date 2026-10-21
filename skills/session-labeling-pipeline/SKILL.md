---
name: session-labeling-pipeline
description: Orchestrate the end-to-end native-session labeling workflow, including ingestion, analysis handoff, labeling, selection, audit, manifests, resume, export, and layered regression. Use for batch or single-session processing.
---

# Session Labeling Pipeline

Run `session-labeling run` for one native session or `session-labeling batch` for a JSONL listing. Supply an absolute new-root path plus `--provider-config`, `--provider`, and a guarded cache directory for automatic understanding, evidence analysis, labeling, S1–S4 selection, resume, manifests, and byte-preserving selected-session export.

The run writes an understanding checkpoint and one checkpoint per assessment. Resume is conservative: source/config/code signature, schema, ID joins, and inventory hash/size must validate. Finish with `session-labeling audit --kind run`. Without a provider, the safe output remains `pending_review`; never present a no-model run or frozen compatibility regression as a fresh Stage 01–06 semantic reproduction.
