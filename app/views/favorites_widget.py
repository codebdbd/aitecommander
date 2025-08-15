import logging
from typing import Any, Dict, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.panel_utils import update_panel
from app.views.base_widgets import BaseLinksPanelWidget

# Используем значение по умолчанию из app_config
DEFAULT_ICON_FILENAME = app_config.get_default_icons().get("default", "star.ico")

class FavoritesWidget(BaseLinksPanelWidget):
    """Виджет для отображения панели избранных ссылок.

    Пассивный UI: не обращается к бизнес-логике напрямую.
    Данные передаются через `set_favorites`,
    обновление инициируется `refresh_requested`,
    очистка избранного инициируется `clear_requested`.
    """

    refresh_requested: pyqtSignal = pyqtSignal()  # Виджет просит обновить список
    clear_requested: pyqtSignal = pyqtSignal()    # Виджет просит очистить избранное

    def __init__(self, main_window):
        # Больше не передаем links_business/db в базовый класс
        super().__init__(main_window)
        # Фиксируем ширину панели, чтобы кнопки не сжимались — ширина определяется числом видимых кнопок
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setObjectName("favoritesPanel")
        self.bg_frame.setObjectName("favoritesPanelBg")
        self._default_icon_path = icon_path_service.get_ui_icons_dir() / DEFAULT_ICON_FILENAME  # теперь берётся из app_config

        # Инициируем первичную загрузку данных через сигнал
        self.update_favorites()

    def _fetch_favorites(self) -> List[Dict[str, Any]]:
        """[deprecated] Ранее получал данные из бизнес-логики. Больше не используется."""
        logging.warning("FavoritesWidget._fetch_favorites is deprecated: UI не должен тянуть данные.")
        return []

    def _create_favorite_button(self, link_data: Dict[str, Any]) -> QToolButton:
        """Создает кнопку для избранной ссылки."""
        button = self._create_link_button(link_data)
        button.setObjectName("favoriteButton")
        button.clicked.connect(lambda: self._handle_link_click(link_data))
        return button

    def _handle_link_click(self, link_data) -> None:
        """Обработчик клика по кнопке избранного."""
        self._handle_link_click_base(link_data)

    def update_favorites(self) -> None:
        """Запрашивает обновление данных извне."""
        self.refresh_requested.emit()

    def set_favorites(self, favorites: List[Dict[str, Any]]) -> None:
        """Устанавливает избранные ссылки и перерисовывает панель."""
        update_panel(self, favorites, self._create_favorite_button)


    def clear_favorites(self):
        """Инициирует очистку избранного и повторное обновление."""
        self.clear_requested.emit()
        self.update_favorites()