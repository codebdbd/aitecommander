import logging
from typing import Any, Dict, List, Literal, Optional

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.utils.ui.icon.path_service import icon_path_service
from app.views.base_widgets import BaseLinksPanelWidget

RECENT_LINKS_LIMIT = 10

Mode = Literal["favorites", "recent", "quick"]


class TopPanelWidget(BaseLinksPanelWidget):
    """Универсальный виджет верхней панели.

    Режимы:
      - favorites: панель избранных ссылок
      - recent: панель недавних ссылок
      - quick: панель быстрых действий (добавление)

    Унифицированные сигналы:
      - actionRequested(object): универсальные события UI
      - refreshRequested(object): запрос обновления данных
      - clearRequested(): запрос очистки (актуально для favorites)

    Для обратной совместимости оставлены сигналы и методы предыдущих виджетов:
      - linkClicked(object)
      - refresh_requested([int])
      - clear_requested()
      - update_favorites()/update_recent_links()/clear_favorites()
      - quickAddRequested(object)
    """

    # Унифицированные сигналы
    actionRequested: pyqtSignal = pyqtSignal(object)
    refreshRequested: pyqtSignal = pyqtSignal(object)
    clearRequested: pyqtSignal = pyqtSignal()

    # Совместимость: перегруженный сигнал
    #  - favorites: refresh_requested()
    #  - recent:    refresh_requested(int)
    refresh_requested: pyqtSignal = pyqtSignal([], [int])
    clear_requested: pyqtSignal = pyqtSignal()
    quickAddRequested: pyqtSignal = pyqtSignal(object)

    def __init__(
        self,
        main_window=None,
        mode: Mode = "favorites",
        category_provider: Optional[object] = None,
    ):
        super().__init__(main_window)
        self._main_window = main_window
        self.mode: Mode = mode
        self.category_provider = category_provider
        self._default_icon_path = get_default_icon_path()

        # Общая политика размеров: фиксированная ширина/высота для кнопок панелей
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Настройка objectName и фоновой рамки для разных режимов
        if mode == "favorites":
            self.setObjectName("favoritesPanel")
            self.bg_frame.setObjectName("favoritesPanelBg")
        elif mode == "recent":
            self.setObjectName("recentPanel")
            self.bg_frame.setObjectName("recentPanelBg")
        else:  # quick
            self.setObjectName("quickAddPanel")
            self.bg_frame.setObjectName("quickAddPanelBg")

        # Построение содержимого
        if self.mode == "quick":
            self._setup_quick_buttons()
        else:
            # В режимах ссылок данные приходят извне через set_data()
            pass

    # ---------- Общие публичные методы ----------

    def set_data(self, items: List[Dict[str, Any]]) -> None:
        """Устанавливает данные панели (для favorites/recent)."""
        if self.mode == "quick":
            return
        factory = (
            self._create_favorite_button
            if self.mode == "favorites"
            else self._create_recent_button
        )
        self._populate_panel(items, factory)

        # Корректно выставим видимость панели в зависимости от наличия элементов
        try:
            self.setVisible(bool(items))
        except Exception:
            pass

        # Попросим менеджер топ-бара пересчитать видимость кнопок/панелей
        try:
            mgr = getattr(self._main_window, "_topbar_manager", None)
            if mgr:
                mgr._request_adjust()
        except Exception:
            pass

    def update(self) -> None:
        """Запрашивает обновление данных извне."""
        # Больше не инициируем refresh из программного update(),
        # чтобы избежать кругового пути. Обновление инициируется
        # контроллером (request_refresh/refresh_*) и пользовательскими действиями.
        return

    def clear(self) -> None:
        """Инициирует очистку (только favorites)."""
        if self.mode == "favorites":
            self.clear_requested.emit()
            self.clearRequested.emit()

    # ---------- Методы совместимости ----------

    def set_favorites(self, favorites: List[Dict[str, Any]]) -> None:
        if self.mode == "favorites":
            self.set_data(favorites)

    def set_recent_links(self, recent_links: List[Dict[str, Any]]) -> None:
        if self.mode == "recent":
            self.set_data(recent_links)

    def update_favorites(self) -> None:
        if self.mode == "favorites":
            self.update()

    def update_recent_links(self) -> None:
        if self.mode == "recent":
            self.update()

    def clear_favorites(self) -> None:
        if self.mode == "favorites":
            self.clear()

    # ---------- Кнопки для ссылок ----------

    def _create_favorite_button(self, link_data: Dict[str, Any]) -> QToolButton:
        button = self._create_link_button(link_data)
        button.setObjectName("favoriteButton")
        button.clicked.connect(lambda: self._handle_link_click(link_data))
        return button

    def _create_recent_button(self, link_data: Dict[str, Any]) -> QToolButton:
        button = self._create_link_button(link_data)
        button.setObjectName("recentButton")
        button.clicked.connect(lambda: self._handle_recent_click(link_data))
        return button

    def _handle_link_click(self, link_data: Dict[str, Any]) -> None:
        """Клик по ссылке в режиме favorites."""
        self._handle_link_click_base(link_data)  # эмитит linkClicked(link_data)
        # Унифицированный сигнал
        try:
            self.actionRequested.emit({"type": "open_link", "link": link_data})
        except Exception as exc:
            logging.error("TopPanelWidget: failed to emit actionRequested: %s", exc)

    def _handle_recent_click(self, link_data: Dict[str, Any]) -> None:
        """Клик по ссылке в режиме recent: открыть и запросить обновление."""
        self._handle_link_click_base(link_data)
        # Унифицированный сигнал действия
        try:
            self.actionRequested.emit({"type": "open_link", "link": link_data})
        except Exception as exc:
            logging.error("TopPanelWidget: failed to emit actionRequested: %s", exc)
        # Запросить обновление после клика (как было в RecentLinksWidget)
        try:
            self.refresh_requested[int].emit(RECENT_LINKS_LIMIT)
            self.refreshRequested.emit({"limit": RECENT_LINKS_LIMIT})
        except Exception as exc:
            logging.warning(
                "TopPanelWidget: failed to emit refresh after recent click: %s", exc
            )

    # ---------- Кнопки Quick Add ----------

    def _setup_quick_buttons(self) -> None:
        quick_types = app_config.get_quick_types()
        button_size = app_config.get_top_panel_button_size()
        icon_size = app_config.get_top_panel_icon_size()
        quick_type_tooltips = app_config.get_quick_type_tooltips()

        for code, icon_name, tooltip in quick_types:
            btn = QToolButton()
            btn.setObjectName("quickButton")
            btn.setFixedSize(button_size, button_size)
            btn.setIconSize(QSize(icon_size[0], icon_size[1]))
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            if icon_path.exists():
                btn.setIcon(create_icon_from_path(str(icon_path)))
            btn.setToolTip(quick_type_tooltips.get(code, tooltip))
            btn.clicked.connect(lambda _, ct=code: self._handle_quick_add(ct))
            # Добавляем в panel_layout (не затеняем QWidget.layout())
            self.panel_layout.addWidget(btn)

    def _handle_quick_add(self, link_type: str) -> None:
        category_id = None
        if self.category_provider and hasattr(
            self.category_provider, "get_current_category_id"
        ):
            try:
                category_id = self.category_provider.get_current_category_id()
            except Exception as exc:
                logging.warning(
                    "TopPanelWidget: не удалось получить текущую категорию: %s", exc
                )
        payload = {
            "type": "quick_add",
            "link_type": link_type,
            "category_id": category_id,
        }
        try:
            # Совместимость
            self.quickAddRequested.emit(
                {"link_type": link_type, "category_id": category_id}
            )
            # Унифицированный
            self.actionRequested.emit(payload)
        except Exception as exc:
            logging.error(
                "TopPanelWidget: не удалось эмитить сигналы quick add: %s", exc
            )
