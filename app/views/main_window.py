from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QUndoStack
from PyQt6.QtWidgets import QMainWindow, QWidget

from app.views.link import LinksTableView

if TYPE_CHECKING:
    from app.controllers.ui.links.links_actions import LinksActions
    from app.controllers.ui.menu_controller import ActionController, MenuController
    from app.controllers.ui.state.ui_state_manager import UIStateManager
    from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
    from app.controllers.ui.structure.structure_ui_controller import (
        StructureUIController,
    )
    from app.controllers.ui.theme_controller import ThemeController
    from app.controllers.ui.top_panels_controller import TopPanelsController

from app.settings import AppSettings
from app.utils.db.synchronization import signal_guard
from app.views.status_bar import update_status_bar as _update_status_bar


class MainWindow(QMainWindow):
    shown: pyqtSignal = pyqtSignal()

    structure: "StructureUIController"
    menu_controller: "MenuController"
    action_controller: "ActionController"
    links_actions: "LinksActions"
    spheres_controller: "SpheresBarController"
    top_panels_controller: "TopPanelsController"
    ui_state: "UIStateManager"
    system_dialogs: object
    theme_ctrl: "ThemeController"
    table: LinksTableView
    left_panel: QWidget
    undo_stack: Optional[QUndoStack]

    def handle_import_browser_bookmarks(self):
        self.system_dialogs.handle_import_browser_bookmarks()

    def get_current_category_id(self) -> Optional[int]:
        """Возвращает ID текущей категории или None до инициализации."""
        structure = getattr(self, "structure", None)
        if structure is None:
            return None
        return structure.get_current_category_id()

    def edit_structure_item(self, item):
        """Редактирует элемент структуры."""
        self.structure.edit_item(item)

    def add_new_category(self):
        """Добавляет новую категорию."""
        self.structure.add_new_category()

    def reload_structure(self) -> None:
        """Перезагружает структуру."""
        self.structure.load()

    def reload_current_category(self) -> None:
        """Перезагружает текущую категорию через UIStateManager."""
        category_id = self.get_current_category_id()
        if category_id:
            self.ui_state.load_category(category_id, source="reload_current_category")

    def get_link_at_row(self, row: int):
        """Возвращает ссылку по номеру строки."""
        return self.links_actions.get_link_at(row)

    def select_all_links(self):
        """Выделяет все ссылки."""
        self.table.selectAll()

    def get_selected_rows(self):
        """Возвращает номера выбранных строк."""
        return self.links_actions.get_selected_rows()

    def get_available_themes(self):
        """Возвращает список доступных тем."""
        return self.theme_ctrl.available()

    def apply_theme(self, theme_name: str):
        """Применяет тему."""
        self.theme_ctrl.apply(theme_name)

    def get_undo_stack(self):
        """Возвращает undo stack или None."""
        return getattr(self, "undo_stack", None)

    def create_undo_redo_actions(self):
        """Создает действия Undo/Redo."""
        us = getattr(self, "undo_stack", None)
        if us is None:
            return None, None

        undo_action = us.createUndoAction(self)
        undo_action.setText("&Отменить")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)

        redo_action = us.createRedoAction(self)
        redo_action.setText("&Повторить")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)

        us.undoTextChanged.connect(lambda *_: undo_action.setText("&Отменить"))
        us.redoTextChanged.connect(lambda *_: redo_action.setText("&Повторить"))

        self.undo_action = undo_action
        self.redo_action = redo_action

        return undo_action, redo_action

    def __init__(self, settings: AppSettings, theme_ctrl: ThemeController):
        super().__init__()
        # Инициализация перенесена в bootstrap. Здесь только приём базовых зависимостей.
        self.settings = settings
        self.theme_ctrl = theme_ctrl

    def _init_spheres_ui(self):
        """Инициализирует UI сфер (асинхронно)."""
        self.spheres_controller.init()

    def _on_spheres_loaded_ui(self, spheres: list):
        """Обрабатывает завершение загрузки сфер."""
        self.spheres_controller._on_spheres_loaded_ui(spheres)

    @signal_guard("_update_active_sphere_button")
    def _update_active_sphere_button(self, sphere_id: int):
        """Обновляет состояние кнопок сфер через контроллер."""
        self.spheres_controller._update_active_sphere_button(sphere_id)

    def show_link_dialog(self, link=None, category_id=None):
        """Показывает диалог создания/редактирования ссылки."""
        selected_link_id = link.get("id") if link else None

        result = self.links_actions.show_link_dialog(link, category_id)
        self.update_statusbar()

        if result and selected_link_id:
            from app.controllers.ui.state.task_scheduler import (
                schedule_selection_restore,
            )

            schedule_selection_restore(
                lambda: getattr(
                    self.links_actions, "restore_selection", lambda *_: None
                )(selected_link_id),
                f"table_selection_{selected_link_id}",
            )
        # Возвращаем результат, чтобы внешние вызовы могли узнать об успешности
        return bool(result)

    def show_link_dialog_for_category(
        self, category_id: int | None = None, link=None
    ) -> bool:
        """Открывает диалог ссылки для указанной категории (используется плитками категорий)."""
        return bool(self.show_link_dialog(link=link, category_id=category_id))

    def _get_selected_links(self):
        """Возвращает список выбранных ссылок."""
        return self.links_actions.get_selected_links()

    def _edit_selected_link(self):
        """Редактирует выбранную ссылку."""
        return self.links_actions.edit_selected_link()

    def edit_current(self):
        """Редактирует текущий элемент."""
        self.action_controller.edit_current()

    def delete_current(self):
        """Удаляет текущий элемент (ссылку или структурный элемент)."""
        self.action_controller.delete_current()

    def show_section_dialog(self):
        self.structure.add_new_section()

    def show_category_dialog(self):
        self.structure.add_new_category()

    def update_statusbar(self):
        _update_status_bar(self)

    def on_structure_item_added(self, item_type: str, parent_id: int, data: dict):
        self.structure.on_structure_item_added(item_type, parent_id, data)

    @signal_guard("on_structure_item_changed")
    def on_structure_item_changed(self, item_type: str, item_id: int, data: dict):
        self.structure.on_structure_item_changed(item_type, item_id, data)

    def show_about_dialog(self):
        self.system_dialogs.show_about_dialog()

    def show_settings_dialog(self):
        self.system_dialogs.show_settings_dialog()

    def show_file_search_dialog(self):
        self.system_dialogs.show_file_search_dialog()

    def update_theme(self):
        """Применяет тему и обновляет UI."""
        self.theme_ctrl.apply_and_refresh_ui()

    def _switch_sphere(self, sphere_id: int) -> None:
        self.spheres_controller._switch_sphere(sphere_id)

    @signal_guard("_update_left_panel_style")
    def _update_left_panel_style(self, sphere_id: int):
        """Обновляет стиль левой панели при смене сферы."""
        current_sphere = self.left_panel.property("sphere")
        if current_sphere == str(sphere_id):
            return

        self.left_panel.setUpdatesEnabled(False)
        try:
            self.left_panel.setProperty("sphere", str(sphere_id))
            self.left_panel.style().unpolish(self.left_panel)
            self.left_panel.style().polish(self.left_panel)
        finally:
            self.left_panel.setUpdatesEnabled(True)

    def on_search(self, text: str):
        self.links_actions.on_search(text)

    def showEvent(self, event):
        """Эмитит сигнал shown при первом показе окна."""
        super().showEvent(event)
        if not hasattr(self, "_shown_emitted"):
            self._shown_emitted = True
            QTimer.singleShot(200, self.shown.emit)

    def closeEvent(self, event):
        """Корректно завершает работу и закрывает ресурсы."""
        if hasattr(self, "app_shutdown") and self.app_shutdown:
            self.app_shutdown.perform_shutdown(event)
            return
        super().closeEvent(event)
