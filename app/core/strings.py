"""Centralized UI strings."""

from __future__ import annotations

from PyQt6.QtCore import QT_TRANSLATE_NOOP

_TR_BOTTOM_PANEL = "BottomPanel"
_TR_MAIN_WINDOW = "MainWindow"


class WindowStrings:
    """Window-level UI strings."""

    WINDOW_TITLE = QT_TRANSLATE_NOOP("MainWindow", "AiteCommander")
    SEARCH_PLACEHOLDER = QT_TRANSLATE_NOOP(
        "WindowUISetup", "Search\u2026 (Ctrl+F)"
    )


class MenuStrings:
    """Menu UI strings."""

    ACTION_ADD_SECTION = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Add Section")
    ACTION_ADD_CATEGORY = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Add Category")
    ACTION_ADD_LINK = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Add Link")
    ACTION_EDIT = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Edit")
    ACTION_DELETE = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Delete")
    ACTION_SPHERE = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Sphere")

    PANEL_RECENT_LINKS = QT_TRANSLATE_NOOP(_TR_MAIN_WINDOW, "Recent Links")
    PANEL_FAVORITES = QT_TRANSLATE_NOOP(_TR_MAIN_WINDOW, "Favorites")
    PANEL_QUICK_ADD = QT_TRANSLATE_NOOP(_TR_MAIN_WINDOW, "Quick Add")


class DialogStrings:
    """Dialog UI strings."""

    TOOLTIP_ADD_SECTION = QT_TRANSLATE_NOOP(
        _TR_BOTTOM_PANEL, "Create a new section."
    )
    TOOLTIP_ADD_CATEGORY = QT_TRANSLATE_NOOP(
        _TR_BOTTOM_PANEL, "Create a new category in the selected section."
    )
    TOOLTIP_ADD_LINK = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Create a new link.")
    TOOLTIP_EDIT = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Edit the selected item.")
    TOOLTIP_DELETE = QT_TRANSLATE_NOOP(_TR_BOTTOM_PANEL, "Delete the selected item.")
    TOOLTIP_SWITCH_SPHERE = QT_TRANSLATE_NOOP(
        _TR_BOTTOM_PANEL, "Switch to next available sphere"
    )


class StatusStrings:
    """Status UI strings."""

    ACCESSIBLE_ACTION_TEMPLATE = QT_TRANSLATE_NOOP(
        _TR_BOTTOM_PANEL, "Action button: {label}"
    )
    BUTTON_VISIBLE_TEMPLATE = QT_TRANSLATE_NOOP(
        _TR_MAIN_WINDOW, "Button {idx} of {total} visible buttons"
    )
    BUTTON_HIDDEN = QT_TRANSLATE_NOOP(_TR_MAIN_WINDOW, "Hidden button")


# NOTE: This block is never executed. It exists to help pylupdate6 extract strings.
if False:  # pragma: no cover
    from PyQt6.QtCore import QCoreApplication

    QCoreApplication.translate("WindowUISetup", "Search\u2026 (Ctrl+F)")
    QCoreApplication.translate("BottomPanel", "Add Section")
    QCoreApplication.translate("BottomPanel", "Add Category")
    QCoreApplication.translate("BottomPanel", "Add Link")
    QCoreApplication.translate("BottomPanel", "Edit")
    QCoreApplication.translate("BottomPanel", "Delete")
    QCoreApplication.translate("BottomPanel", "Sphere")
    QCoreApplication.translate("BottomPanel", "Create a new section.")
    QCoreApplication.translate(
        "BottomPanel", "Create a new category in the selected section."
    )
    QCoreApplication.translate("BottomPanel", "Create a new link.")
    QCoreApplication.translate("BottomPanel", "Edit the selected item.")
    QCoreApplication.translate("BottomPanel", "Delete the selected item.")
    QCoreApplication.translate(
        "BottomPanel", "Switch to next available sphere"
    )
    QCoreApplication.translate("BottomPanel", "Action button: {label}")
    QCoreApplication.translate("MainWindow", "Button {idx} of {total} visible buttons")
    QCoreApplication.translate("MainWindow", "Hidden button")
    QCoreApplication.translate("MainWindow", "Recent Links")
    QCoreApplication.translate("MainWindow", "Favorites")
    QCoreApplication.translate("MainWindow", "Quick Add")
