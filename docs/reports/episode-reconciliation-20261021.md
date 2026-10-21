# Episode Reconciliation — 2026-10-21

Understanding uses overlapping turn windows. Exact boundary plus normalized-goal duplicates are merged deterministically while retaining candidate-window provenance. Candidates clipped at neighboring window boundaries with similar goals form ambiguity clusters and receive a targeted reconciliation request over surrounding real turns.

The resulting Episode records `single_window`, `duplicate_merged`, `model_reconciled`, or `unresolved`. A failed follow-up never causes a silent merge: candidates are retained with `unresolved cross-window Episode boundary`. A dedicated test forces three one-turn windows and verifies one reconciled Episode covering all source turns.
