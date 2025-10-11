from __future__ import annotations

import logging

from PyQt6.QtCore import QObject

from i18n.language_service import LanguageService

logger = logging.getLogger(__name__)


class ReTranslatable:
    """Mixin that reconnects UI text whenever application language changes.
    
    IMPORTANT: When used with multiple inheritance (e.g., BaseDialog, ReTranslatable),
    you must call ReTranslatable.__init__(self) explicitly AFTER all UI elements
    are initialized to avoid AttributeError when retranslateUi() is called.
    """

    def __init__(self, *, auto_connect: bool = True, call_retranslate: bool = True) -> None:
        """Initialize the ReTranslatable mixin.
        
        Args:
            auto_connect: If True, automatically connect to language change signals.
            call_retranslate: If True, call retranslateUi() immediately. Set to False
                            when using multiple inheritance to avoid AttributeError.
        """
        widget_class = self.__class__.__name__
        logger.debug("ReTranslatable.__init__ for %s: auto_connect=%s, call_retranslate=%s", widget_class, auto_connect, call_retranslate)
        self._language_service = LanguageService.instance()
        if auto_connect:
            logger.debug("ReTranslatable: connecting %s to languageChanged signal", widget_class)
            self._language_service.languageChanged.connect(self._handle_language_changed)
            if isinstance(self, QObject):
                self.destroyed.connect(self._disconnect_from_language_service)  # type: ignore[attr-defined]
        if call_retranslate and hasattr(self, "retranslateUi"):
            logger.debug("ReTranslatable: calling initial retranslateUi for %s", widget_class)
            self.retranslateUi()  # type: ignore[misc]

    def retranslateUi(self) -> None:  # pragma: no cover - override expected
        raise NotImplementedError("Subclasses must implement retranslateUi")

    def _handle_language_changed(self, _lang_code: str) -> None:
        widget_class = self.__class__.__name__
        logger.debug("ReTranslatable._handle_language_changed for %s: lang_code=%s", widget_class, _lang_code)
        if hasattr(self, "retranslateUi"):
            logger.debug("ReTranslatable: calling retranslateUi() for %s", widget_class)
            self.retranslateUi()  # type: ignore[misc]
        else:
            logger.warning("ReTranslatable: %s has no retranslateUi method!", widget_class)

    def _disconnect_from_language_service(self) -> None:
        try:
            self._language_service.languageChanged.disconnect(self._handle_language_changed)
        except Exception:  # noqa: BLE001 - PyQt raises TypeError on missing connection
            pass


__all__ = ["ReTranslatable"]
