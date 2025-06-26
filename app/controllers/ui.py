# app/controllers/ui.py

import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QToolButton
from PyQt6.QtGui import QIcon
from app.config import QSS_DIR, THEMES_MANIFEST, LINK_ICONS_DIR, FAVORITE_ICON_SIZE

class ThemeController:
    def __init__(self, settings):
        self.settings = settings
        # Загружаем манифест или дефолтный список тем
        if Path(THEMES_MANIFEST).exists():
            data = json.loads(Path(THEMES_MANIFEST).read_text(encoding="utf-8"))
            self.themes = data.get("themes", [])
        else:
            self.themes = [
                {"name": "light", "file": str(QSS_DIR / "light.qss"), "display": "Светлая"},
                {"name": "dark",  "file": str(QSS_DIR / "dark.qss"),  "display": "Тёмная"},
            ]

    def available(self):
        """Возвращает список (name, display) доступных тем."""
        return [(t["name"], t["display"]) for t in self.themes]

    def apply(self, name: str):
        """Применяет тему по имени и сохраняет в настройках."""
        theme = next((t for t in self.themes if t["name"] == name), None)
        if not theme:
            return
        path = Path(theme["file"])
        if path.exists():
            qss = path.read_text(encoding="utf-8")
            app = QApplication.instance()
            app.setStyleSheet(qss)
            self.settings.set_theme(name)

class FavoritesWidget(QWidget):
    def __init__(self, main_window, db):
        """
        :param main_window: MainWindow — для открытия ссылки
        :param db: Database — для запроса избранного
        """
        super().__init__()
        self.main = main_window
        self.db = db

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        self.update_favorites()

    def update_favorites(self):
        """Перестраивает панель избранного на основе БД."""
        # Очищаем старые кнопки
        while self.layout.count():
            item = self.layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Загружаем избранные ссылки
        raw_rows = self.db.conn.execute(
            "SELECT * FROM link WHERE is_favorite=1 ORDER BY position"
        ).fetchall()
        links = [dict(r) for r in raw_rows]

        for link in links:
            btn = QToolButton()
            # Иконка: либо кешированная, либо дефолтная «звезда»
            icon_name = link.get("icon_path") or ""
            icon_path = LINK_ICONS_DIR / icon_name
            if icon_name and Path(icon_path).exists():
                btn.setIcon(QIcon(str(icon_path)))
            else:
                # дефолтная звезда из ui_icons
                star = Path(__file__).parent.parent / "views" / "resources" / "ui_icons" / "favorite.svg"
                btn.setIcon(QIcon(str(star)))
            btn.setIconSize(FAVORITE_ICON_SIZE)
            btn.setToolTip(link["name"])
            btn.clicked.connect(lambda _, l=link: self.main.links._open_link(l))
            self.layout.addWidget(btn)

        # Позволяем растягиваться
        self.layout.addStretch()
