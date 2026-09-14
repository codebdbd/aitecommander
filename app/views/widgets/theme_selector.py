from __future__ import annotations

import logging

from PyQt6.QtWidgets import QComboBox, QWidget

from app.core.settings_manager import SettingsManager
from app.utils.ui.qt.combo_helpers import PopupComboBox, select_combo_data
from app.views.common.retranslatable import ReTranslatable

logger = logging.getLogger(__name__)


class ThemeSelector(PopupComboBox, ReTranslatable):
    """Combo box that lists available UI themes and switches them on selection."""

    def __init__(self, theme_ctrl, parent: QWidget | None = None) -> None:
        self._theme_ctrl = theme_ctrl
        PopupComboBox.__init__(self, parent)
        self.setObjectName("themeSelector")
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        logger.debug("ThemeSelector: connecting currentIndexChanged signal")
        self.currentIndexChanged.connect(self._on_index_changed)
        ReTranslatable.__init__(self)

    def _get_current_theme(self) -> str:
        current = None
        if self._theme_ctrl and hasattr(self._theme_ctrl, "settings") and hasattr(self._theme_ctrl.settings, "get_theme"):
            current = self._theme_ctrl.settings.get_theme()
        if not current:
            current = SettingsManager.get("theme.name")
        return current or "light"

    def _populate(self) -> None:
        if self._theme_ctrl is None:
            return
        themes = self._theme_ctrl.available()  # returns list of (name, translated_name)
        current = self._get_current_theme()

        self.blockSignals(True)
        self.clear()
        for name, display_name in themes:
            self.addItem(display_name, name)

        select_combo_data(
            self,
            current_data=current,
            fallback_to_first=True,
        )
        self.blockSignals(False)
        self._resize_to_contents()

    def _resize_to_contents(self) -> None:
        fm = self.fontMetrics()
        max_width = 0
        for i in range(self.count()):
            width = fm.horizontalAdvance(self.itemText(i))
            if width > max_width:
                max_width = width
        arrow_width = max(self.iconSize().width(), 16) + 12
        frame = 2
        padding = 24
        total = max_width + arrow_width + frame * 2 + padding
        self.setMinimumWidth(total)
        self.setMaximumWidth(total)
        self.adjustSize()

    def retranslateUi(self) -> None:
        self.setToolTip(self.tr("Change application theme"))
        self.setAccessibleName(self.tr("Theme Selector"))
        self._populate()

    def update_theme_selection(self, theme_id: str | None = None) -> None:
        """Update selected theme in combo without firing index changed signals."""
        if self._theme_ctrl is None:
            return
        target = theme_id or self._get_current_theme()
        # If theme is not in combo (e.g. newly imported), reload list
        if self.findData(target) == -1:
            self._populate()
            return

        self.blockSignals(True)
        select_combo_data(
            self,
            current_data=target,
            fallback_to_first=True,
        )
        self.blockSignals(False)
        self._resize_to_contents()

    def refresh_themes(self) -> None:
        """Reload available themes and update selection."""
        self._populate()

    def _on_index_changed(self, index: int) -> None:
        theme_id: str | None = self.itemData(index)
        if not theme_id:
            return
        current = self._get_current_theme()
        if theme_id == current:
            return
        logger.debug("ThemeSelector: applying theme %s", theme_id)
        self._theme_ctrl.apply(theme_id)

        # After switching theme, refresh selection to reflect any normalization.
        normalized = self._get_current_theme()
        if self.count() > 0:
            self.blockSignals(True)
            select_combo_data(
                self,
                current_data=normalized,
                fallback_to_first=True,
            )
            self.blockSignals(False)


__all__ = ["ThemeSelector"]
