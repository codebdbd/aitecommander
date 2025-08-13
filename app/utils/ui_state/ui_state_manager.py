# app/utils/ui_state_manager.py

"""Централизованный менеджер состояния UI для устранения дублирования логики."""

import logging
from typing import Optional

from app.config_data import app_config


class UIStateManager:
    """Централизованный менеджер для управления состоянием UI компонентов.
    
    ЕДИНСТВЕННАЯ ТОЧКА ОТВЕТСТВЕННОСТИ за загрузку категорий в приложении.
    Устраняет дублирование логики load_category в 15+ местах.
    """
    
    def __init__(self, main_window):
        self.main = main_window
        self.logger = logging.getLogger(__name__)
        # Простой флаг, чтобы не запускать параллельные загрузки одной категории
        self._loading: bool = False
    
    def load_category(self, category_id: int, source: str = "unknown") -> bool:
        """ЕДИНСТВЕННЫЙ метод для загрузки категорий в приложении.
        
        Заменяет все дублированные реализации:
        - MainWindow.load_category()
        - LinksUIController.load_category() (только UI координация)
        - BaseCommand.update_links_table()
        - SelectionHandling вызовы
        - Dialog контроллеры вызовы
        
        Args:
            category_id: ID категории для загрузки
            source: Источник вызова для логирования и отладки
            
        Returns:
            bool: True если загрузка успешна, False при ошибке
        """
        # Простая защита от параллельных вызовов без сложной магии
        if self._loading:
            self.logger.info(f"load_category пропущен: уже идет загрузка (source={source})")
            return True

        try:
            self._loading = True
            self.logger.debug(f"Loading category {category_id} from {source}")
            
            # 1. Валидация входных данных
            if not isinstance(category_id, int) or category_id <= 0:
                self.logger.warning(f"Invalid category_id: {category_id} from {source}")
                return False
            
            # 2. Обновляем состояние приложения
            self.main.current_category_id = category_id
            
            # 3. Загружаем данные через бизнес-логику
            if hasattr(self.main, 'links_business') and self.main.links_business:
                self.main.links_business.load_links(category_id)
            elif hasattr(self.main, 'links') and self.main.links:
                # Fallback на UI контроллер (только для бизнес-логики)
                self.main.links.business.load_links(category_id)
            else:
                self.logger.error(f"No links business logic available for category {category_id}")
                return False
            
            # 4. Обновляем UI состояние
            self._switch_to_table_view()
            self._clear_tiles_selection()
            
            self.logger.debug(f"Successfully loaded category {category_id} from {source}")
            return True
            
        except Exception as e:
            self.logger.exception(f"Error loading category {category_id} from {source}: {e}")
            self._handle_load_error()
            return False
        finally:
            self._loading = False
    
    def _switch_to_table_view(self) -> None:
        """Переключить UI на таблицу ссылок."""
        if hasattr(self.main, 'stack'):
            table_index = app_config.get('ui.stack_indices.table', 1)
            self.main.stack.setCurrentIndex(table_index)
    
    def _handle_load_error(self) -> None:
        """Обработка ошибок загрузки категорий."""
        self._clear_tiles_selection()
        # Можно добавить показ уведомления пользователю в будущем
    
    
    def switch_to_category_tiles(self, categories_data: list) -> None:
        """Переключиться на плитки категорий для указанного раздела."""
        try:
            # 1. Устанавливаем данные категорий в плитки
            if hasattr(self.main, 'tiles') and self.main.tiles:
                self.main.tiles.set_categories(categories_data)
            
            # 2. Переключаем стек на плитки категорий
            if hasattr(self.main, 'stack'):
                tiles_index = app_config.get('ui.stack_indices.tiles', 0)
                self.main.stack.setCurrentIndex(tiles_index)
                
        except Exception as e:
            self.logger.exception(f"Ошибка при переключении на плитки категорий: {e}")
    
    def update_category_without_stack_switch(self, category_id: int) -> bool:
        """Обновить текущую категорию без переключения стека.
        
        Используется для обновления данных без изменения текущего вида.
        
        Returns:
            bool: True если обновление успешно
        """
        try:
            self.logger.debug(f"Updating category {category_id} without stack switch")
            
            # 1. Валидация входных данных
            if not isinstance(category_id, int) or category_id <= 0:
                self.logger.warning(f"Invalid category_id: {category_id}")
                return False
            
            # 2. Обновляем current_category_id
            self.main.current_category_id = category_id
            
            # 3. Загружаем данные через бизнес-логику (БЕЗ переключения UI)
            if hasattr(self.main, 'links_business') and self.main.links_business:
                self.main.links_business.load_links(category_id)
            elif hasattr(self.main, 'links') and self.main.links:
                self.main.links.business.load_links(category_id)
            else:
                self.logger.error(f"No links business logic available for category {category_id}")
                return False
            
            return True
                
        except Exception as e:
            self.logger.exception(f"Error updating category {category_id}: {e}")
            return False
    
    def _clear_tiles_selection(self) -> None:
        """Сбросить выбор плиток категорий."""
        if hasattr(self.main, 'tiles') and self.main.tiles:
            self.main.tiles._current_item_id = None
    
    def clear_tiles_selection(self) -> None:
        """Публичный метод для сброса выбора плиток категорий."""
        self._clear_tiles_selection()
    
    def get_stack_index_table(self) -> int:
        """Получить индекс стека для таблицы ссылок."""
        return app_config.get('ui.stack_indices.table', 1)
    
    def get_stack_index_tiles(self) -> int:
        """Получить индекс стека для плиток категорий."""
        return app_config.get('ui.stack_indices.tiles', 0)
    

    
    # ========== МЕТОДЫ ДЛЯ ОТЛАДКИ И МОНИТОРИНГА ==========
    
    def get_current_category_id(self) -> Optional[int]:
        """Получить текущий ID категории."""
        return getattr(self.main, 'current_category_id', None)
    
    def is_category_loaded(self, category_id: int) -> bool:
        """Проверить, загружена ли указанная категория."""
        current_id = self.get_current_category_id()
        return current_id == category_id
    
    def get_load_category_stats(self) -> dict:
        """Получить статистику использования load_category для отладки."""
        # В будущем можно добавить счетчики вызовов по источникам
        return {
            'current_category_id': self.get_current_category_id(),
            'ui_state_manager_available': True,
            'links_business_available': hasattr(self.main, 'links_business') and bool(self.main.links_business),
            'links_ui_available': hasattr(self.main, 'links') and bool(self.main.links)
        }
