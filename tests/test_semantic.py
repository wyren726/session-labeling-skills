import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from session_labeling.path_policy import PathPolicy
from session_labeling.ingest import normalize_session
from session_labeling.semantic import (
    build_canonical_analysis,
    build_canonical_episode,
    run_semantic,
    understand,
    taxonomy_role_index,
)
from session_labeling.selection import evaluate


class Fake:
    def __init__(self, taxonomy_row=2):
        self.i = 0
        self.taxonomy_row = taxonomy_row
        self.label_payload = None

    def complete_json_schema(self, system, user, **kwargs):
        self.i += 1
        payload = json.loads(user)
        if self.i == 1:
            turn = payload["turns"][0]
            return {
                "episodes": [
                    {
                        "start_turn_id": turn["turn_id"],
                        "end_turn_id": turn["turn_id"],
                        "goal": "change x",
                        "requirements": [
                            {
                                "requirement_id": "r1",
                                "text": "change x",
                                "origin_event_ids": [turn["events"][0]["event_id"]],
                                "is_core": True,
                            }
                        ],
                        "boundary_confidence": 1.0,
                        "limitations": [],
                    }
                ]
            }, {"fake": True}
        if self.i == 2:
            event = payload["events"][0]
            return {
                "evidence": [
                    {
                        "evidence_id": "e1",
                        "event_id": event["event_id"],
                        "quote": "change x",
                        "purpose": "requirement",
                    }
                ],
                "agent_claimed_status": "no_claim",
                "verified_outcome": "unknown",
                "requirement_results": [
                    {
                        "requirement_id": "r1",
                        "status": "unknown",
                        "evidence_refs": ["e1"],
                        "reason": "no result",
                    }
                ],
                "limitations": [],
            }, {"fake": True}
        self.label_payload = payload
        return {
            "difficulty": "medium",
            "difficulty_evidence_refs": ["e1"],
            "capability_mappings": [
                {
                    "mapping_id": "m1",
                    "requirement_id": "r1",
                    "taxonomy_row": self.taxonomy_row,
                    "status": "supported",
                    "evidence_refs": ["e1"],
                    "reason": "matches",
                }
            ],
            "claims": [
                {
                    "claim_id": "c1",
                    "field_path": "goal",
                    "support_status": "supported",
                    "evidence_refs": ["e1"],
                    "reason": "quoted",
                }
            ],
            "S3": {"status": "pass", "reason": "coherent", "evidence_refs": ["e1"]},
            "S4": {"status": "pass", "reason": "checkable", "evidence_refs": ["e1"]},
            "limitations": [],
        }, {"fake": True}


class TestSemantic(unittest.TestCase):
    def make_session(self, directory):
        row = {
            "type": "user",
            "sessionId": "s",
            "uuid": "u",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "please change x"}],
            },
        }
        path = Path(directory) / "session.jsonl"
        path.write_text(json.dumps(row) + "\n")
        return normalize_session(PathPolicy([directory], new_root=directory), path)

    def test_end_to_end_fake_writes_canonical_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(directory)
            client = Fake()
            output = run_semantic(session, client)
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0]["episode"]["schema_version"], "episode-v1")
            self.assertEqual(output[0]["analysis"]["schema_version"], "analysis-v1")
            self.assertEqual(evaluate(output[0]["labels"])["decision"], "selected")
            self.assertEqual(len(client.label_payload["taxonomy_registry"]), 216)
            self.assertNotIn("taxonomy_candidates", client.label_payload)

    def test_canonical_builders_add_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(directory)
            turn = session["turns"][0]
            episode = build_canonical_episode(
                session,
                {
                    "start_turn_id": turn["turn_id"],
                    "end_turn_id": turn["turn_id"],
                    "goal": "change x",
                    "requirements": [
                        {
                            "requirement_id": "r1",
                            "text": "change x",
                            "origin_event_ids": [turn["event_ids"][0]],
                            "is_core": True,
                        }
                    ],
                    "boundary_confidence": 0.9,
                    "limitations": [],
                },
            )
            analysis = build_canonical_analysis(
                session,
                episode,
                {
                    "evidence": [],
                    "agent_claimed_status": "unknown",
                    "verified_outcome": "unknown",
                    "requirement_results": [],
                    "limitations": [],
                },
            )
            self.assertEqual(episode["source_snapshot_id"], session["source_snapshot"]["source_snapshot_id"])
            self.assertEqual(analysis["episode_id"], episode["episode_id"])
            self.assertEqual(analysis["provenance"]["producer_skill"], "session-evidence-analysis")

    def test_roles_are_registry_derived(self):
        roles = taxonomy_role_index()
        self.assertEqual(roles[2], "primary")
        self.assertEqual(roles[212], "auxiliary")

    def test_auxiliary_mapping_cannot_satisfy_s1(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(directory)
            output = run_semantic(session, Fake(taxonomy_row=212))[0]
            self.assertEqual(output["labels"]["capability_mappings"][0]["role"], "auxiliary")
            decision = evaluate(output["labels"])
            self.assertEqual(decision["rules"][0]["status"], "pending")
            self.assertEqual(decision["decision"], "pending_review")


class BoundaryReconcileFake:
    def __init__(self):
        self.discovery_calls = 0
        self.reconcile_calls = 0

    def complete_json_schema(self, system, user, **kwargs):
        payload = json.loads(user)
        if payload.get("mode") == "reconcile_boundary_candidates":
            self.reconcile_calls += 1
            turns = payload["turns"]
            first = turns[0]
            last = turns[-1]
            return {
                "episodes": [{
                    "start_turn_id": first["turn_id"],
                    "end_turn_id": last["turn_id"],
                    "goal": "one task across windows",
                    "requirements": [{
                        "requirement_id": "r1",
                        "text": "one task across windows",
                        "origin_event_ids": [first["events"][0]["event_id"], last["events"][0]["event_id"]],
                        "is_core": True,
                    }],
                    "boundary_confidence": 0.95,
                    "limitations": [],
                }]
            }, {"phase": "reconcile"}
        self.discovery_calls += 1
        turn = payload["turns"][0]
        return {
            "episodes": [{
                "start_turn_id": turn["turn_id"],
                "end_turn_id": turn["turn_id"],
                "goal": "one task across windows",
                "requirements": [{
                    "requirement_id": "r1",
                    "text": "one task across windows",
                    "origin_event_ids": [turn["events"][0]["event_id"]],
                    "is_core": True,
                }],
                "boundary_confidence": 0.7,
                "limitations": [],
            }]
        }, {"phase": "discover"}


class TestEpisodeReconciliation(unittest.TestCase):
    def test_cross_window_candidates_receive_targeted_followup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            rows = [
                {
                    "type": "user",
                    "sessionId": "s",
                    "uuid": f"u{i}",
                    "message": {"role": "user", "content": [{"type": "text", "text": f"part {i}"}]},
                }
                for i in range(3)
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            session = normalize_session(PathPolicy([directory], new_root=directory), path)
            client = BoundaryReconcileFake()
            with patch("session_labeling.semantic.UNDERSTANDING_WINDOW_MAX_CHARS", 1):
                episodes, metadata = understand(session, client)
            self.assertEqual(client.discovery_calls, 3)
            self.assertEqual(client.reconcile_calls, 1)
            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0]["boundary"]["turn_ids"], [turn["turn_id"] for turn in session["turns"]])
            self.assertEqual(episodes[0]["boundary"]["reconciliation"]["status"], "model_reconciled")
            self.assertEqual(len(episodes[0]["boundary"]["candidate_windows"]), 3)
            self.assertTrue(any(item["phase"] == "boundary_reconciliation" for item in metadata))
