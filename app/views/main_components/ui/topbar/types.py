"""Type definitions for topbar components."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from PyQt6.QtWidgets import QLineEdit, QWidget


class PanelLabel(str, Enum):
    """Labels for topbar panels."""
    
    RECENT = "recent"
    FAVORITES = "fav"
    QUICK = "quick"


class ButtonObjectName(str, Enum):
    """Object names for panel buttons."""
    
    RECENT = "recentButton"
    FAVORITE = "favoriteButton"
    QUICK = "quickButton"


class TopBarWindow(Protocol):
    """Protocol defining required attributes for TopBarLayoutManager window.
    
    This protocol ensures type safety when passing window objects to topbar components.
    Any window using TopBarLayoutManager must implement these attributes.
    """
    
    search: QLineEdit
    """Main search widget in the top bar."""
    
    fav_widget: QWidget | None
    """Favorites panel widget."""
    
    recent_links_widget: QWidget | None
    """Recent links panel widget."""
    
    quick_add_widget: QWidget | None
    """Quick add panel widget."""
    
    top_bar_host: QWidget | None
    """Container widget for the top bar."""
    
    def width(self) -> int:
        """Return window width."""
        ...
    
    def isVisible(self) -> bool:
        """Check if window is visible."""
        ...
