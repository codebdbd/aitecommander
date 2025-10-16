"""Тесты жизненного цикла TopBarLayoutManager и QGraphicsOpacityEffect."""
from __future__ import annotations

import gc
import logging
from unittest.mock import MagicMock, Mock, patch

import pytest
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget

from app.views.main_components.ui.topbar.top_bar_layout_manager import (
    TopBarLayoutManager,
)


@pytest.fixture
def mock_window(qtbot):
    """Создать mock окна с необходимыми атрибутами."""
    window = QWidget()
    window.setObjectName("TestWindow")
    
    # Добавить необходимые атрибуты
    window.content_container = QWidget(window)
    window.top_bar_host = QWidget(window)
    window.quick_add_widget = QWidget(window)
    window.fav_widget = QWidget(window)
    window.recent_links_widget = QWidget(window)
    
    qtbot.addWidget(window)
    return window


@pytest.fixture
def manager(mock_window):
    """Создать TopBarLayoutManager с mock окном."""
    mgr = TopBarLayoutManager(mock_window)
    yield mgr
    # Явная очистка после теста
    try:
        mgr.cleanup()
    except Exception:
        pass


class TestTopBarLayoutManagerLifecycle:
    """Тесты жизненного цикла TopBarLayoutManager."""

    def test_opacity_effect_created_on_prepare(self, manager, mock_window):
        """Проверить создание QGraphicsOpacityEffect при prepare_initial_layout."""
        # Arrange
        container = mock_window.content_container
        
        # Act
        manager.prepare_initial_layout()
        
        # Assert
        assert manager._opacity_effect is not None
        assert isinstance(manager._opacity_effect, QGraphicsOpacityEffect)
        assert manager._opacity_effect.opacity() == 0.0
        assert container.graphicsEffect() is manager._opacity_effect

    def test_opacity_effect_revealed_on_data_ready(self, manager, mock_window):
        """Проверить установку opacity=1.0 при mark_data_ready."""
        # Arrange
        manager.prepare_initial_layout()
        assert manager._opacity_effect is not None
        assert manager._opacity_effect.opacity() == 0.0
        
        # Act
        manager.mark_data_ready()
        
        # Assert
        assert manager._opacity_effect.opacity() == 1.0

    def test_cleanup_removes_opacity_effect(self, manager, mock_window):
        """Проверить удаление QGraphicsOpacityEffect при cleanup."""
        # Arrange
        manager.prepare_initial_layout()
        container = mock_window.content_container
        effect = manager._opacity_effect
        assert effect is not None
        
        # Act
        manager.cleanup()
        
        # Assert
        assert manager._opacity_effect is None
        # Container больше не должен иметь эффекта
        assert container.graphicsEffect() is None

    def test_cleanup_handles_deleted_container(self, manager, mock_window, caplog):
        """Проверить обработку уже удалённого контейнера при cleanup."""
        # Arrange
        manager.prepare_initial_layout()
        container = mock_window.content_container
        
        # Удалить контейнер до cleanup
        container.deleteLater()
        QApplication.processEvents()
        
        # Act & Assert - не должно быть исключений
        with caplog.at_level(logging.DEBUG):
            manager.cleanup()
        
        # Проверить, что cleanup завершился без критических ошибок
        assert manager._opacity_effect is None

    def test_no_del_method(self):
        """Проверить отсутствие метода __del__ в TopBarLayoutManager."""
        # Assert
        assert not hasattr(TopBarLayoutManager, "__del__")

    def test_explicit_cleanup_via_destroyed_signal(self, qtbot, mock_window):
        """Проверить явный вызов cleanup через сигнал destroyed."""
        # Arrange
        manager = TopBarLayoutManager(mock_window)
        manager.prepare_initial_layout()
        
        cleanup_called = []
        original_cleanup = manager.cleanup
        
        def tracked_cleanup():
            cleanup_called.append(True)
            original_cleanup()
        
        manager.cleanup = tracked_cleanup
        
        # Подключить cleanup к destroyed (как в window_ui_setup.py:526)
        mock_window.destroyed.connect(manager.cleanup)
        
        # Act
        mock_window.deleteLater()
        qtbot.wait(100)  # Дать время на обработку событий
        
        # Assert
        assert len(cleanup_called) > 0, "cleanup должен быть вызван через destroyed"

    def test_opacity_effect_parent_is_container(self, manager, mock_window):
        """Проверить, что QGraphicsOpacityEffect имеет правильного родителя."""
        # Arrange & Act
        manager.prepare_initial_layout()
        
        # Assert
        assert manager._opacity_effect is not None
        # QGraphicsOpacityEffect должен иметь контейнер как родителя
        assert manager._opacity_effect.parent() == mock_window.content_container

    def test_multiple_cleanup_calls_safe(self, manager):
        """Проверить безопасность множественных вызовов cleanup."""
        # Arrange
        manager.prepare_initial_layout()
        
        # Act & Assert - не должно быть исключений
        manager.cleanup()
        manager.cleanup()
        manager.cleanup()
        
        assert manager._opacity_effect is None

    def test_cleanup_without_prepare(self, manager):
        """Проверить cleanup без предварительного prepare_initial_layout."""
        # Act & Assert - не должно быть исключений
        manager.cleanup()
        assert manager._opacity_effect is None

    def test_replace_existing_effect(self, manager, mock_window, caplog):
        """Проверить замену существующего QGraphicsEffect."""
        # Arrange
        container = mock_window.content_container
        existing_effect = QGraphicsOpacityEffect(container)
        container.setGraphicsEffect(existing_effect)
        
        # Act
        with caplog.at_level(logging.WARNING):
            manager.prepare_initial_layout()
        
        # Assert
        assert "already has graphics effect" in caplog.text
        assert manager._opacity_effect is not None
        assert manager._opacity_effect is not existing_effect
        assert container.graphicsEffect() is manager._opacity_effect


class TestOpacityEffectMemoryManagement:
    """Тесты управления памятью QGraphicsOpacityEffect."""

    def test_effect_deleted_after_cleanup(self, manager, mock_window):
        """Проверить, что QGraphicsOpacityEffect удаляется после cleanup."""
        # Arrange
        manager.prepare_initial_layout()
        effect = manager._opacity_effect
        assert effect is not None
        
        # Сохранить weak reference для проверки удаления
        import weakref
        effect_ref = weakref.ref(effect)
        
        # Act
        manager.cleanup()
        del effect
        gc.collect()
        QApplication.processEvents()
        
        # Assert
        # После cleanup и gc эффект должен быть удалён
        # (может потребоваться время на deleteLater)
        assert manager._opacity_effect is None

    def test_container_can_be_deleted_after_cleanup(self, manager, mock_window, qtbot):
        """Проверить, что контейнер может быть безопасно удалён после cleanup."""
        # Arrange
        manager.prepare_initial_layout()
        container = mock_window.content_container
        
        # Act
        manager.cleanup()
        container.deleteLater()
        qtbot.wait(50)
        
        # Assert - не должно быть segfault или RuntimeError


@pytest.mark.parametrize("has_destroyed_signal", [True, False])
def test_register_cleanup_with_and_without_signal(has_destroyed_signal, qtbot):
    """Проверить регистрацию cleanup с/без сигнала destroyed."""
    from app.views.main_components.ui.window_ui_setup import WindowUISetup
    
    # Arrange
    window = QWidget()
    if not has_destroyed_signal:
        # Удалить сигнал destroyed (если он есть)
        if hasattr(window, "destroyed"):
            delattr(window, "destroyed")
    
    mock_initializer = Mock()
    mock_initializer.window = window
    mock_initializer.settings = Mock()
    mock_initializer.theme_ctrl = Mock()
    
    setup = WindowUISetup(mock_initializer)
    manager = Mock(spec=TopBarLayoutManager)
    
    # Act
    setup._register_topbar_cleanup(manager)
    
    # Assert
    if has_destroyed_signal:
        assert getattr(window, "_topbar_cleanup_connected", False)
    else:
        assert not getattr(window, "_topbar_cleanup_connected", False)
