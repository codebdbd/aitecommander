"""Language service for managing UI translations and locale switching."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QCoreApplication, QLocale, QObject, QSettings, QTranslator, pyqtSignal
from PyQt6.QtWidgets import QApplication

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

    # Signal emitted when language changes
    languageChanged = pyqtSignal(str)

    _instance: Optional[LanguageService] = None

    def __init__(self) -> None:
        if LanguageService._instance is not None:
            raise RuntimeError("LanguageService is a singleton. Use instance() method.")

        super().__init__()
        self._translators: Dict[str, QTranslator] = {}
        self._current_language: str = "en"
        self._settings = QSettings("AiteCommander", "Language")

        # Define available languages
        self._languages = {
            "en": LanguageDescriptor("en", "English", "English"),
            "uk": LanguageDescriptor("uk", "Ukrainian", "Українська"),
            "ru": LanguageDescriptor("ru", "Russian", "Русский"),
            "fr": LanguageDescriptor("fr", "French", "Français"),
            "es": LanguageDescriptor("es", "Spanish", "Español"),
            "de": LanguageDescriptor("de", "German", "Deutsch"),
        }

        # Load saved language or detect system language
        self._load_saved_language()

    @classmethod
    def instance(cls) -> LanguageService:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def available_languages(self) -> List[LanguageDescriptor]:
        """Get list of available languages."""
        return list(self._languages.values())

    def current_language(self) -> str:
        """Get current language code."""
        return self._current_language

    def set_language(self, language_code: str) -> bool:
        """Set UI language.

        Args:
            language_code: Language code (e.g., 'en', 'uk', 'ru')

        Returns:
            True if language was changed successfully
        """
        if language_code not in self._languages:
            logger.warning("Unknown language code: %s", language_code)
            return False

        if language_code == self._current_language:
            logger.debug("Language already set to: %s", language_code)
            return True

        # Remove current translators
        self._remove_translators()

        # Load new translators
        if self._load_translators(language_code):
            self._current_language = language_code
            self._save_language(language_code)

            # Notify all widgets to retranslate
            self.languageChanged.emit(language_code)

            logger.info("Language changed to: %s", language_code)
            return True

        logger.error("Failed to load translators for: %s", language_code)
        return False

    def _load_saved_language(self) -> None:
        """Load previously saved language or detect system language."""
        # Try to load from settings
        saved = self._settings.value("language")
        if saved and saved in self._languages:
            logger.info("Loading saved language: %s", saved)
            self.set_language(saved)
            return

        # Detect system language
        system_locale = QLocale.system()
        system_code = system_locale.name()[:2]  # Get first 2 characters (e.g., 'en' from 'en_US')

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

    def _load_translators(self, language_code: str) -> bool:
        """Load translators for the specified language.

        Args:
            language_code: Language code to load

        Returns:
            True if all translators loaded successfully
        """
        if language_code == "en":
            # English is the source language, no translation needed
            return True

        # Get application directory for translation files
        app_dir = Path(QCoreApplication.applicationDirPath())
        i18n_dir = app_dir / "i18n"

        if not i18n_dir.exists():
            logger.warning("i18n directory not found: %s", i18n_dir)
            return False

        # Load main translation file
        qm_file = i18n_dir / f"app_{language_code}.qm"
        if qm_file.exists():
            translator = QTranslator()
            if translator.load(str(qm_file)):
                QCoreApplication.installTranslator(translator)
                self._translators[language_code] = translator
                logger.debug("Loaded translator: %s", qm_file)
            else:
                logger.warning("Failed to load translator: %s", qm_file)
                return False
        else:
            logger.warning("Translation file not found: %s", qm_file)
            return False

        return True

    def _remove_translators(self) -> None:
        """Remove all currently installed translators."""
        for translator in self._translators.values():
            QCoreApplication.removeTranslator(translator)
        self._translators.clear()

    def get_language_descriptor(self, code: str) -> Optional[LanguageDescriptor]:
        """Get language descriptor by code."""
        return self._languages.get(code)

    def install_translator(self, app: QApplication) -> bool:
        """Install translator for the given QApplication.

        Args:
            app: QApplication instance

        Returns:
            True if translator was installed successfully
        """
        try:
            # Load translators for current language
            if not self._load_translators(self._current_language):
                logger.warning("Failed to load translators for language: %s", self._current_language)
                return False

            logger.info("Translator installed successfully for language: %s", self._current_language)
            return True
        except Exception as e:
            logger.error("Error installing translator: %s", e)
            return False
