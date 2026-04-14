from __future__ import annotations

import re
from pathlib import Path


FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*from\s+app\.config_data\s+import\s+app_config\b", re.MULTILINE
)


def test_no_direct_app_config_imports_in_ui_service_layers() -> None:
    roots = [
        Path("app/controllers"),
        Path("app/views"),
        Path("app/services"),
    ]
    violations: list[str] = []

    for root in roots:
        if not root.exists():
            continue
        for file_path in root.rglob("*.py"):
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            if FORBIDDEN_IMPORT_RE.search(text):
                violations.append(str(file_path).replace("\\", "/"))

    assert not violations, (
        "Direct imports 'from app.config_data import app_config' are forbidden in "
        "app/controllers, app/views, app/services.\n"
        + "\n".join(violations)
    )
