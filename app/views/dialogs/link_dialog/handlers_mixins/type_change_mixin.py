"""
Миксин для смены типа ссылки и обновления UI в LinkDialogHandlers.
"""
import logging
from pathlib import Path

from PyQt6.QtGui import QIcon

from app.models.link_type import LinkType
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.ui_helpers import set_icon_to_button

logger = logging.getLogger(__name__)


class TypeChangeMixin:
    def on_type_changed(self, link_type) -> None:
        """Обработчик изменения типа ссылки."""
        lt = LinkType.from_value(link_type)
        self.dialog.link_type = lt

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
                logger.debug("Ошибка отмены активного воркера: %s", e)
            self._active_worker = None

        # Установка иконки по умолчанию через централизованный резолвер
        try:
            resolved_icon_path = resolve_icon_for_link(
                {"type": lt.value, "icon_path": ""}
            )
        except (AttributeError, KeyError, ValueError) as e:
            logger.warning("Ошибка резолвинга иконки для типа %s: %s", link_type, e)
            resolved_icon_path = ""
        self.dialog.icon_name = (
            Path(resolved_icon_path).name if resolved_icon_path else ""
        )
        if resolved_icon_path and Path(resolved_icon_path).exists():
            set_icon_to_button(
                self.dialog._get_icon_btn(), resolved_icon_path
            )
        else:
            self.dialog._get_icon_btn().setIcon(QIcon())

        self._update_ui_state()

    def _update_ui_state(self) -> None:
        """Обновляет состояние UI в зависимости от типа ссылки."""
        lt = LinkType.from_value(self.dialog.link_type)
        is_web = lt == LinkType.WEB
        profile_btn = self.dialog._get_profile_btn()
        browse_btn = self.dialog._get_browse_btn()
        args_le = self.dialog._get_args_le()
        args_label = self.dialog._get_args_label()

        profile_btn.setVisible(is_web)

        # Кнопка 'Обзор' для определенных типов
        browse_btn.setVisible(
            lt in (
                LinkType.FILE,
                LinkType.FOLDER,
                LinkType.PROGRAM,
                LinkType.SCRIPT,
                LinkType.CHROMEAPP,
            )
        )

        # Аргументы только для типов, где они предусмотрены
        args_supported_types = (LinkType.PROGRAM, LinkType.SCRIPT, LinkType.CHROMEAPP, LinkType.WEB)
        show_args = lt in args_supported_types
        args_le.setVisible(show_args)
        args_label.setVisible(show_args)

    def set_link_type(self, link_type) -> None:
        """Программно выбрать тип ссылки и обновить UI."""
        # Безопасно получаем список доступных типов из диалога
        try:
            link_types = getattr(self.dialog, "link_types", None)
        except (AttributeError, RuntimeError):
            link_types = None

        if not link_types:
            return

        # Нормализуем link_types к множеству кодов типов (строки)
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
        except (TypeError, ValueError, AttributeError) as e:
            # В спорных случаях просто выходим тихо, не меняя состояние
            logging.debug("set_link_type: ошибка нормализации link_types: %s", e)
            return

        # Поддерживаем внешние вызовы как строками, так и Enum
        lt = LinkType.from_value(link_type)
        if lt.value not in codes:
            return

        type_group = self.dialog.ui.widgets["type_group"]
        for btn in type_group.buttons():
            if btn.property("link_type") == lt.value:
                btn.setChecked(True)
                break

        # Для обратной совместимости вызываем обработчик с исходным значением
        # (строкой), так как тесты ожидают именно строковый аргумент.
        self.on_type_changed(link_type)
