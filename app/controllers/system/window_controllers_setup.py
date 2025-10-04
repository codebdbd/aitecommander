"""
Тонкий фасад для настройки контроллеров главного окна.

Основная логика вынесена в модули:
- app.controllers.system.window_setup.types - типы и протоколы
- app.controllers.system.window_setup.business - бизнес-логика и UI setup
- app.controllers.system.window_setup.wiring - подключение сигналов
- app.controllers.system.window_setup.coordinator - координатор настройки

Этот модуль предоставляет только публичный API и вспомогательные функции.
"""

import logging

from app.controllers.system.window_setup.types import (
    SetupError,
)
from app.controllers.business import StructureBusinessLogic
from app.controllers.system.window_setup.coordinator import (
    setup_controllers,
    WindowControllersSetup,
)
from app.controllers.system.window_setup.ui import (
    setup_ui_elements,
    setup_dependency_injection,
)
from app.controllers.system.window_setup.wiring import (
    setup_signal_connections,
    _connect_structure_signals as _new_connect_structure_signals,
    _connect_top_panels_signals_explicit as _new_connect_top_panels_signals_explicit,
    _on_structure_changed_schedule_refresh as _new_on_structure_changed_schedule_refresh,
    DatabaseEventHandler,
)
from app.controllers.system.window_setup.keyboard import (
    setup_keyboard,
)

logger = logging.getLogger(__name__)


def _resolve_structure_loader(structure_business: StructureBusinessLogic):
    """Вернуть callable для загрузки структуры: load_structure_async или load_structure.

    Строго типизированный поиск загрузчика: проверяем наличие методов через hasattr
    и сразу поднимаем SetupError, если оба метода отсутствуют.
    """
    # Проверяем наличие методов загрузки до попытки их использования
    has_async = hasattr(structure_business, "load_structure_async")
    has_sync = hasattr(structure_business, "load_structure")

    if not has_async and not has_sync:
        raise SetupError(
            "StructureBusinessLogic must provide load_structure_async() or load_structure()"
        )

    try:
        # Приоритет async методу, если доступен
        if has_async:
            loader = structure_business.load_structure_async  # type: ignore[attr-defined]
            if not callable(loader):
                raise SetupError(
                    "StructureBusinessLogic.load_structure_async must be callable"
                )
            return loader

        if has_sync:
            loader = structure_business.load_structure  # type: ignore[attr-defined]
            if not callable(loader):
                raise SetupError(
                    "StructureBusinessLogic.load_structure must be callable"
                )
            return loader

    except SetupError:
        # SetupError уже содержит информативное сообщение - пробрасываем как есть
        raise
    except Exception as e:
        logger.exception("Unexpected error while resolving structure loader")
        raise SetupError(
            "Failed to resolve structure loader due to unexpected error"
        ) from e

    # Этот код никогда не должен выполниться из-за проверок выше
    raise SetupError("Internal error: structure loader resolution failed")


def _connect_structure_signals(*args, **kwargs):
    """Backward-compatible wrapper around the refactored implementation."""
    return _new_connect_structure_signals(*args, **kwargs)


def _connect_top_panels_signals_explicit(*args, **kwargs):
    """Backward-compatible wrapper around the refactored implementation."""
    return _new_connect_top_panels_signals_explicit(*args, **kwargs)


def _on_structure_changed_schedule_refresh(*args, **kwargs):
    """Backward-compatible wrapper around the refactored implementation."""
    return _new_on_structure_changed_schedule_refresh(*args, **kwargs)


__all__ = [
    "setup_controllers",
    "setup_ui_elements", 
    "setup_dependency_injection",
    "setup_signal_connections",
    "setup_keyboard",
    "WindowControllersSetup",
    "_resolve_structure_loader",
    "DatabaseEventHandler",
    "_connect_structure_signals",
    "_connect_top_panels_signals_explicit",
    "_on_structure_changed_schedule_refresh",
]
