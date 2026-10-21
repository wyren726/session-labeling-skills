from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


class build_py(_build_py):
    """Copy canonical top-level resources into the built package.

    The repository keeps one editable source of truth under config/, schemas/, and
    prompts/. Copies exist only as generated wheel/build artifacts.
    """

    def run(self):
        super().run()
        repository_root = Path(__file__).parent
        destination = Path(self.build_lib) / "session_labeling" / "resources"
        for name in ("config", "schemas", "prompts"):
            source = repository_root / name
            if not source.is_dir():
                raise RuntimeError(f"required resource directory is missing: {source}")
            target = destination / name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(
                source,
                target,
                ignore=(shutil.ignore_patterns("providers.yaml") if name == "config" else None),
            )


setup(cmdclass={"build_py": build_py})
