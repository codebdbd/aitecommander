import types
import pytest

from app.views.dialogs.link_dialog.link_dialog import LinkDialog


@pytest.fixture
def init_data():
    return {
        "spheres": [
            {"id": 1, "name": "Work"},
        ],
        "sections": [
            {"id": 10, "name": "Docs", "sphere_id": 1, "icon_path": ""},
        ],
        "categories": [
            {"id": 100, "name": "APIs", "section_id": 10, "icon_path": ""},
        ],
        "category_hierarchy": {"sphere_id": 1, "section_id": 10, "category_id": 100},
    }


@pytest.fixture
def dialog_controller_stub():
    class Ctrl:
        def get_sections_for_sphere(self, sphere_id):
            return [{"id": 10, "name": "Docs", "sphere_id": sphere_id, "icon_path": ""}]

        def get_categories_for_section(self, section_id):
            return [{"id": 100, "name": "APIs", "section_id": section_id, "icon_path": ""}]

        def validate_and_save(self, form_data: dict):
            # По умолчанию: валидно, может быть переопределено в тестах
            return {"is_valid": True, "errors": []}

    return Ctrl()


@pytest.fixture
def make_dialog(init_data, dialog_controller_stub, monkeypatch):
    def _make(link: dict | None = None):
        # Гарантируем успешную валидацию конфигурации иконок в диалоге
        from app.views.dialogs.link_dialog import link_dialog as link_dialog_mod
        monkeypatch.setattr(link_dialog_mod, "validate_config_for_icons", lambda *_: True)

        # parent=None, link_controller=None — по умолчанию
        d = LinkDialog(init_data, dialog_controller_stub, link=link)
        return d

    return _make


@pytest.mark.qt_no_exception_capture
def test_switch_link_types_updates_ui(qtbot, make_dialog):
    dlg = make_dialog()
    qtbot.addWidget(dlg)

    # program: profile_btn скрыт, browse_btn видим, args видим
    dlg.set_link_type("program")
    profile_btn = dlg.ui.get_widget("profile_btn")
    browse_btn = dlg.ui.get_widget("browse_btn")
    args_le = dlg.ui.get_widget("args_le")
    args_label = dlg.ui.get_widget("args_label")

    assert not profile_btn.isVisible()
    assert browse_btn.isVisible()
    assert args_le.isVisible() and args_label.isVisible()

    # web: profile_btn видим, browse_btn скрыт, args видим
    dlg.set_link_type("web")
    assert profile_btn.isVisible()
    assert not browse_btn.isVisible()
    assert args_le.isVisible() and args_label.isVisible()


@pytest.mark.qt_no_exception_capture
def test_on_browse_program_lnk_resolves_shortcut(qtbot, make_dialog, monkeypatch):
    from app.views.dialogs.link_dialog import link_dialog_handlers as handlers_mod
    from PyQt6.QtWidgets import QFileDialog

    dlg = make_dialog()
    qtbot.addWidget(dlg)
    dlg.set_link_type("program")

    # Подменим _parse_lnk и QFileDialog
    monkeypatch.setattr(
        handlers_mod,
        "_parse_lnk",
        lambda p: {"path": r"C:\\Program Files\\App\\app.exe", "args": "--foo"},
    )

    class FakeDialog:
        def __init__(self, *_a, **_k):
            self._dir = ""

        def setFileMode(self, *_):
            pass

        def setWindowTitle(self, *_):
            pass

        def setNameFilter(self, *_):
            pass

        def setDirectory(self, d):
            self._dir = d

        def exec(self):
            return QFileDialog.DialogCode.Accepted

        def selectedFiles(self):
            return [r"C:\\Temp\\shortcut.lnk"]

    monkeypatch.setattr(handlers_mod, "QFileDialog", FakeDialog)

    # Поле аргументов пустое — должно заполниться из ярлыка
    assert not dlg.ui.get_widget("args_le").text()

    # Запускаем обзор
    dlg.handlers._on_browse()

    assert dlg.ui.get_widget("url_le").text().endswith("app.exe")
    assert dlg.ui.get_widget("args_le").text() == "--foo"


@pytest.mark.qt_no_exception_capture
def test_on_accept_valid(qtbot, make_dialog, monkeypatch):
    dlg = make_dialog()
    qtbot.addWidget(dlg)

    # Заполняем форму валидными данными
    dlg.ui.set_form_data({
        "url_le": "https://example.com",
        "name_le": "Example",
        "args_le": "",
        "notes_te": "",
        "fav_chk": True,
    })

    accepted = {"v": False}

    def fake_accept():
        accepted["v"] = True

    monkeypatch.setattr(dlg, "accept", fake_accept)

    # Валидатор по умолчанию из Ctrl возвращает is_valid=True
    dlg.handlers._on_accept()

    assert accepted["v"] is True


@pytest.mark.qt_no_exception_capture
def test_on_accept_invalid_empty_form_shows_info(qtbot, make_dialog, monkeypatch):
    dlg = make_dialog()
    qtbot.addWidget(dlg)

    # Очищаем форму: пустые URL и Name
    dlg.ui.set_form_data({
        "url_le": "",
        "name_le": "",
        "args_le": "",
        "notes_te": "",
        "fav_chk": False,
    })

    called = {"args": None}

    def fake_show_info(msg, title, informative_text=None, details=None, silent=False):
        called["args"] = (msg, title, informative_text, details, silent)

    monkeypatch.setattr(dlg, "show_info", fake_show_info)

    # Сделаем, чтобы валидатор возвращал ошибку, но наш сценарий пустой формы её перехватит
    dlg.dialog_controller.validate_and_save = types.MethodType(
        lambda _self, _fd: {"is_valid": False, "errors": ["name required", "url required"]},
        dlg.dialog_controller,
    )

    dlg.handlers._on_accept()

    assert called["args"] is not None
    assert "Подсказка" in called["args"][1]


@pytest.mark.qt_no_exception_capture
def test_closeEvent_confirmation_blocks_when_processing(qtbot, make_dialog, monkeypatch):
    dlg = make_dialog()
    qtbot.addWidget(dlg)

    # Сымитируем активную обработку
    dlg.handlers._is_processing = True

    # Пользователь отклоняет закрытие
    monkeypatch.setattr(dlg, "ask_confirmation", lambda *a, **k: False)
    was_visible = dlg.isVisible()
    dlg.close()
    # Должен остаться открыт
    assert dlg.isVisible() == was_visible

    # Теперь пользователь подтверждает закрытие
    monkeypatch.setattr(dlg, "ask_confirmation", lambda *a, **k: True)
    dlg.handlers._is_processing = True
    dlg.close()
    assert not dlg.isVisible()
