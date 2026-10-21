import json
import tempfile
import unittest
from pathlib import Path
from session_labeling.audit import audit_run, audit_tree
from session_labeling.path_policy import PathPolicy
from session_labeling.pipeline import run_pipeline


class TestAudit(unittest.TestCase):
    def test_clean_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "a.py").write_text("print('ok')")
            self.assertTrue(audit_tree(directory)["valid"])

    def test_runtime_import_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "a.py").write_text("import trace_analysis.pipeline")
            report = audit_tree(directory)
            self.assertFalse(report["valid"])
            self.assertEqual(report["forbidden_runtime_imports"], ["a.py"])

    def test_auditor_does_not_flag_detection_logic(self):
        report = audit_tree(Path(__file__).parents[1])
        self.assertEqual(report["forbidden_runtime_imports"], [])

    def test_cache_binary_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory, "__pycache__")
            cache.mkdir()
            (cache / "x.pyc").write_bytes(b"trace_analysis")
            self.assertTrue(audit_tree(directory)["valid"])

    def test_run_audit_and_artifact_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "session.jsonl"
            source.write_text(json.dumps({"type":"user","sessionId":"s","uuid":"u","message":{"content":[{"type":"text","text":"x"}]}})+"\n")
            policy = PathPolicy([root], new_root=root)
            run_pipeline(policy, source, root / "run", client=None)
            report = audit_run(policy, root / "run")
            self.assertTrue(report["valid"], report["issues"])
            labels = root / "run" / "final_labels.json"
            labels.write_text(labels.read_text() + " ")
            report = audit_run(policy, root / "run")
            self.assertFalse(report["valid"])
            self.assertTrue(any("hash/size mismatch" in issue for issue in report["issues"]))
