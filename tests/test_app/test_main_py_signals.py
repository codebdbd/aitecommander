# tests/test_app/test_main_py_signals.py

import os
import signal
import sys
import time
from unittest.mock import patch, MagicMock

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

# Пропускаем тесты, если мы не на Unix-подобной системе
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Signal tests are for Unix-like systems")

# Добавляем путь к приложению, чтобы импортировать main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../app')))

# Этот импорт должен быть после добавления пути
from app import main as app_main


@pytest.fixture
def mock_app_init(monkeypatch):
    """Мок для ApplicationInitializer, чтобы избежать полной инициализации."""
    mock_initializer = MagicMock()
    mock_initializer.initialize_all.return_value = True
    mock_initializer_class = MagicMock(return_value=mock_initializer)
    monkeypatch.setattr('app.main.ApplicationInitializer', mock_initializer_class)
    
    # Мокаем should_install_signal_handlers, чтобы всегда устанавливать обработчики
    monkeypatch.setattr('app.main.should_install_signal_handlers', lambda: True)
    
    # Мокаем AppShutdownController, так как он зависит от MainWindow
    monkeypatch.setattr('app.controllers.system.app_shutdown_controller.AppShutdownController', MagicMock())
    
    return mock_initializer_class, mock_initializer


def test_sigterm_triggers_graceful_shutdown_via_qsocketnotifier(qtbot, mock_app_init):
    """
    Проверяет, что SIGTERM вызывает QCoreApplication.exit() через QSocketNotifier.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Мокаем QCoreApplication.exit для проверки вызова
    with patch('PyQt6.QtCore.QCoreApplication.exit') as mock_exit:
        
        # Запускаем main в отдельном потоке или используем QTimer для симуляции
        # Здесь мы просто вызываем ключевые части main() для настройки
        initializer = app_main.ApplicationInitializer()
        notifiers = app_main.setup_signal_handling(app, initializer)
        assert len(notifiers) > 0, "QSocketNotifier должен был быть создан"

        # Даем циклу событий Qt время на обработку
        qtbot.wait(100)

        # Отправляем сигнал SIGTERM текущему процессу
        os.kill(os.getpid(), signal.SIGTERM)

        # Ждем, пока сигнал будет обработан циклом событий
        # qtbot.wait_until будет ждать, пока лямбда не вернет True
        try:
            qtbot.wait_until(lambda: mock_exit.called, timeout=1000)
        except TimeoutError:
            pytest.fail("QCoreApplication.exit не был вызван после отправки SIGTERM")

        # Проверяем, что exit был вызван с правильным кодом
        expected_exit_code = app_main.SIGNAL_EXIT_CODE_BASE + signal.SIGTERM
        mock_exit.assert_called_once_with(expected_exit_code)

        # Очистка: восстанавливаем обработчик по умолчанию
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        
        # Закрываем пайпы, если они были созданы
        if app_main.unix_signal_pipe_read != -1:
            os.close(app_main.unix_signal_pipe_read)
            os.close(app_main.unix_signal_pipe_write)
            app_main.unix_signal_pipe_read = -1
            app_main.unix_signal_pipe_write = -1

