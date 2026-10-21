from __future__ import annotations
import datetime
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from .ingest import normalize_session
from .selection import evaluate
from .semantic import (
    PIPELINE_VERSION,
    analyze_episode,
    label_episode,
    understand,
)
from .utils import atomic_write_json, digest_bytes, canonical_json, load_json, stable_id
from .contracts import (
    load_yaml,
    validate_artifact,
    validate_label_references,
    resource_root,
    load_text,
)


def _write(policy, path, value):
    path = policy.validate_for_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, value)


def _write_artifact(policy, path, value, schema_name):
    validate_artifact(value, schema_name)
    _write(policy, path, value)


def _copy_native(policy, src, dst):
    dst = policy.validate_for_write(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{dst.name}.", dir=str(dst.parent))
    try:
        with policy.open_binary(src) as source, os.fdopen(fd, "wb") as target:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, dst)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _signature(normalized, client):
    taxonomy = load_yaml("taxonomy.yaml")
    selection = load_yaml("selection_policy.yaml")
    return digest_bytes(
        canonical_json(
            {
                "source": normalized["source_snapshot"]["sha256"],
                "taxonomy": taxonomy,
                "selection": selection,
                "model": getattr(client, "model", None),
                "provider": getattr(getattr(client, "config", None), "name", None),
                "pipeline": PIPELINE_VERSION,
            }
        )
    )


def _selection(labels, normalized):
    policy = load_yaml("selection_policy.yaml")
    reference_issues = validate_label_references(labels, normalized)
    selection = evaluate(labels, policy)
    if reference_issues:
        labels.setdefault("validation_issues", []).extend(reference_issues)
        selection["issues"] = sorted(set(selection.get("issues", []) + reference_issues))
        selection["prechecks"]["valid_references"] = "invalid"
        selection["decision"] = "invalid"
        selection["legacy_decision"] = "review"
    validate_artifact(selection, "selection_decision.schema.json")
    return selection


def _empty_labels(normalized):
    snapshot_id = normalized["source_snapshot"]["source_snapshot_id"]
    assessment_id = stable_id("assessment", snapshot_id)
    return {
        "schema_version": "final-labels-v1",
        "assessment_id": assessment_id,
        "session_id": normalized["session_id"],
        "episode_id": stable_id("episode", snapshot_id, "unspecified"),
        "source_snapshot_id": snapshot_id,
        "evidence": [],
        "claims": [],
        "capability_mappings": [],
        "task_attributes": {"difficulty": "unknown", "difficulty_evidence_refs": []},
        "semantic_rule_reviews": [],
        "execution": {
            "agent_claimed_status": "unknown",
            "verified_outcome": {"status": "unknown"},
            "requirement_results": [],
        },
        "scope_match": "pass",
        "selection_critical_conflicts": [],
        "limitations": [
            "No semantic analysis was supplied; selection-critical semantic fields remain pending."
        ],
        "validation_issues": [],
        "provenance": {
            "producer_skill": "session-labeling-pipeline",
            "producer_version": PIPELINE_VERSION,
            "method": "no_semantic_analysis",
            "source_snapshot_id": snapshot_id,
        },
    }


def _load_valid(policy, path, schema_name):
    value = load_json(policy.validate_for_read(path))
    validate_artifact(value, schema_name)
    return value


def _safe_relative(path):
    value = PurePosixPath(str(path))
    if value.is_absolute() or ".." in value.parts:
        raise ValueError(f"unsafe artifact relative path: {path}")
    return value


def _file_digest(policy, path):
    hasher = __import__("hashlib").sha256()
    size = 0
    with policy.open_binary(path) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _artifact_inventory(policy, run_dir, paths):
    inventory = []
    for relative in dict.fromkeys(paths):
        safe = _safe_relative(relative)
        path = run_dir / str(safe)
        sha256, size = _file_digest(policy, path)
        inventory.append(
            {
                "path": str(safe),
                "sha256": sha256,
                "size_bytes": size,
                "kind": (
                    "native_session_export"
                    if str(safe) == "export/session.jsonl"
                    else "checkpoint"
                    if str(safe).endswith("checkpoint.json")
                    else "artifact"
                ),
            }
        )
    return inventory


def _inventory_valid(policy, run_dir, manifest):
    try:
        for artifact in manifest.get("artifacts", []):
            relative = _safe_relative(artifact["path"])
            sha256, size = _file_digest(policy, run_dir / str(relative))
            if sha256 != artifact["sha256"] or size != artifact["size_bytes"]:
                return False
        return bool(manifest.get("artifacts"))
    except (OSError, ValueError, KeyError):
        return False


def _resource_bundle_hash():
    root = resource_root()
    payload = {}
    for directory in ("config", "schemas", "prompts"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file():
                relative = str(path.relative_to(root))
                payload[relative] = digest_bytes(load_text(path).encode("utf-8"))
    return digest_bytes(canonical_json(payload))


def _understanding_checkpoint(path_policy, run_dir, normalized, signature, client, resume):
    checkpoint_path = run_dir / "checkpoints" / "semantic_checkpoint.json"
    if resume and checkpoint_path.exists():
        try:
            checkpoint = _load_valid(
                path_policy, checkpoint_path, "semantic_checkpoint.schema.json"
            )
            if checkpoint["signature"] == signature and checkpoint["status"] == "understanding_complete":
                for episode in checkpoint["episodes"]:
                    validate_artifact(episode, "episode.schema.json")
                return checkpoint, True
        except Exception:
            pass
    episodes, metadata = understand(normalized, client)
    checkpoint = {
        "schema_version": "semantic-checkpoint-v1",
        "signature": signature,
        "source_snapshot_id": normalized["source_snapshot"]["source_snapshot_id"],
        "status": "understanding_complete",
        "episodes": episodes,
        "model_metadata": metadata,
    }
    _write_artifact(
        path_policy,
        checkpoint_path,
        checkpoint,
        "semantic_checkpoint.schema.json",
    )
    return checkpoint, False


def _resume_assessment(path_policy, base, signature):
    checkpoint_path = base / "assessment_checkpoint.json"
    if not checkpoint_path.exists():
        return None
    try:
        checkpoint = _load_valid(
            path_policy, checkpoint_path, "assessment_checkpoint.schema.json"
        )
        if checkpoint["signature"] != signature or checkpoint["status"] != "complete":
            return None
        episode = _load_valid(path_policy, base / "episode.json", "episode.schema.json")
        analysis = _load_valid(path_policy, base / "analysis.json", "analysis.schema.json")
        labels = _load_valid(path_policy, base / "final_labels.json", "final_labels.schema.json")
        selection = _load_valid(
            path_policy, base / "selection_decision.json", "selection_decision.schema.json"
        )
        if not (
            checkpoint["assessment_id"] == labels["assessment_id"] == analysis["assessment_id"]
            and checkpoint["episode_id"] == episode["episode_id"] == analysis["episode_id"] == labels["episode_id"]
            and selection["assessment_id"] == labels["assessment_id"]
        ):
            return None
        return episode, analysis, labels, selection
    except Exception:
        return None


def run_pipeline(path_policy, input_locator, run_dir, analysis_path=None, client=None, resume=True):
    run_dir = path_policy.validate_for_write(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalize_session(path_policy, input_locator)
    signature = _signature(normalized, client)
    manifest_path = run_dir / "run_manifest.json"
    if resume and manifest_path.exists():
        try:
            old = _load_valid(path_policy, manifest_path, "run_manifest.schema.json")
            if (
                old.get("signature") == signature
                and old.get("status") == "complete"
                and _inventory_valid(path_policy, run_dir, old)
            ):
                return old
        except Exception:
            pass
    _write_artifact(
        path_policy,
        run_dir / "normalized_session.json",
        normalized,
        "normalized_session.schema.json",
    )
    records = []
    artifact_paths = ["normalized_session.json"]
    if client:
        understanding_checkpoint, understanding_resumed = _understanding_checkpoint(
            path_policy, run_dir, normalized, signature, client, resume
        )
        artifact_paths.append("checkpoints/semantic_checkpoint.json")
        for episode in understanding_checkpoint["episodes"]:
            assessment_id = stable_id(
                "assessment",
                normalized["source_snapshot"]["source_snapshot_id"],
                episode["episode_id"],
            )
            base = run_dir / "assessments" / assessment_id
            resumed = _resume_assessment(path_policy, base, signature) if resume else None
            if resumed:
                episode, analysis, labels, selection = resumed
            else:
                _write_artifact(path_policy, base / "episode.json", episode, "episode.schema.json")
                analysis, evidence_metadata = analyze_episode(normalized, episode, client)
                _write_artifact(path_policy, base / "analysis.json", analysis, "analysis.schema.json")
                labels, labeling_metadata = label_episode(normalized, episode, analysis, client)
                selection = _selection(labels, normalized)
                _write_artifact(
                    path_policy, base / "final_labels.json", labels, "final_labels.schema.json"
                )
                _write_artifact(
                    path_policy,
                    base / "selection_decision.json",
                    selection,
                    "selection_decision.schema.json",
                )
                model_metadata = {
                    "understanding": understanding_checkpoint["model_metadata"],
                    "understanding_resumed": understanding_resumed,
                    "evidence": evidence_metadata,
                    "labeling": labeling_metadata,
                }
                _write(path_policy, base / "model_metadata.json", model_metadata)
                assessment_checkpoint = {
                    "schema_version": "assessment-checkpoint-v1",
                    "signature": signature,
                    "assessment_id": labels["assessment_id"],
                    "episode_id": episode["episode_id"],
                    "status": "complete",
                }
                _write_artifact(
                    path_policy,
                    base / "assessment_checkpoint.json",
                    assessment_checkpoint,
                    "assessment_checkpoint.schema.json",
                )
            relative = str(base.relative_to(run_dir))
            records.append(
                {
                    "assessment_id": labels["assessment_id"],
                    "episode_id": episode["episode_id"],
                    "decision": selection["decision"],
                    "path": relative,
                }
            )
            artifact_paths.extend(
                [
                    f"{relative}/episode.json",
                    f"{relative}/analysis.json",
                    f"{relative}/final_labels.json",
                    f"{relative}/selection_decision.json",
                    f"{relative}/model_metadata.json",
                    f"{relative}/assessment_checkpoint.json",
                ]
            )
    else:
        labels = (
            load_json(path_policy.validate_for_read(analysis_path))
            if analysis_path
            else _empty_labels(normalized)
        )
        validate_artifact(labels, "final_labels.schema.json")
        selection = _selection(labels, normalized)
        _write_artifact(
            path_policy, run_dir / "final_labels.json", labels, "final_labels.schema.json"
        )
        _write_artifact(
            path_policy,
            run_dir / "selection_decision.json",
            selection,
            "selection_decision.schema.json",
        )
        artifact_paths.extend(["final_labels.json", "selection_decision.json"])
        records = [
            {
                "assessment_id": labels["assessment_id"],
                "episode_id": labels["episode_id"],
                "decision": selection["decision"],
                "path": ".",
            }
        ]
    selected = any(record["decision"] == "selected" for record in records)
    if selected:
        _copy_native(path_policy, input_locator, run_dir / "export" / "session.jsonl")
        artifact_paths.append("export/session.jsonl")
    policy = load_yaml("selection_policy.yaml")
    taxonomy = load_yaml("taxonomy.yaml")
    inventory = _artifact_inventory(path_policy, run_dir, artifact_paths)
    manifest = {
        "schema_version": "run-manifest-v1",
        "run_id": stable_id("run", signature),
        "signature": signature,
        "status": "complete",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input": {
            "locator": str(path_policy.remap_locator(input_locator)),
            "session_id": normalized["session_id"],
            "source_snapshot_id": normalized["source_snapshot"]["source_snapshot_id"],
            "sha256": normalized["source_snapshot"]["sha256"],
        },
        "assessments": records,
        "decision_summary": {
            decision: sum(record["decision"] == decision for record in records)
            for decision in ("selected", "not_selected", "pending_review", "invalid")
        },
        "exported_native_session": selected,
        "artifacts": inventory,
        "versions": {
            "pipeline": PIPELINE_VERSION,
            "taxonomy": taxonomy["version"],
            "selection_policy": policy["version"],
        },
        "config_hashes": {
            "taxonomy_sha256": digest_bytes(canonical_json(taxonomy)),
            "selection_policy_sha256": digest_bytes(canonical_json(policy)),
            "resource_bundle_sha256": _resource_bundle_hash(),
        },
        "code_revision": {
            "commit": os.environ.get("SESSION_LABELING_CODE_REVISION"),
            "state": (
                "declared" if os.environ.get("SESSION_LABELING_CODE_REVISION") else "uncommitted"
            ),
        },
        "model": {
            "provider": getattr(getattr(client, "config", None), "name", None),
            "model": getattr(client, "model", None),
        },
    }
    _write_artifact(path_policy, manifest_path, manifest, "run_manifest.schema.json")
    return manifest


def run_batch(path_policy, input_list, output_dir, client=None, limit=None, resume=True):
    rows = []
    with path_policy.open_text(input_list) as source:
        for line in source:
            if line.strip():
                value = json.loads(line)
                rows.append(value if isinstance(value, dict) else {"session_jsonl_path": str(value)})
    if limit is not None:
        rows = rows[:limit]
    results = []
    for row in rows:
        locator = row.get("session_jsonl_path") or row.get("path")
        session_id = row.get("session_id") or stable_id("input", locator)
        try:
            manifest = run_pipeline(
                path_policy,
                locator,
                Path(output_dir) / session_id,
                client=client,
                resume=resume,
            )
            results.append(
                {
                    "session_id": session_id,
                    "status": "complete",
                    "run_id": manifest["run_id"],
                    "decision_summary": manifest["decision_summary"],
                }
            )
        except Exception as error:
            results.append(
                {
                    "session_id": session_id,
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    manifest = {
        "schema_version": "batch-manifest-v1",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_count": len(rows),
        "complete": sum(result["status"] == "complete" for result in results),
        "failed": sum(result["status"] == "failed" for result in results),
        "results": results,
    }
    _write_artifact(
        path_policy,
        Path(output_dir) / "batch_manifest.json",
        manifest,
        "batch_manifest.schema.json",
    )
    return manifest
