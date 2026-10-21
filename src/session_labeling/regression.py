from __future__ import annotations
import json, datetime
from pathlib import Path
from .contracts import load_yaml, validate_artifact
from .ingest import normalize_session
from .legacy import stage06_to_canonical
from .selection import evaluate
from .utils import atomic_write_json

def _jsonl(policy,path):
    with policy.open_text(path) as f:
        for n,line in enumerate(f,1):
            if line.strip():
                try: yield json.loads(line)
                except json.JSONDecodeError as e: raise ValueError(f"invalid JSONL {path}:{n}: {e}") from e
def _case_id(x): return x.get("case_id") or x.get("assessment_target",{}).get("case_id")
def run_ten_session_regression(path_policy, trace_root, output_dir, baseline_path=None):
    trace_root=Path(trace_root); output_dir=path_policy.validate_for_write(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    cfg=load_yaml("regression_baseline.yaml") if baseline_path is None else load_yaml(baseline_path)
    rows=sorted(_jsonl(path_policy,trace_root/cfg["candidate_listing"]),key=lambda r:r["session_id"])[:10]
    cases={c for r in rows for c in r["case_ids"]}; labels={}; selections={}
    for pair in cfg["artifacts"]:
        for x in _jsonl(path_policy,trace_root/pair["labels"]):
            if _case_id(x) in cases: labels[_case_id(x)]=x
        for x in _jsonl(path_policy,trace_root/pair["selection"]):
            if _case_id(x) in cases: selections[_case_id(x)]=x
    case_results=[]; session_results=[]
    for row in rows:
        normalized=normalize_session(path_policy,row["session_jsonl_path"])
        session_results.append({"session_id":row["session_id"],"native_session_id":normalized["session_id"],"source_sha256":normalized["source_snapshot"]["sha256"],"record_count":normalized["source_snapshot"]["record_count"],"event_count":len(normalized["events"]),"turn_count":len(normalized["turns"]),"parse_error_count":len(normalized["source_snapshot"]["parse_errors"]),"session_id_match":normalized["session_id"]==row["session_id"],"case_ids":row["case_ids"]})
        for cid in row["case_ids"]:
            if cid not in labels or cid not in selections:
                case_results.append({"case_id":cid,"status":"missing_baseline"}); continue
            canonical=stage06_to_canonical(labels[cid],selections[cid]); validate_artifact(canonical,"final_labels.schema.json")
            actual=evaluate(canonical); expected=selections[cid]
            expected_rules={k:v.get("status") for k,v in expected.get("rule_checks",{}).items()}
            actual_rules={r["rule_id"]:r["status"] for r in actual["rules"]}
            expected_decision={"priority_candidate":"selected","review":"pending_review","not_selected":"not_selected"}.get(expected.get("decision"),"invalid")
            case_results.append({"case_id":cid,"status":"compared","expected_rules":expected_rules,"actual_rules":actual_rules,"rule_match":expected_rules==actual_rules,"expected_decision":expected_decision,"actual_decision":actual["decision"],"decision_match":expected_decision==actual["decision"],"legacy_reviewer_type":expected.get("evaluation",{}).get("reviewer_type"),"mapping_count":len(canonical["capability_mappings"]),"evidence_count":len(canonical["evidence"]),"claim_count":len(canonical["claims"])})
    summary={"sessions":len(session_results),"cases":len(case_results),"session_ids_matched":sum(x["session_id_match"] for x in session_results),"parse_error_sessions":sum(x["parse_error_count"]>0 for x in session_results),"cases_with_baseline":sum(x["status"]=="compared" for x in case_results),"rule_matches":sum(x.get("rule_match",False) for x in case_results),"decision_matches":sum(x.get("decision_match",False) for x in case_results),"all_pass":all(x["session_id_match"] and x["parse_error_count"]==0 for x in session_results) and all(x.get("rule_match") and x.get("decision_match") for x in case_results)}
    report={"schema_version":"ten-session-regression-v1","generated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"baseline":cfg["name"],"sample_strategy":cfg["sample_strategy"],"summary":summary,"sessions":session_results,"cases":case_results,"limitations":["Episode boundaries, goals, and exact quote-to-new-event alignment require the model-assisted analysis path and are not asserted by this deterministic compatibility run.","Legacy labels are explicitly migrated as frozen program decisions; they are not presented as newly generated model judgments."]}
    out=output_dir/"ten-session-regression.json"; out=path_policy.validate_for_write(out); atomic_write_json(out,report); return report
