from __future__ import annotations

import logging

from app.utils.ui.qt.combo_helpers import PopupComboBox, select_combo_data
from app.views.common.retranslatable import ReTranslatable
from i18n.language_service import LanguageService

logger = logging.getLogger(__name__)


class LanguageSelector(PopupComboBox, ReTranslatable):
    """Combo box that lists available UI languages and switches them on selection."""

    def __init__(self, parent=None) -> None:
        PopupComboBox.__init__(self, parent)
        self._service = LanguageService.instance()
        self.setObjectName("languageSelector")
        self._populate()
        logger.debug("LanguageSelector: connecting currentIndexChanged signal")
        self.currentIndexChanged.connect(self._on_index_changed)
        ReTranslatable.__init__(self)

    def _populate(self) -> None:
        service = self._ensure_service()
        languages = service.available_languages()
        current = service.current_language()
        self.blockSignals(True)
        self.clear()
        for descriptor in languages:
            self.addItem(descriptor.native_name, descriptor.code)
        select_combo_data(
            self,
            current_data=current,
            fallback_to_first=False,
        )
        self.blockSignals(False)

    def retranslateUi(self) -> None:
        # Language names are stored in native form; only tooltips need translation.
        self.setToolTip(self.tr("Change application language"))
        self.setAccessibleName(self.tr("Language Selector"))
        # Re-populate to ensure dynamic data stays in sync with available languages.
        self._populate()

    def _on_index_changed(self, index: int) -> None:
        logger.debug("LanguageSelector._on_index_changed: index=%d", index)
        code: str | None = self.itemData(index)
        logger.debug("LanguageSelector: selected code=%s", code)
        service = self._ensure_service()
        if not code:
            logger.warning("LanguageSelector: no code for index %d", index)
            return
        current = service.current_language()
        logger.debug(
            "LanguageSelector: current language=%s, selected=%s", current, code
        )
        if code == current:
            logger.debug("LanguageSelector: language unchanged, skipping")
            return
        logger.debug("LanguageSelector: calling service.set_language(%s)", code)
        service.set_language(code)
        # After switching language, refresh selection to reflect any normalization.
        normalized = service.current_language()
        logger.debug(
            "LanguageSelector: after set_language, normalized=%s",
            normalized,
        )
        if self.count() > 0:
            self.blockSignals(True)
            select_combo_data(
                self,
                current_data=normalized,
                fallback_to_first=False,
            )
            self.blockSignals(False)

    def _ensure_service(self) -> LanguageService:
        service = getattr(self, "_service", None)
        if service is None:
            service = LanguageService.instance()
            self._service = service
        return service


__all__ = ["LanguageSelector"]
