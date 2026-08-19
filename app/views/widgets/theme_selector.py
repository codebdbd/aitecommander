from __future__ import annotations

import logging

from PyQt6.QtWidgets import QWidget
from app.utils.ui.qt.combo_helpers import PopupComboBox, select_combo_data
from app.views.common.retranslatable import ReTranslatable
from app.core.settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class ThemeSelector(PopupComboBox, ReTranslatable):
    """Combo box that lists available UI themes and switches them on selection."""

    def __init__(self, theme_ctrl, parent: QWidget | None = None) -> None:
        self._theme_ctrl = theme_ctrl
        PopupComboBox.__init__(self, parent)
        self.setObjectName("themeSelector")
        logger.debug("ThemeSelector: connecting currentIndexChanged signal")
        self.currentIndexChanged.connect(self._on_index_changed)
        ReTranslatable.__init__(self)

    def _populate(self) -> None:
        if self._theme_ctrl is None:
            return
        themes = self._theme_ctrl.available()  # returns list of (name, translated_name)
        current = SettingsManager.get("theme.name") or "light"

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

    def retranslateUi(self) -> None:
        self.setToolTip(self.tr("Change application theme"))
        self.setAccessibleName(self.tr("Theme Selector"))
        self._populate()

    def _on_index_changed(self, index: int) -> None:
        theme_id: str | None = self.itemData(index)
        if not theme_id:
            return
        current = SettingsManager.get("theme.name") or "light"
        if theme_id == current:
            return
        logger.debug("ThemeSelector: applying theme %s", theme_id)
        self._theme_ctrl.apply(theme_id)

        # After switching theme, refresh selection to reflect any normalization.
        normalized = SettingsManager.get("theme.name") or theme_id
        if self.count() > 0:
            self.blockSignals(True)
            select_combo_data(
                self,
                current_data=normalized,
                fallback_to_first=True,
            )
            self.blockSignals(False)


__all__ = ["ThemeSelector"]
