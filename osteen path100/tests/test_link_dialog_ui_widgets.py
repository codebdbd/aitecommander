import pytest

from app.views.dialogs.link_dialog.link_dialog_ui import LinkDialogUI

try:
    from PyQt6.QtWidgets import QApplication, QWidget
except Exception:  # pragma: no cover - PyQt import guard for environments without Qt
    QApplication = None  # type: ignore
    QWidget = None  # type: ignore


@pytest.mark.skipif(
    QApplication is None,
    reason="PyQt6 is not available in the test environment",
)
def test_link_dialog_ui_builds_expected_widgets_keys():
    # Инициализация QApplication (если ещё не создан)
    app = QApplication.instance() or QApplication([])

    parent = QWidget()
    ui = LinkDialogUI(parent)

    link_types = [("web", "Веб"), ("file", "Файл")]
    ui.build_ui(link_types)

    expected_keys = {
        "type_group",
        "url_le",
        "browse_btn",
        "profile_btn",
        "name_le",
        "icon_btn",
        "args_le",
        "args_label",
        "sphere_cb",
        "section_cb",
        "category_cb",
        "notes_te",
        "fav_chk",
        "button_box",
        "ok_btn",
    }

    missing = [k for k in expected_keys if k not in ui.widgets]
    assert not missing, f"В widgets отсутствуют ключи: {missing}"

    # Дополнительно убеждаемся, что ок-кнопка действительно существует
    ok_btn = ui.widgets.get("ok_btn")
    assert ok_btn is not None

    # Чистка созданного окна
    parent.deleteLater()

    # QApplication остаётся жить до завершения тестового процесса
    _ = app
