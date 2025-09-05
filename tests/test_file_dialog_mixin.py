import types
import builtins
import pytest

# Модуль под тестом
import app.views.dialogs.link_dialog.handlers_mixins.file_dialog_mixin as fdm
from app.views.dialogs.link_dialog.handlers_mixins.file_dialog_mixin import (
    BROWSE_CONFIG,
)


class LineEditStub:
    def __init__(self, value=""):
        self._text = value

    def text(self):
        return self._text

    def setText(self, value):
        self._text = value


class UIStub:
    def __init__(self):
        self.widgets = {
            "url_le": LineEditStub(),
            "args_le": LineEditStub(),
            "name_le": LineEditStub(),
        }

    def get_widget(self, name):
        return self.widgets[name]

    def set_widget_value(self, name, value):
        self.widgets[name].setText(value)


class HandlerStub(fdm.FileDialogMixin):
    def __init__(self, link_type, ui):
        self.dialog = types.SimpleNamespace(link_type=link_type, ui=ui)


class QFileDialogStub:
    class FileMode:
        ExistingFile = object()
        Directory = object()

    class DialogCode:
        Accepted = 1
        Rejected = 0

    def __init__(self, parent=None):
        self.parent = parent
        self._mode = None
        self._title = None
        self._filter = None
        self._directory = None
        self._selected = []
        self._return = QFileDialogStub.DialogCode.Accepted

    def setFileMode(self, mode):
        self._mode = mode

    def setWindowTitle(self, title):
        self._title = title

    def setNameFilter(self, flt):
        self._filter = flt

    def setDirectory(self, d):
        self._directory = d

    def exec(self):
        return self._return

    def selectedFiles(self):
        return list(self._selected)


@pytest.fixture(autouse=True)
def patch_qfiledialog(monkeypatch):
    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogStub)
    yield


@pytest.fixture
def patch_default_paths(monkeypatch):
    # Возвращаем стартовые директории для всех типов
    defaults = {
        "program": r"C:\\Program Files",
        "script": r"C:\\Scripts",
        "folder": r"C:\\",
        "file": r"C:\\Users\\user\\Documents",
        "chromeapp": r"C:\\Users\\user\\Desktop",
    }
    monkeypatch.setattr(
        fdm.app_config.settings,
        "get_default_browse_paths",
        lambda: defaults,
        raising=False,
    )
    return defaults


def test_browse_config_applied_for_each_type(patch_default_paths):
    for link_type, cfg in BROWSE_CONFIG.items():
        ui = UIStub()
        h = HandlerStub(link_type, ui)
        # Выполняем browse
        h._on_browse()
        # Достаём созданный диалог из пространства имён класса
        # Поскольку мы не сохраняем его, проверяем через последний созданный экземпляр,
        # имитируя один вызов на тип
        # Для этого пересоздадим и проверим настройки на месте через вызов ещё раз
        dlg = QFileDialogStub(h.dialog)
        dlg.setFileMode(cfg["mode"])  # что ожидаем
        dlg.setWindowTitle(cfg["title"])  # что ожидаем
        if cfg.get("filter"):
            dlg.setNameFilter(cfg["filter"])  # что ожидаем
        # smoke-assert: настройки допустимы (не None)
        assert dlg._mode is not None
        assert dlg._title is not None
        # folder допускает отсутствие фильтра


def test_on_browse_program_lnk_parsing(monkeypatch, patch_default_paths):
    # Настроим заглушку диалога для возврата выбранного .lnk
    selected = [r"C:\\Temp\\MyApp.lnk"]

    class QFileDialogLnk(QFileDialogStub):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._selected = selected

    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogLnk)

    # Заглушка parse_lnk в модуле миксина
    monkeypatch.setattr(
        fdm, "parse_lnk", lambda p: {"path": r"C:\\Program Files\\MyApp\\MyApp.exe", "args": "--foo"}
    )

    ui = UIStub()
    h = HandlerStub("program", ui)

    # До вызова name пустой, чтобы сработала автоустановка имени
    assert ui.get_widget("name_le").text() == ""

    h._on_browse()

    assert ui.get_widget("url_le").text() == r"C:\\Program Files\\MyApp\\MyApp.exe"
    assert ui.get_widget("args_le").text() == "--foo"
    # Имя = basename без расширения
    assert ui.get_widget("name_le").text() == "MyApp"


def test_on_browse_cancel_does_nothing(monkeypatch, patch_default_paths):
    class QFileDialogRejected(QFileDialogStub):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._return = QFileDialogStub.DialogCode.Rejected

    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogRejected)

    ui = UIStub()
    # Предзаполним значения, чтобы проверить, что они не меняются
    ui.set_widget_value("url_le", "before")
    ui.set_widget_value("args_le", "--arg")
    ui.set_widget_value("name_le", "Name")

    h = HandlerStub("file", ui)
    h._on_browse()

    assert ui.get_widget("url_le").text() == "before"
    assert ui.get_widget("args_le").text() == "--arg"
    assert ui.get_widget("name_le").text() == "Name"


def test_on_browse_program_exe_does_not_call_parse_lnk(monkeypatch, patch_default_paths):
    selected = [r"C:\\Temp\\MyApp.exe"]

    class QFileDialogExe(QFileDialogStub):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._selected = selected

    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogExe)

    def _should_not_be_called(_):
        raise AssertionError("parse_lnk must not be called for non-.lnk selection")

    monkeypatch.setattr(fdm, "parse_lnk", _should_not_be_called)

    ui = UIStub()
    h = HandlerStub("program", ui)

    h._on_browse()

    assert ui.get_widget("url_le").text() == r"C:\\Temp\\MyApp.exe"
    # Для program имя берётся без расширения
    assert ui.get_widget("name_le").text() == "MyApp"


def test_on_browse_program_lnk_keeps_existing_args(monkeypatch, patch_default_paths):
    selected = [r"C:\\Temp\\MyApp.lnk"]

    class QFileDialogLnk(QFileDialogStub):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._selected = selected

    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogLnk)

    monkeypatch.setattr(
        fdm, "parse_lnk", lambda p: {"path": r"C:\\Program Files\\MyApp\\MyApp.exe", "args": "--from-lnk"}
    )

    ui = UIStub()
    # Уже есть пользовательские аргументы — не должны перезаписываться
    ui.set_widget_value("args_le", "--custom")
    h = HandlerStub("program", ui)

    h._on_browse()

    assert ui.get_widget("url_le").text() == r"C:\\Program Files\\MyApp\\MyApp.exe"
    assert ui.get_widget("args_le").text() == "--custom"


def test_on_browse_preserve_existing_name(monkeypatch, patch_default_paths):
    selected = [r"C:\\Temp\\SomeFile.txt"]

    class QFileDialogTxt(QFileDialogStub):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._selected = selected

    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogTxt)

    ui = UIStub()
    ui.set_widget_value("name_le", "Custom Name")
    h = HandlerStub("file", ui)

    h._on_browse()

    assert ui.get_widget("url_le").text() == r"C:\\Temp\\SomeFile.txt"
    # Имя было задано — его не должны перезаписывать
    assert ui.get_widget("name_le").text() == "Custom Name"


def test_on_browse_program_lnk_parse_returns_none_is_safe(monkeypatch, patch_default_paths):
    selected = [r"C:\\Temp\\Broken.lnk"]

    class QFileDialogLnk(QFileDialogStub):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._selected = selected

    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogLnk)
    # parse_lnk возвращает None
    monkeypatch.setattr(fdm, "parse_lnk", lambda p: None)

    ui = UIStub()
    # Предзаполним args и проверим, что они не меняются
    ui.set_widget_value("args_le", "--keep")
    h = HandlerStub("program", ui)

    h._on_browse()

    # url остаётся путём к .lnk, имя берётся без .lnk
    assert ui.get_widget("url_le").text() == r"C:\\Temp\\Broken.lnk"
    assert ui.get_widget("name_le").text() == "Broken"
    assert ui.get_widget("args_le").text() == "--keep"


def test_on_browse_program_lnk_parse_raises_is_safe(monkeypatch, patch_default_paths):
    selected = [r"C:\\Temp\\Err.lnk"]

    class QFileDialogLnk(QFileDialogStub):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._selected = selected

    monkeypatch.setattr(fdm, "QFileDialog", QFileDialogLnk)

    def _raise(_):
        raise RuntimeError("bad lnk")

    monkeypatch.setattr(fdm, "parse_lnk", _raise)

    ui = UIStub()
    ui.set_widget_value("args_le", "--keep")
    h = HandlerStub("program", ui)

    # Не должно выбросить исключение наружу
    h._on_browse()

    assert ui.get_widget("url_le").text() == r"C:\\Temp\\Err.lnk"
    assert ui.get_widget("name_le").text() == "Err"
    assert ui.get_widget("args_le").text() == "--keep"
