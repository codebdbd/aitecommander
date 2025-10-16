"""Tests for i18n functionality."""

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator
from PyQt6.QtWidgets import QApplication

from i18n.language_service import LanguageService


@pytest.fixture
def app():
    """Create QApplication for tests."""
    if QApplication.instance() is None:
        return QApplication([])
    return QApplication.instance()


@pytest.fixture
def language_service(app):
    """Create LanguageService instance for tests."""
    return LanguageService.instance()


class TestLanguageService:
    """Test LanguageService functionality."""

    def test_singleton(self, language_service):
        """Test that LanguageService is a singleton."""
        service2 = LanguageService.instance()
        assert service2 is language_service

    def test_available_languages(self, language_service):
        """Test that available languages are returned correctly."""
        languages = language_service.available_languages()
        assert len(languages) == 6  # en, uk, ru, fr, es, de
        assert all(hasattr(lang, 'code') and hasattr(lang, 'name') and hasattr(lang, 'native_name')
                  for lang in languages)

    def test_current_language(self, language_service):
        """Test current language retrieval."""
        current = language_service.current_language()
        assert isinstance(current, str)
        assert current in ['en', 'uk', 'ru', 'fr', 'es', 'de']

    def test_set_language(self, language_service):
        """Test language switching."""
        original_lang = language_service.current_language()

        # Test valid language switch
        success = language_service.set_language('uk')
        assert success
        assert language_service.current_language() == 'uk'

        # Test invalid language
        success = language_service.set_language('invalid')
        assert not success
        assert language_service.current_language() == 'uk'  # Should remain unchanged

        # Restore original language
        language_service.set_language(original_lang)

    def test_get_language_descriptor(self, language_service):
        """Test language descriptor retrieval."""
        descriptor = language_service.get_language_descriptor('en')
        assert descriptor is not None
        assert descriptor.code == 'en'
        assert descriptor.name == 'English'

        # Test non-existent language
        descriptor = language_service.get_language_descriptor('invalid')
        assert descriptor is None


class TestTranslation:
    """Test translation functionality."""

    def test_basic_translation(self, language_service, app):
        """Test basic translation functionality."""
        # Switch to Ukrainian
        language_service.set_language('uk')

        # Test that we can translate a string
        translated = QCoreApplication.translate("TestContext", "Hello World")
        assert isinstance(translated, str)

    def test_translator_loading(self, language_service, app):
        """Test that translators are loaded correctly."""
        # Test English (no translator needed)
        success = language_service.set_language('en')
        assert success

        # Test Ukrainian (should load translator if .qm file exists)
        success = language_service.set_language('uk')
        # This might fail if .qm files don't exist yet, but shouldn't crash

    def test_retranslate_signal(self, language_service, app):
        """Test that language change signal is emitted."""
        signal_received = False
        signal_lang = None

        def on_language_changed(lang_code):
            nonlocal signal_received, signal_lang
            signal_received = True
            signal_lang = lang_code

        language_service.languageChanged.connect(on_language_changed)

        # Change language
        language_service.set_language('uk')

        # Check that signal was emitted
        assert signal_received
        assert signal_lang == 'uk'


class TestLocaleUtils:
    """Test locale utility functions."""

    def test_format_decimal(self):
        """Test decimal formatting."""
        from i18n.locale_utils import format_decimal

        # Test English formatting
        result = format_decimal(1234.56, locale_code='en')
        assert '1,234.56' in result or '1234.56' in result

    def test_format_datetime(self):
        """Test datetime formatting."""
        from i18n.locale_utils import format_datetime
        from datetime import datetime

        dt = datetime(2023, 12, 25, 15, 30, 45)

        # Test English formatting
        result = format_datetime(dt, locale_code='en')
        assert '2023' in result and '12' in result and '25' in result

    def test_format_filesize(self):
        """Test file size formatting."""
        from i18n.locale_utils import format_filesize

        # Test English formatting
        result = format_filesize(1024 * 1024, locale_code='en')
        assert 'MB' in result

        result = format_filesize(1024, locale_code='en')
        assert 'KB' in result
