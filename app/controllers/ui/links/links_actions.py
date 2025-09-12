# app/controllers/ui/links/links_actions.py

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.services import share_service


class LinksActions:
    """Фасад для ссылочных действий UI.
    Делегирует операции существующим контроллерам: `LinksUIController` и `LinkOperationsController`.
    """

    def __init__(self, main_window, links, link_ops):
        """Создаёт фасад действий со ссылками.

        Обязательные зависимости передаются явно:
        - links: экземпляр `LinksUIController`
        - link_ops: экземпляр `LinkOperationsController`

        Исключены динамические getattr — при отсутствии зависимостей бросаем ValueError.
        """
        self.main = main_window
        self.links = links
        self.link_ops = link_ops
        if self.links is None or self.link_ops is None:
            raise ValueError(
                "LinksActions requires explicit 'links' and 'link_ops' instances"
            )

    # --- Диалог ссылки ---
    def show_link_dialog(
        self, link: Optional[Dict] = None, category_id: Optional[int] = None
    ) -> bool:
        if not self.link_ops:
            return False
        return bool(self.link_ops.show_link_dialog(link=link, category_id=category_id))

    def delete_links_with_confirmation(self, links: List[Dict]):
        if not self.link_ops:
            return
        return self.link_ops.delete_links_with_confirmation(links)

    # --- Действия над ссылками ---
    def open_link(self, link: Dict):
        if self.links:
            self.links.open_link(link)

    def toggle_link_favorite(self, link: Optional[Dict] = None):
        if self.links:
            self.links.toggle_favorite(link)

    def copy_selected_links(self):
        if self.links:
            self.links.copy_selected_links()

    def paste_links(self):
        if self.links:
            self.links.paste_links()

    def cut_selected_links(self):
        if self.links:
            self.links.cut_selected_links()

    def delete_selected_links(self):
        if self.links:
            self.links.delete_selected_links()

    def show_note_dialog(self, link: Dict):
        if self.links:
            self.links.show_note_dialog(link)

    # --- Поделиться ссылкой ---
    def share_via_telegram(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_telegram(name, url)

    def share_via_whatsapp(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_whatsapp(name, url)

    def share_via_viber(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_viber(name, url)

    def share_via_email(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_email(name, url)

    def share_via_email_client(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_email_client(name, url)

    def share_via_email_gmail(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_email_gmail(name, url)

    def copy_email_template(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.copy_email_template(name, url)

    # --- Соцсети: X(Twitter), Facebook, LinkedIn ---
    def share_via_x(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_x(name, url)

    def share_via_facebook(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_facebook(name, url)

    def share_via_linkedin(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_linkedin(name, url)

    def share_via_pinterest(self, link: Dict) -> bool:
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        return share_service.share_via_pinterest(name, url)

    # --- Поиск и восстановление выбора ---
    def on_search(self, text: str):
        if self.links:
            self.links.on_search(text)

    def restore_selection(self, link_id: int):
        if self.links and hasattr(self.links, "focus_on_link"):
            self.links.focus_on_link(link_id)

    def focus_on_link(self, link_id: int):
        """Алиас для совместимости: фокус на ссылке по ID."""
        self.restore_selection(link_id)

    def schedule_restore_selection(self, link_id: int) -> None:
        """Планирует восстановление выделения/фокуса на ссылке.

        Инкапсулирует использование планировщика задач, чтобы вызовы из MainWindow
        не зависели от импорта и не использовали getattr/lambda.
        """
        key = f"table_selection_{link_id}"
        # Передаем явный коллбек на метод контроллера
        schedule_selection_restore(lambda: self.restore_selection(link_id), key)

    # --- Доступ к данным виджета ссылок / выбор ---
    def get_link_at(self, row: int):
        if not self.links:
            return None
        return self.links.get_link_at(row)

    def get_selected_rows(self):
        if not self.links:
            return []
        return self.links.get_selected_rows()

    def current_row(self) -> Optional[int]:
        if not self.links or not hasattr(self.links, "current_row"):
            return None
        return self.links.current_row()

    def get_selected_links(self):
        rows = self.get_selected_rows()
        if not rows:
            return []
        links = [self.get_link_at(r) for r in rows]
        return [ln for ln in links if ln]

    # --- Редактирование текущей ссылки ---
    def edit_selected_link(self) -> bool:
        row = self.current_row()
        if row is None:
            return False
        # Используем актуальный API получения ссылки по строке
        link = self.get_link_at(row)
        if not link:
            return False
        # Покажем диалог через существующий API, статусбар обновит MainWindow
        result = self.show_link_dialog(link=link)
        if result:
            # Уведомить статусбар через MainWindow
            if hasattr(self.main, "update_statusbar"):
                self.main.update_statusbar()
            return True
        return False

    # --- Unified action handler for new panel widgets ---
    def on_action_requested(self, action_data: Dict[str, Any] | None) -> None:
        """Обработчик унифицированных действий от верхних панелей.

        Контракт action_data (dict):
        - type: str — тип действия.
            - "open_link": открыть ссылку из панели.
            - "quick_add": быстро добавить ссылку заданного типа.
        - link: dict | None — ссылка (для type == "open_link").
        - link_type: str | None — тип быстрой ссылки (для type == "quick_add").
        - category_id: int | None — категория назначения (опционально; если не указана,
          используется текущая категория через LinksUIController).

        Поведение:
        - open_link: делегирует в self.open_link(link).
        - quick_add: делегирует в LinksUIController.quick_add_link(link_type, category_id).
        """
        if not isinstance(action_data, dict):
            return

        action_type = action_data.get("type")
        if action_type == "open_link":
            link = action_data.get("link")
            if link:
                self.open_link(link)
        elif action_type == "quick_add":
            # Delegate to LinksUIController for unified behavior
            link_type = action_data.get("link_type")
            category_id = action_data.get("category_id")
            if self.links and hasattr(self.links, "quick_add_link"):
                self.links.quick_add_link(link_type, category_id)

    # --- Делегаты для пассивных виджетов (Recent/Favorites) ---
    def on_recent_refresh_requested(self, limit: int):
        if self.links and hasattr(self.links, "on_recent_refresh_requested"):
            return self.links.on_recent_refresh_requested(limit)

    def on_favorites_refresh_requested(self):
        if self.links and hasattr(self.links, "on_favorites_refresh_requested"):
            return self.links.on_favorites_refresh_requested()

    def on_favorites_clear_requested(self):
        if self.links and hasattr(self.links, "on_favorites_clear_requested"):
            return self.links.on_favorites_clear_requested()
