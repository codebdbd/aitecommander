from __future__ import annotations

from PyQt6.QtCore import QObject

from i18n.language_service import LanguageService


class ReTranslatable:
    """Mixin that reconnects UI text whenever application language changes."""

    def __init__(self, *, auto_connect: bool = True) -> None:
        self._language_service = LanguageService.instance()
        if auto_connect:
            self._language_service.languageChanged.connect(self._handle_language_changed)
            if isinstance(self, QObject):
                self.destroyed.connect(self._disconnect_from_language_service)  # type: ignore[attr-defined]
        if hasattr(self, "retranslateUi"):
            self.retranslateUi()  # type: ignore[misc]

    def retranslateUi(self) -> None:  # pragma: no cover - override expected
        raise NotImplementedError("Subclasses must implement retranslateUi")

    def _handle_language_changed(self, _lang_code: str) -> None:
        if hasattr(self, "retranslateUi"):
            self.retranslateUi()  # type: ignore[misc]

    def _disconnect_from_language_service(self) -> None:
        try:
            self._language_service.languageChanged.disconnect(self._handle_language_changed)
        except Exception:  # noqa: BLE001 - PyQt raises TypeError on missing connection
            pass


__all__ = ["ReTranslatable"]
