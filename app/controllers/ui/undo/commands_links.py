# app/utils/system/undo/commands_links.py
from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtGui import QUndoCommand

from app.services import LinksService


class SaveLinkCmd(QUndoCommand):
    def __init__(self, new_data: Dict, old_data: Optional[Dict], main_window):
        super().__init__("Save link")
        self.main = main_window
        self.db = main_window.db
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.created_id: Optional[int] = None

    def redo(self):
        # Сохраняем ссылку через сервисный слой (UnitOfWork внутри)
        if hasattr(self.main, "links_business") and self.main.links_business:
            result = self.main.links_business.links.create_or_update_link(self.new_data)
        else:
            # Фоллбек через сервисный слой
            result = LinksService(self.db).create_or_update_link(self.new_data)
        if result and not self.new_data.get("id"):
            self.new_data["id"] = result
            self.created_id = result
        # UI сигнал обновления через LinksBusinessLogic, если есть
        if hasattr(self.main, "links_business") and self.main.links_business:
            try:
                self.main.links_business.link_updated.emit(self.new_data)
            except Exception:
                pass
            # Перезагружаем таблицу текущей категории, если не подавлено
            try:
                if not getattr(self, "_suppress_ui", False):
                    cat_id = self.new_data.get("category_id") or (
                        self.old_data or {}
                    ).get("category_id")
                    if isinstance(cat_id, int) and cat_id > 0:
                        self.main.links_business.load_links(cat_id)
            except Exception:
                pass

    def undo(self):
        # Если создавали новую — удаляем
        link_id = self.new_data.get("id")
        if self.old_data is None and link_id:
            if hasattr(self.main, "links_business") and self.main.links_business:
                self.main.links_business.links.delete_link(link_id)
            else:
                LinksService(self.db).delete_link(link_id)
        else:
            # Иначе восстанавливаем старые данные
            if self.old_data:
                if hasattr(self.main, "links_business") and self.main.links_business:
                    self.main.links_business.links.create_or_update_link(self.old_data)
                else:
                    LinksService(self.db).create_or_update_link(self.old_data)
                if hasattr(self.main, "links_business") and self.main.links_business:
                    try:
                        self.main.links_business.link_updated.emit(self.old_data)
                    except Exception:
                        pass
        # Перезагружаем таблицу соответствующей категории, если не подавлено
        try:
            if (
                hasattr(self.main, "links_business")
                and self.main.links_business
                and not getattr(self, "_suppress_ui", False)
            ):
                cat_id = (self.old_data or {}).get("category_id") or self.new_data.get(
                    "category_id"
                )
                if isinstance(cat_id, int) and cat_id > 0:
                    self.main.links_business.load_links(cat_id)
        except Exception:
            pass


class DeleteLinkCmd(QUndoCommand):
    def __init__(self, link_to_delete: Dict, main_window):
        super().__init__("Delete link")
        self.main = main_window
        self.db = main_window.db
        self.link = dict(link_to_delete) if link_to_delete else {}

    def redo(self):
        link_id = self.link.get("id")
        if link_id:
            # Удаляем через сервисный слой, если доступен
            if hasattr(self.main, "links_business") and self.main.links_business:
                self.main.links_business.links.delete_link(link_id)
            else:
                # Фоллбек на прямой репозиторий
                self.db.links.delete_link(link_id)
        # После удаления перезагружаем таблицу соответствующей категории, если не подавлено
        try:
            if (
                hasattr(self.main, "links_business")
                and self.main.links_business
                and not getattr(self, "_suppress_ui", False)
            ):
                cat_id = self.link.get("category_id")
                if isinstance(cat_id, int) and cat_id > 0:
                    self.main.links_business.load_links(cat_id)
        except Exception:
            pass

    def undo(self):
        # Восстанавливаем удалённую ссылку
        if hasattr(self.main, "links_business") and self.main.links_business:
            self.main.links_business.links.create_or_update_link(self.link)
        else:
            # Фоллбек через сервисный слой
            LinksService(self.db).create_or_update_link(self.link)
        if hasattr(self.main, "links_business") and self.main.links_business:
            try:
                self.main.links_business.link_updated.emit(self.link)
            except Exception:
                pass
            # Перезагружаем таблицу, если не подавлено
            try:
                if not getattr(self, "_suppress_ui", False):
                    cat_id = self.link.get("category_id")
                    if isinstance(cat_id, int) and cat_id > 0:
                        self.main.links_business.load_links(cat_id)
            except Exception:
                pass


class BatchSaveLinksCmd(QUndoCommand):
    def __init__(
        self, links_data: List[Dict], old_link_data: Optional[Dict], main_window
    ):
        super().__init__("Batch save links")
        self.main = main_window
        self.db = main_window.db
        self.links_data = [dict(x) for x in (links_data or [])]
        self.created_ids: List[int] = []

    def redo(self):
        self.created_ids.clear()
        for data in self.links_data:
            if hasattr(self.main, "links_business") and self.main.links_business:
                result = self.main.links_business.links.create_or_update_link(data)
            else:
                result = LinksService(self.db).create_or_update_link(data)
            if result and not data.get("id"):
                data["id"] = result
                self.created_ids.append(result)
        # Эмит обновлений для UI (по каждому элементу)
        if hasattr(self.main, "links_business") and self.main.links_business:
            for data in self.links_data:
                try:
                    self.main.links_business.link_updated.emit(data)
                except Exception:
                    pass
            # Разовая перезагрузка таблицы по категории первой ссылки, если не подавлено
            try:
                if not getattr(self, "_suppress_ui", False):
                    cat_id = (self.links_data[0] if self.links_data else {}).get(
                        "category_id"
                    )
                    if isinstance(cat_id, int) and cat_id > 0:
                        self.main.links_business.load_links(cat_id)
            except Exception:
                pass

    def undo(self):
        # Простейшая политика: если запись была новой (id получен впервые) — удаляем; иначе откат не трогаем
        for data in self.links_data:
            link_id = data.get("id")
            if link_id in self.created_ids:
                if hasattr(self.main, "links_business") and self.main.links_business:
                    self.main.links_business.links.delete_link(link_id)
                else:
                    LinksService(self.db).delete_link(link_id)
        # Перезагрузить таблицу, если не подавлено
        try:
            if (
                hasattr(self.main, "links_business")
                and self.main.links_business
                and not getattr(self, "_suppress_ui", False)
            ):
                cat_id = (self.links_data[0] if self.links_data else {}).get(
                    "category_id"
                )
                if isinstance(cat_id, int) and cat_id > 0:
                    self.main.links_business.load_links(cat_id)
        except Exception:
            pass
