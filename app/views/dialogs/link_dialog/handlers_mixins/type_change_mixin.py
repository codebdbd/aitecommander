"""
Миксин для смены типа ссылки и обновления UI в LinkDialogHandlers.
"""
import logging
from pathlib import Path
from PyQt6.QtGui import QIcon
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.ui_helpers import set_icon_to_button

logger = logging.getLogger(__name__)


class TypeChangeMixin:
    def on_type_changed(self, link_type: str) -> None:
        """Обработчик изменения типа ссылки."""
        self.dialog.link_type = link_type

        # Очистка полей при смене типа
        self.dialog.ui.set_widget_value("url_le", "")
        self.dialog.ui.set_widget_value("name_le", "")
        self.dialog.ui.set_widget_value("args_le", "")

        # Сброс состояния обработки ссылок для возможности повторного автозаполнения
        self._last_processed_path = ""
        self._is_processing = False

        # Отмена активной задачи при смене типа ссылки
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except (AttributeError, RuntimeError) as e:
                logger.debug(f"Ошибка отмены активного воркера: {e}")
            self._active_worker = None

        # Установка иконки по умолчанию через централизованный резолвер
        try:
            resolved_icon_path = resolve_icon_for_link(
                {"type": link_type, "icon_path": ""}
            )
        except (AttributeError, KeyError, ValueError) as e:
            logger.warning(f"Ошибка резолвинга иконки для типа {link_type}: {e}")
            resolved_icon_path = ""
        self.dialog.icon_name = (
            Path(resolved_icon_path).name if resolved_icon_path else ""
        )
        if resolved_icon_path and Path(resolved_icon_path).exists():
            set_icon_to_button(
                self.dialog.ui.get_widget("icon_btn"), resolved_icon_path
            )
        else:
            self.dialog.ui.get_widget("icon_btn").setIcon(QIcon())

        self._update_ui_state()

    def _update_ui_state(self) -> None:
        """Обновляет состояние UI в зависимости от типа ссылки."""
        is_web = self.dialog.link_type == "web"

        profile_btn = self.dialog.ui.get_widget("profile_btn")
        browse_btn = self.dialog.ui.get_widget("browse_btn")
        args_le = self.dialog.ui.get_widget("args_le")
        args_label = self.dialog.ui.get_widget("args_label")

        profile_btn.setVisible(is_web)

        # Кнопка 'Обзор' для определенных типов
        browse_btn.setVisible(
            self.dialog.link_type
            in ("file", "folder", "program", "script", "chromeapp")
        )

        # Аргументы только для типов, где они предусмотрены
        args_supported_types = ("program", "script", "chromeapp", "web")
        show_args = self.dialog.link_type in args_supported_types
        args_le.setVisible(show_args)
        args_label.setVisible(show_args)

    def set_link_type(self, link_type: str) -> None:
        """Программно выбрать тип ссылки и обновить UI."""
        # Безопасно получаем список доступных типов из диалога
        try:
            link_types = getattr(self.dialog, "link_types", None)
        except Exception:
            link_types = None

        if not link_types:
            return

        # Нормализуем link_types к множеству кодов типов
        codes = set()
        try:
            for item in link_types:
                if isinstance(item, (list, tuple)):
                    if len(item) >= 1:
                        codes.add(item[0])
                elif isinstance(item, dict):
                    code = item.get("code") or item.get("id") or item.get("type")
                    if code:
                        codes.add(code)
                else:
                    # Строка или произвольный скаляр
                    codes.add(str(item))
        except Exception as e:
            # В спорных случаях просто выходим тихо, не меняя состояние
            logging.debug(f"set_link_type: ошибка нормализации link_types: {e}")
            return

        if link_type not in codes:
            return

        type_group = self.dialog.ui.widgets["type_group"]
        for btn in type_group.buttons():
            if btn.property("link_type") == link_type:
                btn.setChecked(True)
                break

        self.on_type_changed(link_type)
