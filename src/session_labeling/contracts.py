from __future__ import annotations
import json, os, stat
from pathlib import Path, PurePosixPath
import jsonschema, yaml

_RESOURCE_DIRS = ("config", "schemas", "prompts")


def _source_root():
    return Path(__file__).absolute().parents[2]


def _has_resources(root):
    return all((root / name).is_dir() for name in _RESOURCE_DIRS)


def resource_root():
    """Return the sole runtime resource tree.

    A source checkout uses the repository-level directories. Wheel builds copy those
    exact files into ``session_labeling/resources``; no second source tree is kept.
    """
    source = _source_root()
    if _has_resources(source):
        return source
    packaged = Path(__file__).absolute().parent / "resources"
    if _has_resources(packaged):
        return packaged
    raise FileNotFoundError(
        "session-labeling resources were not found in the source checkout or installed package"
    )


def project_root():
    # Backwards-compatible name used by the semantic prompt loader.
    return resource_root()


def config_root():
    return resource_root() / "config"


def schema_root():
    return resource_root() / "schemas"


def prompt_root():
    return resource_root() / "prompts"


def _safe_text(path):
    path = Path(path).absolute()
    root = PurePosixPath(str(resource_root()))
    p = PurePosixPath(str(path))
    if not (p == root or root in p.parents):
        raise ValueError(f"internal resource outside resource root: {path}")
    cur = PurePosixPath("/")
    for part in p.parts[1:]:
        cur /= part
        mode = os.lstat(str(cur)).st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"symlink resource rejected: {cur}")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "r", encoding="utf-8") as f:
        return f.read()


def load_text(path):
    return _safe_text(path)


def load_yaml(name):
    return yaml.safe_load(_safe_text(config_root() / name))


def load_schema(name):
    return json.loads(_safe_text(schema_root() / name))


def validate_artifact(value, name):
    jsonschema.Draft202012Validator(load_schema(name)).validate(value)
    return value


def validate_label_references(labels, normalized=None):
    issues = []
    evidence = {
        e.get("evidence_id"): e
        for e in labels.get("evidence", [])
        if isinstance(e, dict) and e.get("evidence_id")
    }
    event_ids = {e.get("event_id") for e in (normalized or {}).get("events", [])}
    for eid, evidence_item in evidence.items():
        if normalized is not None and evidence_item.get("event_id") not in event_ids:
            issues.append(
                f"evidence {eid} references missing event {evidence_item.get('event_id')}"
            )
        if not isinstance(evidence_item.get("quote"), str) or not evidence_item.get("quote"):
            issues.append(f"evidence {eid} has no exact quote")
    for group in ("claims", "capability_mappings", "semantic_rule_reviews"):
        for obj in labels.get(group, []):
            for ref in obj.get("evidence_refs", []):
                if ref not in evidence:
                    issues.append(f"{group} object references missing evidence {ref}")
    return issues
