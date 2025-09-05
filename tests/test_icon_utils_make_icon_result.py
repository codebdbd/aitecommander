import builtins
from pathlib import Path

import pytest

from app.views.dialogs.link_dialog.icon_utils import (
    make_icon_result,
    IconErrorKind,
)


def test_make_icon_result_invalid_path_empty():
    res = make_icon_result("")
    assert not res.success
    assert res.error_kind == IconErrorKind.INVALID_PATH
    assert res.icon is None


def test_make_icon_result_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Настроим user/ui папки на пустые временные директории
    from app.views.dialogs.link_dialog import icon_utils as iu

    monkeypatch.setattr(iu.icon_path_service, "get_user_icons_dir", lambda: tmp_path / "user_icons")
    monkeypatch.setattr(iu.icon_path_service, "get_ui_icons_dir", lambda: tmp_path / "ui_icons")

    # Директории существуют, но файла нет
    (tmp_path / "user_icons").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ui_icons").mkdir(parents=True, exist_ok=True)

    res = make_icon_result("missing.png")
    assert not res.success
    assert res.error_kind == IconErrorKind.NOT_FOUND
    assert res.icon is None


def test_make_icon_result_success_absolute(tmp_path: Path):
    icon_file = tmp_path / "ok.png"
    icon_file.write_bytes(b"fake image content")

    res = make_icon_result(str(icon_file))
    assert res.success
    assert res.icon is not None
    assert res.resolved_path == icon_file


def test_make_icon_result_os_error_on_user_dir(monkeypatch: pytest.MonkeyPatch):
    # Симулируем сбой доступа к пользовательской папке
    from app.views.dialogs.link_dialog import icon_utils as iu

    def boom():
        raise OSError("boom user dir")

    monkeypatch.setattr(iu.icon_path_service, "get_user_icons_dir", boom)
    # UI dir не должен вызываться, но на всякий случай заглушим корректным значением
    monkeypatch.setattr(iu.icon_path_service, "get_ui_icons_dir", lambda: Path.cwd())

    res = make_icon_result("any.png")
    assert not res.success
    assert res.error_kind == IconErrorKind.OS_ERROR
    assert "пользовательской" in res.message


def test_make_icon_result_permission_denied_on_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Подмена user/ui директорий на tmp, чтобы получить кандидаты
    from app.views.dialogs.link_dialog import icon_utils as iu

    monkeypatch.setattr(iu.icon_path_service, "get_user_icons_dir", lambda: tmp_path)
    monkeypatch.setattr(iu.icon_path_service, "get_ui_icons_dir", lambda: tmp_path)

    # Патчим Path.exists так, чтобы при встрече имени с 'deny' бросался PermissionError
    real_exists = Path.exists

    def exists_with_denied(self: Path) -> bool:
        if "deny" in str(self):
            raise PermissionError("denied by test")
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", exists_with_denied)

    res = make_icon_result("deny.png")
    assert not res.success
    assert res.error_kind == IconErrorKind.PERMISSION_DENIED
    assert "Нет доступа" in res.message
