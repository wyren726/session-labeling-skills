from __future__ import annotations
import hashlib, json, os, tempfile
from pathlib import Path
from typing import Any

def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{digest_bytes(canonical_json(parts))[:24]}"

def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f: return json.load(f)

def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload=json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n"
    fd,tmp=tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
