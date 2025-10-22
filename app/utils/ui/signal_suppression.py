"""Utilities for suppressing and restoring UI signals during batch operations.

Improvement note: centralizes signal suppression logic that was duplicated across
move_operations_handler.py, commands.py, and commands_structure.py.
"""

from __future__ import annotations

from typing import Any, Protocol


class SelectionProtocol(Protocol):
    """Protocol for selection managers with suppress/restore capabilities."""

    def begin_suppress_selection(self) -> None:
        """Begin suppressing selection change signals."""
        ...

    def end_suppress_selection(self) -> None:
        """End suppressing selection change signals."""
        ...


class TreeProtocol(Protocol):
    """Protocol for tree widgets with signal blocking capabilities."""

    def blockSignals(self, block: bool) -> bool:
        """Block or unblock signals from the tree widget."""
        ...


def suppress_ui_signals(
    selection: SelectionProtocol | None = None,
    tree: TreeProtocol | None = None,
) -> tuple[bool, bool]:
    """Suppress selection and tree signals for batch operations.

    Args:
        selection: Selection manager to suppress (optional)
        tree: Tree widget to block signals (optional)

    Returns:
        Tuple of (selection_was_suppressed, tree_was_blocked) indicating
        which operations succeeded. Use these flags when restoring signals.

    Example:
        >>> selection_state, tree_state = suppress_ui_signals(selection, tree)
        >>> try:
        ...     # Perform batch operations
        ...     pass
        ... finally:
        ...     restore_ui_signals(selection, tree, selection_state, tree_state)
    """
    selection_suppressed = False
    tree_blocked = False

    if selection is not None:
        try:
            selection.begin_suppress_selection()
            selection_suppressed = True
        except Exception:
            # Suppress errors — signal suppression is best-effort
            pass

    if tree is not None:
        try:
            tree.blockSignals(True)
            tree_blocked = True
        except Exception:
            # Suppress errors — signal blocking is best-effort
            pass

    return (selection_suppressed, tree_blocked)


def restore_ui_signals(
    selection: SelectionProtocol | None = None,
    tree: TreeProtocol | None = None,
    selection_was_suppressed: bool = True,
    tree_was_blocked: bool = True,
) -> None:
    """Restore selection and tree signals after batch operations.

    Args:
        selection: Selection manager to restore (optional)
        tree: Tree widget to unblock signals (optional)
        selection_was_suppressed: Whether selection was actually suppressed
        tree_was_blocked: Whether tree signals were actually blocked

    Note:
        Restoration happens in reverse order (tree first, then selection)
        to ensure proper signal propagation.

    Example:
        >>> selection_state, tree_state = suppress_ui_signals(selection, tree)
        >>> try:
        ...     # Perform batch operations
        ...     pass
        ... finally:
        ...     restore_ui_signals(selection, tree, selection_state, tree_state)
    """
    # Restore in reverse order: tree first, then selection
    if tree is not None and tree_was_blocked:
        try:
            tree.blockSignals(False)
        except Exception:
            # Suppress errors — signal restoration is best-effort
            pass

    if selection is not None and selection_was_suppressed:
        try:
            selection.end_suppress_selection()
        except Exception:
            # Suppress errors — signal restoration is best-effort
            pass


__all__ = [
    "SelectionProtocol",
    "TreeProtocol",
    "suppress_ui_signals",
    "restore_ui_signals",
]
