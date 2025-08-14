import logging
from pathlib import Path
from typing import Any, Dict, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.panel_utils import update_panel
from app.views.base_widgets import BaseLinksPanelWidget

DEFAULT_ICON_FILENAME = app_config.get_default_icons().get("default", "star.ico")
RECENT_LINKS_LIMIT = 10

class RecentLinksWidget(BaseLinksPanelWidget):
    """Виджет для отображения панели недавних ссылок.

    Виджет стал пассивным: он не обращается к бизнес-логике напрямую.
    Данные передаются извне через `set_recent_links`,
    а запрос на обновление инициируется сигналом `refresh_requested`.
    """

    link_launched: pyqtSignal = pyqtSignal()  # Сигнал запуска ссылки
    refresh_requested: pyqtSignal = pyqtSignal(int)  # Виджет просит обновить список (limit)

    def __init__(self, main_window):
        # Больше не передаем links_business/db в базовый класс
        super().__init__(main_window)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setObjectName("recentPanel")
        self.bg_frame.setObjectName("recentPanelBg")
        self._default_icon_path = self._get_default_icon_path()

        # Первичное обновление выполняется после подключения сигналов

    def _get_default_icon_path(self) -> Path:
        """Возвращает путь к иконке по умолчанию."""
        return icon_path_service.get_ui_icons_dir() / DEFAULT_ICON_FILENAME
    
    def _fetch_recent_links(self) -> List[Dict[str, Any]]:
        """[deprecated] Ранее получал ссылки из бизнес-логики. Больше не используется."""
        logging.warning("RecentLinksWidget._fetch_recent_links is deprecated: UI не должен тянуть данные.")
        return []

    def _create_recent_button(self, link_data: Dict[str, Any]) -> QToolButton:
        """Создает кнопку для недавней ссылки."""
        button = self._create_link_button(link_data)
        button.setObjectName("recentButton")
        button.clicked.connect(lambda: self._handle_link_click(link_data))
        return button

    def _handle_link_click(self, link_data) -> None:
        """Обрабатывает клик по кнопке недавней ссылки."""
        self._handle_link_click_base(link_data)
        self.link_launched.emit()
        # После клика просим контроллер обновить данные
        self.refresh_requested.emit(RECENT_LINKS_LIMIT)

    def update_recent_links(self) -> None:
        """[deprecated] Больше не тянет данные, только запрашивает их извне."""
        self.refresh_requested.emit(RECENT_LINKS_LIMIT)

    def set_recent_links(self, recent_links: List[Dict[str, Any]]) -> None:
        """Устанавливает данные недавних ссылок и перерисовывает панель."""
        update_panel(self, recent_links, self._create_recent_button)
