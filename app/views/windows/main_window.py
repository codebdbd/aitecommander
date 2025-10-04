from __future__ import annotations

import logging
import weakref
from contextlib import suppress
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QEvent, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QUndoStack
from PyQt6.QtWidgets import QMainWindow, QWidget

from app.utils.ui.timings import SEARCH_RETRY_ATTEMPTS, SEARCH_RETRY_INTERVAL_MS
from app.views.widgets.link import LinksTableView
from app.ui.retranslatable import ReTranslatable

if TYPE_CHECKING:
    # Узкоспециализированные типы только для статического анализа
    from typing import Any, Dict, Protocol

    class StructureItem(Protocol):
        """Элемент структуры (дерева). Минимальный протокол для статпроверки.

        Конкретный тип в рантайме может быть `QModelIndex` или объект модели дерева.
        Здесь протокол пустой, так как `MainWindow` лишь проксирует объект дальше.
        """

        ...

    LinkDict = Dict[str, Any]
    from app.controllers.ui.links.links_actions import LinksActions
    from app.controllers.ui.menu_controller import ActionController, MenuController
    from app.controllers.ui.state.ui_state_manager import UIStateManager
    from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
    from app.controllers.ui.structure.structure_ui_controller import (
        StructureUIController,
    )
    from app.controllers.ui.theme_controller import ThemeController
    from app.controllers.ui.top_panels_controller import TopPanelsController

from app.controllers.ui.window_facade import WindowFacade
from app.settings import AppSettings
from app.utils.db.synchronization import signal_guard
from app.utils.ui.updates import suspend_updates
from app.views.widgets.status_bar import update_status_bar as _update_status_bar

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow, ReTranslatable):
    """Главное окно приложения.
    
    Координирует работу контроллеров через WindowFacade.
    Основная ответственность - UI layout и обработка событий Qt.
    """
    
    shown: pyqtSignal = pyqtSignal()

    # Контроллеры (инициализируются в bootstrap)
    structure: "StructureUIController"
    menu_controller: "MenuController"
    action_controller: "ActionController"
    links_actions: "LinksActions"
    spheres_controller: "SpheresBarController"
    top_panels_controller: "TopPanelsController"
    ui_state: "UIStateManager"
    system_dialogs: object
    theme_ctrl: "ThemeController"
    
    # UI компоненты
    table: LinksTableView
    left_panel: QWidget
    
    # Undo/Redo
    undo_stack: Optional[QUndoStack]
    undo_action: Optional[QAction]
    redo_action: Optional[QAction]
    
    # Фасад для упрощения делегирования
    facade: Optional[WindowFacade]

    def handle_import_browser_bookmarks(self) -> None:
        self.system_dialogs.handle_import_browser_bookmarks()

    # === Делегирование через фасад ===
    
    def get_current_category_id(self) -> Optional[int]:
        """Возвращает ID текущей категории."""
        return self.facade.get_current_category_id() if self.facade else None

    def edit_structure_item(self, item: "StructureItem") -> None:
        """Редактирует элемент структуры."""
        self.structure.edit_item(item)

    def add_new_category(self) -> None:
        """Добавляет новую категорию."""
        if self.facade:
            self.facade.add_new_category()

    def reload_structure(self) -> None:
        """Перезагружает структуру."""
        if self.facade:
            self.facade.reload_structure()

    def reload_current_category(self) -> None:
        """Перезагружает текущую категорию."""
        if self.facade:
            self.facade.reload_current_category()

    def get_link_at_row(self, row: int) -> "LinkDict | None":
        """Возвращает ссылку по номеру строки."""
        return self.facade.get_link_at_row(row) if self.facade else None

    def select_all_links(self) -> None:
        """Выделяет все ссылки."""
        self.table.selectAll()

    def get_selected_rows(self) -> list[int]:
        """Возвращает номера выбранных строк."""
        return self.facade.get_selected_rows() if self.facade else []

    def get_available_themes(self) -> list[tuple[str, str]]:
        """Возвращает список доступных тем.
        
        Примечание: Использует theme_ctrl напрямую, т.к. вызывается до инициализации фасада.
        """
        # Меню создается рано, до facade, поэтому прямой доступ
        return self.theme_ctrl.available() if hasattr(self, 'theme_ctrl') else []

    def apply_theme(self, theme_name: str) -> None:
        """Применяет тему.
        
        Примечание: Использует theme_ctrl напрямую, т.к. вызывается до инициализации фасада.
        """
        # Меню используется рано, до facade, поэтому прямой доступ
        if hasattr(self, 'theme_ctrl'):
            self.theme_ctrl.apply(theme_name)

    def get_undo_stack(self) -> Optional[QUndoStack]:
        """Возвращает undo stack или None."""
        return getattr(self, "undo_stack", None)

    def create_undo_redo_actions(self) -> tuple[Optional[QAction], Optional[QAction]]:
        """Создает действия Undo/Redo."""
        us = getattr(self, "undo_stack", None)
        if us is None:
            return None, None

        undo_action = us.createUndoAction(self)
        undo_action.setText(self.tr("&Undo"))
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)

        redo_action = us.createRedoAction(self)
        redo_action.setText(self.tr("&Redo"))
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)

        us.undoTextChanged.connect(lambda *_: undo_action.setText(self.tr("&Undo")))
        us.redoTextChanged.connect(lambda *_: redo_action.setText(self.tr("&Redo")))

        self.undo_action = undo_action
        self.redo_action = redo_action

        # Диагностические логи undo/redo и состояния стека для расследования двойного вызова
        try:
            # Логируем активации действий меню/шорткатов
            undo_action.triggered.connect(
                lambda checked=False: logging.getLogger(__name__).debug(
                    "[UI] QAction.undo.triggered checked=%s", checked
                )
            )
            redo_action.triggered.connect(
                lambda checked=False: logging.getLogger(__name__).debug(
                    "[UI] QAction.redo.triggered checked=%s", checked
                )
            )
        except Exception:
            logger.debug(
                "MainWindow: failed to connect undo/redo triggered diagnostics",
                exc_info=True,
            )

        try:
            # Локальные безопасные колбэки через weakref, чтобы избежать обращения к удалённому объекту
            _us_ref = weakref.ref(us)

            def _on_index_changed(idx: int):
                u = _us_ref()
                if u is None:
                    return
                try:
                    can_undo = bool(u.canUndo())
                except RuntimeError:
                    return
                try:
                    can_redo = bool(u.canRedo())
                except RuntimeError:
                    return
                logging.getLogger(__name__).debug(
                    "[UndoStack] indexChanged=%s canUndo=%s canRedo=%s",
                    idx,
                    can_undo,
                    can_redo,
                )

            def _on_clean_changed(clean: bool):
                u = _us_ref()
                index_val = None
                if u is not None:
                    try:
                        index_val = u.index()
                    except RuntimeError:
                        index_val = None
                logging.getLogger(__name__).debug(
                    "[UndoStack] cleanChanged=%s index=%s", clean, index_val
                )

            us.indexChanged.connect(_on_index_changed)
            us.cleanChanged.connect(_on_clean_changed)
        except Exception:
            logger.debug(
                "MainWindow: failed to connect undo stack diagnostics (index/clean)",
                exc_info=True,
            )
        try:
            us.canUndoChanged.connect(
                lambda can: logging.getLogger(__name__).debug(
                    "[UndoStack] canUndoChanged=%s", can
                )
            )
        except Exception:
            logger.debug(
                "MainWindow: failed to connect canUndoChanged diagnostics",
                exc_info=True,
            )
        try:
            us.canRedoChanged.connect(
                lambda can: logging.getLogger(__name__).debug(
                    "[UndoStack] canRedoChanged=%s", can
                )
            )
        except Exception:
            logger.debug(
                "MainWindow: failed to connect canRedoChanged diagnostics",
                exc_info=True,
            )

        return undo_action, redo_action

    def __init__(self, settings: AppSettings, theme_ctrl: ThemeController):
        super().__init__()
        # Инициализация перенесена в bootstrap. Здесь только приём базовых зависимостей.
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        self.facade = None  # Будет установлен в bootstrap после инициализации контроллеров

        # Debounce таймер для поиска
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)  # 300ms задержка
        self._search_timer.timeout.connect(self._execute_search)
        self._pending_search = ""

        ReTranslatable.__init__(self)

    def retranslateUi(self) -> None:
        undo_action = getattr(self, "undo_action", None)
        if undo_action is not None:
            undo_action.setText(self.tr("&Undo"))
        redo_action = getattr(self, "redo_action", None)
        if redo_action is not None:
            redo_action.setText(self.tr("&Redo"))


    def _init_spheres_ui(self) -> None:
        """Инициализирует UI сфер (асинхронно)."""
        self.spheres_controller.init()

    def show_link_dialog(
        self,
        link: "LinkDict | None" = None,
        category_id: int | None = None,
    ) -> bool:
        """Показывает диалог создания/редактирования ссылки."""
        if not self.facade:
            return False

        result = self.facade.show_link_dialog(link, category_id)
        self.update_statusbar()
        return result

    def show_link_dialog_for_category(
        self, category_id: int | None = None, link: "LinkDict | None" = None
    ) -> bool:
        """Открывает диалог ссылки для указанной категории."""
        return self.show_link_dialog(link=link, category_id=category_id)

    def _get_selected_links(self) -> list["LinkDict"]:
        """Возвращает список выбранных ссылок."""
        return self.facade.get_selected_links() if self.facade else []

    def _edit_selected_link(self) -> bool:
        """Редактирует выбранную ссылку."""
        return self.facade.edit_selected_link() if self.facade else False

    def edit_current(self) -> None:
        """Редактирует текущий элемент."""
        if self.facade:
            self.facade.edit_current()

    def delete_current(self) -> None:
        """Удаляет текущий элемент."""
        if self.facade:
            self.facade.delete_current()

    def show_section_dialog(self) -> None:
        """Открывает диалог создания раздела."""
        if self.facade:
            self.facade.add_new_section()

    def update_statusbar(self) -> None:
        _update_status_bar(self)

    def on_structure_item_added(
        self, item_type: str, parent_id: int, data: dict
    ) -> None:
        """Обрабатывает добавление элемента структуры."""
        if self.facade:
            self.facade.on_structure_item_added(item_type, parent_id, data)

    @signal_guard("on_structure_item_changed")
    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        """Обрабатывает изменение элемента структуры."""
        if self.facade:
            self.facade.on_structure_item_changed(item_type, item_id, data)

    def show_about_dialog(self) -> None:
        self.system_dialogs.show_about_dialog()

    def show_settings_dialog(self) -> None:
        self.system_dialogs.show_settings_dialog()

    def show_file_search_dialog(self) -> None:
        self.system_dialogs.show_file_search_dialog()

    def update_theme(self) -> None:
        """Применяет тему и обновляет UI."""
        if self.facade:
            self.facade.update_theme()

    def update_widget_font_size(self, widget, size: int) -> None:
        """Унифицированно применяет размер шрифта к переданному виджету.

        Ожидается, что у виджета есть метод `update_font_size(int)`.
        Безопасно обрабатывает отсутствие атрибута/метода и редкие непредвиденные ошибки.

        Примечание: со временем логику можно перенести в соответствующие контроллеры
        дерева/таблицы, а здесь оставить только делегирование.
        """
        try:
            with suppress(AttributeError, RuntimeError, TypeError, ValueError):
                if widget and hasattr(widget, "update_font_size"):
                    widget.update_font_size(size)
        except Exception:
            # Лог с типом виджета для диагностики неожиданных ошибок
            logger.exception(
                "MainWindow: unexpected error updating font size for %s",
                type(widget).__name__ if widget is not None else "<None>",
            )

    def apply_font_size_to_content(self, fs: int) -> None:
        """Централизованно применяет размер шрифта к основным контент‑виджетам.

        Применяется ТОЛЬКО к дереву и таблице (пользовательская настройка).
        """
        if isinstance(fs, bool):  # защитимся от ошибок типов
            return
        try:
            size = int(fs)
        except (TypeError, ValueError):
            return

        # Дерево
        tree = getattr(self, "tree", None)
        self.update_widget_font_size(tree, size)

        # Таблица
        table = getattr(self, "table", None)
        self.update_widget_font_size(table, size)

        # Плитки категорий — намеренно НЕ меняем здесь, их шрифт независим

    @signal_guard("_update_left_panel_style")
    def _update_left_panel_style(self, sphere_id: int) -> None:
        """Обновляет стиль левой панели при смене сферы."""
        current_sphere = self.left_panel.property("sphere")
        if current_sphere == str(sphere_id):
            return

        with suspend_updates(self.left_panel):
            self.left_panel.setProperty("sphere", str(sphere_id))
            self.left_panel.style().unpolish(self.left_panel)
            self.left_panel.style().polish(self.left_panel)

    def on_search(self, text: str) -> None:
        """Откладывает выполнение поиска на 300ms (debounce)."""
        self._pending_search = text
        self._search_timer.start()  # Перезапускает таймер при каждом вводе

    def _execute_search(self) -> None:
        """Выполняет поиск после задержки."""
        la = getattr(self, "links_actions", None)
        if la is None:
            logger.debug("MainWindow: links_actions ещё не инициализирован")
            return
        try:
            la.on_search(self._pending_search)
        except Exception:
            logger.exception("MainWindow._execute_search failed")

    def showEvent(self, event: QEvent) -> None:
        """Эмитит сигнал shown при первом показе окна."""
        super().showEvent(event)
        if not hasattr(self, "_shown_emitted"):
            self._shown_emitted = True
            # Отложенный вызов через очередь событий Qt
            # Предотвращает блокировку отрисовки окна, если слот выполняет тяжёлую операцию
            QTimer.singleShot(0, self.shown.emit)

    def closeEvent(self, event: QEvent) -> None:
        """Корректно завершает работу и закрывает ресурсы."""
        logger.info("MainWindow.closeEvent: initiating shutdown")
        
        # Останавливаем search timer для предотвращения утечек
        try:
            if hasattr(self, '_search_timer'):
                self._search_timer.stop()
                self._search_timer.deleteLater()
        except (AttributeError, RuntimeError):
            pass
        
        if hasattr(self, "app_shutdown") and self.app_shutdown:
            try:
                logger.info("MainWindow.closeEvent: delegating to AppShutdownController")
                self.app_shutdown.perform_shutdown(event)
                return
            except Exception:
                logger.exception("MainWindow.closeEvent: AppShutdownController failed, falling back to base closeEvent")
        super().closeEvent(event)
