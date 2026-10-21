from __future__ import annotations
from .utils import stable_id
from .contracts import load_yaml, validate_label_references

VALID = {"pass", "fail", "pending", "invalid"}


def _rule(rule_id, status, reason, evidence_refs=()):
    if status not in VALID:
        raise ValueError(status)
    return {
        "rule_id": rule_id,
        "status": status,
        "reason": reason,
        "evidence_refs": list(evidence_refs),
    }


def evaluate(labels, policy=None):
    policy = policy or load_yaml("selection_policy.yaml")
    evidence_ids = {
        evidence.get("evidence_id")
        for evidence in labels.get("evidence", [])
        if evidence.get("evidence_id")
    }
    issues = list(labels.get("validation_issues", []))
    issues.extend(validate_label_references(labels))
    for claim in labels.get("claims", []):
        missing = [ref for ref in claim.get("evidence_refs", []) if ref not in evidence_ids]
        if missing:
            issues.append(f"claim {claim.get('claim_id', '?')} has missing evidence refs: {missing}")
    for mapping in labels.get("capability_mappings", []):
        missing = [ref for ref in mapping.get("evidence_refs", []) if ref not in evidence_ids]
        if missing:
            issues.append(f"mapping {mapping.get('mapping_id', '?')} has missing evidence refs: {missing}")
    issues = sorted(set(issues))
    prechecks = {
        "valid_schema": "invalid" if labels.get("validation_issues") else "pass",
        "valid_references": "invalid" if issues else "pass",
        "scope_match": labels.get("scope_match", "pass"),
        "no_selection_critical_unresolved_conflict": (
            "pending" if labels.get("selection_critical_conflicts") else "pass"
        ),
    }
    primary_mappings = [
        mapping
        for mapping in labels.get("capability_mappings", [])
        if mapping.get("role") == "primary"
    ]
    supported = [
        mapping
        for mapping in primary_mappings
        if mapping.get("status") == "supported"
        and mapping.get("evidence_refs")
        and all(ref in evidence_ids for ref in mapping.get("evidence_refs", []))
    ]
    if supported:
        s1 = _rule(
            "S1",
            "pass",
            "at least one evidence-supported primary mapping",
            [ref for mapping in supported for ref in mapping.get("evidence_refs", [])],
        )
    elif any(mapping.get("status") in {"unresolved", "invalid"} for mapping in primary_mappings):
        s1 = _rule("S1", "pending", "primary mapping is unresolved")
    elif primary_mappings:
        s1 = _rule("S1", "fail", "no evidence-supported primary mapping")
    else:
        s1 = _rule(
            "S1",
            "pending",
            "no primary mapping; auxiliary mappings cannot satisfy S1",
        )
    difficulty = labels.get("task_attributes", {}).get("difficulty", "unknown")
    s2_config = policy["rules"]["S2"]
    if difficulty in set(s2_config["pass_values"]):
        s2 = _rule(
            "S2",
            "pass",
            f"difficulty={difficulty}",
            labels.get("task_attributes", {}).get("difficulty_evidence_refs", []),
        )
    elif difficulty in set(s2_config["fail_values"]):
        s2 = _rule("S2", "fail", "reviewed difficulty=low")
    else:
        s2 = _rule("S2", "pending", "difficulty unresolved")
    supplied = {
        rule.get("rule_id"): rule
        for rule in labels.get("semantic_rule_reviews", [])
        if isinstance(rule, dict)
    }
    semantic = []
    for rule_id in ("S3", "S4"):
        rule = supplied.get(rule_id)
        if not rule:
            semantic.append(_rule(rule_id, "pending", "semantic audit not supplied"))
            continue
        status = rule.get("status", "invalid")
        if status not in VALID:
            status = "invalid"
        semantic.append(
            _rule(
                rule_id,
                status,
                rule.get("reason", "supplied semantic audit"),
                rule.get("evidence_refs", []),
            )
        )
    rules = [s1, s2, *semantic]
    statuses = [*prechecks.values(), *(rule["status"] for rule in rules)]
    if "invalid" in statuses:
        decision = "invalid"
    elif prechecks["scope_match"] == "fail" or any(rule["status"] == "fail" for rule in rules):
        decision = "not_selected"
    elif all(value == "pass" for value in prechecks.values()) and all(
        rule["status"] == "pass" for rule in rules
    ):
        decision = "selected"
    else:
        decision = "pending_review"
    return {
        "schema_version": "selection-decision-v1",
        "selection_id": stable_id(
            "selection", labels.get("assessment_id"), rules, prechecks
        ),
        "assessment_id": labels.get("assessment_id"),
        "policy_id": policy["policy_id"],
        "policy_version": policy["version"],
        "prechecks": prechecks,
        "rules": rules,
        "decision": decision,
        "legacy_decision": {
            "selected": "priority_candidate",
            "pending_review": "review",
            "not_selected": "not_selected",
            "invalid": "review",
        }[decision],
        "issues": issues,
    }
