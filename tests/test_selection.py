import unittest
from session_labeling.selection import evaluate
class TestSelection(unittest.TestCase):
 def base(self): return {"assessment_id":"a","evidence":[{"evidence_id":"e1","source_snapshot_id":"src","event_id":"ev","quote":"exact evidence","content_digest":"digest"}],"capability_mappings":[{"mapping_id":"m","role":"primary","status":"supported","evidence_refs":["e1"]}],"task_attributes":{"difficulty":"high","difficulty_evidence_refs":["e1"]},"semantic_rule_reviews":[{"rule_id":"S3","status":"pass","reason":"coherent","evidence_refs":["e1"]},{"rule_id":"S4","status":"pass","reason":"checkable","evidence_refs":["e1"]}]}
 def test_all_pass_selected(self): self.assertEqual(evaluate(self.base())["decision"],"selected")
 def test_unknown_semantics_pending(self):
  x=self.base(); x["semantic_rule_reviews"]=[]
  self.assertEqual(evaluate(x)["decision"],"pending_review")
 def test_low_fails(self):
  x=self.base(); x["task_attributes"]["difficulty"]="low"
  self.assertEqual(evaluate(x)["decision"],"not_selected")
 def test_missing_reference_invalid(self):
  x=self.base(); x["capability_mappings"][0]["evidence_refs"]=["missing"]
  self.assertEqual(evaluate(x)["decision"],"invalid")
 def test_auxiliary_only_never_passes_s1(self):
  x=self.base(); x["capability_mappings"][0]["role"]="auxiliary"
  out=evaluate(x)
  self.assertEqual(out["rules"][0]["status"],"pending")
  self.assertEqual(out["decision"],"pending_review")
