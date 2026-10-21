from __future__ import annotations
import os, stat
from pathlib import Path, PurePosixPath

FORBIDDEN_ROOT = PurePosixPath("/mnt/shared-storage-user" + "/songdemin/user/renwanying")
DEFAULT_NEW_ROOT = PurePosixPath("/mnt/shared-storage-user/gpfs1-agent-mlcoding/users/renwanying")

class PathPolicyError(ValueError): pass

class PathPolicy:
    def __init__(self, allowed_roots, *, new_root=DEFAULT_NEW_ROOT, forbidden_root=FORBIDDEN_ROOT):
        self.allowed_roots=tuple(self._clean(PurePosixPath(str(p))) for p in allowed_roots)
        self.new_root=self._clean(PurePosixPath(str(new_root)))
        self.forbidden_root=self._clean(PurePosixPath(str(forbidden_root)))
        if not self.allowed_roots: raise PathPolicyError("at least one allowed root is required")
    @staticmethod
    def _clean(p):
        if not p.is_absolute() or ".." in p.parts: raise PathPolicyError(f"unsafe absolute path: {p}")
        return p
    @staticmethod
    def _under(path, root): return path == root or root in path.parents
    def remap_locator(self, locator):
        raw=str(locator)
        if "\x00" in raw: raise PathPolicyError("NUL in locator")
        p=self._clean(PurePosixPath(raw))
        # Lexical conversion only. Never inspect the source locator.
        if self._under(p,self.forbidden_root):
            suffix=p.relative_to(self.forbidden_root)
            p=self.new_root/suffix
        if not any(self._under(p,r) for r in self.allowed_roots):
            raise PathPolicyError(f"path outside allowed roots: {p}")
        return Path(str(p))
    def validate_for_read(self, locator):
        p=self.remap_locator(locator)
        cur=PurePosixPath("/")
        for part in PurePosixPath(str(p)).parts[1:]:
            cur=cur/part
            try: mode=os.lstat(str(cur)).st_mode
            except FileNotFoundError: raise PathPolicyError(f"missing path: {cur}") from None
            if stat.S_ISLNK(mode): raise PathPolicyError(f"symlink component rejected: {cur}")
        if not stat.S_ISREG(os.lstat(p).st_mode): raise PathPolicyError(f"not a regular file: {p}")
        return p

    def validate_for_write(self, locator):
        p=self.remap_locator(locator)
        # The leaf may not exist; every existing ancestor must be non-symlink.
        probe=PurePosixPath(str(p))
        chain=[]
        while str(probe) != "/" and not os.path.lexists(str(probe)):
            chain.append(probe.name); probe=probe.parent
        cur=PurePosixPath("/")
        for part in probe.parts[1:]:
            cur=cur/part
            mode=os.lstat(str(cur)).st_mode
            if stat.S_ISLNK(mode): raise PathPolicyError(f"symlink component rejected: {cur}")
        if os.path.lexists(str(p)) and stat.S_ISLNK(os.lstat(str(p)).st_mode):
            raise PathPolicyError(f"symlink target rejected: {p}")
        return Path(str(p))

    def open_binary(self, locator):
        p=self.validate_for_read(locator)
        fd=os.open(p,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        return os.fdopen(fd,"rb")

    def open_text(self, locator):
        p=self.validate_for_read(locator)
        fd=os.open(p,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        return os.fdopen(fd,"r",encoding="utf-8")
