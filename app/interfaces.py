# app/interfaces.py

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class SupportsUpdates(Protocol):
    """Минимальный протокол для объектов, поддерживающих включение/выключение обновлений."""

    def setUpdatesEnabled(self, enabled: bool) -> None:
        ...


@runtime_checkable
class MainWindowLike(Protocol):
    """Минимальный протокол главного окна, используемый инициализатором.

    Содержит только строго необходимые методы, которые вызываются напрямую в
    `WindowInitializer`. Дополнительные методы UI-компонентов остаются
    незафиксированными в этом контракте и проверяются через hasattr в рантайме.
    """

    def setUpdatesEnabled(self, enabled: bool) -> None:
        ...

    # Используются в WindowUISetup.setup_window_properties()
    def setWindowTitle(self, title: str) -> None:  # noqa: N802 (Qt-style)
        ...

    def resize(self, width: int, height: int) -> None:
        ...

    def setMinimumSize(self, width: int, height: int) -> None:  # noqa: N802
        ...

    def setWindowIcon(self, icon: Any) -> None:  # noqa: N802
        ...

    # Используются в WindowUISetup.setup_menu() / setup_central_widget()
    def setMenuBar(self, menu_bar: Any) -> None:  # noqa: N802
        ...

    def setCentralWidget(self, widget: Any) -> None:  # noqa: N802
        ...


@runtime_checkable
class SupportsFontSizeApply(Protocol):
    """Опциональный протокол: окно умеет применять размер шрифта к контенту."""

    def apply_font_size_to_content(self, size: int) -> None:  # noqa: N802 (Qt-style)
        ...


@runtime_checkable
class SettingsLike(Protocol):
    """Протокол настроек приложения с доступом к размеру шрифта."""

    def get_font_size(self) -> Optional[int]:
        ...


@runtime_checkable
class FavoritesPanelLike(Protocol):
    """Панель избранного, требующая метод set_favorites."""

    def set_favorites(self, items: list[Any]) -> None:
        ...


@runtime_checkable
class FavoritesPanelWithClear(FavoritesPanelLike, Protocol):
    """Расширенный протокол панели избранного: поддерживает очистку на стороне виджета."""

    def clear_favorites(self) -> None:
        ...


@runtime_checkable
class RecentsPanelLike(Protocol):
    """Панель недавних ссылок, требующая метод set_recent_links."""

    def set_recent_links(self, items: list[Any]) -> None:
        ...


@runtime_checkable
class RecentsPanelWithLimit(RecentsPanelLike, Protocol):
    """Расширенный протокол панели недавних: предоставляет лимит элементов."""

    def get_limit(self) -> Optional[int]:
        ...
