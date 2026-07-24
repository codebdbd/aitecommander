"""Fix icon_resolver.py to handle None from get_default_icon_path()."""

import sys
from pathlib import Path


def main():
    file_path = Path(__file__).parent.parent / "app" / "utils" / "ui" / "icon" / "icon_resolver.py"

    content = file_path.read_text(encoding="utf-8")

    # Add helper function after imports
    old_imports = 'from .validation import is_valid_icon_file\n\n\ndef get_default_icon_path()'
    new_imports = '''from .validation import is_valid_icon_file


def _safe_default_icon_path() -> str:
    """Return default icon path as string, or empty string if not configured."""
    path = get_default_icon_path()
    return str(path) if path else ""


def get_default_icon_path()'''

    if old_imports in content:
        content = content.replace(old_imports, new_imports)
        print("Added _safe_default_icon_path helper")
    else:
        print("Could not find insertion point")

    # Replace all str(get_default_icon_path()) with _safe_default_icon_path()
    old_call = 'str(get_default_icon_path())'
    new_call = '_safe_default_icon_path()'

    count = content.count(old_call)
    if count > 0:
        content = content.replace(old_call, new_call)
        print(f"Replaced {count} occurrences of str(get_default_icon_path())")
    else:
        print("No occurrences to replace")

    file_path.write_text(content, encoding="utf-8")
    print("Done")


if __name__ == "__main__":
    main()
