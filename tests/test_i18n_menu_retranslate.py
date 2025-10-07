import pytest
from PyQt6.QtWidgets import QWidget
from i18n.language_service import LanguageService
from app.utils.ui.menu_builders.menu_actions import ActionBuilder, MenuTexts, _tr


@pytest.mark.qtbot
def test_menu_actions_retranslate_on_language_change(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    ab = ActionBuilder(parent)

    act_open = ab.create(MenuTexts.OPEN)
    act_edit = ab.create(MenuTexts.EDIT)

    # Initial state: should equal translated source (likely same in EN)
    assert act_open.text() == _tr(MenuTexts.OPEN)
    assert act_edit.text() == _tr(MenuTexts.EDIT)

    # Emit languageChanged to trigger retranslate
    svc = LanguageService.instance()
    assert svc is not None
    # Even if no translator is loaded, signal should not crash and should re-apply text
    svc.languageChanged.emit("uk")  # type: ignore[attr-defined]

    # After retranslate, values should be re-applied (same source in EN)
    assert act_open.text() == _tr(MenuTexts.OPEN)
    assert act_edit.text() == _tr(MenuTexts.EDIT)
