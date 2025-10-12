"""Pytest configuration and fixtures for main_components tests."""

import pytest
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def qt_app():
    """Create QApplication instance for Qt tests.
    
    This fixture creates a QApplication once per test session
    and reuses it for all Qt-related tests.
    """
    try:
        from PyQt6.QtWidgets import QApplication
        
        # Check if QApplication already exists
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        yield app
        
        # Cleanup is handled automatically by Qt
    except ImportError:
        pytest.skip("PyQt6 not available")


@pytest.fixture
def mock_window():
    """Create a mock MainWindow for testing."""
    from unittest.mock import Mock
    
    window = Mock()
    window.width.return_value = 1000
    window.height.return_value = 600
    window.isVisible.return_value = True
    window.isEnabled.return_value = True
    
    return window


@pytest.fixture
def mock_settings():
    """Create a mock Settings object."""
    from unittest.mock import Mock
    
    settings = Mock()
    settings.get_font_size.return_value = 12
    settings.get.return_value = None
    
    return settings


@pytest.fixture
def mock_theme_controller():
    """Create a mock ThemeController."""
    from unittest.mock import Mock
    
    theme = Mock()
    theme.current_theme.return_value = "light"
    
    return theme
