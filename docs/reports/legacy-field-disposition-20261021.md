# Legacy Field Runtime Disposition — 2026-10-21

The 51 Stage 01–06 mappings now carry one of four runtime statuses in `docs/design/legacy-to-canonical-label-map.yaml`: `implemented`, `derived`, `historical_only`, or `explicitly_deferred`. Implemented/derived entries must name their artifact, field path, and executable verification; deferred entries must explain the semantic gap; historical-only entries cannot be direct selector truth.

Current counts are 25 implemented, 0 derived, 3 historical-only, and 23 explicitly deferred. This conservative baseline intentionally refuses to call a field implemented merely because it could theoretically be reconstructed. `tests/test_legacy_disposition.py` enforces completeness and prevents silent selection-relevant deferral.
