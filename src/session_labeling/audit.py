from __future__ import annotations
from pathlib import Path, PurePosixPath
import ast
import hashlib
import json
from .contracts import validate_artifact, validate_label_references
from .selection import evaluate
from .utils import load_json

FORBIDDEN = "/mnt/shared-storage-user" + "/songdemin/user/renwanying"
SKIP_DIRS = {".git", "__pycache__", ".venv", "build", "dist"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".csv"}


def _imports_legacy_package(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "trace_analysis" or alias.name.startswith("trace_analysis.")
            for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "trace_analysis" or node.module.startswith("trace_analysis."))
        ):
            return True
    return False


def audit_tree(root):
    root = Path(root)
    hits = []
    forbidden_imports = []
    read_errors = []
    files = 0
    for path in root.rglob("*"):
        if (
            not path.is_file()
            or any(part in SKIP_DIRS for part in path.parts)
            or path.suffix.lower() not in TEXT_SUFFIXES
        ):
            continue
        files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as error:
            read_errors.append(
                {"path": str(path.relative_to(root)), "error": str(error)}
            )
            continue
        if FORBIDDEN in text:
            hits.append(str(path.relative_to(root)))
        if path.suffix == ".py" and _imports_legacy_package(text):
            forbidden_imports.append(str(path.relative_to(root)))
    issues = [
        *[f"forbidden path literal: {path}" for path in hits],
        *[f"forbidden runtime import: {path}" for path in forbidden_imports],
        *[f"read error: {item['path']}: {item['error']}" for item in read_errors],
    ]
    return {
        "schema_version": "audit-report-v1",
        "mode": "repository",
        "files_scanned": files,
        "forbidden_path_hits": hits,
        "forbidden_runtime_imports": forbidden_imports,
        "read_errors": read_errors,
        "checks": {},
        "issues": issues,
        "warnings": [],
        "valid": not issues,
    }


def _safe_relative(value):
    path = PurePosixPath(str(value))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe relative path: {value}")
    return path


def _digest(policy, path):
    hasher = hashlib.sha256()
    size = 0
    with policy.open_binary(path) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _event_text(event):
    data = event.get("data", {})
    content = data.get("content") if isinstance(data, dict) else None
    if isinstance(content, str):
        return content
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def audit_run(path_policy, run_dir):
    run_dir = path_policy.validate_for_write(run_dir)
    issues = []
    warnings = []
    checks = {
        "manifest_schema": False,
        "artifact_inventory": False,
        "normalized_session_schema": False,
        "assessment_schemas": False,
        "lineage_joins": False,
        "evidence_cross_references": False,
        "selection_recomputation": False,
        "export_integrity": False,
    }
    try:
        manifest = load_json(path_policy.validate_for_read(run_dir / "run_manifest.json"))
        validate_artifact(manifest, "run_manifest.schema.json")
        checks["manifest_schema"] = True
    except Exception as error:
        issues.append(f"run manifest invalid: {type(error).__name__}: {error}")
        return {
            "schema_version": "audit-report-v1",
            "mode": "run",
            "files_scanned": 0,
            "forbidden_path_hits": [],
            "forbidden_runtime_imports": [],
            "read_errors": [],
            "checks": checks,
            "issues": issues,
            "warnings": warnings,
            "valid": False,
        }
    inventory_paths = set()
    for artifact in manifest["artifacts"]:
        try:
            relative = _safe_relative(artifact["path"])
            inventory_paths.add(str(relative))
            sha256, size = _digest(path_policy, run_dir / str(relative))
            if sha256 != artifact["sha256"] or size != artifact["size_bytes"]:
                issues.append(f"artifact hash/size mismatch: {relative}")
        except Exception as error:
            issues.append(f"artifact missing or unsafe {artifact.get('path')}: {type(error).__name__}: {error}")
    checks["artifact_inventory"] = not any("artifact" in issue for issue in issues)
    normalized = None
    try:
        normalized = load_json(path_policy.validate_for_read(run_dir / "normalized_session.json"))
        validate_artifact(normalized, "normalized_session.schema.json")
        checks["normalized_session_schema"] = True
        if normalized["session_id"] != manifest["input"]["session_id"]:
            issues.append("normalized session ID does not match manifest input")
        if normalized["source_snapshot"]["source_snapshot_id"] != manifest["input"]["source_snapshot_id"]:
            issues.append("normalized source snapshot does not match manifest input")
        if normalized["source_snapshot"]["sha256"] != manifest["input"]["sha256"]:
            issues.append("normalized source hash does not match manifest input")
    except Exception as error:
        issues.append(f"normalized session invalid: {type(error).__name__}: {error}")
    schema_failures = []
    lineage_failures = []
    reference_failures = []
    selection_failures = []
    selected = []
    if normalized is not None:
        event_by_id = {event["event_id"]: event for event in normalized["events"]}
        for record in manifest["assessments"]:
            try:
                relative = _safe_relative(record["path"])
                base = run_dir if str(relative) == "." else run_dir / str(relative)
                if str(relative) == ".":
                    episode = None
                    analysis = None
                else:
                    episode = load_json(path_policy.validate_for_read(base / "episode.json"))
                    analysis = load_json(path_policy.validate_for_read(base / "analysis.json"))
                    validate_artifact(episode, "episode.schema.json")
                    validate_artifact(analysis, "analysis.schema.json")
                labels = load_json(path_policy.validate_for_read(base / "final_labels.json"))
                decision = load_json(path_policy.validate_for_read(base / "selection_decision.json"))
                validate_artifact(labels, "final_labels.schema.json")
                validate_artifact(decision, "selection_decision.schema.json")
            except Exception as error:
                schema_failures.append(
                    f"assessment {record.get('assessment_id')} schema/read failure: {type(error).__name__}: {error}"
                )
                continue
            if labels["assessment_id"] != record["assessment_id"] or decision["assessment_id"] != record["assessment_id"]:
                lineage_failures.append(f"assessment ID mismatch for {record['assessment_id']}")
            if labels["episode_id"] != record["episode_id"]:
                lineage_failures.append(f"episode ID mismatch for {record['assessment_id']}")
            if labels["session_id"] != normalized["session_id"] or labels["source_snapshot_id"] != normalized["source_snapshot"]["source_snapshot_id"]:
                lineage_failures.append(f"session/source lineage mismatch for {record['assessment_id']}")
            if episode is not None and analysis is not None:
                if not (
                    episode["episode_id"] == analysis["episode_id"] == labels["episode_id"]
                    and analysis["assessment_id"] == labels["assessment_id"]
                    and analysis["source_snapshot_id"] == labels["source_snapshot_id"]
                ):
                    lineage_failures.append(f"episode-analysis-label join mismatch for {record['assessment_id']}")
                if analysis["execution"] != labels["execution"]:
                    lineage_failures.append(f"analysis/label execution mismatch for {record['assessment_id']}")
            reference_failures.extend(
                f"{record['assessment_id']}: {issue}"
                for issue in validate_label_references(labels, normalized)
            )
            for evidence in labels["evidence"]:
                event = event_by_id.get(evidence["event_id"])
                if event is not None and evidence["quote"] not in _event_text(event):
                    reference_failures.append(
                        f"{record['assessment_id']}: evidence {evidence['evidence_id']} quote is not exact event text"
                    )
                if evidence["source_snapshot_id"] != normalized["source_snapshot"]["source_snapshot_id"]:
                    reference_failures.append(
                        f"{record['assessment_id']}: evidence {evidence['evidence_id']} source snapshot mismatch"
                    )
            recomputed = evaluate(labels)
            expected_rules = {rule["rule_id"]: rule["status"] for rule in decision["rules"]}
            actual_rules = {rule["rule_id"]: rule["status"] for rule in recomputed["rules"]}
            if decision["decision"] != recomputed["decision"] or expected_rules != actual_rules:
                selection_failures.append(f"selection is stale or inconsistent for {record['assessment_id']}")
            if record["decision"] != decision["decision"]:
                selection_failures.append(f"manifest decision mismatch for {record['assessment_id']}")
            if decision["decision"] == "selected":
                selected.append(record["assessment_id"])
    issues.extend(schema_failures + lineage_failures + reference_failures + selection_failures)
    checks["assessment_schemas"] = not schema_failures
    checks["lineage_joins"] = not lineage_failures
    checks["evidence_cross_references"] = not reference_failures
    checks["selection_recomputation"] = not selection_failures
    export_path = run_dir / "export" / "session.jsonl"
    should_export = bool(selected)
    if manifest["exported_native_session"] != should_export:
        issues.append("manifest export flag does not match selected assessments")
    if should_export:
        try:
            export_hash, _ = _digest(path_policy, export_path)
            if export_hash != manifest["input"]["sha256"]:
                issues.append("native export hash does not match source snapshot")
            if "export/session.jsonl" not in inventory_paths:
                issues.append("native export is absent from artifact inventory")
        except Exception as error:
            issues.append(f"selected run lacks valid native export: {type(error).__name__}: {error}")
    elif export_path.exists():
        issues.append("non-selected run contains a stale native export")
    checks["export_integrity"] = not any("export" in issue for issue in issues)
    return {
        "schema_version": "audit-report-v1",
        "mode": "run",
        "files_scanned": len(manifest.get("artifacts", [])) + 1,
        "forbidden_path_hits": [],
        "forbidden_runtime_imports": [],
        "read_errors": [],
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
        "valid": not issues and all(checks.values()),
    }
