"""Общие утилиты для команд DnD."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.views.windows.main_window_protocol import MainWindowProtocol


def _require_main(main: object | None) -> MainWindowProtocol:
    if main is None:
        raise RuntimeError("Command requires an attached main window")
    return cast("MainWindowProtocol", main)


def _require_structure_business(main: object | None) -> StructureBusinessLogic:
    main_window = _require_main(main)
    structure_business = getattr(main_window, "structure_business", None)
    if structure_business is None:
        raise RuntimeError("Main window is missing structure_business")
    return cast("StructureBusinessLogic", structure_business)


def _get_structure_business(main: object | None) -> StructureBusinessLogic | None:
    try:
        return _require_structure_business(main)
    except RuntimeError:
        return None


__all__ = [
    "_require_main",
    "_require_structure_business",
    "_get_structure_business",
]
