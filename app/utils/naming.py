"""Naming and unique name generation utilities."""

from __future__ import annotations

import re
from collections.abc import Iterable


class UniqueNameAllocator:
    """Append-only name index for a batch, including cached suffix searches."""

    def __init__(self, names: Iterable[str] = ()) -> None:
        self._names = {name.strip().casefold() for name in names}
        self._next_suffix: dict[str, int] = {}

    def add(self, name: str) -> None:
        self._names.add(name.strip().casefold())

    def suggest(self, base_name: str) -> str:
        if base_name.strip().casefold() not in self._names:
            return base_name
        match = re.match(r"^(.*?)\s*\((\d+)\)$", base_name.strip())
        prefix = match.group(1) if match else base_name.strip()
        key = prefix.casefold()
        counter = self._next_suffix.get(key, 1)
        while f"{prefix} ({counter})".casefold() in self._names:
            counter += 1
        self._next_suffix[key] = counter
        return f"{prefix} ({counter})"


def generate_unique_name(existing_names: Iterable[str] | UniqueNameAllocator, base_name: str) -> str:
    """Generate a unique name: 'Base', 'Base (1)', 'Base (2)', etc."""
    allocator = existing_names if isinstance(existing_names, UniqueNameAllocator) else UniqueNameAllocator(existing_names)
    return allocator.suggest(base_name)
