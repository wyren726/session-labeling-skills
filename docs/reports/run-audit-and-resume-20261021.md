# Run Audit and Resume — 2026-10-21

The pipeline persists `semantic_checkpoint.json` after understanding and `assessment_checkpoint.json` after each completed assessment. A completed assessment is reused only after schema validation and session/source/Episode/assessment ID joins. A completed run is reused only when manifest signature and every artifact inventory hash and size still match.

`audit_run()` validates the manifest, normalized session, assessment artifacts, evidence event refs and exact quotes, source snapshot refs, analysis/label execution agreement, deterministic selector recomputation, selected-assessment/native-export joins, export SHA-256, and missing or stale files. The injected-failure test interrupts after one of two assessments and proves that restart reuses understanding and the first assessment while performing only the unfinished calls.
