#!/usr/bin/env python3
"""
Тесты переключения языков в системе i18n.

Проверяет:
1. Корректность переключения языков
2. Загрузку переводов
3. Работу ReTranslatable миксина
4. Обновление UI при смене языка
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import QCoreApplication, QLocale
from PyQt6.QtWidgets import QApplication, QWidget, QLabel

from i18n.language_service import LanguageService, LanguageDescriptor
from app.views.common.retranslatable import ReTranslatable


class TestWidget(QWidget, ReTranslatable):
    """Тестовый виджет для проверки ReTranslatable."""
    
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.label = QLabel("Test Label", self)
        ReTranslatable.__init__(self)
    
    def retranslateUi(self):
        """Обновить UI при смене языка."""
        self.label.setText(self.tr("Test Label"))
        self.setWindowTitle(self.tr("Test Window"))


class TestLanguageSwitching:
    """Тесты переключения языков."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        # Создаем QApplication если его нет
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()
        
        # Сбрасываем LanguageService для чистого состояния
        LanguageService.reset_for_tests()
        self.service = LanguageService.instance()
    
    def teardown_method(self):
        """Очистка после каждого теста."""
        LanguageService.reset_for_tests()
    
    def test_language_service_initialization(self):
        """Тест инициализации LanguageService."""
        assert self.service is not None
        assert isinstance(self.service, LanguageService)
        assert self.service.current_language() in ["en", "ru", "uk", "de", "es", "fr"]
    
    def test_available_languages(self):
        """Тест получения доступных языков."""
        languages = self.service.available_languages()
        assert len(languages) == 6
        
        # Проверяем, что все языки присутствуют
        codes = [lang.code for lang in languages]
        assert "en" in codes
        assert "ru" in codes
        assert "uk" in codes
        assert "de" in codes
        assert "es" in codes
        assert "fr" in codes
    
    def test_language_descriptors(self):
        """Тест дескрипторов языков."""
        languages = self.service.available_languages()
        
        for lang in languages:
            assert isinstance(lang, LanguageDescriptor)
            assert lang.code
            assert lang.name
            assert lang.locale_name
            
            # Проверяем соответствие кода и локали
            if lang.code == "en":
                assert lang.locale_name == "en_US"
            elif lang.code == "ru":
                assert lang.locale_name == "ru_RU"
            elif lang.code == "uk":
                assert lang.locale_name == "uk_UA"
    
    def test_language_switching(self):
        """Тест переключения языков."""
        initial_lang = self.service.current_language()
        
        # Переключаемся на русский
        self.service.set_language("ru")
        assert self.service.current_language() == "ru"
        
        # Переключаемся на украинский
        self.service.set_language("uk")
        assert self.service.current_language() == "uk"
        
        # Возвращаемся к исходному языку
        self.service.set_language(initial_lang)
        assert self.service.current_language() == initial_lang
    
    def test_language_normalization(self):
        """Тест нормализации кодов языков."""
        # Тестируем различные форматы
        test_cases = [
            ("en-US", "en"),
            ("ru_RU", "ru"),
            ("uk-UA", "uk"),
            ("de_DE", "de"),
            ("es-ES", "es"),
            ("fr_FR", "fr"),
        ]
        
        for input_code, expected_code in test_cases:
            self.service.set_language(input_code)
            assert self.service.current_language() == expected_code
    
    def test_invalid_language_fallback(self):
        """Тест fallback для неверного языка."""
        initial_lang = self.service.current_language()
        
        # Пытаемся установить несуществующий язык
        self.service.set_language("xyz")
        
        # Должен вернуться к языку по умолчанию
        assert self.service.current_language() == "en"
    
    def test_current_locale(self):
        """Тест получения текущей локали."""
        self.service.set_language("ru")
        locale = self.service.current_locale()
        assert isinstance(locale, QLocale)
        assert locale.name() == "ru_RU"
        
        self.service.set_language("uk")
        locale = self.service.current_locale()
        assert locale.name() == "uk_UA"
    
    def test_retranslatable_mixin(self):
        """Тест ReTranslatable миксина."""
        widget = TestWidget()
        
        # Проверяем, что виджет подключен к сигналу
        assert hasattr(widget, '_language_service')
        assert widget._language_service is not None
        
        # Проверяем наличие метода retranslateUi
        assert hasattr(widget, 'retranslateUi')
        assert callable(widget.retranslateUi)
    
    def test_retranslate_on_language_change(self):
        """Тест автоматического обновления UI при смене языка."""
        widget = TestWidget()
        
        # Мокаем метод retranslateUi
        widget.retranslateUi = Mock()
        
        # Переключаем язык
        self.service.set_language("ru")
        
        # Проверяем, что retranslateUi был вызван
        widget.retranslateUi.assert_called()
    
    def test_translator_installation(self):
        """Тест установки переводчика."""
        # Мокаем QApplication
        mock_app = Mock()
        
        # Устанавливаем переводчик
        self.service.install_translator(mock_app, "ru")
        
        # Проверяем, что язык установлен
        assert self.service.current_language() == "ru"
    
    def test_language_changed_signal(self):
        """Тест сигнала смены языка."""
        # Создаем мок для обработки сигнала
        signal_handler = Mock()
        self.service.languageChanged.connect(signal_handler)
        
        # Переключаем язык
        self.service.set_language("ru")
        
        # Проверяем, что сигнал был отправлен
        signal_handler.assert_called_once_with("ru")
    
    def test_multiple_language_switches(self):
        """Тест множественных переключений языков."""
        languages = ["en", "ru", "uk", "de", "es", "fr"]
        
        for lang in languages:
            self.service.set_language(lang)
            assert self.service.current_language() == lang
    
    def test_language_persistence(self):
        """Тест сохранения выбранного языка."""
        # Устанавливаем язык
        self.service.set_language("ru")
        
        # Создаем новый экземпляр сервиса
        new_service = LanguageService.instance()
        
        # Проверяем, что язык сохранился
        assert new_service.current_language() == "ru"


class TestTranslationLoading:
    """Тесты загрузки переводов."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()
        
        LanguageService.reset_for_tests()
        self.service = LanguageService.instance()
    
    def teardown_method(self):
        """Очистка после каждого теста."""
        LanguageService.reset_for_tests()
    
    def test_translation_files_exist(self):
        """Тест наличия файлов переводов."""
        i18n_dir = Path(__file__).parent.parent / "i18n"
        
        for lang in ["en", "ru", "uk", "de", "es", "fr"]:
            qm_file = i18n_dir / f"app_{lang}.qm"
            assert qm_file.exists(), f"Файл перевода {qm_file} не найден"
            assert qm_file.stat().st_size > 1000, f"Файл перевода {qm_file} слишком мал"
    
    def test_translation_loading(self):
        """Тест загрузки переводов."""
        # Устанавливаем приложение
        self.service.install_translator(self.app, "ru")
        
        # Проверяем, что переводчик установлен
        assert self.service._translator is not None
    
    @patch('i18n.language_service.QTranslator')
    def test_translation_fallback(self, mock_translator):
        """Тест fallback при ошибке загрузки переводов."""
        # Настраиваем мок для неудачной загрузки
        mock_translator_instance = Mock()
        mock_translator_instance.load.return_value = False
        mock_translator.return_value = mock_translator_instance
        
        # Устанавливаем приложение
        self.service.install_translator(self.app, "ru")
        
        # Проверяем, что fallback сработал
        assert self.service.current_language() == "en"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


