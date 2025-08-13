import logging

from PyQt6.QtWidgets import QSizePolicy

from app.views.favorites_widget import FavoritesWidget
from app.views.recent_links_widget import RecentLinksWidget


class DelayedWidgetsInitializer:
    """Компонент для отложенной инициализации виджетов избранных и недавних ссылок."""
    
    def __init__(self, main_window):
        """Инициализация компонента."""
        self.window = main_window
    
    def initialize_delayed_widgets(self):
        """Выполняет отложенную инициализацию виджетов избранных и недавних ссылок."""
        self._initialize_recent_links_widget()
        self._initialize_favorites_widget()
        self._cleanup_temporary_db_reference()
    
    def _initialize_recent_links_widget(self):
        """Инициализирует виджет недавних ссылок."""
        if not self.window.recent_links_widget and self.window.db_for_delayed_init:
            # Виджет больше не зависит от links_business напрямую
            # Создаем пассивный виджет без прямых зависимостей от бизнес-логики/БД
            self.window.recent_links_widget = RecentLinksWidget(self.window)
            self.window.recent_links_widget.setObjectName("recentLinksWidget")
            self.window.recent_links_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed, 
                QSizePolicy.Policy.Fixed
            )
            
            top_bar = self.window.content_container.layout()
            if top_bar:
                top_bar.insertWidget(0, self.window.recent_links_widget)
            
            # Подключаем сигнал запуска ссылки к обработчику в окне
            self.window.recent_links_widget.linkClicked.connect(self.window.open_link)
            # При запуске ссылки виджет сам инициирует refresh_requested, см. его реализацию

            # Пассивная схема: сигнал виджета обрабатывает контроллер ссылок, если он уже создан
            if hasattr(self.window, 'links') and self.window.links:
                self.window.recent_links_widget.refresh_requested.connect(
                    self.window.links.on_recent_refresh_requested
                )

            # Инициируем первичную загрузку после подключения обработчиков
            self.window.recent_links_widget.update_recent_links()
    
    def _initialize_favorites_widget(self):
        """Инициализирует виджет избранных ссылок."""
        if not self.window.fav_widget and self.window.db_for_delayed_init:
            # Виджет больше не зависит от links_business напрямую
            # Создаем пассивный виджет без прямых зависимостей от бизнес-логики/БД
            self.window.fav_widget = FavoritesWidget(self.window)
            self.window.fav_widget.setObjectName("favoritesWidget")
            self.window.fav_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed, 
                QSizePolicy.Policy.Fixed
            )
            
            top_bar = self.window.content_container.layout()
            if top_bar:
                for i in range(top_bar.count()):
                    item = top_bar.itemAt(i)
                    if (item.widget() and 
                        item.widget().objectName() == "favQuickSeparatorAfter"):
                        top_bar.insertWidget(i, self.window.fav_widget)
                        break
            
            # Подключаем сигнал запуска ссылки к обработчику в окне
            self.window.fav_widget.linkClicked.connect(self.window.open_link)

            # Пассивная схема: сигналы виджета обрабатывает контроллер ссылок, если он уже создан
            if hasattr(self.window, 'links') and self.window.links:
                self.window.fav_widget.refresh_requested.connect(
                    self.window.links.on_favorites_refresh_requested
                )
                self.window.fav_widget.clear_requested.connect(
                    self.window.links.on_favorites_clear_requested
                )

            # Инициируем первичную загрузку после подключения обработчиков
            self.window.fav_widget.update_favorites()
    
    def _cleanup_temporary_db_reference(self):
        """Удаляет временную ссылку на БД."""
        self.window.db_for_delayed_init = None
