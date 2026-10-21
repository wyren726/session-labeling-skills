# RFC 0001: Canonical Session Labeling and Selection Pipeline

- **Status:** Proposed design baseline
- **Date:** 2026-10-20
- **Scope:** End-to-end reconstruction and refactoring of effective Stage 01–06 capabilities
- **Historical compatibility target:** Four frozen first-selection batches under `stage06-selection-v3`

## 1. Summary

Build an independent repository that accepts native `session.jsonl` files and produces evidence-linked labels, deterministic selection decisions, audit reports, and exported high-quality native sessions. The implementation preserves effective Stage 01–06 semantics but replaces the historical stage layout with six stable capabilities:

1. `session-understanding`
2. `session-evidence-analysis`
3. `session-quality-labeling`
4. `session-quality-selection`
5. `session-quality-audit`
6. `session-labeling-pipeline`

The repository has three authoritative sources: one taxonomy registry, one family of versioned data contracts, and one selection policy. Skills, prompts, Python code, tests, and documentation consume those sources rather than redefining them.

## 2. Motivation

Stage 06 is not independently reproducible from a native session. It relies on Episode boundaries and user-goal recovery, Agent/tool evidence, requirement outcome analysis, source identity, and historical case assembly produced upstream. Mechanical extraction of Stage 06 would preserve imports but lose semantic dependencies and provenance.

The historical implementation also contains multiple generations of Stage 02/03 workflows, presentation-only fields, duplicated labels, and a disabled quality proposal. A canonical design must preserve useful judgments while separating concepts that look similar but answer different questions.

## 3. Historical findings that constrain the design

1. Stage 01 normalizes native records into trace/turn/event structures and preserves source references.
2. Stage 02 performs user-only Episode and requirement understanding; it explicitly must not infer Agent failure.
3. Stage 03 reads assistant/tool/error evidence to verify goals, requirements, outcomes, and attribution.
4. Stage 04 deterministically maps `agent_related` to historical `pain_judgment`; this is not trace quality or selection.
5. Stage 05 is publishing and does not add semantic input required by Stage 06.
6. Stage 06 reloads authoritative Episode events and reuses Stage 02 indexing/retrieval capabilities.
7. Stage 06 per-field claim support and requirement-taxonomy mapping status have distinct semantics.
8. `review_view` is derived presentation data.
9. `quality_policy.json` is disabled and did not drive frozen results.
10. Frozen selection uses `stage06-selection-v3`: prechecks plus S1–S4, with a deterministic final decision.
11. Frozen decisions total 1,278: 780 `priority_candidate`, 498 `review`, and zero `not_selected`; all final decision records identify the final reviewer type as `program`.
12. Historical selection records leave source session identity null and recover it through separate source/export artifacts; the canonical pipeline must repair this lineage gap.

Detailed evidence is in `docs/audit/` and `docs/design/legacy-lineage.json`.

## 4. Goals

- Run from native session files without importing the legacy project at runtime.
- Preserve every upstream capability that materially influences final labels or selection.
- Merge duplicate parsing, evidence retrieval, and schema validation.
- Keep task outcome, Agent attribution, historical pain, label support, analyzability, and selection separate.
- Make every final judgment traceable to exact source evidence and a versioned policy/config/code snapshot.
- Support deterministic resume, cache validation, manifests, and partial failure recovery.
- Export the original selected session files with explicit source lineage.
- Reproduce and explain historical results on a fixed ten-session sample.
- Reject forbidden storage roots statically and at runtime without dereferencing them.

## 5. Non-goals

- Preserve the names or command boundaries of all six historical stages.
- Treat Stage 04 pain cases as the universal input scope for future datasets.
- Enable the disabled `trace_quality` aggregation without a separate reviewed RFC.
- Add ranking scores, capacity limits, or coverage quotas to the historical compatibility policy.
- Claim that selected sessions are already publishable Gold tasks or that workspace reproduction is guaranteed.
- Copy presentation reports as canonical data.

## 6. Canonical architecture

```text
native session.jsonl
  -> ingestion and normalization
  -> Episode/task understanding
  -> evidence and execution analysis
  -> semantic labeling with claims
  -> selection prechecks and S1-S4 audits
  -> deterministic decision
  -> contract/path/provenance audit
  -> selected native-session export and regression report
```

### 6.1 `session-understanding`

Responsibilities:

- validate input paths before opening them;
- stream native JSONL and preserve raw record positions and hashes;
- normalize messages, tools, attachments, errors, and metadata;
- build trace, turn, event, and tool call/result relationships;
- identify real-user events;
- recover Episode boundaries and initial query;
- extract goal hypotheses, user-stated requirements, origin/evolution, and candidate signals;
- emit `normalized_session` and `episode` contracts.

This skill must not infer Agent failure or final quality.

### 6.2 `session-evidence-analysis`

Responsibilities:

- load the authoritative Episode and bounded lookahead;
- read assistant, tool, error, and follow-up evidence;
- verify the user-only goal hypothesis;
- evaluate each requirement independently;
- distinguish Agent claims from verified outcomes;
- attribute failures to Agent, permission, external, user-input, or unknown causes;
- build exact citations and evidence coverage metadata;
- retain omitted-body state so absent retrieval is never interpreted as verification.

### 6.3 `session-quality-labeling`

Responsibilities:

- label the Episode and its concrete requirements against the one taxonomy registry;
- produce task attributes and requirement mappings;
- produce Episode and requirement assessments, feedback/failure annotations, limitations, and atomic field claims;
- attach exact evidence and conflicts to every claim;
- validate taxonomy hierarchy and field paths;
- never persist a second independently editable presentation taxonomy.

### 6.4 `session-quality-selection`

Responsibilities:

- load only valid canonical labels and evidence;
- apply the configured scope policy;
- evaluate S1 and S2 deterministically from usable supported claims;
- run bounded S3/S4 audits only when required;
- keep selection audits separate from semantic labels;
- combine prechecks and rule checks deterministically;
- emit `selected`, `not_selected`, `pending_review`, or `invalid`.

Historical compatibility mapping:

| Legacy | Canonical |
|---|---|
| `priority_candidate` | `selected` |
| semantic `review` | `pending_review` |
| malformed/broken-lineage `review` | `invalid` |
| `not_selected` | `not_selected` |

### 6.5 `session-quality-audit`

Responsibilities:

- JSON Schema validation;
- taxonomy and cross-reference consistency;
- exact quote validation;
- missing evidence and omitted-body checks;
- conflicting claim/review/audit detection;
- source and path compliance;
- provenance and content-hash completeness;
- derived-view regeneration checks;
- layered comparison with historical artifacts.

### 6.6 `session-labeling-pipeline`

Responsibilities:

- batch discovery and deterministic work-unit IDs;
- orchestration of the five capability skills;
- bounded retries and error classification;
- resume and content-addressed caching;
- run manifest, checkpoint, and artifact index;
- selected native-session export;
- regression report generation.

## 7. Authoritative configuration and contracts

### 7.1 One taxonomy registry

`config/taxonomy.yaml` will define:

- stable label ID and canonical field path;
- definition and boundary;
- entity/assessment scope;
- enum values;
- evidence requirements;
- confidence/review requirements;
- primary versus auxiliary selection eligibility;
- legacy field mappings;
- whether the label participates in selection.

Prompts may render subsets of this file but must not redefine it.

### 7.2 One selection policy

`config/selection_policy.yaml` will define:

- policy ID/version and compatibility mode;
- allowed selection modes;
- scope filters and empty-filter semantics;
- primary/auxiliary requirement sets;
- prechecks;
- S1–S4 definitions;
- which rules are deterministic versus audited;
- final decision table;
- disabled ranking/capacity/coverage features;
- exported decision compatibility names.

### 7.3 Versioned contracts

Initial schemas:

```text
schemas/normalized_session.schema.json
schemas/episode.schema.json
schemas/evidence.schema.json
schemas/analysis.schema.json
schemas/final_labels.schema.json
schemas/label_review.schema.json
schemas/selection_audit.schema.json
schemas/selection_decision.schema.json
schemas/run_manifest.schema.json
schemas/audit_report.schema.json
```

Every artifact includes:

- schema ID/version;
- stable object ID and parent IDs;
- source snapshot/content hashes;
- producer skill/version and code revision;
- config/taxonomy/policy hashes as applicable;
- created time and deterministic run/work-unit ID;
- model/provider/prompt/parameters for model-generated fields;
- explicit evidence coverage and limitations.

## 8. Canonical semantic separations

The following fields must never be collapsed:

- Agent-claimed completion versus evidence-verified task outcome;
- verified task outcome versus requirement validity;
- Agent-related failure attribution versus task outcome;
- historical pain attribution versus trace analyzability;
- requirement taxonomy mapping status versus per-field claim evidence support;
- per-field support versus selection-rule pass;
- selection-rule pass versus final collection decision;
- semantic pending review versus invalid processing/lineage state.

The full mapping is in `docs/design/legacy-to-canonical-label-map.yaml`.

## 9. Model and deterministic boundaries

### Deterministic operations

- native parsing and normalization;
- source IDs, offsets, and hashes;
- schema and cross-reference validation;
- exact quote and event-role checks;
- taxonomy hierarchy validation;
- derived view generation;
- effective review resolution when inputs agree;
- S1 and Episode-mode S2 under the compatibility policy;
- final selection decision table;
- manifests, cache keys, resume, export, and regression metrics.

### Model-assisted operations

- Episode boundary and user-goal/requirement understanding;
- Agent/evidence verification where deterministic signals are insufficient;
- semantic task labels and field claims;
- S3/S4 audits when not already supplied.

Model output is always untrusted input: it is schema-validated, reference-validated, evidence-validated, and either accepted, repaired through a bounded protocol, or classified as invalid/pending.

## 10. Evidence contract

Each evidence reference binds:

- `evidence_id`;
- source snapshot ID and event ID;
- role and event type;
- trace, Episode, and turn IDs;
- source locator/record position;
- exact continuous quote;
- whether full body was provided;
- retrieval method and round;
- content digest.

Rules:

1. A quote must be a continuous substring of a provided body.
2. A tool call does not prove the corresponding action succeeded.
3. Unread tool content is omitted evidence, not negative evidence.
4. Later clarification can update scope but cannot be backdated into the initial request.
5. Different Episodes/cases cannot be spliced to satisfy one claim.
6. Conflicting evidence remains explicit until a version-bound review resolves it.

## 11. Selection compatibility policy

The first implementation supports an exact historical compatibility profile:

- S1: at least one evidence-supported primary parent/child requirement mapping;
- S2: evidence-supported medium/high Episode difficulty; reviewed low fails; unresolved values remain pending;
- S3: coherent reconstruction of one task's goal, object, requirements, constraints, evolution, and scope;
- S4: explicit completion conditions from user requirements or linked tests, outputs, metrics, or checkable standards;
- empty scope filters mean no restriction;
- no score, top-N capacity, or coverage quota;
- final decision is deterministic.

The disabled legacy quality proposal is not silently enabled. A future analyzability policy needs a separate RFC, calibration sample, and migration plan.

## 12. Run layout, resume, and cache

Proposed run layout:

```text
runs/<run_id>/
  manifest.json
  inputs.jsonl
  checkpoints/
  artifacts/
    normalized_sessions.jsonl
    episodes.jsonl
    evidence.jsonl
    analyses.jsonl
    labels.jsonl
    label_reviews.jsonl
    selection_audits.jsonl
    selection_decisions.jsonl
  errors.jsonl
  audit/
  exports/
```

A work unit key is derived from source content hash, object ID, producer version, relevant config hashes, prompt version, and model parameters. Resume may reuse an artifact only when the full cache key and schema version match and the artifact passes validation. A changed source file, policy, taxonomy, prompt, or model parameter invalidates the relevant downstream cache.

Writes use temporary files plus atomic replacement. Append-only JSONL checkpoints include record hashes. The manifest records expected, completed, invalid, pending, failed, and exported counts.

## 13. Error model and bounded retries

Canonical error classes:

- `input_invalid`: malformed JSONL or unsupported native record;
- `path_forbidden`: path policy violation before filesystem access;
- `normalization_failed`;
- `boundary_invalid`;
- `evidence_incomplete`;
- `model_transport_failed`;
- `model_output_invalid`;
- `label_conflict`;
- `selection_pending`;
- `export_lineage_missing`;
- `internal_error`.

Retries are bounded and recorded. Transport failures may retry with configured backoff. Schema/reference errors get a small bounded repair budget. Deterministic invalid input does not retry indefinitely. A failed work unit does not corrupt completed checkpoints.

`invalid` is a pipeline/contract decision, not a statement that the underlying session is low quality.

## 14. Path safety

The repository will enforce an allowlist rooted under the approved new storage root and reject forbidden roots before any `resolve`, `stat`, `open`, glob, symlink traversal, subprocess, or model prompt construction.

Required defenses:

1. static repository scan for forbidden path literals and runtime imports of the legacy project;
2. lexical path check before filesystem calls;
3. symlink-aware containment check for allowed inputs and outputs;
4. manifest/config environment expansion through named roots, never hidden fallback paths;
5. sanitized provenance using relative logical locators and content hashes;
6. tests covering direct, normalized, relative, symlink, environment-variable, manifest, and subprocess forms.

Historical manifests may contain legacy path strings inside source data. Migration code may inspect and normalize such strings without dereferencing them. Canonical artifacts must not emit those literals.

## 15. Skill packaging

Each skill directory contains a concise `SKILL.md`, `agents/openai.yaml`, and only the references/scripts needed for that capability. Skills point to canonical contracts and CLI commands; they do not duplicate taxonomy or policy text.

The orchestration skill decides which lower-level skills to call and requires explicit authorization for expensive model runs or external mutations. Ordinary local validation and deterministic dry runs remain safe and discoverable.

Each completed skill is validated with the bundled `quick_validate.py` and with behavioral tests using isolated fixtures.

## 16. Ten-session layered regression

### 16.1 Sample freeze

Choose ten sessions deterministically from the frozen 672-session source list after mapping source locators to the approved new root. Record:

- sampling algorithm and seed;
- source content hashes;
- represented batches/models/harnesses;
- historical case and selection IDs;
- expected artifact versions.

No sample path may fall outside the approved root.

### 16.2 Comparison layers

For each session compare:

1. normalized session/trace/turn/event identity;
2. Episode count and boundaries;
3. initial query, goal, and concrete requirements;
4. Agent behavior, per-requirement result, outcome, and attribution;
5. evidence coverage and exact citations;
6. legacy-to-canonical label mapping;
7. S1–S4 checks and prechecks;
8. final decision and source-session export.

### 16.3 Difference classes

- exact match;
- representational rename with equal semantics;
- intended correction of a documented legacy defect;
- unresolved model variance;
- insufficient historical evidence;
- new implementation defect;
- invalid historical artifact/version mismatch.

Every confirmed new implementation defect is fixed and rerun. Differences that are intentional or irreducible remain documented with evidence; a matching final boolean alone is insufficient.

## 17. Testing strategy

- unit tests for parsers, IDs, path guards, citations, mappings, decision tables, and cache keys;
- contract tests for every schema and cross-reference invariant;
- prompt fixture tests that validate outputs rather than exact prose;
- integration tests from small native sessions through export;
- compatibility fixtures derived from de-identified historical shapes;
- static scan for forbidden paths/imports and duplicated taxonomy/policy definitions;
- regression tests for historical version differences, including the early batch without separate user-turn artifacts;
- failure injection for truncation, interrupted writes, stale cache, conflicting reviews, missing source lineage, and model/API errors.

Legacy tests are evidence, not automatically the new test architecture. Their assertions will be cataloged and ported when they defend a canonical invariant.

## 18. Implementation sequence

1. Review and freeze this RFC, lineage, and mapping baseline.
2. Create an initial Git snapshot before removing or relocating temporary copied files.
3. Add repository metadata, packaging, and path policy.
4. Implement canonical schemas, taxonomy, and compatibility selection policy.
5. Implement normalization and source indexing without runtime legacy imports.
6. Implement understanding and evidence analysis adapters.
7. Implement labeling, reviews, selection audits, and deterministic decision logic.
8. Package and validate the six Skills.
9. Add unit/contract/integration tests and static guards.
10. Freeze the ten-session sample, run layered regression, repair confirmed defects, and publish reports.

## 19. Acceptance criteria

The design is complete when:

- each final selection field has a documented upstream lineage;
- every legacy field is retained, renamed, derived, deprecated, historical-only, or explicitly deferred;
- historical behavior, disabled proposals, and new design are visibly separated;
- no canonical concept has multiple competing sources of truth.

The implementation is complete when:

- the repository installs independently and imports no legacy runtime package;
- all six Skills validate and invoke canonical CLI operations;
- native sessions can run end to end with resume and manifests;
- every output passes schema, evidence, path, and provenance audits;
- selected native sessions export through explicit source lineage;
- static and runtime forbidden-path tests pass;
- the ten-session layered regression is complete and all confirmed implementation defects are fixed;
- README, maintenance guide, compliance report, and regression report are committed.

## 20. Deferred decisions

- Final analyzability/trace-quality taxonomy and aggregation policy;
- calibration thresholds for model confidence and human review;
- optional ranking and coverage optimization after compatibility is established;
- whether future generic input scope should bypass historical pain-case construction entirely (the architecture permits this; compatibility mode initially preserves historical joins).
