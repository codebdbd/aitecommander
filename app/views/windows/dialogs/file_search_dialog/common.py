import datetime
import fnmatch
import os
import stat
from typing import Optional


def check_file_content(
    config: dict, filepath: str, content_regex: Optional[object]
) -> bool:
    """Check file contents against configuration rules.

    `content_regex` is a compiled regex or ``None`` when a plain substring search is required.
    Returns ``True`` if the file matches the requested content conditions.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if content_regex:
            return bool(content_regex.search(content))
        else:
            search_text = config["content"]
            if not isinstance(search_text, str) or not search_text.strip():
                return False
            if not config.get("case_sensitive"):
                content = content.lower()
                search_text = search_text.lower()
            return search_text in content
    except (OSError, UnicodeDecodeError):
        return False


def matches_criteria(
    config: dict,
    filepath: str,
    filename: str,
    name_regex: Optional[object],
    content_regex: Optional[object],
) -> bool:
    """Validate file against all criteria defined in ``config``.

    Consolidates the logic shared by `FileSearchDialog` and `FileSearchWorker`.
    """
    try:
        file_stat = os.stat(filepath)

        # 1. Filename pattern check
        if not fnmatch.fnmatch(filename, config["pattern"]):
            return False

        # 2. Filename regex check
        if name_regex and not name_regex.search(filename):
            return False

        # 3. File size (KB)
        size_kb = file_stat.st_size // 1024
        size_min = config.get("size_min")
        size_max = config.get("size_max")
        if size_min is not None and size_kb < size_min:
            return False
        if size_max is not None and size_kb > size_max:
            return False

        # 4. Modified date
        mtime = datetime.date.fromtimestamp(file_stat.st_mtime)
        if not (config["date_from"] <= mtime <= config["date_to"]):
            return False

        # 5. Attributes (hidden/read-only)
        if config.get("hidden"):
            if os.name == "posix" and not filename.startswith("."):
                return False
            elif os.name == "nt":
                try:
                    attrs = os.stat(filepath).st_file_attributes
                    if not (attrs & stat.FILE_ATTRIBUTE_HIDDEN):
                        return False
                except (AttributeError, OSError):
                    pass

        if config.get("readonly"):
            if os.access(filepath, os.W_OK):
                return False

        # 6. Content match
        if config.get("content"):
            if not check_file_content(config, filepath, content_regex):
                return False

        return True
    except OSError:
        return False
