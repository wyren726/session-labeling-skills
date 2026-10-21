# Legacy pipeline audit artifacts

These files are generated from the existing `trace_analysis` project under the approved new storage root.
They separate two evidence classes:

- `legacy-stage-inventory.json`: static declarations discovered from Python AST inspection.
- `legacy-historical-artifacts.json`: filesystem metadata and parsed manifests from the four historical batches used by the selection report.

Paths are relative to `${TRACE_ANALYSIS_SOURCE}`. Absolute source paths are deliberately normalized so the new repository does not gain a runtime dependency on the source checkout.
Static declarations do not prove runtime behavior; historical manifests are used as a second evidence source and will be reconciled with documentation and sampled records in the lineage RFC.

`legacy-record-shapes.json` also normalizes absolute source paths found in sampled dictionary keys to `${TRACE_ANALYSIS_SOURCE}`; normalization is lexical only and never dereferences a legacy path.
