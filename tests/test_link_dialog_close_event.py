import pytest

from app.views.dialogs.link_dialog.link_dialog import LinkDialog


class DummyDialogController:
    def validate_and_save(self, form_data):
        # Не используется в данном тесте
        return {"is_valid": True}

    def get_sections_for_sphere(self, sphere_id: int):
        return []

    def get_categories_for_section(self, section_id: int):
        return []


@pytest.mark.usefixtures("qapp")
def test_close_event_calls_cancel_processing(monkeypatch, qtbot):
    initialization_data = {
        "spheres": [
            {"id": 1, "name": "S1"},
        ],
        "category_hierarchy": {},
    }

    controller = DummyDialogController()

    # Создаём реальный диалог (он использует упрощённые UI-стабы из LinkDialogUI)
    dlg = LinkDialog(initialization_data, controller, link=None, category_id=None, parent=None)
    qtbot.addWidget(dlg)

    # Подготовка: считаем, что идёт обработка — чтобы прошла ветка с подтверждением
    dlg.handlers._is_processing = True

    # Подменим подтверждение на автоматическое согласие
    monkeypatch.setattr(dlg, "ask_confirmation", lambda *args, **kwargs: True)

    called = {"cnt": 0}

    def _fake_cancel():
        called["cnt"] += 1

    monkeypatch.setattr(dlg.handlers, "cancel_processing", _fake_cancel)

    # Действие: закрытие диалога должно вызвать cancel_processing
    dlg.close()

    assert called["cnt"] == 1
