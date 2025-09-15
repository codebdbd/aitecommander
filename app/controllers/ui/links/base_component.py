"""Базовый компонент для модуля links_ui."""

import logging
from typing import Dict, Optional

from app.config_data import app_config

from .exceptions import CategoryNotFoundError, DatabaseError

logger = logging.getLogger(__name__)


class BaseLinksUIComponent:
    """Базовый класс для всех компонентов LinksUI."""

    def __init__(self, controller, link_operations, links_table_controller=None):
        self.controller = controller
        self.table = controller.table
        self.business = controller.business
        self.main = controller.main
        # Обязательная зависимость: link_operations должен быть передан явно
        if link_operations is None:
            raise ValueError(
                "BaseLinksUIComponent requires explicit 'link_operations' dependency"
            )
        self.link_operations = link_operations
        # Явная зависимость для links_table_controller; fallback — взять из контроллера, если есть
        self.links_table_controller = links_table_controller or getattr(
            controller, "table_controller", None
        )

        # Кешируем конфигурацию для производительности
        self._config = app_config.ui
        self._columns = self._config.get_links_table_columns()
        self._messages = self._config.get_links_table_messages()

    @property
    def COLUMNS(self) -> Dict[str, int]:
        """Индексы колонок таблицы ссылок."""
        return self._columns

    @property
    def MESSAGES(self) -> Dict[str, str]:
        """Сообщения для пользователя."""
        return self._messages

    def get_message(self, key: str, default: Optional[str] = None) -> str:
        """Получить сообщение по ключу."""
        return self._messages.get(key, default or f"Message '{key}' not found")

    def _update_category_safe(self, category_id: int) -> None:
        """Безопасное обновление категории с fallback."""
        try:
            # 1) Предпочитаем явную зависимость, переданную в компонент
            ctrl = self.links_table_controller
            if ctrl is not None:
                ctrl.reload(category_id)
                return

            # 2) Фолбэк: попытаться взять контроллер из main (для совместимости)
            ctrl_from_main = getattr(self.main, "links_table_controller", None)
            if ctrl_from_main is not None:
                ctrl_from_main.reload(category_id)
                return

            # 3) Финальный фолбэк: напрямую дернуть бизнес-логику
            # (без UI-контроллера таблицы; может дать менее согласованное поведение)
            self.business.load_links(category_id)
        except Exception as e:
            logger.error("Error updating category %s: %s", category_id, e)
            raise DatabaseError(f"Failed to update category: {str(e)}")

    def _show_warning(self, message: str, title: Optional[str] = None) -> None:
        """Показать предупреждение пользователю."""
        from app.controllers.ui.dialogs import DialogManager

        title = title or self.get_message("warning_title")
        DialogManager.show_warning(
            self.main,
            title,
            message,
            informative_text="Проверьте корректность данных и повторите попытку.",
        )

    def _show_error(self, message: str, title: Optional[str] = None) -> None:
        """Показать ошибку пользователю."""
        from app.controllers.ui.dialogs import DialogManager

        title = title or self.get_message("error_title")
        DialogManager.show_error(
            self.main,
            title,
            message,
            informative_text="Попробуйте ещё раз или обратитесь в поддержку.",
        )

    def _validate_category_exists(self, category_id: Optional[int]) -> int:
        """Проверить существование категории."""
        if not category_id:
            current_category_id = self.main.get_current_category_id()
            if not current_category_id:
                raise CategoryNotFoundError(self.get_message("no_categories"))
            return current_category_id
        return category_id
