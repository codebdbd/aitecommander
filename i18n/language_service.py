"""Language service for managing UI translations and locale switching."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import (
    QCoreApplication,
    QLibraryInfo,
    QLocale,
    QObject,
    QSettings,
    QTranslator,
    pyqtSignal,
)
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config

logger = logging.getLogger(__name__)


class LanguageDescriptor:
    """Descriptor for a UI language."""

    def __init__(self, code: str, name: str, native_name: str) -> None:
        self.code = code
        self.name = name
        self.native_name = native_name

    def __repr__(self) -> str:
        return f"LanguageDescriptor({self.code!r}, {self.name!r}, {self.native_name!r})"


class LanguageService(QObject):
    """Singleton service for managing UI languages and translations."""

    languageChanged = pyqtSignal(str)

    _instance: LanguageService | None = None

    def __init__(self) -> None:
        if LanguageService._instance is not None:
            raise RuntimeError("LanguageService is a singleton. Use instance() method.")

        super().__init__()
        self._installed_translators: list[QTranslator] = []
        self._current_language: str = "en"
        self._settings = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_config.get_org_name(),
            app_config.get_app_name(),
        )

        self._languages = {
            "en": LanguageDescriptor("en", "English", "English"),
            "uk": LanguageDescriptor(
                "uk",
                "Ukrainian",
                "\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430",
            ),
            "ru": LanguageDescriptor(
                "ru", "Russian", "\u0420\u0443\u0441\u0441\u043a\u0438\u0439"
            ),
            "fr": LanguageDescriptor("fr", "French", "Fran\xe7ais"),
            "es": LanguageDescriptor("es", "Spanish", "Espa\xf1ol"),
            "de": LanguageDescriptor("de", "German", "Deutsch"),
        }

        self._load_saved_language()

    @classmethod
    def instance(cls) -> LanguageService:
        """Get the singleton instance."""
        if cls._instance is not None and sip.isdeleted(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def available_languages(self) -> list[LanguageDescriptor]:
        """Get list of available languages."""
        return list(self._languages.values())

    def current_language(self) -> str:
        """Get current language code."""
        return self._current_language

    def set_language(self, language_code: str) -> bool:
        """Set UI language."""
        if language_code not in self._languages:
            logger.warning("Unknown language code: %s", language_code)
            return False

        if language_code == self._current_language:
            logger.debug("Language already set to: %s", language_code)
            return True

        self._remove_translators()

        if language_code != "en":
            # 1. Install Qt base system translator (QLineEdit context menus, standard dialogs)
            qt_translator = self._load_qt_translator(language_code)
            if qt_translator is not None:
                QCoreApplication.installTranslator(qt_translator)
                self._installed_translators.append(qt_translator)

        # 2. Install application translator (including app_en.qm for %n plural support)
        app_translator = self._load_app_translator(language_code)
        if app_translator is not None:
            QCoreApplication.installTranslator(app_translator)
            self._installed_translators.append(app_translator)

        self._current_language = language_code
        self._save_language(language_code)
        self.languageChanged.emit(language_code)
        logger.info("Language changed to: %s", language_code)
        return True

    def _load_saved_language(self) -> None:
        """Load previously saved language or detect system language."""
        saved = self._settings.value("language")
        if saved and saved in self._languages:
            logger.info("Loading saved language: %s", saved)
            self.set_language(saved)
            return

        system_locale = QLocale.system()
        system_code = system_locale.name()[:2]

        if system_code in self._languages:
            logger.info("Using system language: %s", system_code)
            self.set_language(system_code)
        else:
            logger.info("Using default language: en")
            self.set_language("en")

    def _save_language(self, language_code: str) -> None:
        """Save current language to settings."""
        self._settings.setValue("language", language_code)
        logger.debug("Saved language to settings: %s", language_code)

    def _load_app_translator(self, language_code: str) -> QTranslator | None:
        """Load the application translator (app_<lang>.qm) for the specified language."""
        if getattr(sys, "frozen", False):
            base_path = Path(getattr(sys, "_MEIPASS", "."))
        else:
            base_path = Path(__file__).resolve().parent.parent

        translator = QTranslator()
        i18n_dir = base_path / "i18n"
        qm_file = i18n_dir / f"app_{language_code}.qm"

        if not qm_file.exists():
            logger.warning("Translation file not found: %s", qm_file)
        else:
            if translator.load(str(qm_file)):
                logger.debug("Loaded translator from filesystem: %s", qm_file)
                return translator
            logger.warning("Failed to load translator: %s", qm_file)

        if translator.load(f"app_{language_code}", "i18n"):
            logger.debug(
                "Loaded translator from Qt search path: app_%s", language_code
            )
            return translator

        return None

    def _load_qt_translator(self, language_code: str) -> QTranslator | None:
        """Load standard Qt base translator (qtbase_<lang>.qm) for system widgets."""
        if language_code == "en":
            return None

        translator = QTranslator()

        # 1. Try QLibraryInfo standard Qt translations directory
        qt_trans_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if qt_trans_dir and Path(qt_trans_dir).exists():
            if translator.load(f"qtbase_{language_code}.qm", qt_trans_dir):
                logger.debug("Loaded qtbase translator from Qt library path: %s", qt_trans_dir)
                return translator

        # 2. Fallback to bundled i18n directory (for PyInstaller frozen builds)
        if getattr(sys, "frozen", False):
            base_path = Path(getattr(sys, "_MEIPASS", "."))
        else:
            base_path = Path(__file__).resolve().parent.parent

        i18n_dir = base_path / "i18n"
        bundled_qtbase = i18n_dir / f"qtbase_{language_code}.qm"
        if bundled_qtbase.exists() and translator.load(str(bundled_qtbase)):
            logger.debug("Loaded qtbase translator from bundled i18n: %s", bundled_qtbase)
            return translator

        logger.debug("qtbase translation not available for: %s", language_code)
        return None

    def _remove_translators(self) -> None:
        """Remove all currently installed translators."""
        for translator in self._installed_translators:
            QCoreApplication.removeTranslator(translator)
        self._installed_translators.clear()

    def get_language_descriptor(self, code: str) -> LanguageDescriptor | None:
        """Get language descriptor by code."""
        return self._languages.get(code)

    def install_translator(self, app: QApplication) -> bool:
        """Install translator for the current language on the given application."""
        if app is None:
            logger.warning("install_translator called without QApplication instance")
            return False

        if self._current_language == "en":
            logger.debug(
                "install_translator: English locale active, translator not required"
            )
            return True

        try:
            self._remove_translators()

            qt_translator = self._load_qt_translator(self._current_language)
            if qt_translator is not None:
                QCoreApplication.installTranslator(qt_translator)
                self._installed_translators.append(qt_translator)

            app_translator = self._load_app_translator(self._current_language)
            if app_translator is None:
                logger.error(
                    "install_translator: translator unavailable after load for %s",
                    self._current_language,
                )
                return False

            QCoreApplication.installTranslator(app_translator)
            self._installed_translators.append(app_translator)
            logger.info(
                "Translators installed successfully for language: %s",
                self._current_language,
            )
            return True
        except Exception as exc:
            logger.error("Error installing translator: %s", exc, exc_info=True)
            return False
