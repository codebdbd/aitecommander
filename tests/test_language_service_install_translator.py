import pytest
from PyQt6.QtWidgets import QApplication

# Ensure Qt resource with translations is registered
from i18n import resources_rc  # noqa: F401
from i18n.language_service import LanguageService


@pytest.mark.qtbot
def test_language_service_install_and_switch(qtbot):
    # Reset singleton to a clean state between tests
    LanguageService.reset_for_tests()

    app = QApplication.instance()
    assert app is not None

    svc = LanguageService.instance()

    # Should not raise even if resource/file missing; falls back gracefully
    svc.install_translator(app)

    # Switching language must emit the signal and not crash
    with qtbot.waitSignal(svc.languageChanged, timeout=1000):
        svc.set_language("uk")

    # Normalization ensures code is one of configured languages
    assert svc.current_language() in {"en", "ru", "uk", "de", "es", "fr"}
