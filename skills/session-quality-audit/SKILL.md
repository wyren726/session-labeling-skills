---
name: session-quality-audit
description: Audit session-labeling artifacts for schema, evidence, provenance, path safety, forbidden dependencies, conflicts, and export integrity. Use before release, regression conclusions, or high-quality session export.
---

# Session Quality Audit

Use `session-labeling audit --root /absolute/path --kind auto|repository|run`. Repository audit fails on forbidden-root literals, runtime `trace_analysis` imports, or unreadable files. Run audit verifies manifest schema and artifact inventory hashes/sizes; session/source/Episode/assessment joins; exact evidence quotes and event refs; analysis-to-label execution; selector recomputation; selected export joins and native-byte SHA-256; and stale or missing artifacts.

Distinguish semantic pending review from invalid structure or lineage. Do not declare a run reproducible from file presence alone.
