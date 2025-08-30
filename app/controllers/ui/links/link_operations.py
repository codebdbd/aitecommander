# app/controllers/links_ui/link_operations.py

import logging
from datetime import datetime
from typing import Dict

from PyQt6.QtWidgets import QDialog

from app.controllers.ui.undo.commands_links import SaveLinkCmd
from app.utils.links.link_utils import LinkInfo, LinkOpener
from app.views.dialogs.entity_dialogs import NoteDialog

from .base_component import BaseLinksUIComponent
from .exceptions import CategoryNotFoundError, DatabaseError, LinkValidationError

logger = logging.getLogger(__name__)


class LinksUILinkOperations(BaseLinksUIComponent):
    """Операции с ссылками для LinksUIController."""

    def quick_add_link(self, link_type: str, category_id: int = None):
        """Быстрое добавление ссылки."""
        try:
            cat_id = self._validate_category_exists(category_id)
        except CategoryNotFoundError as e:
            self._show_warning(str(e))
            return

        # Создаем контроллер для диалога
        from PyQt6.QtWidgets import QDialog

        from app.controllers.ui.dialogs import LinkDialogController
        from app.views.dialogs.link_dialog.link_dialog import LinkDialog

        link_controller = LinkDialogController(self.business.db)
        init_data = link_controller.get_initialization_data(cat_id, None)

        dlg = LinkDialog(
            initialization_data=init_data,
            dialog_controller=link_controller,
            link=None,
            category_id=cat_id,
            parent=self.main,
            link_controller=link_controller,
        )

        # Устанавливаем тип ссылки
        dlg.set_link_type(link_type)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            links_to_save = link_controller.get_result_data()
            if links_to_save:
                for data in links_to_save:
                    cmd = SaveLinkCmd(
                        new_data=data, old_data=None, main_window=self.main
                    )
                    self.main.undo_stack.push(cmd)

    def show_note_dialog(self, link: Dict):
        """Показать диалог заметки для ссылки."""
        if not link:
            return

        # Создаем копию ссылки для безопасности
        link_copy = link.copy()

        dlg = NoteDialog(link_copy, parent=self.main)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Обновляем ссылку через бизнес-логику
            try:
                # Бизнес-слой сам эмитит link_updated внутри save_link()
                self.business.save_link(link_copy)
                logger.debug(f"Note saved for link: {link_copy.get('name')}")
            except DatabaseError as e:
                logger.error(f"Database error saving note: {e}")
                self._show_error(f"{self.get_message('database_error')}: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error saving note: {e}")
                self._show_error(f"{self.get_message('error_saving')}: {str(e)}")

    def _open_link(self, link: Dict):
        """Открыть ссылку используя LinkOpener."""
        logger.debug(f"Opening link: type={link.get('type')}, url={link.get('url')}")

        success = False
        try:
            # Создаем LinkInfo из словаря
            logger.debug(f"_open_link: link dict={link}")
            link_info = LinkInfo.from_dict(link)
            logger.info(f"_open_link: link_info={link_info}")
            logger.debug(
                f"_open_link: link_info created with browser_key={link_info.browser_key}"
            )

            # Используем LinkOpener для открытия
            opener = LinkOpener()
            opener.open_link(link_info)

            success = True
        except LinkValidationError as e:
            logger.error(f"Link validation error: {e}")
            self._show_error(f"{self.get_message('validation_error')}: {str(e)}")
        except ValueError as e:
            # Дружелюбная обработка небезопасных URL без всплывающих ошибок
            msg = str(e)
            if msg.startswith("Unsafe URL:"):
                from app.controllers.ui.dialogs import DialogManager

                safe_msg = self.get_message(
                    "unsafe_url_info",
                    "Эта ссылка не может быть открыта по соображениям безопасности.",
                )
                details = msg  # чтобы был доступен текст причины при включённых деталях
                logger.warning(f"Blocked unsafe URL: {msg}")
                DialogManager.show_info(
                    parent=self.main,
                    title=self.get_message("warning_title", "Предупреждение"),
                    message=safe_msg,
                    informative_text=self.get_message(
                        "unsafe_url_hint",
                        "Проверьте адрес ссылки или отредактируйте её.",
                    ),
                    details=details,
                    silent=True,
                )
            else:
                # Прочие ValueError — как ошибка
                logger.error(
                    f"Error opening link {link.get('url', link)}: {e}", exc_info=True
                )
                self._show_error(f"Не удалось открыть ссылку: {str(e)}")
        except Exception as e:
            logger.error(
                f"Error opening link {link.get('url', link)}: {e}", exc_info=True
            )
            self._show_error(f"Не удалось открыть ссылку: {str(e)}")

        # Обновляем счетчик последних ссылок только при успешном открытии
        if success:
            link_data = link.copy()
            link_data["last_used"] = datetime.now().isoformat()

            # Асинхронно сохранить в БД (старое поведение)
            self.business.save_link(link_data)

            # Централизованное обновление верхних панелей через сигнал
            try:
                link_ops = getattr(self.main, "link_operations", None)
                if link_ops:
                    # Используем favorites_changed как триггер общего обновления TopPanels
                    link_ops.favorites_changed.emit()
                    # Сообщаем таблице о возможном изменении данных текущей категории
                    cat_id = link_data.get("category_id")
                    if isinstance(cat_id, int) and cat_id > 0:
                        link_ops.links_changed.emit(cat_id)
            except Exception as e:
                logger.debug(f"Failed to emit favorites_changed after opening link: {e}")

    def _toggle_fav(self, link: Dict = None):
        """Переключить статус избранного."""
        if not link:
            selected_links = self.controller.get_selected_links()
            if not selected_links:
                return
            link = selected_links[0]

        self.business.toggle_favorite(link)
