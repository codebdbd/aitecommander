"""Session controller for resolving name conflicts across batch operations."""

from __future__ import annotations

import logging
from typing import Sequence

from PyQt6.QtWidgets import QDialog, QWidget

from app.utils.naming import generate_unique_name
from app.views.windows.dialogs.entity_dialogs import ImportConflictDialog

logger = logging.getLogger(__name__)


class ConflictResolutionSession:
    """Coordinates conflict resolution during single or batch operations.

    Remembers chosen action ('merge', 'copy', 'skip') when user selects 'Apply to all conflicts',
    avoiding redundant modal prompts during multi-item operations.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        operation: str = "move",
        total_conflicts: int = 1,
    ) -> None:
        self.parent = parent
        self.operation = operation
        self.total_conflicts = total_conflicts
        self.batch_action: str | None = None

    def resolve(
        self,
        entity_type: str,
        name: str,
        existing_names: Sequence[str] | set[str],
        existing_info: dict | None = None,
        incoming_info: dict | None = None,
    ) -> tuple[str, str]:
        """Resolve conflict for an entity.

        Returns:
            tuple[action, copy_name]:
                action: 'merge', 'copy', 'skip', or 'cancel'
                copy_name: generated unique name if action is 'copy'
        """
        copy_name = generate_unique_name(set(existing_names), name)

        if self.batch_action is not None:
            return self.batch_action, copy_name

        dlg = ImportConflictDialog(
            entity_type=entity_type,
            name=name,
            copy_name=copy_name,
            parent=self.parent,
            operation=self.operation,
            has_multiple=(self.total_conflicts > 1),
            existing_info=existing_info,
            incoming_info=incoming_info,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return "cancel", ""

        action = dlg.get_action()
        if action == "cancel":
            return "cancel", ""

        if dlg.apply_to_all():
            self.batch_action = action

        return action, copy_name
