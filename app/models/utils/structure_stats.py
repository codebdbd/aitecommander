"""Statistics and counting utilities for structure data.

Improvement note: centralizes item counting logic that was duplicated between
structure_manager.py and import_worker.py.
"""

from __future__ import annotations

from typing import Any


def count_total_items(root: list[dict[str, Any]]) -> int:
    """Count total items (spheres + sections + categories + links) in structure.

    Args:
        root: List of sphere dictionaries with nested structure:
            - Each sphere contains 'sections' list
            - Each section contains 'categories' list
            - Each category contains 'links' list

    Returns:
        Total count of all items in the hierarchy (spheres + sections + categories + links)

    Example:
        >>> structure = [
        ...     {
        ...         "id": 1,
        ...         "sections": [
        ...             {
        ...                 "id": 10,
        ...                 "categories": [
        ...                     {"id": 100, "links": [{"id": 1000}, {"id": 1001}]}
        ...                 ]
        ...             }
        ...         ]
        ...     }
        ... ]
        >>> count_total_items(structure)
        5  # 1 sphere + 1 section + 1 category + 2 links
    """
    return (
        len(root)
        + sum(len((s or {}).get("sections", [])) for s in root)
        + sum(
            len((sec or {}).get("categories", []))
            for s in root
            for sec in (s or {}).get("sections", [])
        )
        + sum(
            len((cat or {}).get("links", []))
            for s in root
            for sec in (s or {}).get("sections", [])
            for cat in (sec or {}).get("categories", [])
        )
    )


__all__ = ["count_total_items"]
