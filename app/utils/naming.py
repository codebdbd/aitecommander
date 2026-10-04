"""Naming and unique name generation utilities."""

from __future__ import annotations

import re


def generate_unique_name(existing_names: set[str], base_name: str) -> str:
    """Generate a unique name: 'Base', 'Base (1)', 'Base (2)', etc."""
    lower_existing = {n.strip().casefold() for n in existing_names}
    if base_name.strip().casefold() not in lower_existing:
        return base_name
    match = re.match(r"^(.*?)\s*\((\d+)\)$", base_name.strip())
    prefix = match.group(1) if match else base_name.strip()
    counter = 1
    while f"{prefix} ({counter})".casefold() in lower_existing:
        counter += 1
    return f"{prefix} ({counter})"
