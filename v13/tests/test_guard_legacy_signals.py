import re
from pathlib import Path

# Guard-test to ensure legacy signals and names do not reappear in application code
# Scans only the 'app/' directory (not tests) and fails if any forbidden tokens are found.

FORBIDDEN_PATTERNS = [
    r"refresh_requested",  # legacy signal
    r"clear_requested",    # legacy signal
    r"\blinkClicked\b",  # legacy Qt name that must not be used in app code
]

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_no_legacy_signal_names_present_in_app_code():
    assert APP_DIR.exists(), f"App directory not found: {APP_DIR}"

    offenders = []
    for path in APP_DIR.rglob("*"):
        if not path.is_file():
            continue
        # Skip non-text files by extension quickly
        if path.suffix.lower() in {".png", ".ico", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".qss", ".sql", ".db", ".pyc"}:
            continue
        # Exclude view layer and UI controllers: legacy Qt signal names may be legitimate there
        try:
            rel = path.relative_to(APP_DIR)
        except Exception:
            rel = path
        parts = rel.parts
        if len(parts) >= 1 and parts[0] == "views":
            continue
        if len(parts) >= 2 and parts[0] == "controllers" and parts[1] == "ui":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            # Best-effort: ignore unreadable files
            continue
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, content):
                offenders.append((str(path), pat))

    assert not offenders, (
        "Legacy identifiers detected in app/ code. Please remove usages of legacy signal names: "
        "refresh_requested/clear_requested/linkClicked.\n" +
        "\n".join(f"{p}: pattern '{pat}'" for p, pat in offenders)
    )
