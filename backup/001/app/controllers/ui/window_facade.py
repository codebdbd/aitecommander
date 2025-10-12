"""Фасад для упрощения доступа к функционалу главного окна.

Этот модуль предоставляет централизованный доступ к основным операциям
главного окна, скрывая сложность взаимодействия между контроллерами.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from typing import Any, Dict
    
    LinkDict = Dict[str, Any]
    
    from app.controllers.ui.links.links_actions import LinksActions
    from app.controllers.ui.menu_controller import ActionController
    from app.controllers.ui.structure.structure_ui_controller import StructureUIController
    from app.controllers.ui.state.ui_state_manager import UIStateManager
    from app.controllers.ui.theme_controller import ThemeController

logger = logging.getLogger(__name__)


class WindowFacade:
    """Фасад для операций главного окна.
    
    Инкапсулирует логику делегирования к специализированным контроллерам.
    Упрощает MainWindow, перенося всю логику координации сюда.
    
    Attributes:
        structure: Контроллер структуры (дерево, разделы, категории)
        links_actions: Контроллер операций со ссылками
        ui_state: Менеджер состояния UI
        action_controller: Контроллер действий (редактирование, удаление)
        theme_ctrl: Контроллер тем
    """
    
    def __init__(
        self,
        structure: "StructureUIController",
        links_actions: "LinksActions",
        ui_state: "UIStateManager",
        action_controller: "ActionController",
        theme_ctrl: "ThemeController",
    ):
        """Инициализирует фасад с необходимыми контроллерами.
        
        Args:
            structure: Контроллер структуры
            links_actions: Контроллер ссылок
            ui_state: Менеджер состояния UI
            action_controller: Контроллер действий
            theme_ctrl: Контроллер тем
        """
        self.structure = structure
        self.links_actions = links_actions
        self.ui_state = ui_state
        self.action_controller = action_controller
        self.theme_ctrl = theme_ctrl
        
        logger.debug("WindowFacade инициализирован")
    
    # === Операции со структурой ===
    
    def get_current_category_id(self) -> Optional[int]:
        """Возвращает ID текущей выбранной категории.
        
        Returns:
            ID категории или None, если категория не выбрана
        """
        return self.structure.get_current_category_id()
    
    def reload_structure(self) -> None:
        """Перезагружает всю структуру (дерево)."""
        self.structure.load()
    
    def reload_current_category(self) -> None:
        """Перезагружает текущую категорию.
        
        Использует UIStateManager для сохранения состояния.
        """
        category_id = self.get_current_category_id()
        if category_id:
            self.ui_state.load_category(category_id, source="reload_current_category")
        else:
            logger.debug("reload_current_category: категория не выбрана")
    
    def add_new_section(self) -> None:
        """Открывает диалог создания нового раздела."""
        self.structure.add_new_section()
    
    def add_new_category(self) -> None:
        """Открывает диалог создания новой категории."""
        self.structure.add_new_category()
    
    # === Операции со ссылками ===
    
    def get_link_at_row(self, row: int) -> "LinkDict | None":
        """Возвращает ссылку по номеру строки в таблице.
        
        Args:
            row: Номер строки (0-indexed)
            
        Returns:
            Словарь с данными ссылки или None
        """
        return self.links_actions.get_link_at(row)
    
    def get_selected_links(self) -> list["LinkDict"]:
        """Возвращает список выбранных ссылок.
        
        Returns:
            Список словарей с данными ссылок
        """
        return self.links_actions.get_selected_links()
    
    def get_selected_rows(self) -> list[int]:
        """Возвращает номера выбранных строк.
        
        Returns:
            Список индексов строк
        """
        return self.links_actions.get_selected_rows()
    
    def show_link_dialog(
        self,
        link: "LinkDict | None" = None,
        category_id: int | None = None,
    ) -> bool:
        """Показывает диалог создания/редактирования ссылки.
        
        Args:
            link: Существующая ссылка для редактирования (None для создания новой)
            category_id: ID категории для новой ссылки
            
        Returns:
            True если диалог был применён, False если отменён
        """
        selected_link_id = link.get("id") if link else None
        
        result = self.links_actions.show_link_dialog(link, category_id)
        
        if result and selected_link_id:
            # Планирование восстановления выделения
            self.links_actions.schedule_restore_selection(selected_link_id)
        
        return bool(result)
    
    def edit_selected_link(self) -> bool:
        """Редактирует выбранную ссылку.
        
        Returns:
            True если редактирование прошло успешно
        """
        return bool(self.links_actions.edit_selected_link())
    
    # === Универсальные действия ===
    
    def edit_current(self) -> None:
        """Редактирует текущий выбранный элемент (ссылку или структурный элемент).
        
        ActionController автоматически определяет, что редактировать.
        """
        self.action_controller.edit_current()
    
    def delete_current(self) -> None:
        """Удаляет текущий выбранный элемент (ссылку или структурный элемент).
        
        ActionController автоматически определяет, что удалять, и запрашивает подтверждение.
        """
        self.action_controller.delete_current()
    
    # === Операции с темами ===
    
    def get_available_themes(self) -> list[tuple[str, str]]:
        """Возвращает список доступных тем.
        
        Returns:
            Список кортежей (theme_id, theme_display_name)
        """
        return self.theme_ctrl.available()
    
    def apply_theme(self, theme_name: str) -> None:
        """Применяет тему оформления.
        
        Args:
            theme_name: Идентификатор темы (например, 'light', 'dark')
        """
        self.theme_ctrl.apply(theme_name)
    
    def update_theme(self) -> None:
        """Обновляет текущую тему и перерисовывает UI."""
        self.theme_ctrl.apply_and_refresh_ui()
    
    # === Служебные методы ===
    
    def on_structure_item_added(
        self, item_type: str, parent_id: int, data: dict
    ) -> None:
        """Обрабатывает добавление элемента структуры.
        
        Args:
            item_type: Тип элемента ('section', 'category')
            parent_id: ID родительского элемента
            data: Данные элемента
        """
        self.structure.on_structure_item_added(item_type, parent_id, data)
    
    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        """Обрабатывает изменение элемента структуры.
        
        Args:
            item_type: Тип элемента ('section', 'category')
            item_id: ID элемента
            data: Новые данные элемента
        """
        self.structure.on_structure_item_changed(item_type, item_id, data)
