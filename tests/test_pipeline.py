import json,tempfile,unittest
from pathlib import Path
from session_labeling.path_policy import PathPolicy
from session_labeling.pipeline import run_pipeline
class Fake:
 def __init__(self): self.i=0; self.model="fake-model"; self.config=type("C",(),{"name":"fake"})()
 def complete_json_schema(self,system,user,**kw):
  self.i+=1; p=json.loads(user)
  if self.i==1:
   t=p["turns"][0]; return {"episodes":[{"start_turn_id":t["turn_id"],"end_turn_id":t["turn_id"],"goal":"change x","requirements":[{"requirement_id":"r1","text":"change x","origin_event_ids":[t["events"][0]["event_id"]],"is_core":True}],"boundary_confidence":1.0,"limitations":[]}]},{"fake":1}
  if self.i==2:
   e=p["events"][0]; return {"evidence":[{"evidence_id":"e1","event_id":e["event_id"],"quote":"change x","purpose":"requirement"}],"agent_claimed_status":"no_claim","verified_outcome":"unknown","requirement_results":[{"requirement_id":"r1","status":"unknown","evidence_refs":["e1"],"reason":"none"}],"limitations":[]},{"fake":2}
  return {"difficulty":"medium","difficulty_evidence_refs":["e1"],"capability_mappings":[{"mapping_id":"m","requirement_id":"r1","taxonomy_row":2,"status":"supported","evidence_refs":["e1"],"reason":"match"}],"claims":[{"claim_id":"c","field_path":"goal","support_status":"supported","evidence_refs":["e1"],"reason":"quote"}],"S3":{"status":"pass","reason":"coherent","evidence_refs":["e1"]},"S4":{"status":"pass","reason":"checkable","evidence_refs":["e1"]},"limitations":[]},{"fake":3}
class TestPipeline(unittest.TestCase):
 def test_selected_export_and_resume(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); src=root/"session.jsonl"; src.write_text(json.dumps({"type":"user","sessionId":"s","uuid":"u","message":{"role":"user","content":[{"type":"text","text":"please change x"}]}})+"\n")
   pol=PathPolicy([root],new_root=root,forbidden_root=Path("/legacy-root")); client=Fake(); a=run_pipeline(pol,"/legacy-root/session.jsonl",root/"run",client=client)
   self.assertEqual(a["decision_summary"]["selected"],1); self.assertEqual((root/"run/export/session.jsonl").read_bytes(),src.read_bytes())
   self.assertEqual(a["input"]["locator"],str(src)); self.assertNotIn("/legacy-root",json.dumps(a)); self.assertTrue(all(set(x)=={"path","sha256","size_bytes","kind"} for x in a["artifacts"])); self.assertTrue((root/"run/checkpoints/semantic_checkpoint.json").exists()); self.assertTrue(any((root/"run"/x["path"]).name=="assessment_checkpoint.json" for x in a["artifacts"]))
   calls=client.i; b=run_pipeline(pol,"/legacy-root/session.jsonl",root/"run",client=client); self.assertEqual(a["run_id"],b["run_id"]); self.assertEqual(client.i,calls)


class TwoEpisodeInterruptingFake:
 def __init__(self): self.i=0; self.model="fake-model"; self.config=type("C",(),{"name":"fake"})(); self.fail_once=True
 def complete_json_schema(self,system,user,**kw):
  self.i+=1; p=json.loads(user)
  if self.i==1:
   out=[]
   for t in p["turns"]:
    if not t["events"]: continue
    event=t["events"][0]
    out.append({"start_turn_id":t["turn_id"],"end_turn_id":t["turn_id"],"goal":"change x","requirements":[{"requirement_id":"r1","text":"change x","origin_event_ids":[event["event_id"]],"is_core":True}],"boundary_confidence":1.0,"limitations":[]})
   return {"episodes":out},{"fake":1}
  if self.i==4 and self.fail_once:
   self.fail_once=False
   raise RuntimeError("injected interruption")
  if kw.get("name") == "model_evidence":
   event=p["events"][0]
   return {"evidence":[{"evidence_id":"e1","event_id":event["event_id"],"quote":"please change x","purpose":"requirement"}],"agent_claimed_status":"no_claim","verified_outcome":"unknown","requirement_results":[{"requirement_id":"r1","status":"unknown","evidence_refs":["e1"],"reason":"none"}],"limitations":[]},{"fake":self.i}
  return {"difficulty":"medium","difficulty_evidence_refs":["e1"],"capability_mappings":[{"mapping_id":"m","requirement_id":"r1","taxonomy_row":2,"status":"supported","evidence_refs":["e1"],"reason":"match"}],"claims":[{"claim_id":"c","field_path":"goal","support_status":"supported","evidence_refs":["e1"],"reason":"quote"}],"S3":{"status":"pass","reason":"coherent","evidence_refs":["e1"]},"S4":{"status":"pass","reason":"checkable","evidence_refs":["e1"]},"limitations":[]},{"fake":self.i}

class TestInterruptedResume(unittest.TestCase):
 def test_completed_assessment_is_reused_after_interruption(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); src=root/"session.jsonl"
   rows=[]
   for i in range(2):
    rows.append({"type":"user","sessionId":"s","uuid":f"u{i}","message":{"role":"user","content":[{"type":"text","text":"please change x"}]}})
   src.write_text("\n".join(json.dumps(x) for x in rows)+"\n")
   pol=PathPolicy([root],new_root=root,forbidden_root=Path("/legacy-root")); client=TwoEpisodeInterruptingFake(); run=root/"run"
   with self.assertRaisesRegex(RuntimeError,"injected interruption"):
    run_pipeline(pol,str(src),run,client=client)
   self.assertTrue((run/"checkpoints/semantic_checkpoint.json").exists())
   completed=list(run.glob("assessments/*/assessment_checkpoint.json"))
   self.assertEqual(len(completed),1)
   self.assertEqual(client.i,4)
   manifest=run_pipeline(pol,str(src),run,client=client)
   self.assertEqual(len(manifest["assessments"]),2)
   self.assertEqual(client.i,6,"resume must skip understanding and the completed first assessment")
   self.assertEqual(manifest["status"],"complete")
   from session_labeling.audit import audit_run
   report=audit_run(pol,run)
   self.assertTrue(report["valid"],report["issues"])
