import pytest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QObject, pyqtSignal

from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.business.structure_business import StructureBusinessLogic
from app.models.db import Database

# Fixtures and Mocks

@pytest.fixture
def mock_db():
    """Fixture for a mocked Database."""
    return Mock(spec=Database)

@pytest.fixture
def mock_logger():
    """Fixture for a mocked logger."""
    return Mock()

@pytest.fixture
def links_business_logic(mock_db, mock_logger):
    """Fixture for LinksBusinessLogic."""
    logic = LinksBusinessLogic(db=mock_db, logger=mock_logger)
    yield logic
    logic.shutdown()

@pytest.fixture
def structure_business_logic(mock_db, mock_logger):
    """Fixture for StructureBusinessLogic."""
    with patch('app.controllers.business.structure_business.StructureModel'), \
         patch('app.controllers.business.structure_business.StructureService'), \
         patch('app.controllers.business.structure_business.CacheManager'), \
         patch('app.controllers.business.structure_business.ExportService'), \
         patch('app.controllers.business.structure_business.IntegrityService'), \
         patch('app.controllers.business.structure_business.LoaderService'), \
         patch('app.controllers.business.structure_business.SelectionService'), \
         patch('app.controllers.business.structure_business.ValidationService'), \
         patch('app.controllers.business.structure_business.ImportService'), \
         patch('app.controllers.business.structure_business.UtilityService'), \
         patch('app.controllers.business.structure.StructureAsyncService'), \
         patch('app.controllers.business.structure.StructureCacheService'), \
         patch('app.controllers.business.structure.StructureCrudService'), \
         patch('app.controllers.business.structure.StructureEventService'), \
         patch('app.controllers.business.structure.StructureWarmupService'), \
         patch('app.controllers.business.structure.StructureValidationService'), \
         patch('app.controllers.business.structure.StructureQueryService'):
        logic = StructureBusinessLogic(db=mock_db, logger=mock_logger)
        yield logic
        logic.shutdown()

# Tests for LinksBusinessLogic

def test_links_logic_init_shutdown(links_business_logic, mock_logger):
    """Test initialization and shutdown of LinksBusinessLogic."""
    assert links_business_logic is not None
    mock_logger.debug.assert_called_with("LinksBusinessLogic shutdown completed")

def test_links_load_links_emits_signal(qtbot, links_business_logic):
    """Test that load_links emits the links_loaded signal."""
    with qtbot.waitSignal(links_business_logic.links_loaded, timeout=1000) as blocker:
        links_business_logic.load_links(1)
    assert blocker.args[0] == []
    assert blocker.args[1] == 1

# Tests for StructureBusinessLogic

def test_structure_logic_init_shutdown(structure_business_logic, mock_logger):
    """Test initialization and shutdown of StructureBusinessLogic."""
    assert structure_business_logic is not None
    mock_logger.info.assert_any_call("StructureBusinessLogic shutdown completed")

def test_structure_set_current_sphere_emits_signal(qtbot, structure_business_logic):
    """Test that set_current_sphere emits the active_sphere_changed signal."""
    structure_business_logic.current_sphere_id = None
    with qtbot.waitSignal(structure_business_logic.active_sphere_changed, timeout=1000) as blocker:
        structure_business_logic.set_current_sphere(123)
    assert blocker.args[0] == 123

def test_structure_shutdown_disconnects_signals(qtbot, structure_business_logic):
    """Test that shutdown disconnects internal signals."""
    # We can't easily check for disconnection, but we can check that shutdown runs without error
    # and that the services are called.
    structure_business_logic.shutdown()
    structure_business_logic.async_service.shutdown.assert_called_once()
    structure_business_logic.cache_manager.invalidate.assert_called_once()

