# app/controllers/ui/links/links_actions.py

from __future__ import annotations

from typing import Dict, List, Optional
from app.controllers.ui.state.task_scheduler import schedule_selection_restore


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
            raise ValueError("LinksActions requires explicit 'links' and 'link_ops' instances")

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

    def get_link_by_row(self, row: int):
        """Совместимость: вернуть ссылку по номеру строки.
        В UI-контроллере метод get_link_by_row удалён, используем get_link_at.
        """
        if not self.links:
            return None
        # Предпочитаем прямой вызов актуального метода
        if hasattr(self.links, "get_link_at"):
            return self.links.get_link_at(row)
        # Fallback на случай наличия старого метода где-то ещё
        if hasattr(self.links, "get_link_by_row"):
            return self.links.get_link_by_row(row)
        return None

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
