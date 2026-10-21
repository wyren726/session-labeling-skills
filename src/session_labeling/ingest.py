from __future__ import annotations
import hashlib
import json
import os
import re
from collections import Counter
from typing import Any
from .utils import stable_id, digest_bytes
from .contracts import validate_artifact
from .path_policy import FORBIDDEN_ROOT

ADAPTER_NAME = "session_jsonl"
ADAPTER_VERSION = "0.4.0"


class IngestionError(ValueError):
    pass


_REDACTIONS = (
    (
        re.compile(
            r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
            re.I | re.S,
        ),
        "<PRIVATE_KEY>",
    ),
    (re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{12,}\b"), "<API_KEY>"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I), "Bearer <TOKEN>"),
    (
        re.compile(
            r"(?P<label>密码|口令|password|passwd|pwd|passphrase|api[ _-]?key|access[ _-]?token|secret(?:[ _-]?key)?)"
            r"(?P<separator>\s*(?::|：|=|是)?\s*)"
            r"(?P<secret>(?!<)[A-Za-z0-9_./+@=-]{6,})",
            re.I,
        ),
        r"\g<label>\g<separator><SECRET>",
    ),
    (re.compile(r"\b[\w.+-]{1,64}@[\w.-]{1,253}\.[A-Za-z]{2,63}\b"), "<EMAIL>"),
    (re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"), "<IP_ADDRESS>"),
    (re.compile(r"(?<![\w])/(?:Users|home)/[^\s\"']+"), "<LOCAL_PATH>"),
    (re.compile(r"(?<![\w])/mnt/(?:agent-workspace|data)(?:/[^\s\"']*)?"), "<LOCAL_PATH>"),
    (re.compile(r"\b[A-Za-z]:\\Users\\[^\s\"']+", re.I), "<LOCAL_PATH>"),
)


def _redact_text(value: str):
    count = 0
    forbidden = str(FORBIDDEN_ROOT)
    if forbidden in value:
        occurrences = value.count(forbidden)
        value = value.replace(forbidden, "<FORBIDDEN_LEGACY_ROOT>")
        count += occurrences
    for pattern, replacement in _REDACTIONS:
        value, replacements = pattern.subn(replacement, value)
        count += replacements
    return value, count


def _redact(value: Any):
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        output = {}
        count = 0
        for key, item in value.items():
            redacted, nested_count = _redact(item)
            output[str(key)] = redacted
            count += nested_count
        return output, count
    if isinstance(value, (list, tuple)):
        output = []
        count = 0
        for item in value:
            redacted, nested_count = _redact(item)
            output.append(redacted)
            count += nested_count
        return output, count
    return value, 0


def _message_blocks(record):
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    blocks = message.get("content", [])
    if isinstance(blocks, str):
        return [{"type": "text", "text": blocks}]
    return blocks if isinstance(blocks, list) else []


def _is_user_prompt(record):
    return record.get("type") == "user" and any(
        isinstance(block, dict) and block.get("type") == "text"
        for block in _message_blocks(record)
    )


def _event(event_type, data, *, session_id, turn_id, record_meta, offset, timestamp):
    source_ref = {
        "source_snapshot_id": record_meta["source_snapshot_id"],
        "record_id": record_meta["record_id"],
        "record_index": record_meta["record_index"],
        "line_number": record_meta["line_number"],
        "adapter": ADAPTER_NAME,
        "adapter_version": ADAPTER_VERSION,
        "native_uuid": record_meta.get("native_uuid"),
        "parent_record_id": record_meta.get("parent_record_id"),
    }
    return {
        "schema_version": "event-v1",
        "event_id": stable_id(
            "evt",
            record_meta["source_snapshot_id"],
            record_meta["record_id"],
            offset,
            event_type,
        ),
        "session_id": session_id,
        "turn_id": turn_id,
        "sequence": record_meta["record_index"] * 100 + offset,
        "timestamp": timestamp,
        "type": event_type,
        "data": data,
        "links": {},
        "source_ref": source_ref,
    }


def _read_records(path_policy, path, snapshot_id):
    records = []
    parse_errors = []
    physical_lines = 0
    byte_offset = 0
    with path_policy.open_binary(path) as source:
        for index, raw_line in enumerate(source):
            physical_lines += 1
            current_offset = byte_offset
            byte_offset += len(raw_line)
            if not raw_line.strip():
                continue
            try:
                line = raw_line.decode("utf-8-sig" if index == 0 else "utf-8")
            except UnicodeDecodeError as error:
                parse_errors.append(
                    {
                        "line_number": index + 1,
                        "byte_offset": current_offset,
                        "error_type": "UnicodeDecodeError",
                        "error": str(error),
                    }
                )
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise TypeError("record must be a JSON object")
            except (json.JSONDecodeError, TypeError) as error:
                parse_errors.append(
                    {
                        "line_number": index + 1,
                        "byte_offset": current_offset,
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
                continue
            records.append(
                {
                    "record_index": index,
                    "line_number": index + 1,
                    "byte_offset": current_offset,
                    "raw_sha256": digest_bytes(raw_line),
                    "raw": record,
                    "source_snapshot_id": snapshot_id,
                }
            )
    return records, parse_errors, physical_lines


def _assign_record_identity(records, session_id, snapshot_id):
    uuid_to_record_id = {}
    duplicate_uuids = []
    for item in records:
        record = item["raw"]
        native_uuid = record.get("uuid")
        record_id = stable_id(
            "record", snapshot_id, item["line_number"], native_uuid, item["raw_sha256"]
        )
        item["record_id"] = record_id
        item["native_uuid"] = native_uuid
        if native_uuid:
            if native_uuid in uuid_to_record_id:
                duplicate_uuids.append(native_uuid)
            else:
                uuid_to_record_id[native_uuid] = record_id
    by_id = {item["record_id"]: item for item in records}
    for item in records:
        parent_native_uuid = item["raw"].get("parentUuid")
        item["parent_native_uuid"] = parent_native_uuid
        item["parent_record_id"] = uuid_to_record_id.get(parent_native_uuid)
    prompt_turn_by_record = {}
    prompt_turn_by_prompt_id = {}
    for item in records:
        record = item["raw"]
        if _is_user_prompt(record):
            native_turn = record.get("promptId") or record.get("uuid") or f"line-{item['line_number']}"
            turn_id = stable_id("turn", snapshot_id, native_turn)
            prompt_turn_by_record[item["record_id"]] = turn_id
            if record.get("promptId"):
                prompt_turn_by_prompt_id[record["promptId"]] = turn_id
    cache = {}

    def resolve(item):
        record_id = item["record_id"]
        if record_id in cache:
            return cache[record_id]
        if record_id in prompt_turn_by_record:
            cache[record_id] = prompt_turn_by_record[record_id]
            return cache[record_id]
        prompt_id = item["raw"].get("promptId")
        if prompt_id in prompt_turn_by_prompt_id:
            cache[record_id] = prompt_turn_by_prompt_id[prompt_id]
            return cache[record_id]
        seen = {record_id}
        parent_id = item.get("parent_record_id")
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            if parent_id in prompt_turn_by_record:
                cache[record_id] = prompt_turn_by_record[parent_id]
                return cache[record_id]
            parent = by_id.get(parent_id)
            if parent is None:
                break
            parent_prompt = parent["raw"].get("promptId")
            if parent_prompt in prompt_turn_by_prompt_id:
                cache[record_id] = prompt_turn_by_prompt_id[parent_prompt]
                return cache[record_id]
            parent_id = parent.get("parent_record_id")
        cache[record_id] = None
        return None

    for item in records:
        item["resolved_turn_id"] = resolve(item)
    return duplicate_uuids


def _record_artifact(item, session_id):
    redacted, redaction_count = _redact(item["raw"])
    return {
        "record_id": item["record_id"],
        "session_id": session_id,
        "record_type": str(item["raw"].get("type") or "unknown"),
        "native_uuid": item.get("native_uuid"),
        "parent_native_uuid": item.get("parent_native_uuid"),
        "parent_record_id": item.get("parent_record_id"),
        "turn_id": item.get("resolved_turn_id"),
        "line_number": item["line_number"],
        "byte_offset": item["byte_offset"],
        "timestamp": item["raw"].get("timestamp"),
        "raw_sha256": item["raw_sha256"],
        "redaction_count": redaction_count,
        "payload": redacted,
    }


def _events_for_record(item, session_id):
    record = item["raw"]
    record_type = str(record.get("type") or "unknown")
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    blocks = _message_blocks(record)
    turn_id = item.get("resolved_turn_id")
    timestamp = record.get("timestamp")
    meta = item
    events = []

    def emit(event_type, data, offset, assigned_turn=turn_id):
        redacted, _ = _redact(data)
        events.append(
            _event(
                event_type,
                redacted,
                session_id=session_id,
                turn_id=assigned_turn,
                record_meta=meta,
                offset=offset,
                timestamp=timestamp,
            )
        )

    if record_type == "user":
        for offset, block in enumerate(blocks, 1):
            if not isinstance(block, dict):
                emit("unknown", {"content": block, "harness": "claude_code"}, offset)
            elif block.get("type") == "text":
                emit(
                    "user_message",
                    {
                        "content": block.get("text", ""),
                        "harness": "claude_code",
                        "is_meta": bool(record.get("isMeta")),
                        "is_compact_summary": bool(record.get("isCompactSummary")),
                    },
                    offset,
                )
            elif block.get("type") == "tool_result":
                emit(
                    "tool_result",
                    {
                        "call_id": block.get("tool_use_id"),
                        "content": block.get("content"),
                        "is_error": block.get("is_error"),
                        "tool_use_result": record.get("toolUseResult"),
                        "source_tool_assistant_uuid": record.get("sourceToolAssistantUUID"),
                        "harness": "claude_code",
                    },
                    offset,
                )
            else:
                emit("unknown", {"content_block": block, "harness": "claude_code"}, offset)
    elif record_type == "assistant":
        model = message.get("model")
        provider = message.get("provider")
        emit(
            "model_call",
            {
                "request_id": message.get("id"),
                "model": model,
                "provider": provider,
                "harness": "claude_code",
            },
            1,
        )
        for offset, block in enumerate(blocks, 2):
            if not isinstance(block, dict):
                emit(
                    "unknown",
                    {"content": block, "model": model, "provider": provider, "harness": "claude_code"},
                    offset,
                )
                continue
            kind = block.get("type")
            if kind == "thinking":
                emit(
                    "reasoning",
                    {"content": block.get("thinking", ""), "model": model, "provider": provider, "harness": "claude_code"},
                    offset,
                )
            elif kind == "redacted_thinking":
                emit(
                    "reasoning",
                    {"content": "<REDACTED_THINKING>", "redacted": True, "model": model, "provider": provider, "harness": "claude_code"},
                    offset,
                )
            elif kind == "text":
                emit(
                    "assistant_message",
                    {"content": block.get("text", ""), "model": model, "provider": provider, "harness": "claude_code"},
                    offset,
                )
            elif kind == "tool_use":
                emit(
                    "tool_call",
                    {"call_id": block.get("id"), "tool_name": block.get("name"), "arguments": block.get("input"), "model": model, "provider": provider, "harness": "claude_code"},
                    offset,
                )
            else:
                emit(
                    "unknown",
                    {"content_block": block, "model": model, "provider": provider, "harness": "claude_code"},
                    offset,
                )
        usage = message.get("usage")
        next_offset = len(blocks) + 2
        if isinstance(usage, dict):
            emit(
                "token_usage",
                {**usage, "model": model, "provider": provider, "harness": "claude_code"},
                next_offset,
            )
            next_offset += 1
        if record.get("isApiErrorMessage") or record.get("error"):
            emit(
                "error",
                {
                    "error": record.get("error") or message.get("error") or "API error",
                    "status_code": record.get("apiErrorStatus"),
                    "model": model,
                    "provider": provider,
                    "harness": "claude_code",
                },
                next_offset,
            )
            next_offset += 1
        emit(
            "model_result",
            {
                "request_id": message.get("id"),
                "model": model,
                "provider": provider,
                "stop_reason": message.get("stop_reason"),
                "stop_sequence": message.get("stop_sequence"),
                "harness": "claude_code",
            },
            next_offset,
        )
    elif record_type == "attachment":
        emit(
            "attachment",
            {
                "attachment": record.get("attachment"),
                "is_sidechain": record.get("isSidechain"),
                "harness": "claude_code",
            },
            1,
        )
    else:
        metadata = {
            key: value
            for key, value in record.items()
            if key not in {"message", "attachment", "cwd", "gitBranch"}
        }
        metadata.update({"kind": record_type, "harness": "claude_code"})
        assigned_turn = turn_id if record_type in {"progress", "system"} else None
        emit("system_event", metadata, 1, assigned_turn=assigned_turn)
    return events


def _link_tools(events):
    calls_by_id = {}
    unmatched_results = []
    for event in events:
        call_id = event.get("data", {}).get("call_id")
        if event["type"] == "tool_call" and call_id:
            calls_by_id.setdefault(call_id, []).append(event)
            event["links"]["result_event_ids"] = []
        elif event["type"] == "tool_result" and call_id:
            candidates = calls_by_id.get(call_id, [])
            call = next(
                (
                    candidate
                    for candidate in reversed(candidates)
                    if not candidate["links"].get("result_event_ids")
                ),
                candidates[-1] if candidates else None,
            )
            if call:
                event["links"]["call_event_id"] = call["event_id"]
                call["links"].setdefault("result_event_ids", []).append(event["event_id"])
            else:
                unmatched_results.append(event["event_id"])
    unmatched_calls = [
        event["event_id"]
        for event in events
        if event["type"] == "tool_call" and not event["links"].get("result_event_ids")
    ]
    return unmatched_calls, unmatched_results


def _build_turns(records, events):
    turn_ids = []
    for item in records:
        turn_id = item.get("resolved_turn_id")
        if turn_id and turn_id not in turn_ids:
            turn_ids.append(turn_id)
    turns = []
    for turn_id in turn_ids:
        turn_events = [event for event in events if event.get("turn_id") == turn_id]
        turn_records = [item for item in records if item.get("resolved_turn_id") == turn_id]
        has_error = any(event["type"] == "error" for event in turn_events)
        completed = any(
            event["type"] == "model_result"
            and event.get("data", {}).get("stop_reason") in {"end_turn", "stop_sequence"}
            for event in turn_events
        )
        status = "error" if has_error else "completed" if completed else "incomplete"
        root = next((item for item in turn_records if _is_user_prompt(item["raw"])), None)
        turns.append(
            {
                "turn_id": turn_id,
                "native_prompt_id": root["raw"].get("promptId") if root else None,
                "root_record_id": root["record_id"] if root else None,
                "status": status,
                "record_ids": [item["record_id"] for item in turn_records],
                "event_ids": [event["event_id"] for event in turn_events],
            }
        )
    return turns


def normalize_session(path_policy, locator):
    path = path_policy.validate_for_read(locator)
    hasher = hashlib.sha256()
    size_bytes = 0
    with path_policy.open_binary(path) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
            size_bytes += len(chunk)
    source_hash = hasher.hexdigest()
    snapshot_id = stable_id("src", source_hash)
    parsed, parse_errors, physical_lines = _read_records(path_policy, path, snapshot_id)
    session_ids = {
        str(item["raw"].get("sessionId"))
        for item in parsed
        if item["raw"].get("sessionId")
    }
    if len(session_ids) > 1:
        raise IngestionError(
            f"one session file contains multiple session IDs: {sorted(session_ids)}"
        )
    session_id = next(iter(session_ids), stable_id("session", source_hash))
    duplicate_uuids = _assign_record_identity(parsed, session_id, snapshot_id)
    record_artifacts = [_record_artifact(item, session_id) for item in parsed]
    events = []
    for item in parsed:
        events.extend(_events_for_record(item, session_id))
    events.sort(key=lambda event: (event["sequence"], event["event_id"]))
    unmatched_calls, unmatched_results = _link_tools(events)
    turns = _build_turns(parsed, events)
    record_types = Counter(str(item["raw"].get("type") or "unknown") for item in parsed)
    block_types = Counter()
    for item in parsed:
        for block in _message_blocks(item["raw"]):
            block_types[str(block.get("type") if isinstance(block, dict) else "non_object")] += 1
    event_types = Counter(event["type"] for event in events)
    orphan_attachments = [
        item["record_id"]
        for item in parsed
        if item["raw"].get("type") == "attachment" and not item.get("resolved_turn_id")
    ]
    substantive_types = {
        "user_message",
        "assistant_message",
        "reasoning",
        "tool_call",
        "tool_result",
        "attachment",
        "error",
    }
    turnless_substantive = [
        event["event_id"]
        for event in events
        if event["type"] in substantive_types and not event.get("turn_id")
    ]
    warnings = []
    if duplicate_uuids:
        warnings.append(f"duplicate native UUIDs: {len(duplicate_uuids)}")
    if parse_errors:
        warnings.append(f"parse errors: {len(parse_errors)}")
    if orphan_attachments:
        warnings.append(f"orphan attachments: {len(orphan_attachments)}")
    if unmatched_results:
        warnings.append(f"unmatched tool results: {len(unmatched_results)}")
    if unmatched_calls:
        warnings.append(f"unmatched tool calls: {len(unmatched_calls)}")
    if turnless_substantive:
        warnings.append(f"turnless substantive events: {len(turnless_substantive)}")
    result = {
        "schema_version": "normalized-session-v1",
        "session_id": session_id,
        "source_snapshot": {
            "source_snapshot_id": snapshot_id,
            "sha256": source_hash,
            "size_bytes": size_bytes,
            "record_count": physical_lines,
            "parsed_record_count": len(parsed),
            "parse_errors": parse_errors,
            "adapter": ADAPTER_NAME,
            "adapter_version": ADAPTER_VERSION,
        },
        "records": record_artifacts,
        "turn_ids": [turn["turn_id"] for turn in turns],
        "turns": turns,
        "events": events,
        "ingestion_report": {
            "record_types_seen": dict(sorted(record_types.items())),
            "record_types_preserved": dict(sorted(record_types.items())),
            "block_types_seen": dict(sorted(block_types.items())),
            "event_types_emitted": dict(sorted(event_types.items())),
            "unknown_event_count": event_types.get("unknown", 0),
            "orphan_attachment_record_ids": orphan_attachments,
            "unmatched_tool_call_event_ids": unmatched_calls,
            "unmatched_tool_result_event_ids": unmatched_results,
            "turnless_substantive_event_ids": turnless_substantive,
            "redaction_count": sum(record["redaction_count"] for record in record_artifacts),
            "warnings": warnings,
        },
    }
    return validate_artifact(result, "normalized_session.schema.json")
