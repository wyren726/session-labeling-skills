---
name: session-quality-labeling
description: Generate canonical quality labels from versioned session analysis using the shared taxonomy. Use for task attributes, requirement mappings, outcomes, claims, annotations, and review state; do not duplicate taxonomy definitions in prompts.
---

# Session Quality Labeling

Read the complete registry from `config/taxonomy.yaml` and validate against `schemas/final_labels.schema.json`. The model evaluates registry definitions, inputs, outputs, and boundaries; it must not classify by keyword alone or choose primary/auxiliary role. Role is derived from the registry. Auxiliary-only mappings cannot satisfy S1.

Every selection-relevant claim or mapping requires valid evidence refs. Preserve unresolved results rather than forcing labels. Treat `docs/design/legacy-to-canonical-label-map.yaml` as the runtime coverage ledger: an explicitly deferred historical field must not be presented as implemented or silently synthesized from a different canonical concept.
