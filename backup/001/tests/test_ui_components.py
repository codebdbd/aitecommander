"""Тесты для UI компонентов с использованием pytest-qt."""

import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMessageBox
from PyQt6.QtCore import Qt, QTimer


pytestmark = pytest.mark.qt  # Помечаем все тесты как требующие Qt


@pytest.fixture(scope="session")
def qapp():
    """Fixture для QApplication (один на всю сессию)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestDialogManager:
    """Тесты для DialogManager."""
    
    def test_show_error_creates_message_box(self, qapp, qtbot):
        """Тест создания диалога ошибки."""
        from app.controllers.ui.dialogs.dialog_manager import DialogManager
        
        parent = QWidget()
        qtbot.addWidget(parent)
        
        # Патчим exec чтобы не показывать реально
        with patch.object(QMessageBox, 'exec') as mock_exec:
            DialogManager.show_error(
                parent,
                "Test error message",
                "Error Title"
            )
            
            # Проверяем, что exec был вызван
            mock_exec.assert_called_once()
    
    def test_ask_confirmation_returns_bool(self, qapp, qtbot):
        """Тест диалога подтверждения."""
        from app.controllers.ui.dialogs.dialog_manager import DialogManager
        
        parent = QWidget()
        qtbot.addWidget(parent)
        
        # Патчим exec для симуляции нажатия "Да"
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes):
            result = DialogManager.ask_confirmation(
                parent,
                "Delete 5 links?",
                "Confirmation"
            )
            
            assert result is True
        
        # Симулируем "Нет"
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.No):
            result = DialogManager.ask_confirmation(
                parent,
                "Delete 5 links?",
                "Confirmation"
            )
            
            assert result is False
    
    def test_show_info_with_details(self, qapp, qtbot):
        """Тест информационного диалога с подробностями."""
        from app.controllers.ui.dialogs.dialog_manager import DialogManager
        
        parent = QWidget()
        qtbot.addWidget(parent)
        
        with patch.object(QMessageBox, 'exec') as mock_exec:
            DialogManager.show_info(
                parent,
                "Operation completed",
                "Success",
                informative_text="All items processed",
                details="Log:\nItem 1: OK\nItem 2: OK"
            )
            
            mock_exec.assert_called_once()


class TestSignalGuard:
    """Тесты для signal_guard context manager."""
    
    def test_signal_guard_blocks_signals(self, qapp, qtbot):
        """Тест блокировки сигналов."""
        from app.utils.ui.signal_utils import signal_guard
        
        button = QPushButton("Test")
        qtbot.addWidget(button)
        
        clicked_count = []
        button.clicked.connect(lambda: clicked_count.append(1))
        
        # Без guard - сигнал работает
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert len(clicked_count) == 1
        
        # С guard - сигнал блокируется
        with signal_guard(button):
            qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        
        # Счётчик не изменился
        assert len(clicked_count) == 1
        
        # После guard - сигнал снова работает
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert len(clicked_count) == 2


class TestSuspendUpdates:
    """Тесты для suspend_updates context manager."""
    
    def test_suspend_updates_disables_then_enables(self, qapp, qtbot):
        """Тест приостановки обновлений виджета."""
        from app.utils.ui.widget_utils import suspend_updates
        
        widget = QWidget()
        qtbot.addWidget(widget)
        
        # Изначально обновления включены
        assert widget.updatesEnabled() is True
        
        # Внутри контекста - выключены
        with suspend_updates(widget):
            assert widget.updatesEnabled() is False
        
        # После контекста - снова включены
        assert widget.updatesEnabled() is True
    
    def test_suspend_updates_restores_on_exception(self, qapp, qtbot):
        """Тест восстановления при исключении."""
        from app.utils.ui.widget_utils import suspend_updates
        
        widget = QWidget()
        qtbot.addWidget(widget)
        
        try:
            with suspend_updates(widget):
                assert widget.updatesEnabled() is False
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Обновления должны быть восстановлены даже после исключения
        assert widget.updatesEnabled() is True


class TestThemeVariables:
    """Тесты для системы CSS-переменных."""
    
    def test_theme_variables_initialization(self):
        """Тест инициализации ThemeVariables."""
        from app.utils.ui.theme_variables import ThemeVariables
        
        theme = ThemeVariables('dark')
        
        assert theme.theme == 'dark'
        assert theme.colors is not None
        assert theme.sizes is not None
    
    def test_get_all_variables(self):
        """Тест получения всех переменных."""
        from app.utils.ui.theme_variables import ThemeVariables
        
        theme = ThemeVariables('dark')
        variables = theme.get_all_variables()
        
        # Проверяем наличие ключевых переменных
        assert 'bg_primary' in variables
        assert 'text_primary' in variables
        assert 'accent_primary' in variables
        assert 'border_radius_md' in variables
        assert 'padding_md' in variables
    
    def test_apply_to_template(self):
        """Тест применения переменных к шаблону."""
        from app.utils.ui.theme_variables import ThemeVariables
        
        theme = ThemeVariables('dark')
        template = "background: {bg_primary}; color: {text_primary};"
        
        result = theme.apply_to_template(template)
        
        # Переменные должны быть заменены
        assert '{bg_primary}' not in result
        assert '{text_primary}' not in result
        assert '#' in result  # Должны быть hex цвета
    
    def test_switch_theme(self):
        """Тест переключения темы."""
        from app.utils.ui.theme_variables import ThemeVariables, LIGHT_PALETTE, DARK_PALETTE
        
        theme = ThemeVariables('dark')
        assert theme.colors == DARK_PALETTE
        
        theme.switch_theme('light')
        assert theme.theme == 'light'
        assert theme.colors == LIGHT_PALETTE
    
    def test_missing_variable_raises_error(self):
        """Тест ошибки при отсутствующей переменной."""
        from app.utils.ui.theme_variables import ThemeVariables
        
        theme = ThemeVariables('dark')
        template = "background: {nonexistent_variable};"
        
        with pytest.raises(ValueError, match="Missing variable"):
            theme.apply_to_template(template)


class TestValidatorIntegration:
    """Интеграционные тесты валидаторов с UI."""
    
    def test_url_validation_in_line_edit(self, qapp, qtbot):
        """Тест валидации URL в QLineEdit."""
        from PyQt6.QtWidgets import QLineEdit
        from app.utils.ui.validators import validate_url
        
        line_edit = QLineEdit()
        qtbot.addWidget(line_edit)
        
        # Вводим валидный URL
        line_edit.setText("https://example.com")
        valid, error = validate_url(line_edit.text())
        
        assert valid is True
        
        # Вводим невалидный URL
        line_edit.setText("not a url")
        valid, error = validate_url(line_edit.text())
        
        assert valid is False
        assert error is not None


class TestResourceManager:
    """Тесты для ResourceManager."""
    
    def test_resource_manager_registers_cleanup(self, qapp):
        """Тест регистрации cleanup функции."""
        from app.utils.resource_manager import ResourceManager
        
        manager = ResourceManager()
        
        cleanup_called = []
        
        class TestResource:
            pass
        
        resource = TestResource()
        
        def cleanup():
            cleanup_called.append(True)
        
        manager.register(resource, cleanup, use_finalize=False)
        
        # Вызываем cleanup вручную
        manager.cleanup_all()
        
        assert len(cleanup_called) > 0


class TestWeakRefUsage:
    """Тесты использования WeakRef."""
    
    def test_weakref_prevents_memory_leak(self, qapp):
        """Тест предотвращения утечек через WeakRef."""
        import weakref
        
        class TestObject:
            def __init__(self):
                self.value = 42
        
        obj = TestObject()
        weak_ref = weakref.ref(obj)
        
        # Объект существует
        assert weak_ref() is not None
        assert weak_ref().value == 42
        
        # Удаляем сильную ссылку
        del obj
        
        # WeakRef теперь None
        assert weak_ref() is None
    
    def test_weakmethod_with_slot(self, qapp):
        """Тест WeakMethod для слотов."""
        import weakref
        
        class TestHandler:
            def __init__(self):
                self.called = False
            
            def handle(self, value):
                self.called = True
                return value * 2
        
        handler = TestHandler()
        weak_method = weakref.WeakMethod(handler.handle)
        
        # Вызываем через WeakMethod
        method = weak_method()
        assert method is not None
        result = method(21)
        assert result == 42
        assert handler.called is True
        
        # Удаляем handler
        del handler
        
        # WeakMethod теперь возвращает None
        assert weak_method() is None


class TestQTimerUsage:
    """Тесты использования QTimer."""
    
    def test_qtimer_single_shot(self, qapp, qtbot):
        """Тест QTimer.singleShot."""
        called = []
        
        def callback():
            called.append(True)
        
        # Планируем выполнение через 10ms
        QTimer.singleShot(10, callback)
        
        # Ждём выполнения
        qtbot.wait(20)
        
        assert len(called) == 1
    
    def test_qtimer_debounce(self, qapp, qtbot):
        """Тест дебаунсинга с QTimer."""
        calls = []
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setInterval(50)
        
        def callback():
            calls.append(True)
        
        timer.timeout.connect(callback)
        
        # Быстрые вызовы start() перезапускают таймер
        timer.start()
        qtbot.wait(20)
        timer.start()  # Перезапуск
        qtbot.wait(20)
        timer.start()  # Ещё перезапуск
        
        # Ждём выполнения
        qtbot.wait(100)
        
        # Callback должен вызваться только один раз
        assert len(calls) == 1
