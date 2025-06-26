# app/controllers/links.py

import os
import webbrowser
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMenu,
    QDialogButtonBox, QDialog
)
from PyQt6.QtGui import QIcon

from app.models.db import Database
from app.views.dialogs import NoteDialog
from app.config import LINK_ICONS_DIR


class LinksController:
    def __init__(self, table_widget: QTableWidget, db: Database, main_window):
        """
        Контроллер таблицы ссылок с контекстным меню.
        """
        self.table = table_widget
        self.db = db
        self.main = main_window

        headers = ["★", "Название", "Последний запуск", "Заметки"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.table.horizontalHeader().sectionClicked.connect(self._on_header_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        # щелчок по звезде
        self.table.cellClicked.connect(self._on_cell_clicked)


    def load_links(self, category_id: int):
        """Заполняет таблицу ссылками из базы."""
        self.table.setRowCount(0)
        self.main.current_category_id = category_id

        raw_rows = self.db.get_links(category_id)
        links: List[Dict] = [dict(r) for r in raw_rows]

        for link in links:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # ★
            star_item = QTableWidgetItem()
            if link.get("is_favorite"):
                star_item.setText("★")
            star_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, star_item)

            # Название + иконка
            name_item = QTableWidgetItem(link.get("name", ""))
            icon_name = link.get("icon_path") or ""
            icon_path = LINK_ICONS_DIR / icon_name
            if icon_name and Path(icon_path).exists():
                name_item.setIcon(QIcon(str(icon_path)))
            self.table.setItem(row, 1, name_item)

            # Последний запуск
            last = link.get("last_used") or ""
            last_item = QTableWidgetItem(last)
            last_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, last_item)

            # Заметки
            notes_item = QTableWidgetItem(link.get("notes") or "")
            self.table.setItem(row, 3, notes_item)

            # Сохраняем словарь в UserRole
            for col in range(4):
                self.table.item(row, col).setData(Qt.ItemDataRole.UserRole, link)

    def get_link_at(self, row: int) -> Optional[Dict]:
        """Возвращает словарь link из UserRole первой колонки."""
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole)

    def _open_link(self, link: Dict):
        """Открывает ссылку и обновляет время запуска."""
        t = link.get("type")
        path = link.get("url") or link.get("path", "")
        args = link.get("args", "")
        try:
            if t == "web":
                if args:
                    subprocess.Popen(["start", "chrome.exe", path] + args.split(), shell=True)
                else:
                    webbrowser.open(path)
            elif t in ("file", "folder"):
                os.startfile(path)
            elif t in ("program", "script"):
                subprocess.Popen([path] + args.split())
            elif t == "chromeapp":
                webbrowser.open(path)
        except Exception:
            pass

        link["last_used"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.upsert_link(link)
        self.load_links(link["category_id"])
        self.main.fav_widget.update_favorites()

    def _on_cell_clicked(self, row: int, col: int):
        """Одиночный щелчок: колонка 0 — переключить избранное."""
        if col == 0:
            link = self.get_link_at(row)
            if link:
                self._toggle_fav(link)

    def _on_double_click(self, row: int, col: int):
        """Двойной клик по ячейке.
        Колонки:
          1,2 — запуск ссылки;
          3   — открытие диалога заметок.
        """
        link = self.get_link_at(row)
        if not link:
            return
        if col in (1, 2):
            self._open_link(link)
        elif col == 3:
            self.show_note_dialog(link)

    def _on_header_click(self, index: int):
        """Сортировка по заголовку."""
        order = self.table.horizontalHeader().sortIndicatorOrder()
        self.table.sortItems(index, order)

    def _on_context_menu(self, pos):
        menu = QMenu(self.table)
        idx = self.table.indexAt(pos)
        has_clip = hasattr(self.main, "_clipboard_link")

        # Всегда доступно
        menu.addAction(
            "Добавить ссылку",
            lambda: self.main.show_link_dialog(category_id=self.main.current_category_id)
        )

        if idx.isValid():
            row = idx.row()
            link = self.get_link_at(row)

            menu.addSeparator()
            menu.addAction("Запустить", lambda: self._open_link(link))

            if link.get("is_favorite"):
                menu.addAction("Удалить из избранного", lambda: self._toggle_fav(link))
            else:
                menu.addAction("Добавить в избранное", lambda: self._toggle_fav(link))

            menu.addSeparator()
            menu.addAction("Редактировать заметку", lambda: self.show_note_dialog(link))
            menu.addAction("Редактировать ссылку", lambda: self.main.show_link_dialog(link=link))

            menu.addSeparator()
            menu.addAction("Вырезать",   self.cut_link)
            menu.addAction("Копировать", self.copy_link)
            if has_clip:
                menu.addAction("Вставить", self.paste_link)

            menu.addSeparator()
            menu.addAction("Удалить", lambda: self.delete_link(link))
            menu.addSeparator()
            menu.addAction("Отменить", self.main.undo)
        else:
            if has_clip:
                menu.addAction("Вставить", self.paste_link)
            menu.addAction("Выбрать всё", lambda: self.table.selectAll())

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _toggle_fav(self, link: Dict):
        link["is_favorite"] = 0 if link.get("is_favorite") else 1
        self.db.upsert_link(link)
        self.load_links(link["category_id"])
        self.main.fav_widget.update_favorites()

    def cut_link(self):
        row = self.table.currentRow()
        link = self.get_link_at(row)
        if link:
            self.main._clipboard_link = link
            self.db.delete_link(link["id"])
            self.load_links(link["category_id"])
            self.main.fav_widget.update_favorites()

    def copy_link(self):
        row = self.table.currentRow()
        link = self.get_link_at(row)
        if link:
            self.main._clipboard_link = link.copy()

    def paste_link(self):
        if not hasattr(self.main, "_clipboard_link"):
            return
        link = dict(self.main._clipboard_link)
        link.pop("id", None)
        link["category_id"] = self.main.current_category_id
        self.db.upsert_link(link)
        self.load_links(self.main.current_category_id)
        self.main.fav_widget.update_favorites()

    def delete_link(self, link: Dict):
        self.db.delete_link(link["id"])
        self.load_links(self.main.current_category_id)
        self.main.fav_widget.update_favorites()

def copy_link(self):
    row = self.table.currentRow()
    link = self.get_link_at(row)
    if link:
        self.main._clipboard_link = link.copy()

def paste_link(self):
    if not hasattr(self.main, "_clipboard_link"):
        return
    link = dict(self.main._clipboard_link)
    link.pop("id", None)
    link["category_id"] = self.main.current_category_id
    self.db.upsert_link(link)
    self.load_links(self.main.current_category_id)
    self.main.fav_widget.update_favorites()

def delete_link(self, link: Dict):
    self.db.delete_link(link["id"])
    self.load_links(self.main.current_category_id)
    self.main.fav_widget.update_favorites()

def show_note_dialog(self, link: Dict):
    """Открывает диалог редактирования заметки и обновляет таблицу."""
    dlg = NoteDialog(link, self.db, parent=self.main)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        self.load_links(link["category_id"])
        self.main.fav_widget.update_favorites()
