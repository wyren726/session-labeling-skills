# Maintenance

## Sources of truth

- `config/taxonomy.yaml`: canonical label definitions and capability registry.
- `config/selection_policy.yaml`: S1–S4 and final decision table.
- `schemas/`: artifact contracts.
- `prompts/`: model instructions that consume, but do not redefine, taxonomy and policy.

Do not duplicate label definitions or selection rules in prompts, Skills, temporary scripts, or Python branches. `setup.py` copies these canonical files only while building install artifacts.

## Change process

1. Update the source-of-truth config/schema and bump its version.
2. Add migration notes and compatibility tests.
3. Run all unit tests.
4. Run the repository path/runtime-dependency audit.
5. Validate all six Skills with the official `skill-creator/scripts/quick_validate.py`.
6. Run the frozen ten-session layered regression before changing ingestion, migration, or selection behavior.
7. For semantic/prompt/model changes, run one small native session first, inspect schema/quote/cost behavior, then run the frozen ten sessions with a configured provider.
8. Update `docs/reports/` and state clearly whether a result is deterministic compatibility or fresh model-assisted relabeling.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m session_labeling.cli audit --root "$PWD"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m session_labeling.cli regression \
  --trace-root /mnt/shared-storage-user/gpfs1-agent-mlcoding/users/renwanying/trace_analysis \
  --output-dir "$PWD/runs/regression-10"
```

## Packaging check

Build from a clean source snapshot, install outside the checkout, and verify that taxonomy, schemas, and prompts load from `session_labeling/resources`. Use a real path rather than a symlinked path because resource reads intentionally reject symlink components.

## Safety

Historical locators may contain the forbidden old prefix. They may only be transformed lexically by `PathPolicy.remap_locator`; no filesystem API may receive the old locator. Any symlink component on the mapped data/resource path is rejected. Manifests must store the mapped approved locator, never the historical forbidden string.

Before deleting runs, replacing repositories, or resetting work, create a git commit or verified backup first.
