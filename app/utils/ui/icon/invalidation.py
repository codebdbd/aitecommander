"""Path matching shared by the icon cache layers."""

import os
from pathlib import Path


def normalized_path(value):
    return os.path.normcase(os.path.abspath(os.path.normpath(str(value).strip())))


class IconInvalidationTarget:
    def __init__(self, path):
        self.path = Path(str(path).strip())
        self.absolute = normalized_path(self.path)
        self.aliases = {self.path.name.casefold(), self.path.stem.casefold()}

    def matches(self, reference, resolved=None):
        reference = str(reference or "").strip()
        if not reference:
            return False
        path = Path(reference)
        if path.is_absolute() or path.parent != Path("."):
            return normalized_path(path) == self.absolute
        # A known resolution takes precedence over a coincidental short name.
        if resolved:
            return normalized_path(resolved) == self.absolute
        return reference.casefold() in self.aliases
