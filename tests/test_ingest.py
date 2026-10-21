import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from session_labeling.path_policy import PathPolicy
from session_labeling.ingest import IngestionError, normalize_session


class TestIngest(unittest.TestCase):
    def write_rows(self, directory, rows):
        path = Path(directory) / "session.jsonl"
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
        path.write_bytes(payload)
        return path, payload

    def test_claude_code_blocks_and_tool_links(self):
        rows = [
            {"type":"user","sessionId":"s","uuid":"u","message":{"role":"user","content":[{"type":"text","text":"do x"}]}},
            {"type":"assistant","sessionId":"s","uuid":"a","parentUuid":"u","message":{"role":"assistant","model":"m","provider":"p","content":[{"type":"tool_use","id":"c","name":"Read","input":{"file":"x"}},{"type":"text","text":"done"}],"stop_reason":"end_turn"}},
            {"type":"user","sessionId":"s","uuid":"r","parentUuid":"a","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"c","content":"ok"}]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.write_rows(directory, rows)
            output = normalize_session(PathPolicy([directory], new_root=directory), path)
            self.assertEqual(output["session_id"], "s")
            self.assertEqual([event["type"] for event in output["events"]], ["user_message","model_call","tool_call","assistant_message","model_result","tool_result"])
            self.assertEqual(output["source_snapshot"]["parse_errors"], [])
            self.assertEqual(len(output["turns"]), 1)
            self.assertEqual(output["turns"][0]["status"], "completed")
            self.assertEqual(len(output["turns"][0]["event_ids"]), 6)
            call = next(event for event in output["events"] if event["type"] == "tool_call")
            result = next(event for event in output["events"] if event["type"] == "tool_result")
            self.assertEqual(result["links"]["call_event_id"], call["event_id"])
            self.assertEqual(call["links"]["result_event_ids"], [result["event_id"]])
            self.assertEqual(call["data"]["provider"], "p")

    def test_attachment_chain_resolves_to_originating_user_turn(self):
        rows = [
            {"type":"user","sessionId":"s","uuid":"u","promptId":"p","message":{"content":[{"type":"text","text":"analyze file"}]}},
            {"type":"attachment","sessionId":"s","uuid":"at1","parentUuid":"u","attachment":{"type":"file","filename":"a.txt"}},
            {"type":"attachment","sessionId":"s","uuid":"at2","parentUuid":"at1","attachment":{"type":"text","content":"context"}},
            {"type":"assistant","sessionId":"s","uuid":"a","parentUuid":"at2","message":{"model":"m","content":[{"type":"text","text":"ok"}],"stop_reason":"end_turn"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.write_rows(directory, rows)
            output = normalize_session(PathPolicy([directory], new_root=directory), path)
            turn_id = output["turns"][0]["turn_id"]
            attachments = [event for event in output["events"] if event["type"] == "attachment"]
            self.assertEqual(len(attachments), 2)
            self.assertTrue(all(event["turn_id"] == turn_id for event in attachments))
            self.assertEqual(output["ingestion_report"]["orphan_attachment_record_ids"], [])
            self.assertEqual(output["ingestion_report"]["turnless_substantive_event_ids"], [])

    def test_raw_byte_hash_redaction_usage_and_error(self):
        rows = [
            {"type":"user","sessionId":"s","uuid":"u","cwd":"/home/alice/private","message":{"content":[{"type":"text","text":"email a@example.com and key sk-abcdefghijklmnop"}]}},
            {"type":"assistant","sessionId":"s","uuid":"a","parentUuid":"u","isApiErrorMessage":True,"message":{"model":"m","provider":"p","usage":{"input_tokens":3,"output_tokens":4},"content":[],"stop_reason":"end_turn"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.write_rows(directory, rows)
            output = normalize_session(PathPolicy([directory], new_root=directory), path)
            self.assertEqual(output["source_snapshot"]["sha256"], hashlib.sha256(payload).hexdigest())
            serialized = json.dumps(output, ensure_ascii=False)
            self.assertNotIn("a@example.com", serialized)
            self.assertNotIn("sk-abcdefghijklmnop", serialized)
            self.assertNotIn("/home/alice/private", serialized)
            self.assertGreaterEqual(output["ingestion_report"]["redaction_count"], 3)
            self.assertIn("token_usage", [event["type"] for event in output["events"]])
            self.assertIn("error", [event["type"] for event in output["events"]])
            self.assertEqual(output["turns"][0]["status"], "error")

    def test_conflicting_session_ids_fail_explicitly(self):
        rows = [
            {"type":"user","sessionId":"s1","uuid":"u1","message":{"content":[{"type":"text","text":"x"}]}},
            {"type":"user","sessionId":"s2","uuid":"u2","message":{"content":[{"type":"text","text":"y"}]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.write_rows(directory, rows)
            with self.assertRaises(IngestionError):
                normalize_session(PathPolicy([directory], new_root=directory), path)
