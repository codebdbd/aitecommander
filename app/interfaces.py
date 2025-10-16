# app/interfaces.py

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMenuBar


@runtime_checkable
class SupportsUpdates(Protocol):
    """Minimal protocol for objects that support enabling/disabling updates."""

    def setUpdatesEnabled(self, enabled: bool) -> None: ...


@runtime_checkable
class MainWindowLike(Protocol):
    """Minimal protocol of the main window used by the initializer.

    Contains only strictly necessary methods called directly by
    `WindowInitializer`. Additional UI-component methods are intentionally
    not part of this contract and are checked via hasattr at runtime.
    """

    def setUpdatesEnabled(self, enabled: bool) -> None: ...

    # Used in WindowUISetup.setup_window_properties()
    def setWindowTitle(self, title: str) -> None:  # noqa: N802 (Qt-style)
        ...

    def resize(self, width: int, height: int) -> None: ...

    def setMinimumSize(self, width: int, height: int) -> None:  # noqa: N802
        ...

    def setWindowIcon(self, icon: Any) -> None:  # noqa: N802
        ...

    # Used in WindowUISetup.setup_menu() / setup_central_widget()
    def menuBar(self) -> QMenuBar:
        """Returns the menu bar."""
        from PyQt6.QtWidgets import QMenuBar

        _menu_bar = QMenuBar()
        return _menu_bar

    def setCentralWidget(self, widget: Any) -> None:  # noqa: N802
        ...


@runtime_checkable
class SupportsFontSizeApply(Protocol):
    """Optional protocol: window can apply font size to its content."""

    def apply_font_size_to_content(self, size: int) -> None:  # noqa: N802 (Qt-style)
        ...


@runtime_checkable
class SettingsLike(Protocol):
    """Protocol for application settings with access to font size."""

    def get_font_size(self) -> int | None: ...


@runtime_checkable
class TopPanelDataLike(Protocol):
    """Unified contract for top panels: provide data for rendering.

    Widgets do not contain business logic and do not access the DB; they only
    display the provided items.
    """

    def set_data(self, items: list[Any]) -> None: ...


@runtime_checkable
class FavoritesPanelWithClear(TopPanelDataLike, Protocol):
    """Favorites: supports clearing on the widget side."""

    def clear_favorites(self) -> None: ...


@runtime_checkable
class RecentsPanelWithLimit(TopPanelDataLike, Protocol):
    """Recents: can report a desired item limit (optional)."""

    def get_limit(self) -> int | None: ...
