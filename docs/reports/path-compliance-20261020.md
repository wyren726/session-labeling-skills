# Path and Runtime-Dependency Compliance — 2026-10-20

## Policy

- Allowed storage root: `/mnt/shared-storage-user/gpfs1-agent-mlcoding/users/renwanying/`.
- Historical forbidden locators may appear only as input strings to lexical remapping logic; they must never be passed to filesystem inspection or persisted into generated manifests.
- Every mapped data path must remain under an allowed root.
- Existing path components are checked with `lstat`; symlinks are rejected.
- Final reads use `O_NOFOLLOW`.
- The new package must not import `trace_analysis` at runtime.

## Final audit

The repository audit completed successfully with:

- forbidden path hits: 0
- forbidden runtime imports: 0
- read errors: 0
- valid: true

A regression test now runs the pipeline through a synthetic historical locator, verifies that only the mapped locator is persisted, and verifies that the historical locator is absent from the manifest.

The generated smoke manifest that previously retained an unmapped locator was normalized in place; generated artifacts are not exempted from the audit.

## Notes

The audit intentionally recognizes the detector's own forbidden-path construction as detection logic rather than a violation. Binary/cache files are skipped by policy. Source, generated JSON/JSONL artifacts under the repository, Skills, docs, schemas, and configuration remain in scope.
