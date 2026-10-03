from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"@([a-z][a-z0-9_]*)")


def resolve_token_placeholders(qss: str, tokens: dict[str, str] | None) -> str:
    """Replace ``@token_name`` placeholders in theme QSS with token values."""
    if not qss or "@" not in qss:
        return qss
    tokens = tokens or {}

    def _repl(match: re.Match[str]) -> str:
        value = tokens.get(match.group(1))
        if value is None:
            logger.warning("Unknown theme token placeholder: %s", match.group(0))
            return match.group(0)
        return value

    return _PLACEHOLDER_RE.sub(_repl, qss)
