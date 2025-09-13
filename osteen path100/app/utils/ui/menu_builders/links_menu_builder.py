"""Строитель контекстного меню для таблицы ссылок."""

import json
import logging
from typing import TYPE_CHECKING, Callable, Dict

from PyQt6.QtCore import QModelIndex
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from app.utils.ui.menu_builders.menu_actions import ActionBuilder, Shortcuts

from .base import get_menu_icon

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class LinksMenuBuilder:
    """Строитель контекстного меню для таблицы ссылок."""

    def __init__(self, table_widget: QWidget, main_window: "MainWindow"):
        self.table_widget = table_widget
        self.main_window = main_window
        self.actions = ActionBuilder(table_widget)
        self.theme = main_window.settings.get_theme()

    def build(self, idx: QModelIndex, paste_link_cb: Callable) -> QMenu:
        """Создаёт контекстное меню для таблицы ссылок."""
        menu = QMenu(self.table_widget)

        if idx.isValid():
            link = self.main_window.get_link_at_row(idx.row())
            self._add_link_item_actions(menu, link)
            self._add_common_link_actions(menu, paste_link_cb)
            self._add_additional_actions(menu, link)
        else:
            self._add_empty_area_actions(menu, paste_link_cb)

        return menu

    def _add_link_item_actions(self, menu: QMenu, link: Dict) -> None:
        """Добавляет действия для выбранной ссылки."""
        logger.debug("LinksMenuBuilder._add_link_item_actions: link=%s", link)
        # Открыть ссылку
        menu.addAction(
            self.actions.create(
                "Открыть",
                lambda: self.main_window.links_actions.open_link(link),
                Shortcuts.ENTER,
                get_menu_icon("run", self.theme),
            )
        )

        # Добавить ссылку
        menu.addAction(
            self.actions.create(
                "Добавить ссылку",
                lambda: self.main_window.links_actions.show_link_dialog(
                    category_id=self.main_window.get_current_category_id()
                ),
                Shortcuts.ADD_LINK,
                get_menu_icon("add_link", self.theme),
            )
        )

        # Избранное (динамически)
        is_favorite = link and link.get("is_favorite")
        fav_text = "Удалить из избранного" if is_favorite else "Добавить в избранное"
        fav_icon = (
            get_menu_icon("delete_favorites", self.theme)
            if is_favorite
            else get_menu_icon("add_favorites", self.theme)
        )

        menu.addAction(
            self.actions.create(
                fav_text,
                lambda: self.main_window.links_actions.toggle_link_favorite(link),
                Shortcuts.CTRL_D,
                fav_icon,
            )
        )

        # Поделиться (сразу после избранного) — только для веб‑ссылок
        if self._is_web_link(link):
            self._add_share_submenu(menu, link)

        menu.addSeparator()

        # Редактировать
        menu.addAction(
            self.actions.create(
                "Редактировать",
                lambda: self.main_window.links_actions.show_link_dialog(link=link),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )

        # Удалить
        menu.addAction(
            self.actions.create(
                "Удалить",
                self._create_delete_callback(),
                Shortcuts.DELETE,
                get_menu_icon("delete", self.theme),
            )
        )

        menu.addSeparator()

        # Копировать
        menu.addAction(
            self.actions.create(
                "Копировать",
                self.main_window.links_actions.copy_selected_links,
                Shortcuts.CTRL_C,
                get_menu_icon("copy", self.theme),
            )
        )

    def _add_common_link_actions(self, menu: QMenu, paste_link_cb: Callable):
        """Добавляет общие действия для ссылок."""
        if self._clipboard_has_links():
            menu.addAction(
                self.actions.create(
                    "Вставить",
                    self.main_window.links_actions.paste_links,
                    Shortcuts.CTRL_V,
                    get_menu_icon("paste", self.theme),
                )
            )

        menu.addAction(
            self.actions.create(
                "Вырезать",
                self.main_window.links_actions.cut_selected_links,
                Shortcuts.CTRL_X,
                get_menu_icon("cut", self.theme),
            )
        )

        # Добавляем действия undo/redo из главного окна (только если они созданы)
        if getattr(self.main_window, "undo_action", None) is not None:
            menu.addAction(self.main_window.undo_action)
        if getattr(self.main_window, "redo_action", None) is not None:
            menu.addAction(self.main_window.redo_action)

    def _add_share_submenu(self, menu: QMenu, link: Dict) -> None:
        """Добавляет подменю «Поделиться» для одиночной ссылки."""
        try:
            # Защита от не‑веб ссылок (например, program://, file:// и т.п.)
            if not self._is_web_link(link):
                return
            share_menu = QMenu("Поделиться", menu)
            share_menu.setIcon(get_menu_icon("share", self.theme))

            # Telegram
            share_menu.addAction(
                self.actions.create(
                    "Telegram",
                    lambda: self.main_window.links_actions.share_via_telegram(link),
                    None,
                    get_menu_icon("telegram", self.theme),
                )
            )
            # WhatsApp
            share_menu.addAction(
                self.actions.create(
                    "WhatsApp",
                    lambda: self.main_window.links_actions.share_via_whatsapp(link),
                    None,
                    get_menu_icon("whatsapp", self.theme),
                )
            )
            # Viber
            share_menu.addAction(
                self.actions.create(
                    "Viber",
                    lambda: self.main_window.links_actions.share_via_viber(link),
                    None,
                    get_menu_icon("viber", self.theme),
                )
            )
            # X (Twitter)
            share_menu.addAction(
                self.actions.create(
                    "X (Twitter)",
                    lambda: self.main_window.links_actions.share_via_x(link),
                    None,
                    get_menu_icon("x", self.theme),
                )
            )
            # Facebook
            share_menu.addAction(
                self.actions.create(
                    "Facebook",
                    lambda: self.main_window.links_actions.share_via_facebook(link),
                    None,
                    get_menu_icon("facebook", self.theme),
                )
            )
            # LinkedIn
            share_menu.addAction(
                self.actions.create(
                    "LinkedIn",
                    lambda: self.main_window.links_actions.share_via_linkedin(link),
                    None,
                    get_menu_icon("linkedin", self.theme),
                )
            )
            # Pinterest
            share_menu.addAction(
                self.actions.create(
                    "Pinterest",
                    lambda: self.main_window.links_actions.share_via_pinterest(link),
                    None,
                    get_menu_icon("pinterest", self.theme),
                )
            )
            # Email (подменю)
            email_menu = QMenu("Email", share_menu)
            email_menu.setIcon(get_menu_icon("email", self.theme))
            # Сначала Gmail, затем системный почтовый клиент
            email_menu.addAction(
                self.actions.create(
                    "Через Gmail",
                    lambda: self.main_window.links_actions.share_via_email_gmail(link),
                    None,
                    get_menu_icon("gmail", self.theme),
                )
            )
            email_menu.addAction(
                self.actions.create(
                    "Через приложение (mailto)",
                    lambda: self.main_window.links_actions.share_via_email_client(link),
                    None,
                    get_menu_icon("email_client", self.theme),
                )
            )
            email_menu.addAction(
                self.actions.create(
                    "Скопировать как письмо",
                    lambda: self.main_window.links_actions.copy_email_template(link),
                    None,
                    get_menu_icon("copy", self.theme),
                )
            )

            # Настройка почтового клиента не добавляется по просьбе пользователя –
            # ассоциации mailto управляются в Windows автоматически.

            share_menu.addMenu(email_menu)

            menu.addMenu(share_menu)
        except Exception as e:
            logger.warning("Failed to build Share submenu: %s", e, exc_info=True)

    def _is_web_link(self, link: Dict) -> bool:
        """Проверяет, является ли ссылка веб‑ссылкой (http/https)."""
        if not isinstance(link, dict):
            return False
        try:
            url = link.get("url") or link.get("href")
            if not isinstance(url, str):
                return False
            low = url.strip().lower()
            return low.startswith("http://") or low.startswith("https://")
        except Exception:
            return False

    def _add_additional_actions(self, menu: QMenu, link: dict):
        """Добавляет дополнительные действия."""
        # Используем явную ссылку на undo_action из главного окна
        undo_anchor = getattr(self.main_window, "undo_action", None)
        # Вставляем дополнительные действия только если undo присутствует в текущем меню,
        # чтобы сохранить исходную логику расположения.
        if undo_anchor and undo_anchor in menu.actions():
            menu.insertSeparator(undo_anchor)

            # Выделить все
            menu.insertAction(
                undo_anchor,
                self.actions.create(
                    "Выделить все",
                    self.main_window.select_all_links,
                    Shortcuts.CTRL_A,
                    get_menu_icon("select_all", self.theme),
                ),
            )

            # Редактировать заметку
            menu.insertAction(
                undo_anchor,
                self.actions.create(
                    "Редактировать заметку",
                    lambda: self.main_window.links_actions.show_note_dialog(link),
                    Shortcuts.CTRL_N,
                    get_menu_icon("edit_note", self.theme),
                ),
            )

            menu.insertSeparator(undo_anchor)

    def _add_empty_area_actions(self, menu: QMenu, paste_link_cb: Callable):
        """Добавляет действия для пустой области таблицы."""
        current_category_id = self.main_window.get_current_category_id()
        if current_category_id is not None:
            menu.addAction(
                self.actions.create(
                    "Добавить ссылку",
                    lambda: self.main_window.links_actions.show_link_dialog(
                        category_id=current_category_id
                    ),
                    Shortcuts.ADD_LINK,
                    get_menu_icon("add_link", self.theme),
                )
            )

        # Только вставить и undo/redo для пустой области
        if self._clipboard_has_links():
            menu.addAction(
                self.actions.create(
                    "Вставить",
                    self.main_window.links_actions.paste_links,
                    Shortcuts.CTRL_V,
                    get_menu_icon("paste", self.theme),
                )
            )

        # Добавляем действия undo/redo из главного окна (только если они созданы)
        if getattr(self.main_window, "undo_action", None) is not None:
            menu.addAction(self.main_window.undo_action)
        if getattr(self.main_window, "redo_action", None) is not None:
            menu.addAction(self.main_window.redo_action)

    def _create_delete_callback(self):
        """Создаёт коллбек для удаления выбранных ссылок."""
        return lambda: self.main_window.links_actions.delete_selected_links()

    def _clipboard_has_links(self) -> bool:
        """Проверяет, содержит ли буфер обмена ссылки."""
        try:
            app = QApplication.instance()
            if app is None:
                # Нет активного приложения — вставка недоступна
                return False

            clipboard = app.clipboard()
            if clipboard is None:
                return False

            text = clipboard.text() or ""
            if not text.strip():
                # Пустой буфер обмена — это не ошибка
                return False

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # В буфере не JSON нашего формата — это штатная ситуация
                logger.debug(
                    "[LinksMenu] Clipboard does not contain valid JSON for links"
                )
                return False

            if isinstance(data, dict) and "name" in data:
                return True
            if isinstance(data, list) and any(
                isinstance(link, dict) and "name" in link for link in data
            ):
                return True
        except Exception as e:
            # Нежданные ошибки логируем без трейсбека, чтобы не шуметь
            logger.warning("[LinksMenu] Clipboard check failed: %s", e)
        return False
