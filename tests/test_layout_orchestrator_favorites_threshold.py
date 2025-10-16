"""Тесты для favorites_min_visible_threshold в LayoutOrchestrator."""
from __future__ import annotations

import pytest
from unittest.mock import Mock

from app.views.main_components.ui.topbar.services.layout_orchestrator import (
    LayoutOrchestrator,
)
from app.views.main_components.ui.topbar.models.topbar_constants import (
    TOPBAR_CONSTANTS as C,
)


@pytest.fixture
def mock_services():
    """Создать mock-сервисы для LayoutOrchestrator."""
    return {
        "window": Mock(),
        "widget_accessor": Mock(),
        "visibility_manager": Mock(),
        "visibility_solver": Mock(),
        "search_manager": Mock(),
        "separator_service": Mock(),
        "hysteresis_service": Mock(),
        "narrow_mode_service": Mock(),
        "panel_definitions": (),
        "panel_labels": ("recent", "fav", "quick"),
        "min_search_width": 140,
        "narrow_threshold": 600,
        "log_info": False,
        "slow_adjust_threshold_ms": 50.0,
        "side_spacing": 8,
    }


class TestFavoritesThresholdInitialization:
    """Тесты инициализации favorites threshold."""

    def test_uses_constant_when_no_parameter(self, mock_services):
        """Проверить использование константы при отсутствии параметра."""
        # Arrange - не передаём favorites_min_visible_threshold

        # Act
        orchestrator = LayoutOrchestrator(**mock_services)

        # Assert
        assert orchestrator._favorites_min_visible_threshold == C.FAVORITES_MIN_VISIBLE_THRESHOLD
        assert orchestrator._favorites_min_visible_threshold == 5

    def test_uses_provided_value(self, mock_services):
        """Проверить использование переданного значения."""
        # Arrange
        mock_services["favorites_min_visible_threshold"] = 3

        # Act
        orchestrator = LayoutOrchestrator(**mock_services)

        # Assert
        assert orchestrator._favorites_min_visible_threshold == 3

    def test_uses_zero_threshold(self, mock_services):
        """Проверить использование нулевого порога."""
        # Arrange
        mock_services["favorites_min_visible_threshold"] = 0

        # Act
        orchestrator = LayoutOrchestrator(**mock_services)

        # Assert
        assert orchestrator._favorites_min_visible_threshold == 0

    def test_uses_large_threshold(self, mock_services):
        """Проверить использование большого порога."""
        # Arrange
        mock_services["favorites_min_visible_threshold"] = 100

        # Act
        orchestrator = LayoutOrchestrator(**mock_services)

        # Assert
        assert orchestrator._favorites_min_visible_threshold == 100

    def test_none_parameter_uses_constant(self, mock_services):
        """Проверить, что None использует константу."""
        # Arrange
        mock_services["favorites_min_visible_threshold"] = None

        # Act
        orchestrator = LayoutOrchestrator(**mock_services)

        # Assert
        assert orchestrator._favorites_min_visible_threshold == C.FAVORITES_MIN_VISIBLE_THRESHOLD


class TestFavoritesThresholdApplication:
    """Тесты применения favorites threshold в _handle_normal_mode."""

    def test_hides_fav_when_below_threshold(self, mock_services):
        """Проверить скрытие favorites когда count < threshold."""
        # Arrange
        manager_ref = Mock()
        config = Mock()
        config.get_favorites_min_visible_threshold.return_value = 5
        manager_ref._config = config
        mock_services["manager_ref"] = manager_ref

        orchestrator = LayoutOrchestrator(**mock_services)

        # Mock visibility_solver to return counts with fav=3
        mock_services["visibility_solver"].compute_visible_counts.return_value = {
            "recent": 5,
            "fav": 3,  # Ниже порога (5)
            "quick": 6,
        }

        # Mock hysteresis_service to pass through
        mock_services["hysteresis_service"].apply_hysteresis.side_effect = lambda ctx, counts, *args: counts

        # Mock apply_counts to return what was passed
        mock_services["visibility_manager"].apply_counts.side_effect = lambda states, counts: counts

        # Create mock context
        ctx = Mock()
        ctx.panel_states = []
        ctx.top_bar = Mock()
        ctx.search = Mock()

        # Act
        result = orchestrator._handle_normal_mode(ctx)

        # Assert
        assert result["fav"] == 0  # Должно быть скрыто
        assert result["recent"] == 5
        assert result["quick"] == 6

    def test_shows_fav_when_above_threshold(self, mock_services):
        """Проверить показ favorites когда count >= threshold."""
        # Arrange
        manager_ref = Mock()
        config = Mock()
        config.get_favorites_min_visible_threshold.return_value = 5
        manager_ref._config = config
        mock_services["manager_ref"] = manager_ref

        orchestrator = LayoutOrchestrator(**mock_services)

        # Mock visibility_solver to return counts with fav=6
        mock_services["visibility_solver"].compute_visible_counts.return_value = {
            "recent": 5,
            "fav": 6,  # Выше порога (5)
            "quick": 6,
        }

        mock_services["hysteresis_service"].apply_hysteresis.side_effect = lambda ctx, counts, *args: counts
        mock_services["visibility_manager"].apply_counts.side_effect = lambda states, counts: counts

        ctx = Mock()
        ctx.panel_states = []
        ctx.top_bar = Mock()
        ctx.search = Mock()

        # Act
        result = orchestrator._handle_normal_mode(ctx)

        # Assert
        assert result["fav"] == 6  # Должно быть показано
        assert result["recent"] == 5
        assert result["quick"] == 6

    def test_shows_fav_when_equal_to_threshold(self, mock_services):
        """Проверить показ favorites когда count == threshold."""
        # Arrange
        manager_ref = Mock()
        config = Mock()
        config.get_favorites_min_visible_threshold.return_value = 5
        manager_ref._config = config
        mock_services["manager_ref"] = manager_ref

        orchestrator = LayoutOrchestrator(**mock_services)

        mock_services["visibility_solver"].compute_visible_counts.return_value = {
            "recent": 5,
            "fav": 5,  # Равно порогу (5)
            "quick": 6,
        }

        mock_services["hysteresis_service"].apply_hysteresis.side_effect = lambda ctx, counts, *args: counts
        mock_services["visibility_manager"].apply_counts.side_effect = lambda states, counts: counts

        ctx = Mock()
        ctx.panel_states = []
        ctx.top_bar = Mock()
        ctx.search = Mock()

        # Act
        result = orchestrator._handle_normal_mode(ctx)

        # Assert
        assert result["fav"] == 5  # Должно быть показано (>= threshold)

    def test_keeps_fav_zero_when_already_zero(self, mock_services):
        """Проверить сохранение fav=0 когда уже 0."""
        # Arrange
        manager_ref = Mock()
        config = Mock()
        config.get_favorites_min_visible_threshold.return_value = 5
        manager_ref._config = config
        mock_services["manager_ref"] = manager_ref

        orchestrator = LayoutOrchestrator(**mock_services)

        mock_services["visibility_solver"].compute_visible_counts.return_value = {
            "recent": 5,
            "fav": 0,  # Уже 0
            "quick": 6,
        }

        mock_services["hysteresis_service"].apply_hysteresis.side_effect = lambda ctx, counts, *args: counts
        mock_services["visibility_manager"].apply_counts.side_effect = lambda states, counts: counts

        ctx = Mock()
        ctx.panel_states = []
        ctx.top_bar = Mock()
        ctx.search = Mock()

        # Act
        result = orchestrator._handle_normal_mode(ctx)

        # Assert
        assert result["fav"] == 0  # Остаётся 0


class TestFavoritesThresholdEdgeCases:
    """Тесты граничных случаев."""

    def test_handles_missing_fav_in_counts(self, mock_services):
        """Проверить обработку отсутствия 'fav' в counts."""
        # Arrange
        orchestrator = LayoutOrchestrator(**mock_services)

        mock_services["visibility_solver"].compute_visible_counts.return_value = {
            "recent": 5,
            # "fav" отсутствует
            "quick": 6,
        }

        mock_services["hysteresis_service"].apply_hysteresis.side_effect = lambda ctx, counts, *args: counts
        mock_services["visibility_manager"].apply_counts.side_effect = lambda states, counts: counts

        ctx = Mock()
        ctx.panel_states = []
        ctx.top_bar = Mock()
        ctx.search = Mock()

        # Act & Assert - не должно быть исключений
        result = orchestrator._handle_normal_mode(ctx)
        assert "fav" not in result or result.get("fav", 0) == 0

    def test_threshold_zero_shows_all(self, mock_services):
        """Проверить, что threshold=0 показывает все кнопки."""
        # Arrange
        manager_ref = Mock()
        config = Mock()
        config.get_favorites_min_visible_threshold.return_value = 0
        manager_ref._config = config
        mock_services["manager_ref"] = manager_ref

        orchestrator = LayoutOrchestrator(**mock_services)

        mock_services["visibility_solver"].compute_visible_counts.return_value = {
            "recent": 5,
            "fav": 1,  # Любое положительное значение
            "quick": 6,
        }

        mock_services["hysteresis_service"].apply_hysteresis.side_effect = lambda ctx, counts, *args: counts
        mock_services["visibility_manager"].apply_counts.side_effect = lambda states, counts: counts

        ctx = Mock()
        ctx.panel_states = []
        ctx.top_bar = Mock()
        ctx.search = Mock()

        # Act
        result = orchestrator._handle_normal_mode(ctx)

        # Assert - при threshold=0 условие 0 < 1 < 0 ложно, fav остаётся
        assert result["fav"] == 1

    def test_different_threshold_values(self, mock_services):
        """Проверить работу с различными значениями threshold."""
        for threshold_value in [1, 3, 5, 10]:
            # Arrange
            manager_ref = Mock()
            config = Mock()
            config.get_favorites_min_visible_threshold.return_value = threshold_value
            manager_ref._config = config
            mock_services["manager_ref"] = manager_ref

            orchestrator = LayoutOrchestrator(**mock_services)

            # Test value just below threshold
            mock_services["visibility_solver"].compute_visible_counts.return_value = {
                "fav": threshold_value - 1,
            }
            mock_services["hysteresis_service"].apply_hysteresis.side_effect = lambda ctx, counts, *args: counts
            mock_services["visibility_manager"].apply_counts.side_effect = lambda states, counts: counts

            ctx = Mock()
            ctx.panel_states = []
            ctx.top_bar = Mock()
            ctx.search = Mock()

            # Act
            result = orchestrator._handle_normal_mode(ctx)

            # Assert
            assert result["fav"] == 0, f"Failed for threshold={threshold_value}"
