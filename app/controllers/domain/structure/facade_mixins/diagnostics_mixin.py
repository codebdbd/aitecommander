from __future__ import annotations

from typing import Any, Dict

from app.controllers.domain.structure.infrastructure.diagnostics import Diagnostics


class DiagnosticsMixin:
    """Миксин для методов диагностики/отладки фасада."""

    def get_cache_info(self) -> Dict[str, Any]:
        """Возвращает информацию о состоянии кэша (делегировано в Diagnostics)."""
        return Diagnostics.get_cache_info(self.cache_manager)
