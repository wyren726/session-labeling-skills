from __future__ import annotations
import argparse, json
from pathlib import Path
from .path_policy import PathPolicy, DEFAULT_NEW_ROOT
from .ingest import normalize_session
from .selection import evaluate
from .pipeline import run_pipeline, run_batch
from .audit import audit_tree, audit_run
from .contracts import validate_artifact, project_root
from .utils import atomic_write_json, load_json
from .regression import run_ten_session_regression
from .model_api import load_provider, StructuredJSONClient

def policy(args): return PathPolicy([Path(args.new_root),*(Path(x) for x in args.allowed_root)],new_root=Path(args.new_root))
def guarded_write(pol,path,value): path=pol.validate_for_write(path); path.parent.mkdir(parents=True,exist_ok=True); atomic_write_json(path,value)
def add_model(p):
    p.add_argument("--provider-config"); p.add_argument("--provider"); p.add_argument("--model"); p.add_argument("--cache-dir")
def client_from(args,pol):
    if not args.provider_config and not args.provider: return None
    if not args.provider_config or not args.provider: raise ValueError("--provider-config and --provider must be supplied together")
    cfg=load_provider(pol.validate_for_read(args.provider_config),args.provider)
    cache=pol.validate_for_write(args.cache_dir) if args.cache_dir else None
    return StructuredJSONClient(cfg,model=args.model,cache_dir=cache)
def main(argv=None):
    ap=argparse.ArgumentParser(prog="session-labeling"); ap.add_argument("--new-root",default=str(DEFAULT_NEW_ROOT)); ap.add_argument("--allowed-root",action="append",default=[])
    sub=ap.add_subparsers(dest="cmd",required=True)
    n=sub.add_parser("normalize"); n.add_argument("--input",required=True); n.add_argument("--output",required=True)
    s=sub.add_parser("select"); s.add_argument("--labels",required=True); s.add_argument("--output",required=True)
    r=sub.add_parser("run"); r.add_argument("--input",required=True); r.add_argument("--run-dir",required=True); r.add_argument("--analysis"); r.add_argument("--no-resume",action="store_true"); add_model(r)
    b=sub.add_parser("batch"); b.add_argument("--input-list",required=True); b.add_argument("--output-dir",required=True); b.add_argument("--limit",type=int); b.add_argument("--no-resume",action="store_true"); add_model(b)
    a=sub.add_parser("audit"); a.add_argument("--root",required=True); a.add_argument("--kind",choices=["auto","repository","run"],default="auto"); a.add_argument("--output")
    g=sub.add_parser("regression"); g.add_argument("--trace-root",required=True); g.add_argument("--output-dir",required=True)
    args=ap.parse_args(argv); pol=policy(args)
    if args.cmd=="normalize": guarded_write(pol,args.output,normalize_session(pol,args.input))
    elif args.cmd=="select":
        labels=load_json(pol.validate_for_read(args.labels)); validate_artifact(labels,"final_labels.schema.json"); guarded_write(pol,args.output,evaluate(labels))
    elif args.cmd=="run": print(json.dumps(run_pipeline(pol,args.input,args.run_dir,args.analysis,client_from(args,pol),not args.no_resume),ensure_ascii=False,indent=2))
    elif args.cmd=="batch": print(json.dumps(run_batch(pol,args.input_list,args.output_dir,client_from(args,pol),args.limit,not args.no_resume),ensure_ascii=False,indent=2))
    elif args.cmd=="regression":
        report=run_ten_session_regression(pol,args.trace_root,args.output_dir); print(json.dumps(report["summary"],ensure_ascii=False,indent=2))
    else:
        root=pol.remap_locator(args.root); kind=args.kind
        if kind=="auto": kind="run" if (root/"run_manifest.json").is_file() else "repository"
        report=audit_run(pol,root) if kind=="run" else audit_tree(root)
        if args.output: guarded_write(pol,args.output,report)
        else: print(json.dumps(report,ensure_ascii=False,indent=2))
        if not report["valid"]: raise SystemExit(2)
if __name__=="__main__": main()
