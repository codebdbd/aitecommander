from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QComboBox

from app.ui.retranslatable import ReTranslatable
from i18n.language_service import LanguageDescriptor, LanguageService


class LanguageSelector(QComboBox, ReTranslatable):
    """Combo box that lists available UI languages and switches them on selection."""

    def __init__(self, parent=None) -> None:
        QComboBox.__init__(self, parent)
        self._service = LanguageService.instance()
        self.setObjectName("languageSelector")
        self._populate()
        self.currentIndexChanged.connect(self._on_index_changed)
        ReTranslatable.__init__(self)

    def _populate(self) -> None:
        languages = self._service.available_languages()
        current = self._service.current_language()
        self.blockSignals(True)
        self.clear()
        for descriptor in languages:
            self.addItem(descriptor.name, descriptor.code)
        index = self.findData(current)
        if index >= 0:
            self.setCurrentIndex(index)
        self.blockSignals(False)

    def retranslateUi(self) -> None:
        # Language names are already stored in native form, but tooltips must be updated.
        self.setToolTip(self.tr("Change application language"))
        self.setAccessibleName(self.tr("Language Selector"))
        # Re-populate to ensure dynamic data stays in sync with available languages.
        self._populate()

    def _on_index_changed(self, index: int) -> None:
        code: Optional[str] = self.itemData(index)
        if not code:
            return
        if code == self._service.current_language():
            return
        self._service.set_language(code)
        # After switching language, refresh selection to reflect any normalization.
        normalized = self._service.current_language()
        normalized_index = self.findData(normalized)
        if normalized_index >= 0:
            self.blockSignals(True)
            self.setCurrentIndex(normalized_index)
            self.blockSignals(False)


__all__ = ["LanguageSelector"]
