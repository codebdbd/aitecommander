import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.views.base_widgets import BasePanelWidget


class QuickAddWidget(BasePanelWidget):
    """Виджет кнопок быстрого добавления в верхней панели."""
    
    # Сигнал слабой связанности: внешний код решает, как добавлять ссылку
    # payload: {"link_type": str, "category_id": Optional[int]}
    quickAddRequested: pyqtSignal = pyqtSignal(object)
    
    def __init__(self, main_window=None, links_controller=None, category_provider=None):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setObjectName("quickAddPanel")
        self.bg_frame.setObjectName("quickAddPanelBg")
        
        # Зависимости оставлены для обратной совместимости, но внутри не используются
        self.links_controller = links_controller  # deprecated
        self.category_provider = category_provider  # deprecated
        
        self._setup_buttons()

    def _setup_buttons(self):
        """Создает кнопки для каждого типа быстрого добавления."""
        quick_types = app_config.get_quick_types()
        # Используем единые параметры для всех кнопок топпанели
        button_size = app_config.get_top_panel_button_size()
        icon_size = app_config.get_top_panel_icon_size()
        quick_type_tooltips = app_config.get_quick_type_tooltips()
        
        for code, icon_name, tooltip in quick_types:
            btn = QToolButton()
            btn.setObjectName("quickButton")  # Для CSS стилизации
            btn.setFixedSize(button_size, button_size)
            btn.setIconSize(icon_size)
            icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            if icon_path.exists():
                btn.setIcon(create_icon_from_path(str(icon_path)))
            
            btn.setToolTip(quick_type_tooltips.get(code, tooltip))
            btn.clicked.connect(lambda _, ct=code: self._handle_quick_add(ct))
            self.layout.addWidget(btn)
    
    def _handle_quick_add(self, link_type: str):
        """Обрабатывает клик по кнопке быстрого добавления."""
        category_id = None
        if self.category_provider and hasattr(self.category_provider, 'get_current_category_id'):
            try:
                category_id = self.category_provider.get_current_category_id()
            except Exception as exc:
                logging.warning("QuickAddWidget: не удалось получить текущую категорию: %s", exc)
        payload = {"link_type": link_type, "category_id": category_id}
        try:
            self.quickAddRequested.emit(payload)
        except Exception as exc:
            logging.error("QuickAddWidget: не удалось эмитить quickAddRequested: %s", exc)