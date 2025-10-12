"""Compatibility layer for legacy `app.views.link` imports."""

from app.views.widgets.link.data_management import DataManagementMixin
from app.views.widgets.link.links_model import LinksTableModel
from app.views.widgets.link.population_manager import (
    PopulationManagerMixin as _PopulationManagerMixin,
)
from app.views.widgets.link.row_operations import RowOperationsMixin

# Legacy alias: historical code expected a class named PopulationManager. In the
# refactored code the functionality lives in PopulationManagerMixin. We expose
# the same object under the old name to maintain backwards compatibility.
PopulationManager = _PopulationManagerMixin

__all__ = [
    "LinksTableModel",
    "DataManagementMixin",
    "RowOperationsMixin",
    "PopulationManager",
    "PopulationManagerMixin",
]

# Some tests import PopulationManagerMixin directly from this namespace.
PopulationManagerMixin = _PopulationManagerMixin
