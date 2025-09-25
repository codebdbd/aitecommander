"""Исключения для topbar модуля."""

from __future__ import annotations


class TopBarError(Exception):
    """Базовое исключение для topbar."""
    pass


class LayoutCalculationError(TopBarError):
    """Ошибка при расчете layout."""
    pass


class PanelConfigurationError(TopBarError):
    """Ошибка конфигурации панели."""
    pass


class SizeConstraintError(TopBarError):
    """Ошибка ограничений размера."""
    pass
