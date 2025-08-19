import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QSizePolicy, QWidget, QHBoxLayout

from app.views.favorites_widget import FavoritesWidget
from app.views.recent_links_widget import RecentLinksWidget
from app.config_data import app_config


class DelayedWidgetsInitializer:
    """Компонент для отложенной инициализации виджетов избранных и недавних ссылок."""
    
    def __init__(self, main_window):
        """Инициализация компонента."""
        self.window = main_window
    
    def _apply_topbar_autohide(self):
        """Применить авто-скрытие топ-бара, если фильтр установлен."""
        try:
            filt = getattr(self.window, '_auto_hide_tree_filter', None)
            if filt:
                QTimer.singleShot(0, filt._apply)
        except Exception:
            pass
    
    def initialize_delayed_widgets(self):
        """Выполняет отложенную инициализацию виджетов избранных и недавних ссылок."""
        # Порядок инициализации может отличаться из-за разных источников (shown/QTimer),
        # поэтому каждая функция вставляет виджет в нужное место относительно уже созданных.
        # Итоговый порядок в топ-баре должен быть: QuickAdd → Favorites → Recent → Search
        self._initialize_recent_links_widget()
        self._initialize_favorites_widget()
        self._cleanup_temporary_db_reference()
        # После вставки панелей дернуть пересчет менеджера топ-бара, если он есть
        try:
            mgr = getattr(self.window, '_topbar_manager', None)
            if mgr:
                QTimer.singleShot(0, mgr.adjust)
        except Exception:
            pass
    
    def _initialize_recent_links_widget(self):
        """Инициализирует виджет недавних ссылок."""
        if not self.window.recent_links_widget and self.window.db_for_delayed_init:
            # Виджет больше не зависит от links_business напрямую
            # Создаем пассивный виджет без прямых зависимостей от бизнес-логики/БД
            self.window.recent_links_widget = RecentLinksWidget(self.window)
            self.window.recent_links_widget.setObjectName("recentLinksWidget")
            # Недавние не должны растягиваться, только поиск растягивается
            self.window.recent_links_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
            
            top_bar = self.window.content_container.layout()
            if top_bar:
                # Вставляем Recent по простому правилу:
                # после Favorites, иначе после QuickAdd, иначе перед Search
                insert_index = top_bar.count()
                try:
                    search_idx = next((i for i in range(top_bar.count())
                                       if top_bar.itemAt(i).widget() and top_bar.itemAt(i).widget().objectName() == "mainSearch"), None)
                    fav_idx = next((i for i in range(top_bar.count())
                                    if top_bar.itemAt(i).widget() and top_bar.itemAt(i).widget().objectName() == "favoritesWidget"), None)
                    qa_idx = next((i for i in range(top_bar.count())
                                   if top_bar.itemAt(i).widget() and top_bar.itemAt(i).widget().objectName() == "quickAddPanel"), None)
                    if fav_idx is not None:
                        insert_index = fav_idx + 1
                    elif qa_idx is not None:
                        insert_index = qa_idx + 1
                    elif search_idx is not None:
                        insert_index = search_idx
                except Exception:
                    if insert_index is None:
                        insert_index = top_bar.count()
                top_bar.insertWidget(insert_index, self.window.recent_links_widget)
            
            # Подключаем сигнал запуска ссылки к фасаду ссылок
            self.window.recent_links_widget.linkClicked.connect(self.window.links_actions.open_link)
            # При запуске ссылки виджет сам инициирует refresh_requested, см. его реализацию

            # Пассивная схема: сигнал виджета обрабатывает фасад ссылок
            if hasattr(self.window, 'links_actions') and self.window.links_actions:
                self.window.recent_links_widget.refresh_requested.connect(
                    self.window.links_actions.on_recent_refresh_requested
                )

            # Инициируем первичную загрузку после подключения обработчиков
            self.window.recent_links_widget.update_recent_links()
            # Если окно уже узкое, скрыть панель немедленно
            self._apply_topbar_autohide()
    
    def _initialize_favorites_widget(self):
        """Инициализирует виджет избранных ссылок."""
        if not self.window.fav_widget and self.window.db_for_delayed_init:
            # Виджет больше не зависит от links_business напрямую
            # Создаем пассивный виджет без прямых зависимостей от бизнес-логики/БД
            self.window.fav_widget = FavoritesWidget(self.window)
            self.window.fav_widget.setObjectName("favoritesWidget")
            # Избранные не должны растягиваться
            self.window.fav_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
            
            top_bar = self.window.content_container.layout()
            if top_bar:
                # Вставляем Favorites после QuickAdd, иначе перед Search
                insert_index = top_bar.count()
                try:
                    search_idx = next((i for i in range(top_bar.count())
                                       if top_bar.itemAt(i).widget() and top_bar.itemAt(i).widget().objectName() == "mainSearch"), None)
                    qa_idx = next((i for i in range(top_bar.count())
                                   if top_bar.itemAt(i).widget() and top_bar.itemAt(i).widget().objectName() == "quickAddPanel"), None)
                    if qa_idx is not None:
                        insert_index = qa_idx + 1
                    elif search_idx is not None:
                        insert_index = search_idx
                except Exception:
                    if insert_index is None:
                        insert_index = top_bar.count()
                top_bar.insertWidget(insert_index, self.window.fav_widget)
            
            # Подключаем сигнал запуска ссылки к фасаду ссылок
            self.window.fav_widget.linkClicked.connect(self.window.links_actions.open_link)

            # Пассивная схема: сигналы виджета обрабатывает фасад ссылок
            if hasattr(self.window, 'links_actions') and self.window.links_actions:
                self.window.fav_widget.refresh_requested.connect(
                    self.window.links_actions.on_favorites_refresh_requested
                )
                self.window.fav_widget.clear_requested.connect(
                    self.window.links_actions.on_favorites_clear_requested
                )

            # Инициируем первичную загрузку после подключения обработчиков
            self.window.fav_widget.update_favorites()
            # Если окно уже узкое, скрыть панель немедленно
            self._apply_topbar_autohide()
    
    def _cleanup_temporary_db_reference(self):
        """Удаляет временную ссылку на БД."""
        self.window.db_for_delayed_init = None
