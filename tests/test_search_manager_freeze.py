"""Тесты freeze/unfreeze механизма SearchWidgetManager."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLineEdit

from app.views.main_components.ui.topbar.services.search_manager import (
    SearchWidgetManager,
)
from app.views.main_components.ui.topbar.models.topbar_constants import (
    TOPBAR_CONSTANTS as C,
)


@pytest.fixture
def search_widget(qtbot):
    """Создать QLineEdit для тестов."""
    widget = QLineEdit()
    widget.setMinimumWidth(C.MIN_SEARCH_WIDTH_ABSOLUTE)
    widget.setMaximumWidth(C.MAX_WIDGET_WIDTH)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def search_manager():
    """Создать SearchWidgetManager."""
    from unittest.mock import Mock
    width_calculator = Mock()
    return SearchWidgetManager(width_calculator)


class TestFreezeUnfreezeMechanism:
    """Тесты механизма freeze/unfreeze."""

    def test_freeze_saves_constraints(self, search_manager, search_widget):
        """Проверить сохранение ограничений при freeze."""
        # Arrange
        initial_min = search_widget.minimumWidth()
        initial_max = search_widget.maximumWidth()
        freeze_width = 200

        # Act
        search_manager.freeze_width(search_widget, freeze_width)

        # Assert
        assert search_widget.minimumWidth() == freeze_width
        assert search_widget.maximumWidth() == freeze_width
        # Проверить, что ограничения сохранены
        search_id = id(search_widget)
        assert search_id in search_manager._saved_constraints
        saved_min, saved_max = search_manager._saved_constraints[search_id]
        assert saved_min == initial_min
        assert saved_max == initial_max

    def test_unfreeze_restores_constraints(self, search_manager, search_widget):
        """Проверить восстановление ограничений при unfreeze."""
        # Arrange
        initial_min = search_widget.minimumWidth()
        initial_max = search_widget.maximumWidth()
        freeze_width = 200

        search_manager.freeze_width(search_widget, freeze_width)
        assert search_widget.minimumWidth() == freeze_width

        # Act
        search_manager.unfreeze_width(search_widget)

        # Assert
        assert search_widget.minimumWidth() == initial_min
        assert search_widget.maximumWidth() == initial_max
        # Проверить, что сохранённые ограничения удалены
        search_id = id(search_widget)
        assert search_id not in search_manager._saved_constraints

    def test_unfreeze_without_saved_uses_defaults(
        self, search_manager, search_widget
    ):
        """Проверить использование defaults при unfreeze без saved constraints."""
        # Arrange
        search_widget.setMinimumWidth(100)
        search_widget.setMaximumWidth(200)
        default_min = 150

        # Act - unfreeze без предварительного freeze
        search_manager.unfreeze_width(search_widget, default_min=default_min)

        # Assert
        assert search_widget.minimumWidth() == default_min
        assert search_widget.maximumWidth() == C.MAX_WIDGET_WIDTH

    def test_unfreeze_without_default_uses_constant(
        self, search_manager, search_widget
    ):
        """Проверить использование MIN_SEARCH_WIDTH_ABSOLUTE при unfreeze."""
        # Arrange
        search_widget.setMinimumWidth(100)
        search_widget.setMaximumWidth(200)

        # Act - unfreeze без default_min
        search_manager.unfreeze_width(search_widget)

        # Assert
        assert search_widget.minimumWidth() == C.MIN_SEARCH_WIDTH_ABSOLUTE
        assert search_widget.maximumWidth() == C.MAX_WIDGET_WIDTH

    def test_multiple_freeze_only_saves_first(self, search_manager, search_widget):
        """Проверить, что повторный freeze не перезаписывает сохранённые значения."""
        # Arrange
        initial_min = search_widget.minimumWidth()
        initial_max = search_widget.maximumWidth()

        # Act
        search_manager.freeze_width(search_widget, 200)
        search_manager.freeze_width(search_widget, 150)  # Повторный freeze

        # Assert
        search_id = id(search_widget)
        saved_min, saved_max = search_manager._saved_constraints[search_id]
        # Должны быть сохранены ПЕРВОНАЧАЛЬНЫЕ значения
        assert saved_min == initial_min
        assert saved_max == initial_max

    def test_freeze_unfreeze_cycle(self, search_manager, search_widget):
        """Проверить полный цикл freeze -> unfreeze -> freeze."""
        # Arrange
        initial_min = search_widget.minimumWidth()
        initial_max = search_widget.maximumWidth()

        # Act - первый цикл
        search_manager.freeze_width(search_widget, 200)
        search_manager.unfreeze_width(search_widget)

        # Assert - восстановлены начальные значения
        assert search_widget.minimumWidth() == initial_min
        assert search_widget.maximumWidth() == initial_max

        # Act - второй цикл
        search_manager.freeze_width(search_widget, 150)
        search_manager.unfreeze_width(search_widget)

        # Assert - снова восстановлены начальные значения
        assert search_widget.minimumWidth() == initial_min
        assert search_widget.maximumWidth() == initial_max

    def test_freeze_with_none_widget(self, search_manager):
        """Проверить безопасную обработку None widget."""
        # Act & Assert - не должно быть исключений
        search_manager.freeze_width(None, 200)
        search_manager.unfreeze_width(None)

    def test_clamp_width_unfreezes_before_applying(
        self, search_manager, search_widget, qtbot
    ):
        """Проверить, что clamp_width размораживает перед применением ограничений."""
        from unittest.mock import Mock
        from app.views.main_components.ui.topbar.models.layout_context import (
            LayoutContext,
        )

        # Arrange
        search_manager.freeze_width(search_widget, 200)
        assert search_widget.minimumWidth() == 200
        assert search_widget.maximumWidth() == 200

        # Создать mock context
        ctx = Mock(spec=LayoutContext)
        ctx.search = search_widget
        ctx.panel_states = []
        ctx.top_bar = Mock()
        ctx.top_bar.count.return_value = 1
        ctx.top_bar.itemAt.return_value = Mock(widget=Mock(return_value=search_widget))
        ctx.top_bar.spacing.return_value = 0
        ctx.top_bar.contentsMargins.return_value = Mock(left=Mock(return_value=0), right=Mock(return_value=0))

        # Act
        search_manager.clamp_width(ctx, {}, min_search_width=140)

        # Assert - должны быть восстановлены нормальные ограничения
        assert search_widget.minimumWidth() == 140
        assert search_widget.maximumWidth() == C.MAX_WIDGET_WIDTH


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_unfreeze_idempotent(self, search_manager, search_widget):
        """Проверить идемпотентность unfreeze."""
        # Arrange
        search_manager.freeze_width(search_widget, 200)

        # Act - множественные вызовы unfreeze
        search_manager.unfreeze_width(search_widget)
        initial_min = search_widget.minimumWidth()
        initial_max = search_widget.maximumWidth()

        search_manager.unfreeze_width(search_widget)

        # Assert - значения не изменились
        assert search_widget.minimumWidth() == initial_min
        assert search_widget.maximumWidth() == initial_max

    def test_freeze_with_zero_width(self, search_manager, search_widget):
        """Проверить freeze с нулевой шириной."""
        # Act
        search_manager.freeze_width(search_widget, 0)

        # Assert
        assert search_widget.minimumWidth() == 0
        assert search_widget.maximumWidth() == 0

    def test_freeze_with_negative_width(self, search_manager, search_widget):
        """Проверить freeze с отрицательной шириной."""
        # Act - Qt может обработать это по-своему
        search_manager.freeze_width(search_widget, -10)

        # Assert - проверить, что не упало
        # Qt может установить 0 или игнорировать отрицательное значение
        assert search_widget.minimumWidth() >= 0

    def test_saved_constraints_cleanup_on_unfreeze(
        self, search_manager, search_widget
    ):
        """Проверить очистку _saved_constraints при unfreeze."""
        # Arrange
        search_manager.freeze_width(search_widget, 200)
        search_id = id(search_widget)
        assert search_id in search_manager._saved_constraints

        # Act
        search_manager.unfreeze_width(search_widget)

        # Assert
        assert search_id not in search_manager._saved_constraints
        # Повторный unfreeze должен использовать defaults
        search_manager.unfreeze_width(search_widget, default_min=100)
        assert search_widget.minimumWidth() == 100


class TestIntegrationWithNarrowMode:
    """Интеграционные тесты с narrow mode."""

    def test_narrow_mode_freeze_then_normal_mode_unfreeze(
        self, search_manager, search_widget
    ):
        """Симуляция: narrow mode -> freeze -> normal mode -> unfreeze."""
        # Arrange - начальное состояние
        initial_min = search_widget.minimumWidth()
        initial_max = search_widget.maximumWidth()

        # Act - переход в narrow mode (контейнер скрыт)
        search_manager.freeze_width(search_widget, 140)
        assert search_widget.minimumWidth() == 140
        assert search_widget.maximumWidth() == 140

        # Act - возврат в normal mode (контейнер показан)
        search_manager.unfreeze_width(search_widget, default_min=initial_min)

        # Assert - восстановлены нормальные ограничения
        assert search_widget.minimumWidth() == initial_min
        assert search_widget.maximumWidth() == initial_max

    def test_prevents_sticky_width_after_container_show(
        self, search_manager, search_widget
    ):
        """Проверить предотвращение 'залипания' ширины после показа контейнера."""
        # Arrange - установить широкие ограничения
        search_widget.setMinimumWidth(200)
        search_widget.setMaximumWidth(C.MAX_WIDGET_WIDTH)

        # Act - freeze на узкое значение (контейнер скрыт)
        search_manager.freeze_width(search_widget, 100)
        assert search_widget.minimumWidth() == 100

        # Act - unfreeze (контейнер показан)
        search_manager.unfreeze_width(search_widget)

        # Assert - восстановлена широкая минимальная ширина
        assert search_widget.minimumWidth() == 200
        assert search_widget.maximumWidth() == C.MAX_WIDGET_WIDTH
