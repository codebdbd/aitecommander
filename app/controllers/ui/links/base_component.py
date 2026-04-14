"""Base component for links_ui module."""

import logging
from typing import Optional

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from app.config_data.runtime_config import get_ui_config

from .exceptions import DatabaseError

logger = logging.getLogger(__name__)

_LINKS_CONTEXT = "LinksUI"
_LINKS_WARNING_TITLE = QT_TRANSLATE_NOOP(_LINKS_CONTEXT, "Warning")
_LINKS_ERROR_TITLE = QT_TRANSLATE_NOOP(_LINKS_CONTEXT, "Error")
_LINKS_WARN_INFO = QT_TRANSLATE_NOOP(
    _LINKS_CONTEXT, "Check data correctness and try again."
)
_LINKS_ERROR_INFO = QT_TRANSLATE_NOOP(
    _LINKS_CONTEXT, "Try again or contact support."
)
_LINKS_MESSAGES = {
    "no_categories": QT_TRANSLATE_NOOP(
        _LINKS_CONTEXT, "No categories available. Create a category first."
    ),
    "select_category": QT_TRANSLATE_NOOP(
        _LINKS_CONTEXT, "Select a category to insert the link"
    ),
    "error_saving": QT_TRANSLATE_NOOP(_LINKS_CONTEXT, "Error saving note"),
    "database_error": QT_TRANSLATE_NOOP(_LINKS_CONTEXT, "Database error"),
    "validation_error": QT_TRANSLATE_NOOP(_LINKS_CONTEXT, "Validation error"),
    "warning_title": _LINKS_WARNING_TITLE,
    "error_title": _LINKS_ERROR_TITLE,
    "unsafe_url_info": QT_TRANSLATE_NOOP(
        _LINKS_CONTEXT, "This link cannot be opened for security reasons."
    ),
    "unsafe_url_hint": QT_TRANSLATE_NOOP(
        _LINKS_CONTEXT, "Check the link address or edit it."
    ),
}


def _tr_links(text: str) -> str:
    return QCoreApplication.translate(_LINKS_CONTEXT, text)


class BaseLinksUIComponent:
    """Base class for all LinksUI components."""

    def __init__(self, controller, link_operations, links_table_controller=None):
        self.controller = controller
        self.table = controller.table
        self.business = controller.business
        self.main = controller.main
        # Required dependency: link_operations must be passed explicitly
        if link_operations is None:
            raise ValueError(
                "BaseLinksUIComponent requires explicit 'link_operations' dependency"
            )
        self.link_operations = link_operations
        # Explicit dependency for links_table_controller; fallback — take from controller if available
        self.links_table_controller = links_table_controller or getattr(
            controller, "table_controller", None
        )

        # Cache configuration for performance
        self._config = get_ui_config()
        self._columns = self._config.get_links_table_columns()
        self._messages = {key: _tr_links(text) for key, text in _LINKS_MESSAGES.items()}

    @property
    def COLUMNS(self) -> dict[str, int]:
        """Link table column indices."""
        return self._columns

    @property
    def MESSAGES(self) -> dict[str, str]:
        """User messages."""
        return self._messages

    def get_message(self, key: str, default: str | None = None) -> str:
        """Get message by key."""
        msg = self._messages.get(key)
        if msg is None:
            return _tr_links(default) if default else f"Message '{key}' not found"
        return msg

    def _update_category_safe(self, category_id: int) -> None:
        """Safe category update with fallback."""
        try:
            # 1) Prefer explicit dependency passed to component
            ctrl = self.links_table_controller
            if ctrl is not None:
                ctrl.reload(category_id)
                return

            # 2) Fallback: try to get controller from main (for compatibility)
            ctrl_from_main = getattr(self.main, "links_table_controller", None)
            if ctrl_from_main is not None:
                ctrl_from_main.reload(category_id)
                return

            # 3) Final fallback: directly call business logic
            # (without table UI controller; may give less consistent behavior)
            self.business.load_links(category_id)
        except Exception as e:
            logger.error("Error updating category %s: %s", category_id, e)
            raise DatabaseError(f"Failed to update category: {str(e)}") from e

    def _show_warning(self, message: str, title: str | None = None) -> None:
        """Show warning to user."""
        from app.controllers.ui.dialogs import DialogManager

        resolved_title = _tr_links(title) if title else self.get_message("warning_title")
        DialogManager.show_warning(
            self.main,
            message,
            resolved_title,
            informative_text=_tr_links(_LINKS_WARN_INFO),
        )

    def _show_error(self, message: str, title: str | None = None) -> None:
        """Show error to user."""
        from app.controllers.ui.dialogs import DialogManager

        resolved_title = _tr_links(title) if title else self.get_message("error_title")
        DialogManager.show_error(
            self.main,
            message,
            resolved_title,
            informative_text=_tr_links(_LINKS_ERROR_INFO),
        )

    def _validate_category_exists(self, category_id: Optional[int]) -> Optional[int]:
        """Check category existence and return valid category ID.

        Returns category_id if provided and valid, otherwise tries to get current category.
        Returns None if no valid category found (instead of raising exception).
        """
        if not category_id:
            current_category_id = self.main.get_current_category_id()
            if not current_category_id:
                logger.debug("_validate_category_exists: no category available")
                return None
            return current_category_id
        return category_id
