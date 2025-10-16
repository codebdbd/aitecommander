from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import QComboBox

from app.views.common.retranslatable import ReTranslatable
from i18n.language_service import LanguageDescriptor, LanguageService

logger = logging.getLogger(__name__)


class LanguageSelector(QComboBox, ReTranslatable):
    """Combo box that lists available UI languages and switches them on selection."""

    def __init__(self, parent=None) -> None:
        QComboBox.__init__(self, parent)
        self._service = LanguageService.instance()
        self.setObjectName("languageSelector")
        self._populate()
        logger.info("LanguageSelector: connecting currentIndexChanged signal")
        self.currentIndexChanged.connect(self._on_index_changed)
        ReTranslatable.__init__(self)

    def _populate(self) -> None:
        service = self._ensure_service()
        languages = service.available_languages()
        current = service.current_language()
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
        logger.info("LanguageSelector._on_index_changed: index=%d", index)
        code: Optional[str] = self.itemData(index)
        logger.info("LanguageSelector: selected code=%s", code)
        service = self._ensure_service()
        if not code:
            logger.warning("LanguageSelector: no code for index %d", index)
            return
        current = service.current_language()
        logger.info("LanguageSelector: current language=%s, selected=%s", current, code)
        if code == current:
            logger.info("LanguageSelector: language unchanged, skipping")
            return
        logger.info("LanguageSelector: calling service.set_language(%s)", code)
        service.set_language(code)
        # After switching language, refresh selection to reflect any normalization.
        normalized = service.current_language()
        normalized_index = self.findData(normalized)
        logger.info("LanguageSelector: after set_language, normalized=%s, index=%d", normalized, normalized_index)
        if normalized_index >= 0:
            self.blockSignals(True)
            self.setCurrentIndex(normalized_index)
            self.blockSignals(False)

    def _ensure_service(self) -> LanguageService:
        service = getattr(self, "_service", None)
        if service is None:
            service = LanguageService.instance()
            self._service = service
        return service


__all__ = ["LanguageSelector"]
