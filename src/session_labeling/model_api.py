from __future__ import annotations
import hashlib, json, os, threading, time, stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import jsonschema, yaml
from openai import OpenAI
from .utils import atomic_write_json, canonical_json

@dataclass(frozen=True)
class ProviderConfig:
    name:str; base_url:str; api_key_env:str; default_model:str; allowed_models:tuple[str,...]=(); timeout_seconds:int=120; max_retries:int=2; requests_per_minute:int=30; max_completion_tokens:int|None=8192; reasoning_effort:str|None=None

def load_provider(path,name):
    p=Path(path); mode=os.lstat(p).st_mode
    if stat.S_ISLNK(mode): raise ValueError(f"symlink provider config rejected: {p}")
    fd=os.open(p,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    with os.fdopen(fd,"r",encoding="utf-8") as f: raw=yaml.safe_load(f)["providers"][name]
    return ProviderConfig(name=name,base_url=str(raw["base_url"]).rstrip("/"),api_key_env=str(raw["api_key_env"]),default_model=str(raw["default_model"]),allowed_models=tuple(raw.get("allowed_models") or ()),timeout_seconds=int(raw.get("timeout_seconds",120)),max_retries=int(raw.get("max_retries",2)),requests_per_minute=int(raw.get("requests_per_minute",30)),max_completion_tokens=(int(raw["max_completion_tokens"]) if raw.get("max_completion_tokens") else None),reasoning_effort=raw.get("reasoning_effort"))

class StructuredJSONClient:
    def __init__(self,config,model=None,cache_dir=None,api_key=None):
        self.config=config; self.model=model or config.default_model
        if config.allowed_models and self.model not in config.allowed_models: raise ValueError(f"model not allowed: {self.model}")
        key=api_key or os.environ.get(config.api_key_env)
        if not key: raise ValueError(f"missing API key environment variable: {config.api_key_env}")
        self.cache_dir=Path(cache_dir) if cache_dir else None
        if self.cache_dir: self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.client=OpenAI(api_key=key,base_url=config.base_url,timeout=config.timeout_seconds,max_retries=0)
        self._interval=60/max(1,config.requests_per_minute); self._last=0.; self._lock=threading.Lock()
    def _wait(self):
        with self._lock:
            delay=self._interval-(time.monotonic()-self._last)
            if delay>0: time.sleep(delay)
            self._last=time.monotonic()
    def complete_json_schema(self,system,user,*,name,schema):
        body={"model":self.model,"temperature":0,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"response_format":{"type":"json_schema","json_schema":{"name":name,"strict":True,"schema":schema}}}
        if self.config.max_completion_tokens: body["max_completion_tokens"]=self.config.max_completion_tokens
        if self.config.reasoning_effort: body["reasoning_effort"]=self.config.reasoning_effort
        key=hashlib.sha256(canonical_json(body)).hexdigest(); cp=self.cache_dir/f"{key}.json" if self.cache_dir else None
        if cp and cp.exists():
            x=json.loads(cp.read_text()); jsonschema.Draft202012Validator(schema).validate(x["value"]); return x["value"],{**x.get("metadata",{}),"cache_hit":True,"cache_key":key}
        err=None
        for attempt in range(self.config.max_retries+1):
            try:
                self._wait(); response=self.client.chat.completions.create(**body); content=response.choices[0].message.content; value=json.loads(content); jsonschema.Draft202012Validator(schema).validate(value)
                metadata={"provider":self.config.name,"model":self.model,"cache_hit":False,"cache_key":key,"attempt":attempt+1,"usage":getattr(response.usage,"model_dump",lambda:None)() if response.usage else None}
                if cp: atomic_write_json(cp,{"value":value,"metadata":metadata})
                return value,metadata
            except Exception as e:
                err=e
                if attempt>=self.config.max_retries: break
                time.sleep(min(2**attempt,8))
        raise RuntimeError(f"structured model call failed after {self.config.max_retries+1} attempts: {err}") from err
