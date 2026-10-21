# Design baseline

This directory separates machine-readable legacy lineage from the proposed canonical design.

- `legacy-lineage.json`: capability and field dependency graph, with evidence class and historical status.
- `legacy-to-canonical-label-map.yaml`: explicit disposition of legacy fields and non-mergeable concepts.
- `../rfcs/0001-canonical-session-labeling-pipeline.md`: proposed end-to-end architecture and acceptance criteria.

The design deliberately distinguishes:

1. observed legacy code behavior;
2. frozen historical artifacts;
3. documentary statements and disabled drafts;
4. proposed canonical behavior.

No file in this directory is itself an executable policy. Executable taxonomy, schemas, and policy will be created only after review of RFC 0001.
