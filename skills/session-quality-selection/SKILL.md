---
name: session-quality-selection
description: Apply the canonical S1–S4 policy and deterministic decision table to validated labels. Use to produce selected, not_selected, pending_review, or invalid decisions with rule-level evidence and reasons.
---

# Session Quality Selection

Use `config/selection_policy.yaml` as the only rule source and `session-labeling select` as the deterministic evaluator. Recompute S1 from evidence-supported primary mappings and S2 from configured difficulty values; normalize explicit evidence-linked S3/S4 semantic reviews. Never silently enable the deprecated trace-quality proposal, scoring, capacity, or quotas.

Missing or unresolved semantic judgments produce `pending_review`; schema or reference failures produce `invalid`; a failed scope/rule produces `not_selected`. Preserve legacy decision names only as a derived compatibility view.
