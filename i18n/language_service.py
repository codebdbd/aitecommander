from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Dict, Iterable, List, Optional

from PyQt6.QtCore import QCoreApplication, QLocale, QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator

from app.config_data import app_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LanguageDescriptor:
    code: str
    name: str
    locale_name: str


class LanguageService(QObject):
    """Singleton service that manages application translations."""

    languageChanged: pyqtSignal = pyqtSignal(str)
    _instance: ClassVar[Optional["LanguageService"]] = None

    _LANGUAGES: Dict[str, LanguageDescriptor] = {
        "en": LanguageDescriptor(code="en", name="English", locale_name="en_US"),
        "ru": LanguageDescriptor(code="ru", name="Русский", locale_name="ru_RU"),
        "uk": LanguageDescriptor(code="uk", name="Українська", locale_name="uk_UA"),
        "de": LanguageDescriptor(code="de", name="Deutsch", locale_name="de_DE"),
        "es": LanguageDescriptor(code="es", name="Español", locale_name="es_ES"),
        "fr": LanguageDescriptor(code="fr", name="Français", locale_name="fr_FR"),
    }
    _SETTINGS_KEY = "ui/lang"
    _DEFAULT_LANGUAGE = "en"

    def __init__(self) -> None:
        super().__init__()
        settings_cfg = app_config.settings
        org = settings_cfg.get_org_name()
        app = settings_cfg.get_app_name()

        self._settings = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            org,
            app,
        )
        self._translator: Optional[QTranslator] = None
        self._app: Optional[QApplication] = None
        self._current_language: str = self._load_persisted_language()
        self._translations_root = Path(__file__).resolve().parent

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    @classmethod
    def instance(cls) -> "LanguageService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        if cls._instance is None:
            return
        try:
            cls._instance._detach_translator()
        finally:
            cls._instance.deleteLater()
            cls._instance = None

    # ------------------------------------------------------------------
    def available_languages(self) -> List[LanguageDescriptor]:
        return list(self._LANGUAGES.values())

    def current_language(self) -> str:
        return self._current_language

    def current_locale(self) -> QLocale:
        descriptor = self._LANGUAGES.get(self._current_language)
        locale_name = descriptor.locale_name if descriptor else self._DEFAULT_LANGUAGE
        return QLocale(locale_name)

    def set_language(self, lang_code: str) -> None:
        logger.info("LanguageService.set_language() called with: %s", lang_code)
        lang_code = self._normalize_code(lang_code)
        logger.info("LanguageService: normalized code: %s, current: %s", lang_code, self._current_language)
        if lang_code == self._current_language:
            logger.info("LanguageService: language unchanged, skipping")
            return
        logger.info("LanguageService: applying language %s", lang_code)
        self._apply_language(lang_code)

    def install_translator(self, app: QApplication, lang_code: Optional[str] = None) -> None:
        self._app = app
        target = self._normalize_code(lang_code or self._current_language)
        self._apply_language(target, emit_signal=False)

    # ------------------------------------------------------------------
    def _load_persisted_language(self) -> str:
        stored = self._settings.value(self._SETTINGS_KEY)
        if stored:
            stored = self._normalize_code(str(stored))
            if stored in self._LANGUAGES:
                return stored
        system_locale = QLocale.system()
        system_code = self._normalize_code(system_locale.name())
        if system_code in self._LANGUAGES:
            return system_code
        return self._DEFAULT_LANGUAGE

    def _normalize_code(self, code: Optional[str]) -> str:
        if not code:
            return self._DEFAULT_LANGUAGE
        code = code.replace("-", "_")
        parts = code.split("_")
        if not parts:
            return self._DEFAULT_LANGUAGE
        candidate = parts[0].lower()
        if candidate in self._LANGUAGES:
            return candidate
        return self._DEFAULT_LANGUAGE

    def _apply_language(self, lang_code: str, emit_signal: bool = True) -> None:
        descriptor = self._LANGUAGES.get(lang_code)
        if descriptor is None:
            logger.warning("Requested language '%s' is not configured; falling back to default", lang_code)
            descriptor = self._LANGUAGES[self._DEFAULT_LANGUAGE]
            lang_code = descriptor.code

        success = self._install_qm(descriptor)
        if not success:
            logger.warning("Failed to load translation for '%s'; falling back to default", lang_code)
            descriptor = self._LANGUAGES[self._DEFAULT_LANGUAGE]
            lang_code = descriptor.code
            self._install_qm(descriptor)

        self._current_language = lang_code
        self._settings.setValue(self._SETTINGS_KEY, lang_code)
        self._settings.sync()
        locale = QLocale(descriptor.locale_name)
        QLocale.setDefault(locale)
        self._update_text_direction(locale)
        logger.info("LanguageService: language changed to '%s' (locale: %s)", lang_code, descriptor.locale_name)
        if emit_signal:
            logger.info("LanguageService: emitting languageChanged signal")
            self.languageChanged.emit(lang_code)
        else:
            logger.debug("LanguageService: signal emission suppressed")

    def _detach_translator(self) -> None:
        if self._app and self._translator:
            try:
                self._app.removeTranslator(self._translator)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to remove previous translator", exc_info=True)
        self._translator = None

    def _install_qm(self, descriptor: LanguageDescriptor) -> bool:
        if self._app is None:
            logger.debug("Translator installation skipped: QApplication is not set")
            return False

        self._detach_translator()
        translator = QTranslator(self._app)

        resource_path = f":/i18n/app_{descriptor.code}.qm"
        if translator.load(resource_path):
            self._app.installTranslator(translator)
            self._translator = translator
            logger.info("LanguageService: loaded translation from resource: %s", resource_path)
            return True

        file_path = self._translations_root / f"app_{descriptor.code}.qm"
        if translator.load(str(file_path)):
            self._app.installTranslator(translator)
            self._translator = translator
            logger.info("LanguageService: loaded translation from file: %s", file_path)
            return True

        logger.warning("Translation file not found for '%s' (searched %s and %s)", descriptor.code, resource_path, file_path)
        self._translator = None
        return False

    def _update_text_direction(self, locale: QLocale) -> None:
        direction = locale.textDirection()
        app = QGuiApplication.instance()
        if app is None:
            return
        if direction == Qt.LayoutDirection.RightToLeft:
            app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


# Convenient alias for importers
language_service = LanguageService.instance
