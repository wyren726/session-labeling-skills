from __future__ import annotations
import json
import copy
import re
from .contracts import (
    load_schema,
    load_yaml,
    project_root,
    load_text,
    validate_artifact,
    validate_label_references,
)
from .utils import digest_bytes, stable_id

PIPELINE_VERSION = "0.5.0"
UNDERSTANDING_WINDOW_MAX_CHARS = 120000
UNDERSTANDING_WINDOW_OVERLAP_TURNS = 4
UNDERSTANDING_RECONCILE_CONTEXT_TURNS = 4


def _text(event):
    data = event.get("data", {})
    content = data.get("content")
    if isinstance(content, str):
        return content
    if event.get("type") == "tool_call":
        return json.dumps(
            {"tool_name": data.get("tool_name"), "arguments": data.get("arguments")},
            ensure_ascii=False,
            sort_keys=True,
        )
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def compact_turns(session, max_event_chars=1200):
    by_turn = {turn["turn_id"]: [] for turn in session.get("turns", [])}
    for event in session["events"]:
        if event.get("turn_id") in by_turn:
            by_turn[event["turn_id"]].append(
                {
                    "event_id": event["event_id"],
                    "type": event["type"],
                    "text": _text(event)[:max_event_chars],
                }
            )
    return [
        {"turn_id": turn["turn_id"], "events": by_turn[turn["turn_id"]]}
        for turn in session.get("turns", [])
    ]


def _call(client, prompt_name, payload, schema_name):
    root = project_root()
    system = load_text(root / "prompts" / prompt_name)
    schema = load_schema(schema_name)
    return client.complete_json_schema(
        system,
        json.dumps(payload, ensure_ascii=False),
        name=schema_name.replace(".schema.json", "").replace("-", "_"),
        schema=schema,
    )


def taxonomy_role_index(taxonomy=None):
    """Return taxonomy-row -> deterministic selection role.

    The model never chooses this role. Every registry requirement must be classified
    exactly once by the taxonomy's selection_eligibility section.
    """
    taxonomy = taxonomy or load_yaml("taxonomy.yaml")
    eligibility = taxonomy.get("selection_eligibility", {})
    primary = set(eligibility.get("primary_requirement_ids", []))
    auxiliary = set(eligibility.get("auxiliary_requirement_ids", []))
    overlap = primary & auxiliary
    if overlap:
        raise ValueError(f"taxonomy requirements have conflicting selection roles: {sorted(overlap)}")
    index = {}
    unclassified = []
    duplicate_rows = []
    for row in taxonomy.get("capability_registry", []):
        row_id = row["taxonomy_row"]
        if row_id in index:
            duplicate_rows.append(row_id)
            continue
        requirement_id = row.get("requirement_id")
        if requirement_id in primary:
            role = "primary"
        elif requirement_id in auxiliary:
            role = "auxiliary"
        else:
            unclassified.append((row_id, requirement_id))
            continue
        index[row_id] = role
    if duplicate_rows:
        raise ValueError(f"duplicate taxonomy rows: {sorted(duplicate_rows)}")
    if unclassified:
        raise ValueError(f"taxonomy rows lack a selection role: {unclassified[:10]}")
    return index


def _window_reference(window_index, window_turn_ids):
    turn_ids = list(window_turn_ids or [])
    return {
        "window_index": int(window_index),
        "first_turn_id": turn_ids[0] if turn_ids else "",
        "last_turn_id": turn_ids[-1] if turn_ids else "",
    }


def build_canonical_episode(session, raw_episode, window_index=0, window_turn_ids=None):
    turn_order = [turn["turn_id"] for turn in session.get("turns", [])]
    start = raw_episode["start_turn_id"]
    end = raw_episode["end_turn_id"]
    if start not in turn_order or end not in turn_order:
        raise ValueError("episode boundary references a missing turn")
    start_index = turn_order.index(start)
    end_index = turn_order.index(end)
    if start_index > end_index:
        raise ValueError("episode boundary is reversed")
    episode_turn_ids = turn_order[start_index : end_index + 1]
    event_ids = {event["event_id"] for event in session.get("events", [])}
    requirements = []
    goal_origins = []
    for requirement in raw_episode.get("requirements", []):
        origins = [event_id for event_id in requirement.get("origin_event_ids", []) if event_id in event_ids]
        goal_origins.extend(origins)
        requirements.append(
            {
                "requirement_id": requirement["requirement_id"],
                "text": requirement["text"],
                "origin_event_ids": list(dict.fromkeys(origins)),
                "is_core": bool(requirement.get("is_core", False)),
            }
        )
    snapshot_id = session["source_snapshot"]["source_snapshot_id"]
    goal_text = raw_episode["goal"]
    episode_id = stable_id("episode", snapshot_id, start, end, goal_text)
    source_window = _window_reference(
        window_index, window_turn_ids or episode_turn_ids
    )
    candidate_windows = raw_episode.get("_candidate_windows") or [source_window]
    result = {
        "schema_version": "episode-v1",
        "episode_id": episode_id,
        "session_id": session["session_id"],
        "source_snapshot_id": snapshot_id,
        "boundary": {
            "start_turn_id": start,
            "end_turn_id": end,
            "turn_ids": episode_turn_ids,
            "boundary_confidence": raw_episode.get("boundary_confidence"),
            "source_window": source_window,
            "candidate_windows": list(
                {
                    (item["window_index"], item["first_turn_id"], item["last_turn_id"]): item
                    for item in candidate_windows
                }.values()
            ),
            "reconciliation": raw_episode.get(
                "_reconciliation",
                {"status": "single_window", "candidate_count": 1, "method": "none"},
            ),
        },
        "goal": {
            "text": goal_text,
            "origin_event_ids": list(dict.fromkeys(goal_origins)),
        },
        "requirements": requirements,
        "limitations": list(raw_episode.get("limitations", [])),
        "provenance": {
            "producer_skill": "session-understanding",
            "producer_version": PIPELINE_VERSION,
            "method": raw_episode.get("_provenance_method", "model_assisted_validated"),
            "source_snapshot_id": snapshot_id,
        },
    }
    return validate_artifact(result, "episode.schema.json")


def _turn_windows(turns, max_chars=None, overlap_turns=None):
    max_chars = max_chars or UNDERSTANDING_WINDOW_MAX_CHARS
    overlap_turns = (
        UNDERSTANDING_WINDOW_OVERLAP_TURNS if overlap_turns is None else overlap_turns
    )
    windows = []
    start = 0
    while start < len(turns):
        end = start
        size = 0
        while end < len(turns):
            n = len(json.dumps(turns[end], ensure_ascii=False))
            if end > start and size + n > max_chars:
                break
            size += n
            end += 1
        chunk = turns[start:end]
        windows.append(
            {
                "window_index": len(windows),
                "start_index": start,
                "end_index": end - 1,
                "turns": chunk,
                "turn_ids": [turn["turn_id"] for turn in chunk],
            }
        )
        if end >= len(turns):
            break
        start = max(start + 1, end - max(0, overlap_turns))
    return windows


def _goal_key(text):
    return " ".join(re.sub(r"[^\\w]+", " ", str(text).casefold()).split())


def _goal_similarity(left, right):
    a = set(_goal_key(left).split())
    b = set(_goal_key(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _merge_exact_candidates(candidates):
    grouped = {}
    for episode in candidates:
        key = (
            episode["boundary"]["start_turn_id"],
            episode["boundary"]["end_turn_id"],
            _goal_key(episode["goal"]["text"]),
        )
        grouped.setdefault(key, []).append(episode)
    output = []
    for group in grouped.values():
        chosen = copy.deepcopy(
            max(
                group,
                key=lambda item: item["boundary"].get("boundary_confidence") or 0.0,
            )
        )
        if len(group) > 1:
            windows = []
            requirements = []
            origins = []
            limitations = []
            for item in group:
                windows.extend(item["boundary"]["candidate_windows"])
                requirements.extend(item["requirements"])
                origins.extend(item["goal"]["origin_event_ids"])
                limitations.extend(item["limitations"])
            chosen["boundary"]["candidate_windows"] = list(
                {
                    (item["window_index"], item["first_turn_id"], item["last_turn_id"]): item
                    for item in windows
                }.values()
            )
            chosen["boundary"]["reconciliation"] = {
                "status": "duplicate_merged",
                "candidate_count": len(group),
                "method": "deterministic_exact_boundary_goal",
            }
            chosen["requirements"] = list(
                {
                    (item["requirement_id"], item["text"], item["is_core"]): item
                    for item in requirements
                }.values()
            )
            chosen["goal"]["origin_event_ids"] = list(dict.fromkeys(origins))
            chosen["limitations"] = list(dict.fromkeys(limitations))
            validate_artifact(chosen, "episode.schema.json")
        output.append(chosen)
    return output


def _is_clipped(episode, global_first, global_last):
    start = episode["boundary"]["start_turn_id"]
    end = episode["boundary"]["end_turn_id"]
    for window in episode["boundary"]["candidate_windows"]:
        if start == window["first_turn_id"] and start != global_first:
            return True
        if end == window["last_turn_id"] and end != global_last:
            return True
    return False


def _ambiguous_clusters(candidates, turn_order):
    position = {turn_id: index for index, turn_id in enumerate(turn_order)}
    graph = {index: set() for index in range(len(candidates))}
    clipped = set()
    if not turn_order:
        return []
    for index, episode in enumerate(candidates):
        if _is_clipped(episode, turn_order[0], turn_order[-1]):
            clipped.add(index)
    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            a = candidates[left]
            b = candidates[right]
            if _goal_similarity(a["goal"]["text"], b["goal"]["text"]) < 0.5:
                continue
            a0 = position[a["boundary"]["start_turn_id"]]
            a1 = position[a["boundary"]["end_turn_id"]]
            b0 = position[b["boundary"]["start_turn_id"]]
            b1 = position[b["boundary"]["end_turn_id"]]
            window_a = {item["window_index"] for item in a["boundary"]["candidate_windows"]}
            window_b = {item["window_index"] for item in b["boundary"]["candidate_windows"]}
            neighboring_windows = any(abs(x - y) <= 1 for x in window_a for y in window_b)
            ranges_touch = max(a0, b0) <= min(a1, b1) + 1
            if ranges_touch and neighboring_windows and (left in clipped or right in clipped):
                graph[left].add(right)
                graph[right].add(left)
    pending = set(clipped)
    clusters = []
    while pending:
        seed = pending.pop()
        component = {seed}
        stack = [seed]
        while stack:
            current = stack.pop()
            for neighbor in graph[current]:
                if neighbor not in component:
                    component.add(neighbor)
                    pending.discard(neighbor)
                    stack.append(neighbor)
        clusters.append(sorted(component))
    return clusters


def _model_episodes_from_window(session, value, window, method="model_assisted_validated"):
    chunk = window["turns"]
    chunk_turns = {turn["turn_id"] for turn in chunk}
    chunk_event_ids = {event["event_id"] for turn in chunk for event in turn["events"]}
    episodes = []
    for raw_episode in value.get("episodes", []):
        if raw_episode["start_turn_id"] not in chunk_turns or raw_episode["end_turn_id"] not in chunk_turns:
            continue
        bad = [
            event_id
            for requirement in raw_episode["requirements"]
            for event_id in requirement["origin_event_ids"]
            if event_id not in chunk_event_ids
        ]
        if bad:
            raw_episode.setdefault("limitations", []).append(
                "some requirement origin event IDs were invalid and removed"
            )
            for requirement in raw_episode["requirements"]:
                requirement["origin_event_ids"] = [
                    event_id for event_id in requirement["origin_event_ids"] if event_id not in bad
                ]
        raw_episode["_provenance_method"] = method
        episodes.append(
            build_canonical_episode(
                session,
                raw_episode,
                window["window_index"],
                window["turn_ids"],
            )
        )
    return episodes


def _reconcile_candidates(session, compacted_turns, candidates, client, metadata):
    turn_order = [turn["turn_id"] for turn in compacted_turns]
    position = {turn_id: index for index, turn_id in enumerate(turn_order)}
    clusters = _ambiguous_clusters(candidates, turn_order)
    replaced = set()
    reconciled = []
    for cluster_index, indexes in enumerate(clusters):
        cluster = [candidates[index] for index in indexes]
        lower = max(
            0,
            min(position[item["boundary"]["start_turn_id"]] for item in cluster)
            - UNDERSTANDING_RECONCILE_CONTEXT_TURNS,
        )
        upper = min(
            len(compacted_turns) - 1,
            max(position[item["boundary"]["end_turn_id"]] for item in cluster)
            + UNDERSTANDING_RECONCILE_CONTEXT_TURNS,
        )
        turns = compacted_turns[lower : upper + 1]
        windows = [
            window
            for item in cluster
            for window in item["boundary"]["candidate_windows"]
        ]
        payload_candidates = [
            {
                "episode_id": item["episode_id"],
                "start_turn_id": item["boundary"]["start_turn_id"],
                "end_turn_id": item["boundary"]["end_turn_id"],
                "goal": item["goal"]["text"],
                "requirements": item["requirements"],
                "candidate_windows": item["boundary"]["candidate_windows"],
            }
            for item in cluster
        ]
        value, meta = _call(
            client,
            "reconcile_understanding.md",
            {
                "mode": "reconcile_boundary_candidates",
                "cluster_index": cluster_index,
                "candidate_episodes": payload_candidates,
                "turns": turns,
            },
            "model_understanding.schema.json",
        )
        metadata.append({"phase": "boundary_reconciliation", "cluster_index": cluster_index, "metadata": meta})
        followup_window = {
            "window_index": min(item["window_index"] for item in windows),
            "turns": turns,
            "turn_ids": [turn["turn_id"] for turn in turns],
        }
        produced = _model_episodes_from_window(
            session,
            value,
            followup_window,
            method="model_assisted_cross_window_reconciled",
        )
        if produced:
            for item in produced:
                item["boundary"]["candidate_windows"] = list(
                    {
                        (window["window_index"], window["first_turn_id"], window["last_turn_id"]): window
                        for window in windows
                    }.values()
                )
                item["boundary"]["reconciliation"] = {
                    "status": "model_reconciled",
                    "candidate_count": len(cluster),
                    "method": "targeted_cross_window_followup",
                }
                validate_artifact(item, "episode.schema.json")
            reconciled.extend(produced)
            replaced.update(indexes)
        else:
            for index in indexes:
                item = copy.deepcopy(candidates[index])
                item["limitations"] = list(
                    dict.fromkeys(item["limitations"] + ["unresolved cross-window Episode boundary"])
                )
                item["boundary"]["reconciliation"] = {
                    "status": "unresolved",
                    "candidate_count": len(cluster),
                    "method": "targeted_followup_returned_no_valid_episode",
                }
                validate_artifact(item, "episode.schema.json")
                reconciled.append(item)
                replaced.add(index)
    reconciled.extend(item for index, item in enumerate(candidates) if index not in replaced)
    return reconciled


def understand(session, client):
    turns = compact_turns(session)
    windows = _turn_windows(turns)
    episodes = []
    metadata = []
    for window in windows:
        value, meta = _call(
            client,
            "understanding.md",
            {"mode": "discover_episodes", "chunk_index": window["window_index"], "turns": window["turns"]},
            "model_understanding.schema.json",
        )
        episodes.extend(_model_episodes_from_window(session, value, window))
        metadata.append({"phase": "discovery", "window_index": window["window_index"], "metadata": meta})
    episodes = _merge_exact_candidates(episodes)
    if len(windows) > 1 and episodes:
        episodes = _reconcile_candidates(session, turns, episodes, client, metadata)
        episodes = _merge_exact_candidates(episodes)
    position = {turn["turn_id"]: index for index, turn in enumerate(turns)}
    episodes.sort(
        key=lambda item: (
            position[item["boundary"]["start_turn_id"]],
            position[item["boundary"]["end_turn_id"]],
            item["episode_id"],
        )
    )
    return episodes, metadata


def build_canonical_analysis(session, episode, model_value, validation_issues=None):
    snapshot_id = session["source_snapshot"]["source_snapshot_id"]
    assessment_id = stable_id("assessment", snapshot_id, episode["episode_id"])
    result = {
        "schema_version": "analysis-v1",
        "analysis_id": stable_id("analysis", assessment_id),
        "assessment_id": assessment_id,
        "session_id": session["session_id"],
        "episode_id": episode["episode_id"],
        "source_snapshot_id": snapshot_id,
        "evidence": list(model_value.get("evidence", [])),
        "execution": {
            "agent_claimed_status": model_value.get("agent_claimed_status", "unknown"),
            "verified_outcome": {"status": model_value.get("verified_outcome", "unknown")},
            "requirement_results": list(model_value.get("requirement_results", [])),
        },
        "limitations": list(model_value.get("limitations", [])),
        "validation_issues": list(validation_issues or []),
        "provenance": {
            "producer_skill": "session-evidence-analysis",
            "producer_version": PIPELINE_VERSION,
            "method": "model_assisted_quote_validated",
            "source_snapshot_id": snapshot_id,
        },
    }
    return validate_artifact(result, "analysis.schema.json")


def analyze_episode(session, episode, client):
    turn_order = [turn["turn_id"] for turn in session["turns"]]
    start = episode["boundary"]["start_turn_id"]
    end = episode["boundary"]["end_turn_id"]
    a = turn_order.index(start)
    b = turn_order.index(end)
    allowed = set(turn_order[a : b + 1])
    events = [
        {
            "event_id": event["event_id"],
            "turn_id": event.get("turn_id"),
            "type": event["type"],
            "body": _text(event),
        }
        for event in session["events"]
        if event.get("turn_id") in allowed
    ]
    chunks = []
    current = []
    size = 0
    for event in events:
        n = len(event["body"]) + 200
        if current and size + n > 100000:
            chunks.append(current)
            current = []
            size = 0
        if len(event["body"]) > 12000:
            event = {
                **event,
                "body": event["body"][:6000] + "\n<...TRUNCATED...>\n" + event["body"][-6000:],
            }
        current.append(event)
        size += min(n, 12200)
    if current:
        chunks.append(current)
    partials = []
    metadata = []
    bodies = {event["event_id"]: event["body"] for event in events}
    for index, chunk in enumerate(chunks):
        value, meta = _call(
            client,
            "evidence.md",
            {"episode": episode, "chunk_index": index, "events": chunk},
            "model_evidence.schema.json",
        )
        partials.append(value)
        metadata.append(meta)
    if len(partials) > 1:
        value, reduce_meta = _call(
            client,
            "evidence.md",
            {"episode": episode, "mode": "reduce_partial_analyses", "partial_analyses": partials},
            "model_evidence.schema.json",
        )
        metadata.append(reduce_meta)
        by_id = {
            evidence["evidence_id"]: evidence
            for partial in partials
            for evidence in partial["evidence"]
        }
        value["evidence"] = [
            by_id[evidence_id]
            for evidence_id in dict.fromkeys(
                evidence["evidence_id"] for evidence in value["evidence"]
            )
            if evidence_id in by_id
        ]
    elif partials:
        value = partials[0]
    else:
        value = {
            "evidence": [],
            "agent_claimed_status": "unknown",
            "verified_outcome": "unknown",
            "requirement_results": [],
            "limitations": ["empty episode"],
        }
    valid = []
    issues = []
    for evidence in value["evidence"]:
        if evidence["event_id"] not in bodies:
            issues.append(f"unknown event {evidence['event_id']}")
            continue
        if evidence["quote"] not in bodies[evidence["event_id"]]:
            issues.append(f"non-continuous quote {evidence['evidence_id']}")
            continue
        valid.append(
            {
                **evidence,
                "source_snapshot_id": session["source_snapshot"]["source_snapshot_id"],
                "content_digest": digest_bytes(evidence["quote"].encode("utf-8")),
            }
        )
    value["evidence"] = valid
    return build_canonical_analysis(session, episode, value, issues), metadata


def label_episode(session, episode, analysis, client):
    taxonomy = load_yaml("taxonomy.yaml")
    registry = taxonomy["capability_registry"]
    role_by_row = taxonomy_role_index(taxonomy)
    value, meta = _call(
        client,
        "labeling.md",
        {
            "episode": episode,
            "analysis": analysis,
            "taxonomy_registry_id": taxonomy["registry_id"],
            "taxonomy_version": taxonomy["version"],
            "taxonomy_registry": registry,
        },
        "model_labeling.schema.json",
    )
    rows = {row["taxonomy_row"]: row for row in registry}
    issues = []
    mappings = []
    for mapping in value["capability_mappings"]:
        row = rows.get(mapping["taxonomy_row"])
        if row is None:
            issues.append(f"taxonomy row outside registry: {mapping['taxonomy_row']}")
            mappings.append({"role": "unknown", **mapping, "status": "invalid"})
            continue
        mappings.append(
            {
                **mapping,
                "role": role_by_row[mapping["taxonomy_row"]],
                "taxonomy": {
                    "registry_id": taxonomy["registry_id"],
                    "version": taxonomy["version"],
                    "taxonomy_row": row["taxonomy_row"],
                    "requirement_id": row["requirement_id"],
                    "subrequirement_id": row["subrequirement_id"],
                    "requirement_name": row["requirement_name"],
                    "subrequirement_name": row["subrequirement_name"],
                },
            }
        )
    execution = analysis["execution"]
    labels = {
        "schema_version": "final-labels-v1",
        "assessment_id": analysis["assessment_id"],
        "session_id": session["session_id"],
        "episode_id": episode["episode_id"],
        "source_snapshot_id": session["source_snapshot"]["source_snapshot_id"],
        "evidence": analysis["evidence"],
        "claims": value["claims"],
        "capability_mappings": mappings,
        "task_attributes": {
            "difficulty": value["difficulty"],
            "difficulty_evidence_refs": value.get("difficulty_evidence_refs", []),
        },
        "semantic_rule_reviews": [
            {"rule_id": "S3", **value["S3"]},
            {"rule_id": "S4", **value["S4"]},
        ],
        "execution": execution,
        "scope_match": "pass",
        "selection_critical_conflicts": [],
        "limitations": (
            episode.get("limitations", [])
            + analysis.get("limitations", [])
            + value.get("limitations", [])
        ),
        "validation_issues": issues + analysis.get("validation_issues", []),
        "provenance": {
            "producer_skill": "session-quality-labeling",
            "producer_version": PIPELINE_VERSION,
            "method": "model_assisted_registry_validated",
            "source_snapshot_id": session["source_snapshot"]["source_snapshot_id"],
            "taxonomy_registry_id": taxonomy["registry_id"],
            "taxonomy_version": taxonomy["version"],
        },
    }
    validate_artifact(labels, "final_labels.schema.json")
    labels["validation_issues"].extend(validate_label_references(labels, session))
    return validate_artifact(labels, "final_labels.schema.json"), meta


def run_semantic(session, client):
    episodes, understanding_metadata = understand(session, client)
    outputs = []
    for episode in episodes:
        analysis, evidence_metadata = analyze_episode(session, episode, client)
        labels, labeling_metadata = label_episode(session, episode, analysis, client)
        outputs.append(
            {
                "episode": episode,
                "analysis": analysis,
                "labels": labels,
                "model_metadata": {
                    "understanding": understanding_metadata,
                    "evidence": evidence_metadata,
                    "labeling": labeling_metadata,
                },
            }
        )
    return outputs
