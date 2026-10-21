# Ten-Session Regression — 2026-10-20

## Method

The sample is deterministic: sort the frozen 672-session candidate listing by `session_id` and select the first ten sessions. Native session locators are lexically mapped to the approved new storage root before any I/O.

For each session, the new ingester processes the native JSONL. For each associated historical case, the explicit compatibility adapter maps the frozen Stage 06 labels to canonical labels, validates the canonical artifact, and reruns the new deterministic selector. Rule statuses and decisions are compared with the frozen baseline.

## Result

| Metric | Result |
|---|---:|
| Sessions | 10 |
| Historical cases | 13 |
| Session ID matches | 10/10 |
| Sessions with parse errors | 0 |
| Cases with baseline | 13/13 |
| S1–S4 rule matches | 13/13 |
| Final decision matches | 13/13 |
| Overall | PASS |

Native ingestion totals in this run:

- 19,679 JSONL records
- 38,140 canonical events
- 950 turns
- 0 parse errors

All 13 frozen baseline cases were program-reviewed `priority_candidate` cases. The canonical compatibility mapping produced `selected` for all 13, matching the expected mapped decision.

Machine-readable report:

```text
runs/regression-10/ten-session-regression.json
```

## Interpretation boundary

This proves that native ingestion, frozen-label migration, and the new selector preserve the tested historical decisions. It does **not** prove fresh end-to-end semantic reproduction. Episode boundaries, recovered goals/requirements, exact new evidence alignment, and newly generated labels require the model-assisted path. No configured provider API key was available on 2026-10-20, so that second-layer test remains pending rather than being simulated.
