"""Protocols для строгой типизации компонентов главного окна.

УЛУЧШЕНИЕ: Добавлены строгие Protocol для замены Any типов и улучшения
статического анализа кода. Это устраняет использование Any и делает
код более безопасным и поддерживаемым.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, runtime_checkable, TYPE_CHECKING

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

if TYPE_CHECKING:
    pass
from PyQt6.QtWidgets import (
    QButtonGroup,
    QLineEdit,
    QStackedLayout,
    QWidget,
)


@runtime_checkable
class SettingsProtocol(Protocol):
    """Protocol для объекта настроек приложения."""

    def get_font_size(self) -> int:
        """Возвращает размер шрифта из настроек."""
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """Универсальный метод получения настройки."""
        ...


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol для объекта базы данных."""

    def is_ready(self) -> bool:
        """Проверяет готовность базы данных."""
        ...

    def execute(self, query: str, params: tuple = ()) -> Any:
        """Выполняет SQL запрос."""
        ...


@runtime_checkable
class ThemeControllerProtocol(Protocol):
    """Protocol для контроллера тем."""

    def apply_theme(self, theme_name: str) -> None:
        """Применяет тему к приложению."""
        ...

    def get_current_theme(self) -> str:
        """Возвращает имя текущей темы."""
        ...

    def _log_tables_header_font(self, window: QWidget) -> None:
        """Логирует информацию о шрифте заголовков таблиц (для диагностики)."""
        ...


@runtime_checkable
class MainWindowProtocol(Protocol):
    """Protocol для главного окна приложения.
    
    УЛУЧШЕНИЕ: Строгий Protocol заменяет MainWindowLike и Any типы.
    Определяет все необходимые атрибуты и методы главного окна.
    """

    # Сигналы
    shown: pyqtSignal

    # Настройки и контроллеры
    settings: SettingsProtocol
    theme_ctrl: ThemeControllerProtocol

    # UI компоненты - верхняя панель
    top_bar_host: Optional[QWidget]
    content_container: Optional[QWidget]
    quick_add_widget: Optional[QWidget]
    fav_widget: Optional[QWidget]
    recent_links_widget: Optional[QWidget]
    search: Optional[QLineEdit]

    # UI компоненты - основная область
    left_panel: Optional[QWidget]
    tree: Optional[QWidget]
    tree_model: Optional[QObject]
    splitter: Optional[QWidget]
    stack: Optional[QStackedLayout]
    tiles: Optional[QWidget]
    tiles_scroll: Optional[QWidget]
    table: Optional[QWidget]
    table_container: Optional[QWidget]

    # UI компоненты - нижняя панель
    spheres_bar: Optional[QWidget]
    sphere_group: Optional[QButtonGroup]
    sphere_buttons: dict[int, QWidget]
    bottom_bar_container: Optional[QWidget]
    switch_sphere_button: Optional[QWidget]

    # Состояние
    current_category_id: Optional[int]
    current_sphere_id: Optional[int]
    thread_pool: Optional[QThreadPool]  # УЛУЧШЕНИЕ: Конкретный тип вместо Any
    undo_stack: Optional[Any]  # UndoManager - избегаем циклического импорта

    # Внутренние флаги
    _first_structure_load: bool
    _topbar_manager: Optional[Any]  # TopBarLayoutManager - избегаем циклического импорта
    _topbar_initialized: bool
    _auto_hide_tree_filter: Optional[Any]  # _AutoHideTreeFilter - внутренний класс

    # Методы QMainWindow
    def show(self) -> None:
        """Показывает окно."""
        ...

    def close(self) -> bool:
        """Закрывает окно."""
        ...

    def isVisible(self) -> bool:
        """Проверяет видимость окна."""
        ...

    def isEnabled(self) -> bool:
        """Проверяет доступность окна."""
        ...

    def width(self) -> int:
        """Возвращает ширину окна."""
        ...

    def height(self) -> int:
        """Возвращает высоту окна."""
        ...

    def setUpdatesEnabled(self, enable: bool) -> None:
        """Включает/выключает обновления виджета."""
        ...

    def centralWidget(self) -> Optional[QWidget]:
        """Возвращает центральный виджет."""
        ...

    def setCentralWidget(self, widget: QWidget) -> None:
        """Устанавливает центральный виджет."""
        ...

    def setMenuBar(self, menubar: QWidget) -> None:
        """Устанавливает меню бар."""
        ...

    def installEventFilter(self, filter_obj: QObject) -> None:
        """Устанавливает event filter."""
        ...

    def removeEventFilter(self, filter_obj: QObject) -> None:
        """Удаляет event filter."""
        ...

    # Специфичные методы приложения
    def apply_font_size_to_content(self, size: int) -> None:
        """Применяет размер шрифта к содержимому."""
        ...

    def on_search(self, text: str) -> None:
        """Обработчик изменения текста поиска."""
        ...


@runtime_checkable
class UIStateManagerProtocol(Protocol):
    """Protocol для менеджера состояния UI."""

    def load_category(self, category_id: int, source: str = "") -> None:
        """Загружает категорию."""
        ...

    def get_current_category(self) -> Optional[int]:
        """Возвращает ID текущей категории."""
        ...


@runtime_checkable
class StructureBusinessProtocol(Protocol):
    """Protocol для бизнес-логики структуры."""

    current_sphere_id: Optional[int]
    structure_loaded: pyqtSignal
    async_operations: Optional[Any]

    def load_structure_async(self, sphere_id: int) -> None:
        """Асинхронно загружает структуру сферы."""
        ...


@runtime_checkable
class TopPanelsControllerProtocol(Protocol):
    """Protocol для контроллера верхних панелей."""

    data_loaded: pyqtSignal

    def refresh_all(self) -> None:
        """Обновляет все панели."""
        ...


class ResourceManagerProtocol(Protocol):
    """Protocol для менеджера ресурсов с централизованным cleanup.
    
    УЛУЧШЕНИЕ: Новый Protocol для управления жизненным циклом ресурсов.
    """

    def register_resource(self, resource: Any, cleanup_func: Callable[[], None]) -> None:
        """Регистрирует ресурс для автоматической очистки."""
        ...

    def cleanup_all(self) -> None:
        """Очищает все зарегистрированные ресурсы."""
        ...

    def is_cleaned_up(self) -> bool:
        """Проверяет, были ли очищены ресурсы."""
        ...
