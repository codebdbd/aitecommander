import fnmatch
import os
from collections.abc import Mapping
from typing import Any

# Maximum file size for content search (10 MB)
_MAX_CONTENT_SEARCH_SIZE = 10 * 1024 * 1024
# Buffer size for reading files (1 MB chunks)
_READ_BUFFER_SIZE = 1024 * 1024


def check_file_content(
    config: Mapping[str, Any],
    filepath: str,
) -> bool:
    """Check file contents against configuration rules.

    Returns ``True`` if the file matches the requested content conditions.
    
    Files larger than 10MB are skipped to prevent GUI freezing.
    Files are read in 1MB chunks to avoid loading entire file into memory.
    """
    try:
        # Check file size first to avoid reading huge files
        file_stat = os.stat(filepath)
        if file_stat.st_size > _MAX_CONTENT_SEARCH_SIZE:
            return False
        
        # Plain text search - can search chunk by chunk
        search_text = config["content"]
        if not isinstance(search_text, str) or not search_text.strip():
            return False

        search_text = search_text.lower()

        # Search in chunks
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            # Keep overlap buffer to handle search text spanning chunks
            overlap_size = len(search_text) - 1 if len(search_text) > 1 else 0
            previous_chunk_tail = ""

            while True:
                chunk = f.read(_READ_BUFFER_SIZE)
                if not chunk:
                    break

                # Combine with previous chunk tail for overlap
                search_chunk = previous_chunk_tail + chunk

                if search_text in search_chunk.lower():
                    return True

                # Save tail for next iteration from ORIGINAL chunk (not lowercased)
                if len(chunk) >= overlap_size and overlap_size > 0:
                    previous_chunk_tail = chunk[-overlap_size:]
                else:
                    # If chunk is smaller than overlap, keep entire chunk
                    previous_chunk_tail = chunk if overlap_size > 0 else ""

        return False
            
    except (OSError, UnicodeDecodeError):
        return False


def matches_criteria(
    config: Mapping[str, Any],
    filepath: str,
    filename: str,
    name_regex,
) -> bool:
    """Validate file against all criteria defined in ``config``.

    Consolidates the logic shared by `FileSearchDialog` and `FileSearchWorker`.
    """
    try:
        # Ensure the file is accessible; no need to keep the stat result
        os.stat(filepath)

        # 1. Filename pattern check
        if not fnmatch.fnmatch(filename, config["pattern"]):
            return False

        # 2. Filename regex check
        if name_regex is not None and not name_regex.search(filename):
            return False

        # 3. Content match
        if config.get("content"):
            if not check_file_content(config, filepath):
                return False

        return True
    except OSError:
        return False
