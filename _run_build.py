import sys
import os
import runpy
from pathlib import Path

VENVP = Path(r"d:\01_Codebdbd\01_projects\aitecommander\.venv\Lib\site-packages")
ROOT = Path(r"d:\01_Codebdbd\01_projects\aitecommander")

paths = [
    str(VENVP),
    str(VENVP / "win32"),
    str(VENVP / "win32" / "lib"),
    str(VENVP / "Pythonwin"),
    str(ROOT),
]

for p in paths:
    sys.path.insert(0, p)

existing_pp = os.environ.get("PYTHONPATH", "")
sep = os.pathsep
os.environ["PYTHONPATH"] = sep.join(paths) + (sep + existing_pp if existing_pp else "")

os.environ["PATH"] = str(VENVP / "pywin32_system32") + os.pathsep + os.environ["PATH"]

import pywin32_bootstrap

runpy.run_path(str(ROOT / "scripts" / "build.py"), run_name="__main__")
