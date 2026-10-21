from __future__ import annotations
from .utils import digest_bytes

_STATUS={"supported":"supported","partial":"unresolved","unsupported":"unsupported","unknown":"unresolved",None:"unresolved"}
_CLAIM={"supported":"supported","partial":"insufficient","unsupported":"contradicted","unknown":"insufficient",None:"insufficient"}

def stage06_to_canonical(label, selection):
    evidence=[]
    for e in label.get("evidence_refs",[]):
        quote=e.get("quote") or "<legacy evidence without quote>"
        evidence.append({"evidence_id":e.get("evidence_id"),"source_snapshot_id":"legacy-stage06","event_id":e.get("event_id") or "legacy-unknown-event","quote":quote,"content_digest":digest_bytes(quote.encode("utf-8")),"legacy_locator":e.get("locator"),"legacy_source_role":e.get("source_role")})
    claim_by_id={c.get("claim_id"):c for c in label.get("claims",[])}
    claims=[]
    for c in label.get("claims",[]):
        claims.append({"claim_id":c.get("claim_id"),"field_path":c.get("field_path"),"support_status":_CLAIM.get(c.get("support_status"),"insufficient"),"evidence_refs":list(c.get("evidence_ids",[])),"reason":c.get("reason"),"legacy_support_status":c.get("support_status")})
    mappings=[]
    for m in label.get("capability_mapping",[]):
        refs=[]
        for cid in m.get("claim_ids",[]): refs.extend(claim_by_id.get(cid,{}).get("evidence_ids",[]))
        refs=list(dict.fromkeys(refs))
        mappings.append({"mapping_id":m.get("mapping_id"),"role":"primary" if m.get("parent_requirement_id") in selection.get("primary_requirement_ids",[]) or not selection.get("primary_requirement_ids") else "auxiliary","status":_STATUS.get(m.get("mapping_status"),"unresolved"),"evidence_refs":refs,"claim_refs":list(m.get("claim_ids",[])),"taxonomy":{"parent_requirement_id":m.get("parent_requirement_id"),"subrequirement_id":m.get("subrequirement_id"),"taxonomy_row":m.get("taxonomy_row")},"legacy_mapping_status":m.get("mapping_status")})
    reviews=[]
    for rid in ("S3","S4"):
        r=selection.get("rule_checks",{}).get(rid,{})
        reviews.append({"rule_id":rid,"status":r.get("status","pending"),"reason":r.get("reason") or "migrated frozen Stage 06 program review","evidence_refs":list(r.get("evidence_ids",[])),"provenance":{"kind":"legacy_frozen_program_decision","reviewer_type":selection.get("evaluation",{}).get("reviewer_type")}})
    pre=selection.get("prechecks",{})
    return {"schema_version":"final-labels-v1","assessment_id":selection.get("assessment_id") or label.get("case_id"),"session_id":selection.get("source_session_id"),"episode_id":label.get("case_id") or selection.get("assessment_id") or "legacy-unknown-episode","source_snapshot_id":"legacy-stage06","case_id":label.get("case_id"),"evidence":evidence,"claims":claims,"capability_mappings":mappings,"task_attributes":{"difficulty":label.get("task_attributes",{}).get("difficulty","unknown"),"difficulty_evidence_refs":list(selection.get("rule_checks",{}).get("S2",{}).get("evidence_ids",[]))},"semantic_rule_reviews":reviews,"execution":{"agent_claimed_status":"unknown","verified_outcome":{"status":"unknown"},"requirement_results":[]},"scope_match":pre.get("scope_match","pending"),"selection_critical_conflicts":[] if pre.get("no_selection_critical_unresolved_conflict")=="pass" else ["legacy unresolved conflict"],"limitations":list(label.get("limitations",[])),"validation_issues":[],"provenance":{"kind":"legacy_stage06_compatibility_adapter","source_schema_version":label.get("schema_version"),"selection_policy_version":selection.get("policy_version")}}
