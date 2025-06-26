# app/views/link_dialog.py

import os
import shutil
import logging
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QTextEdit,
    QPushButton, QToolButton, QFileDialog,
    QDialogButtonBox, QMessageBox, QButtonGroup,
    QCheckBox
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize, Qt, QTimer

from app import config
from app.models.db import Database
from app.utils.link_parser import (
    get_name_for_link,
    get_icon_for_link,
    parse_program_shortcut,
    parse_chrome_shortcut,
    extract_icon_from_shortcut
)
from app.views.dialogs import ChromeProfileDialog

logging.basicConfig(level=logging.DEBUG)

LINK_ICONS_DIR = config.LINK_ICONS_DIR
UI_ICONS_DIR = config.UI_ICONS_DIR
DEFAULT_ICONS = config.DEFAULT_ICONS
LINK_ICONS_DIR.mkdir(parents=True, exist_ok=True)


class LinkDialog(QDialog):
    LINK_TYPES = [
        ("web", "Веб-ссылка"),
        ("file", "Файл"),
        ("program", "Программа"),
        ("script", "Скрипт"),
        ("chromeapp", "Chrome App"),
        ("folder", "Папка"),
    ]

    def __init__(self, db: Database, link: Optional[Dict] = None, category_id: Optional[int] = None, parent=None):
        logging.debug("[LinkDialog] __init__ called with link=%s, category_id=%s", link, category_id)
        super().__init__(parent)
        self.db = db
        self.link = link.copy() if link else {}
        self.initial_category = category_id
        self.link_type = self.link.get("type", "web")
        self.icon_name = self.link.get("icon_path", "")
        self.selected_profiles: List[Dict] = []

        self.setWindowTitle("Редактировать ссылку" if link else "Добавить ссылку")
        self.setFixedSize(600, 520)

        self._build_ui()
        self._load_initial()
        self._update_ui_state()

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        # --- Исправление: правильное подключение сигналов для автозаполнения имени web ---
        self._name_autofill_running = False
        try:
            self.url_le.textChanged.disconnect(self._on_path_changed)
        except Exception:
            pass
        self.url_le.textChanged.connect(self._on_url_text_changed)
        try:
            self._update_timer.timeout.disconnect()
        except Exception:
            pass
        self._update_timer.timeout.connect(self._run_name_autofill)

    def _build_ui(self):
        logging.debug("[LinkDialog] _build_ui called")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(10)

        vbox.addWidget(QLabel("Тип ссылки:"))
        self.type_group = QButtonGroup(self)
        hl_type = QHBoxLayout()
        for code, txt in self.LINK_TYPES:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setText(txt)
            icon_filename = DEFAULT_ICONS.get(code, DEFAULT_ICONS["default"])
            icon_path = UI_ICONS_DIR / icon_filename
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(32, 32))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFixedSize(90, 80)
            self.type_group.addButton(btn)
            btn.setProperty("link_type", code)
            hl_type.addWidget(btn)
        vbox.addLayout(hl_type)
        self.type_group.buttonClicked.connect(
            lambda b: self._on_type_changed(b.property("link_type"))
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.url_le = QLineEdit()
        self.url_le.textChanged.connect(self._on_path_changed)
        self.url_le.editingFinished.connect(self._on_url_editing_finished)
        hl_path = QHBoxLayout()
        hl_path.addWidget(self.url_le, 1)
        self.browse_btn = QPushButton("Обзор…")
        self.browse_btn.clicked.connect(self._on_browse)
        hl_path.addWidget(self.browse_btn)
        self.profile_btn = QPushButton("Профиль")
        self.profile_btn.clicked.connect(self._on_profile)
        hl_path.addWidget(self.profile_btn)
        form.addRow("URL/Путь:", hl_path)

        self.name_le = QLineEdit()
        hl_name = QHBoxLayout()
        hl_name.addWidget(self.name_le, 1)
        self.icon_btn = QPushButton("Иконка")
        self.icon_btn.clicked.connect(self._on_choose_icon)
        hl_name.addWidget(self.icon_btn)
        form.addRow("Имя:", hl_name)

        self.args_le = QLineEdit()
        form.addRow("Аргументы:", self.args_le)

        self.sphere_cb = QComboBox()
        self.section_cb = QComboBox()
        self.category_cb = QComboBox()
        form.addRow("Сфера:", self.sphere_cb)
        form.addRow("Раздел:", self.section_cb)
        form.addRow("Категория:", self.category_cb)
        self.sphere_cb.currentIndexChanged.connect(self._update_sections)
        self.section_cb.currentIndexChanged.connect(self._update_categories)

        self.notes_te = QTextEdit()
        form.addRow("Заметки:", self.notes_te)

        self.fav_chk = QCheckBox("Добавить в избранное")
        form.addRow("", self.fav_chk)

        vbox.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Сохранить")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def _load_initial(self):
        logging.debug("[LinkDialog] _load_initial called")
        for btn in self.type_group.buttons():
            if btn.property("link_type") == self.link_type:
                btn.setChecked(True)
                break

        self.url_le.setText(self.link.get("url", ""))
        self.name_le.setText(self.link.get("name", ""))
        self.args_le.setText(self.link.get("args", ""))
        self.notes_te.setPlainText(self.link.get("notes", ""))
        self.fav_chk.setChecked(bool(self.link.get("is_favorite", False)))

        for sp in self.db.get_spheres():
            self.sphere_cb.addItem(sp["name"], sp["id"])
        self._update_sections()

        cid = self.link.get("category_id") or self.initial_category
        if cid:
            row = self.db.conn.execute("SELECT section_id FROM category WHERE id=?", (cid,)).fetchone()
            if row:
                sec_id = row["section_id"]
                sp = self.db.conn.execute("SELECT sphere_id FROM section WHERE id=?", (sec_id,)).fetchone()
                if sp:
                    idx = self.sphere_cb.findData(sp["sphere_id"])
                    if idx >= 0:
                        self.sphere_cb.setCurrentIndex(idx)
                        self._update_sections()
                        j = self.section_cb.findData(sec_id)
                        if j >= 0:
                            self.section_cb.setCurrentIndex(j)
                            self._update_categories()
                            k = self.category_cb.findData(cid)
                            if k >= 0:
                                self.category_cb.setCurrentIndex(k)

    def _on_type_changed(self, link_type: str):
        logging.info(f"[LinkDialog] _on_type_changed called with link_type={link_type}")
        logging.debug(f"[LinkDialog] Тип ссылки изменён: {link_type}")
        self.link_type = link_type
        self.url_le.clear()
        self.name_le.clear()
        self.args_le.clear()
        self.icon_btn.setIcon(QIcon())
        self.icon_name = ""
        # Если выбран тип 'script', подставить дефолтную иконку для скриптов
        if link_type == "script":
            icon_path = UI_ICONS_DIR / DEFAULT_ICONS.get("script", DEFAULT_ICONS["default"])
            if icon_path.exists():
                self.icon_btn.setIcon(QIcon(str(icon_path)))
                self.icon_name = icon_path.name
        self._update_ui_state()
        self._on_path_changed()

    def _update_ui_state(self):
        logging.debug("[LinkDialog] _update_ui_state called")
        is_web = (self.link_type == "web")
        self.profile_btn.setVisible(is_web)
        self.browse_btn.setVisible(not is_web)

    def _on_browse(self):
        logging.info("[LinkDialog] _on_browse called")
        if self.link_type == "folder":
            path = QFileDialog.getExistingDirectory(self, "Выбрать папку", "")
            if path:
                self.url_le.setText(path)
                # Имя папки подставляется напрямую, как в примере
                name = os.path.basename(os.path.normpath(path))
                self.name_le.setText(name)
        else:
            filter_str = "Ярлыки (*.lnk)" if self.link_type == "chromeapp" else "Все файлы (*)"
            path, _ = QFileDialog.getOpenFileName(self, "Выбрать файл", "", filter_str)
            if path:
                self.url_le.setText(path)
                # Имя файла подставляется напрямую, если поле пустое
                if not self.name_le.text().strip():
                    name = os.path.basename(path)
                    self.name_le.setText(name)

    def _on_path_changed(self):
        logging.debug("[LinkDialog] _on_path_changed called, text: %s", self.url_le.text())
        if not hasattr(self, '_update_timer') or self._update_timer is None:
            logging.warning("[LinkDialog] _on_path_changed: _update_timer не инициализирован — пропуск")
            return
        self._update_timer.start(400)

    def _on_url_editing_finished(self):
        pass  # Для web не используется

    def _on_url_text_changed(self, text):
        # Асинхронное автозаполнение имени только для web
        if self.link_type == "web":
            # Только асинхронный воркер, и только обновление иконки после автозаполнения имени
            if self._name_autofill_running:
                logging.debug("[LinkDialog] Автозаполнение имени: воркер уже работает")
                return
            if self.name_le.text().strip():
                logging.debug("[LinkDialog] Автозаполнение имени: поле имени не пустое — не автозаполняем")
                return
            logging.debug(f"[LinkDialog] Автозаполнение имени: старт таймера для '{text}'")
            self._update_timer.stop()
            self._update_timer.start(400)
        elif self.link_type in ("file", "program", "script", "chromeapp", "folder"):
            # Для остальных типов — basename + иконка сразу
            if not self.name_le.text().strip() and text.strip():
                import os
                name = os.path.basename(text.strip()) if self.link_type != "folder" else os.path.basename(os.path.normpath(text.strip()))
                logging.debug(f"[LinkDialog] Автозаполнение имени по basename: '{name}' для '{text}' тип {self.link_type}")
                if name:
                    self.name_le.setText(name)
                # Только для этих типов — обновить иконку
                self._process_link_path()

    def _run_name_autofill(self):
        from PyQt6.QtCore import QRunnable, QThreadPool, pyqtSignal, QObject
        class NameWorkerSignals(QObject):
            finished = pyqtSignal(str)
        class NameWorker(QRunnable):
            def __init__(self, link_type, path, signals):
                super().__init__()
                self.link_type = link_type
                self.path = path
                self.signals = signals
            def run(self):
                from app.utils.link_parser import get_name_for_link
                try:
                    logging.debug(f"[LinkDialog] NameWorker: вызов get_name_for_link({self.link_type}, {self.path})")
                    name = get_name_for_link(self.link_type, self.path)
                    logging.debug(f"[LinkDialog] NameWorker: результат get_name_for_link: '{name}'")
                except Exception as e:
                    logging.error(f"[LinkDialog] NameWorker: ошибка get_name_for_link: {e}")
                    name = ""
                self.signals.finished.emit(name)
        if self._name_autofill_running:
            logging.debug("[LinkDialog] _run_name_autofill: воркер уже работает")
            return
        self._name_autofill_running = True
        signals = NameWorkerSignals()
        signals.finished.connect(self._on_name_autofill_finished)
        url = self.url_le.text().strip()
        logging.debug(f"[LinkDialog] _run_name_autofill: старт воркера для '{url}'")
        worker = NameWorker(self.link_type, url, signals)
        QThreadPool.globalInstance().start(worker)

    def _on_name_autofill_finished(self, name):
        self._name_autofill_running = False
        logging.debug(f"[LinkDialog] _on_name_autofill_finished: name='{name}', поле name пустое: {not self.name_le.text().strip()}")
        if not self.name_le.text().strip() and name:
            self.name_le.setText(name)
            # После автозаполнения имени для web — обновить иконку
            if self.link_type == "web":
                self._process_link_path()

    def _process_link_path(self):
        logging.debug("[LinkDialog] _process_link_path called with path: %s", self.url_le.text())
        path = self.url_le.text().strip()
        if not path:
            logging.debug("[LinkDialog] Путь пустой — выход")
            return

        logging.debug(f"[LinkDialog] Обработка пути: {path} (тип: {self.link_type})")

        if self.link_type == "web" and not path.startswith(("http://", "https://")):
            path = "https://" + path
            self.url_le.setText(path)

        if self.link_type == "chromeapp" and path.lower().endswith(".lnk"):
            info = parse_chrome_shortcut(path)
            logging.debug(f"[LinkDialog] Chrome shortcut: {info}")

            if info.get("args"):
                self.args_le.setText(info["args"])
            if info.get("name") and not self.name_le.text().strip():
                self.name_le.setText(info["name"])

            icon = extract_icon_from_shortcut(info, str(LINK_ICONS_DIR))
            if icon and os.path.exists(icon):
                self.icon_btn.setIcon(QIcon(str(icon)))
                self.icon_name = Path(icon).name
            else:
                logging.warning("[LinkDialog] Не удалось извлечь иконку из ярлыка")
            return

        # При ручном вводе пути — автозаполнение имени, только если поле пустое
        # Для web-ссылок автозаполнение имени выполняется только через _on_url_editing_finished
        if not self.name_le.text().strip():
            if self.link_type == "folder":
                name = os.path.basename(os.path.normpath(path))
                self.name_le.setText(name)
            elif self.link_type in ("file", "program", "script", "batch", "chromeapp"):
                name = os.path.basename(path)
                self.name_le.setText(name)

        icon_path = get_icon_for_link(self.link_type, path, config=config, args=self.args_le.text().strip())
        logging.debug(f"[LinkDialog] get_icon_for_link вернул: {icon_path}")
        if icon_path:
            icon_path_obj = Path(icon_path)
            # Если иконка лежит в UI_ICONS_DIR — не копируем, используем напрямую
            if icon_path_obj.parent.resolve() == UI_ICONS_DIR.resolve():
                self.icon_btn.setIcon(QIcon(str(icon_path_obj)))
                self.icon_name = icon_path_obj.name
            else:
                icon_dst = LINK_ICONS_DIR / icon_path_obj.name
                try:
                    if not icon_dst.exists() or icon_path_obj.resolve() != icon_dst.resolve():
                        shutil.copyfile(icon_path_obj, icon_dst)
                    self.icon_btn.setIcon(QIcon(str(icon_dst)))
                    self.icon_name = icon_dst.name
                except Exception as e:
                    logging.error(f"[LinkDialog] Ошибка копирования иконки: {e}")

        if path.lower().endswith(".lnk") and self.link_type in ("program", "script"):
            pr = parse_program_shortcut(path)
            logging.debug(f"[LinkDialog] Parsed shortcut: {pr}")
            self.args_le.setText(pr.get("args", ""))

    def _on_profile(self):
        logging.info("[LinkDialog] _on_profile called")
        dlg = ChromeProfileDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.selected_profiles = dlg.get_selected_profiles()
            self.profile_btn.setText(self._format_profile_text(self.selected_profiles))

    def _format_profile_text(self, profiles):
        emails = [p.get("email") or p.get("name") for p in profiles]
        if not emails:
            return "Профиль"
        elif len(emails) == 1:
            return f"Профиль: {emails[0]}"
        elif len(emails) == 2:
            return f"Профили: {emails[0]}, {emails[1]}"
        return f"Профили: {emails[0]}, {emails[1]} и ещё {len(emails)-2}"

    def _on_choose_icon(self):
        logging.info("[LinkDialog] _on_choose_icon called")
        p, _ = QFileDialog.getOpenFileName(self, "Выбрать иконку", "", "Изображения (*.png *.ico *.svg)")
        if not p:
            return
        dst = LINK_ICONS_DIR / Path(p).name
        if not dst.exists():
            shutil.copyfile(p, dst)
        self.icon_name = dst.name
        self.icon_btn.setIcon(QIcon(str(dst)))

    def _update_sections(self):
        logging.debug("[LinkDialog] _update_sections called")
        self.section_cb.clear()
        sid = self.sphere_cb.currentData()
        for sec in self.db.get_sections(sid):
            self.section_cb.addItem(sec["name"], sec["id"])
        self._update_categories()

    def _update_categories(self):
        logging.debug("[LinkDialog] _update_categories called")
        self.category_cb.clear()
        sid = self.section_cb.currentData()
        for cat in self.db.get_categories(sid):
            self.category_cb.addItem(cat["name"], cat["id"])

    def _on_accept(self):
        logging.info("[LinkDialog] _on_accept called")
        name = self.name_le.text().strip()
        url = self.url_le.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "Ошибка", "Имя и путь не могут быть пустыми")
            return

        if self.link_type == "web":
            try:
                parsed_url = urlparse(url)
                if not parsed_url.netloc or '.' not in parsed_url.netloc:
                    QMessageBox.warning(self, "Ошибка", "Введите корректный URL с доменом.")
                    return
            except Exception as e:
                logging.error(f"[LinkDialog] URL parse error: {e}")
                QMessageBox.warning(self, "Ошибка", "URL содержит ошибку.")
                return

        # --- Chrome Profiles: мультисоздание ссылок ---
        if self.link_type == "web" and self.selected_profiles:
            for prof in self.selected_profiles:
                prof_name = (prof.get("email") or prof.get("name") or "Chrome").split("@")[0]
                rec = {
                    "name": f"{name} ({prof_name})",
                    "url": url,
                    "type": self.link_type,
                    "icon_path": self.icon_name,
                    "args": prof.get("args", ""),
                    "is_favorite": int(self.fav_chk.isChecked()),
                    "notes": self.notes_te.toPlainText(),
                    "category_id": self.category_cb.currentData(),
                    "last_used": self.link.get("last_used"),
                    "position": self.link.get("position", 0)
                }
                if self.link.get("id") is not None:
                    rec["id"] = self.link["id"]
                self.db.upsert_link(rec)
            self.accept()
            return
        # --- Обычное поведение ---
        rec = {
            "name": name,
            "url": url,
            "type": self.link_type,
            "icon_path": self.icon_name,
            "args": self.args_le.text().strip(),
            "is_favorite": int(self.fav_chk.isChecked()),
            "notes": self.notes_te.toPlainText(),
            "category_id": self.category_cb.currentData(),
            "last_used": self.link.get("last_used"),
            "position": self.link.get("position", 0)
        }
        if self.link.get("id") is not None:
            rec["id"] = self.link["id"]
        self.db.upsert_link(rec)
        self.accept()
