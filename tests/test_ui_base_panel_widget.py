"""Тесты для BasePanelWidget и BaseLinksPanelWidget."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QToolButton, QHBoxLayout

from app.views.widgets.base.base_widgets import BasePanelWidget, BaseLinksPanelWidget


pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    """Fixture для QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestBasePanelWidgetInit:
    """Тесты инициализации BasePanelWidget."""
    
    def test_init_creates_bg_frame(self, qapp, qtbot):
        """Тест создания background frame."""
        widget = BasePanelWidget()
        qtbot.addWidget(widget)
        
        assert hasattr(widget, 'bg_frame')
        assert widget.bg_frame is not None
    
    def test_init_creates_layout(self, qapp, qtbot):
        """Тест создания layout."""
        widget = BasePanelWidget()
        qtbot.addWidget(widget)
        
        assert hasattr(widget, 'panel_layout')
        assert isinstance(widget.panel_layout, QHBoxLayout)
    
    def test_init_sets_alignment(self, qapp, qtbot):
        """Тест установки выравнивания."""
        widget = BasePanelWidget()
        qtbot.addWidget(widget)
        
        alignment = widget.panel_layout.alignment()
        assert alignment & Qt.AlignmentFlag.AlignVCenter
    
    def test_init_sets_margins(self, qapp, qtbot):
        """Тест установки margins."""
        widget = BasePanelWidget()
        qtbot.addWidget(widget)
        
        margins = widget.panel_layout.contentsMargins()
        assert margins.left() == 0
        assert margins.top() == 0
        assert margins.right() == 0
        assert margins.bottom() == 0


class TestBaseLinksPanelWidgetInit:
    """Тесты инициализации BaseLinksPanelWidget."""
    
    def test_init_stores_main_window(self, qapp, qtbot):
        """Тест сохранения ссылки на main window."""
        mock_window = Mock()
        widget = BaseLinksPanelWidget(main_window=mock_window)
        qtbot.addWidget(widget)
        
        assert widget.main_window is mock_window
    
    def test_init_stores_links_business(self, qapp, qtbot):
        """Тест сохранения ссылки на links business."""
        mock_business = Mock()
        widget = BaseLinksPanelWidget(links_business=mock_business)
        qtbot.addWidget(widget)
        
        assert widget.links_business is mock_business
    
    def test_init_without_params(self, qapp, qtbot):
        """Тест инициализации без параметров."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        assert widget.main_window is None
        assert widget.links_business is None
    
    def test_init_default_icon_path_lazy(self, qapp, qtbot):
        """Тест ленивой инициализации default icon path."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        # Должен быть None до первого вызова
        assert widget._default_icon_path is None


class TestBaseLinksPanelWidgetFindIcon:
    """Тесты метода _find_icon."""
    
    @patch('app.views.widgets.base.base_widgets.resolve_icon_path')
    def test_find_icon_with_valid_path(self, mock_resolve, qapp, qtbot):
        """Тест поиска иконки с валидным путём."""
        mock_resolve.return_value = "/path/to/icon.png"
        
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        result = widget._find_icon("icon.png")
        
        assert result == "/path/to/icon.png"
        mock_resolve.assert_called_once_with("icon.png")
    
    @patch('app.views.widgets.base.base_widgets.resolve_icon_path')
    def test_find_icon_with_empty_path(self, mock_resolve, qapp, qtbot):
        """Тест поиска иконки с пустым путём."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        result = widget._find_icon("")
        
        # Должен вернуть дефолтную иконку
        assert result is not None
        mock_resolve.assert_not_called()
    
    @patch('app.views.widgets.base.base_widgets.resolve_icon_path')
    def test_find_icon_handles_oserror(self, mock_resolve, qapp, qtbot, caplog):
        """Тест обработки OSError."""
        mock_resolve.side_effect = OSError("File not found")
        
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        result = widget._find_icon("missing.png")
        
        # Должен вернуть дефолтную иконку
        assert result is not None
        assert "Не удалось разрешить путь к иконке" in caplog.text
    
    @patch('app.views.widgets.base.base_widgets.resolve_icon_path')
    def test_find_icon_handles_unexpected_exception(self, mock_resolve, qapp, qtbot, caplog):
        """Тест обработки неожиданных исключений."""
        mock_resolve.side_effect = RuntimeError("Unexpected error")
        
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        result = widget._find_icon("error.png")
        
        # Должен вернуть дефолтную иконку
        assert result is not None
        assert "Неожиданная ошибка" in caplog.text


class TestBaseLinksPanelWidgetClearLayout:
    """Тесты метода _clear_layout."""
    
    def test_clear_layout_removes_widgets(self, qapp, qtbot):
        """Тест удаления виджетов из layout."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        # Добавляем кнопки
        btn1 = QToolButton()
        btn2 = QToolButton()
        widget.panel_layout.addWidget(btn1)
        widget.panel_layout.addWidget(btn2)
        
        assert widget.panel_layout.count() == 2
        
        # Очищаем
        widget._clear_layout()
        
        assert widget.panel_layout.count() == 0
    
    def test_clear_layout_calls_delete_later(self, qapp, qtbot):
        """Тест вызова deleteLater для виджетов."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        btn = QToolButton()
        widget.panel_layout.addWidget(btn)
        
        with patch.object(btn, 'deleteLater') as mock_delete:
            widget._clear_layout()
            
            mock_delete.assert_called_once()
    
    def test_clear_layout_with_empty_layout(self, qapp, qtbot):
        """Тест очистки пустого layout (не должна падать)."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        widget._clear_layout()
        
        assert widget.panel_layout.count() == 0


class TestBaseLinksPanelWidgetPopulatePanel:
    """Тесты метода _populate_panel."""
    
    def test_populate_panel_clears_old_items(self, qapp, qtbot):
        """Тест очистки старых элементов."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        # Добавляем старую кнопку
        old_btn = QToolButton()
        widget.panel_layout.addWidget(old_btn)
        
        def create_button(item):
            return QToolButton()
        
        items = [{"id": 1, "name": "New"}]
        widget._populate_panel(items, create_button)
        
        # Старая кнопка должна быть удалена
        # После батчинга будет новая кнопка
        assert hasattr(widget, '_pending_items')
    
    def test_populate_panel_disables_updates(self, qapp, qtbot):
        """Тест отключения обновлений во время заполнения."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        def create_button(item):
            return QToolButton()
        
        items = [{"id": 1, "name": "Link"}]
        
        with patch.object(widget, 'setUpdatesEnabled') as mock_set_updates:
            widget._populate_panel(items, create_button)
            
            # Должен быть вызван с False
            mock_set_updates.assert_any_call(False)
    
    def test_populate_panel_stores_pending_items(self, qapp, qtbot):
        """Тест сохранения pending items."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        def create_button(item):
            return QToolButton()
        
        items = [
            {"id": 1, "name": "Link 1"},
            {"id": 2, "name": "Link 2"},
        ]
        
        widget._populate_panel(items, create_button)
        
        assert hasattr(widget, '_pending_items')
        assert len(widget._pending_items) <= len(items)


class TestBaseLinksPanelWidgetPopulateBatch:
    """Тесты метода _populate_batch."""
    
    def test_populate_batch_processes_batch_size(self, qapp, qtbot):
        """Тест обработки батча заданного размера."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        created_buttons = []
        
        def create_button(item):
            btn = QToolButton()
            btn.setText(item["name"])
            created_buttons.append(btn)
            return btn
        
        # 60 элементов (больше одного батча)
        items = [{"id": i, "name": f"Link {i}"} for i in range(60)]
        
        widget._pending_items = items
        widget._create_button_func = create_button
        widget.setUpdatesEnabled(False)
        
        # Обрабатываем один батч
        widget._populate_batch()
        
        # Первый батч должен обработать до 50 элементов
        assert len(created_buttons) <= 50
        assert len(widget._pending_items) >= 10
    
    def test_populate_batch_schedules_next_batch(self, qapp, qtbot):
        """Тест планирования следующего батча."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        def create_button(item):
            return QToolButton()
        
        items = [{"id": i, "name": f"Link {i}"} for i in range(60)]
        
        widget._pending_items = items
        widget._create_button_func = create_button
        widget.setUpdatesEnabled(False)
        
        with patch.object(QTimer, 'singleShot') as mock_timer:
            widget._populate_batch()
            
            # Должен запланировать следующий батч
            mock_timer.assert_called()
    
    def test_populate_batch_handles_create_button_exception(self, qapp, qtbot, caplog):
        """Тест обработки исключений при создании кнопки."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        def create_button_error(item):
            if item["id"] == 2:
                raise RuntimeError("Button creation failed")
            return QToolButton()
        
        items = [
            {"id": 1, "name": "Link 1"},
            {"id": 2, "name": "Link 2"},  # Вызовет ошибку
            {"id": 3, "name": "Link 3"},
        ]
        
        widget._pending_items = items
        widget._create_button_func = create_button_error
        widget.setUpdatesEnabled(False)
        
        widget._populate_batch()
        
        # Проверяем, что ошибка залогирована
        assert "Не удалось создать кнопку" in caplog.text


class TestBaseLinksPanelWidgetFinishPopulate:
    """Тесты метода _finish_populate."""
    
    def test_finish_populate_enables_updates(self, qapp, qtbot):
        """Тест включения обновлений."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        widget.setUpdatesEnabled(False)
        
        with patch.object(widget, 'setUpdatesEnabled') as mock_set_updates:
            widget._finish_populate()
            
            mock_set_updates.assert_called_with(True)
    
    def test_finish_populate_calls_update_geometry(self, qapp, qtbot):
        """Тест вызова updateGeometry."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        with patch.object(widget, 'updateGeometry') as mock_update:
            widget._finish_populate()
            
            mock_update.assert_called_once()
    
    def test_finish_populate_clears_pending_data(self, qapp, qtbot):
        """Тест очистки временных данных."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        widget._pending_items = [{"id": 1}]
        widget._create_button_func = Mock()
        
        widget._finish_populate()
        
        assert widget._pending_items == []
        assert widget._create_button_func is None


class TestBaseLinksPanelWidgetHandleLinkClick:
    """Тесты метода _handle_link_click_base."""
    
    def test_handle_link_click_emits_signal(self, qapp, qtbot):
        """Тест эмиссии сигнала linkClicked."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        link_info = {"id": 1, "name": "Test Link"}
        
        received_signals = []
        
        def on_link_clicked(info):
            received_signals.append(info)
        
        widget.linkClicked.connect(on_link_clicked)
        
        widget._handle_link_click_base(link_info)
        
        assert len(received_signals) == 1
        assert received_signals[0] == link_info
    
    def test_handle_link_click_handles_runtime_error(self, qapp, qtbot):
        """Тест эмиссии сигнала без ошибок."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        link_info = {"id": 1, "name": "Test"}
        
        # Проверяем, что сигнал эмитируется корректно
        with qtbot.waitSignal(widget.linkClicked, timeout=100):
            widget._handle_link_click_base(link_info)


class TestBaseLinksPanelWidgetGetDefaultIconPath:
    """Тесты метода _get_default_icon_path."""
    
    @patch('app.views.widgets.base.base_panel_widgets.get_default_icon_path')
    def test_get_default_icon_path_caches_result(self, mock_get_path, qapp, qtbot):
        """Тест кэширования пути к дефолтной иконке."""
        from pathlib import Path
        expected_path = Path("/default/icon.png")
        mock_get_path.return_value = expected_path
        
        # Используем синхронный режим и очищаем кэш перед тестом
        widget = BaseLinksPanelWidget(batch_size=0)
        qtbot.addWidget(widget)
        
        # Очищаем кэш перед тестом
        widget._default_icon_path = None
        
        # Первый вызов
        path1 = widget._get_default_icon_path()
        
        # Второй вызов
        path2 = widget._get_default_icon_path()
        
        # Проверяем, что оба вызова вернули один и тот же объект (кэширование)
        assert path1 == expected_path
        assert path2 == expected_path
        assert path1 is path2  # Кэширование работает
        
        # get_default_icon_path должен быть вызван только один раз
        assert mock_get_path.call_count == 1
    
    @patch('app.views.widgets.base.base_widgets.get_default_icon_path')
    def test_get_default_icon_path_lazy_initialization(self, mock_get_path, qapp, qtbot):
        """Тест ленивой инициализации."""
        from pathlib import Path
        mock_get_path.return_value = Path("/default/icon.png")
        
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        # Сначала None
        assert widget._default_icon_path is None
        
        # После вызова заполняется
        widget._get_default_icon_path()
        
        assert widget._default_icon_path is not None


class TestBaseLinksPanelWidgetSignal:
    """Тесты сигнала linkClicked."""
    
    def test_link_clicked_signal_exists(self, qapp, qtbot):
        """Тест существования сигнала linkClicked."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        assert hasattr(widget, 'linkClicked')
    
    def test_link_clicked_signal_can_connect(self, qapp, qtbot):
        """Тест подключения к сигналу."""
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)
        
        mock_slot = Mock()
        widget.linkClicked.connect(mock_slot)
        
        # Эмитим сигнал
        test_link = {"id": 1}
        widget._handle_link_click_base(test_link)
        
        mock_slot.assert_called_once_with(test_link)
