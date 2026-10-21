import unittest
from session_labeling.legacy import stage06_to_canonical
from session_labeling.selection import evaluate
class TestLegacyAdapter(unittest.TestCase):
 def test_supported_mapping_and_frozen_rules_reproduce_selected(self):
  label={"case_id":"c","schema_version":"old","evidence_refs":[{"evidence_id":"e","event_id":"v","quote":"q"}],"claims":[{"claim_id":"cl","support_status":"supported","evidence_ids":["e"]}],"capability_mapping":[{"mapping_id":"m","mapping_status":"supported","parent_requirement_id":"p","claim_ids":["cl"]}],"task_attributes":{"difficulty":"medium"}}
  sel={"assessment_id":"a","decision":"priority_candidate","primary_requirement_ids":["p"],"prechecks":{"scope_match":"pass","no_selection_critical_unresolved_conflict":"pass"},"rule_checks":{"S2":{"status":"pass","evidence_ids":["e"]},"S3":{"status":"pass","evidence_ids":["e"]},"S4":{"status":"pass","evidence_ids":["e"]}},"evaluation":{"reviewer_type":"program"}}
  out=evaluate(stage06_to_canonical(label,sel)); self.assertEqual(out["decision"],"selected")
