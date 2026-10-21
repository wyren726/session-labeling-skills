from pathlib import Path
import unittest
import yaml


class TestLegacyRuntimeDisposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "docs/design/legacy-to-canonical-label-map.yaml"
        cls.document = yaml.safe_load(path.read_text(encoding="utf-8"))
        cls.mappings = cls.document["mappings"]

    def test_all_legacy_mappings_have_runtime_disposition(self):
        self.assertEqual(len(self.mappings), 51)
        allowed = {"implemented", "derived", "historical_only", "explicitly_deferred"}
        for mapping in self.mappings:
            with self.subTest(legacy=mapping["legacy"]):
                implementation = mapping.get("implementation")
                self.assertIsInstance(implementation, dict)
                self.assertIn(implementation.get("status"), allowed)
                self.assertTrue(implementation.get("rationale"))
                if implementation["status"] in {"implemented", "derived"}:
                    self.assertTrue(implementation.get("artifact"))
                    self.assertTrue(implementation.get("field_path"))
                    self.assertTrue(implementation.get("verification"))
                if implementation["status"] == "explicitly_deferred":
                    self.assertNotIn("artifact", implementation)
                    self.assertNotIn("field_path", implementation)
                if implementation["status"] == "historical_only":
                    self.assertIsNot(mapping.get("used_for_selection"), True)

    def test_selector_inputs_are_never_silently_deferred(self):
        for mapping in self.mappings:
            if mapping.get("used_for_selection") is True:
                implementation = mapping["implementation"]
                with self.subTest(legacy=mapping["legacy"]):
                    self.assertIn(
                        implementation["status"],
                        {"implemented", "derived", "explicitly_deferred"},
                    )
                    if implementation["status"] == "explicitly_deferred":
                        self.assertGreaterEqual(len(implementation["rationale"]), 40)

    def test_historical_only_fields_do_not_name_selector_artifacts(self):
        for mapping in self.mappings:
            implementation = mapping["implementation"]
            if implementation["status"] == "historical_only":
                with self.subTest(legacy=mapping["legacy"]):
                    self.assertNotIn("selection_decision", implementation.get("artifact", ""))
