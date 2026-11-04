"""Tests for inline script creation, AI code fence cleaning, and ScriptEditorDialog integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from app.models.types.link_type import LinkType
from app.services.script_storage_service import ScriptStorageService
from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog
from app.views.windows.dialogs.script_editor_dialog import ScriptEditorDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_clean_and_detect_script_strips_markdown_fences():
    raw_ps = "```powershell\n# Очистка временных файлов\nGet-ChildItem $env:TEMP\n```"
    code, ext = ScriptStorageService.clean_and_detect_script(raw_ps)
    assert ext == ".ps1"
    assert "```" not in code
    assert "Get-ChildItem" in code

    raw_py = "```python\nimport os\ndef run():\n    print(os.getcwd())\n```"
    code_py, ext_py = ScriptStorageService.clean_and_detect_script(raw_py)
    assert ext_py == ".py"
    assert "```" not in code_py
    assert "import os" in code_py

    raw_bat = "```bat\n@echo off\necho Hello\npause\n```"
    code_bat, ext_bat = ScriptStorageService.clean_and_detect_script(raw_bat)
    assert ext_bat == ".bat"
    assert "@echo off" in code_bat


def test_detect_extension_heuristics_without_fences():
    assert (
        ScriptStorageService.detect_extension_from_code(
            "Write-Host 'Привет из ИИ'\nGet-Process"
        )
        == ".ps1"
    )
    assert (
        ScriptStorageService.detect_extension_from_code(
            "@echo off\nchcp 65001 >nul\ndir"
        )
        == ".bat"
    )
    assert (
        ScriptStorageService.detect_extension_from_code(
            "import pathlib\nif __name__ == '__main__':\n    pass"
        )
        == ".py"
    )
    assert (
        ScriptStorageService.detect_extension_from_code(
            'Option Explicit\nWScript.Echo "Done"'
        )
        == ".vbs"
    )


def test_suggest_script_name_from_comments():
    ps_code = "# Очистка кэша браузера\nRemove-Item -Path $env:TEMP\\*"
    assert ScriptStorageService.suggest_script_name(ps_code) == "Очистка кэша браузера"

    bat_code = "@echo off\n:: Перезапуск проводника\ntaskkill /f /im explorer.exe"
    assert ScriptStorageService.suggest_script_name(bat_code) == "Перезапуск проводника"

    py_code = "#!/usr/bin/env python3\n# Конвертация изображений в WebP\nimport os"
    assert (
        ScriptStorageService.suggest_script_name(py_code)
        == "Конвертация изображений в WebP"
    )


def test_save_and_read_script_utf8_bom_for_ps1(tmp_path: Path):
    with patch.object(ScriptStorageService, "get_scripts_dir", return_value=tmp_path):
        code = "# Тестовый скрипт\nWrite-Host 'Привет, мир!'"
        saved_path = ScriptStorageService.save_script(
            code=code, ext=".ps1", name_hint="Привет мир"
        )
        assert saved_path.exists()
        assert saved_path.suffix == ".ps1"
        assert ScriptStorageService.is_managed_script(saved_path)

        # Verify UTF-8 BOM is written for Windows PowerShell 5.1 Cyrillic support
        raw_bytes = saved_path.read_bytes()
        assert raw_bytes.startswith(b"\xef\xbb\xbf")

        read_code, read_ext = ScriptStorageService.read_script(saved_path)
        assert read_ext == ".ps1"
        assert read_code == code


def test_script_editor_dialog_paste_and_state(qapp):
    dlg = ScriptEditorDialog(initial_code="", initial_ext=".ps1", initial_keep_open=True)
    assert dlg.ok_button is not None
    assert not dlg.ok_button.isEnabled()
    assert dlg.get_keep_console_open() is True
    assert dlg.browse_disk_btn is not None

    dlg._apply_pasted_text(
        "```python\n# Проверка сети\nimport socket\nprint(socket.gethostname())\n```",
        replace_all=True,
    )
    assert dlg.ok_button.isEnabled()
    assert dlg.get_selected_extension() == ".py"
    assert "```" not in dlg.get_script_code()
    assert "import socket" in dlg.get_script_code()
    dlg.close()


def test_link_dialog_script_create_and_cancel_rolls_back_file(
    qapp, tmp_path: Path
):
    init_data = {"category_hierarchy": {}, "spheres": []}
    mock_controller = MagicMock()

    with patch.object(ScriptStorageService, "get_scripts_dir", return_value=tmp_path):
        dialog = LinkDialog(
            initialization_data=init_data,
            dialog_controller=mock_controller,
            link={"type": "web"},
        )
        dialog.handlers.on_type_changed(LinkType.SCRIPT)

        browse_btn = dialog._get_browse_btn()
        assert browse_btn.text() in ("Create", "Создать")
        assert dialog.ui.get_widget("keep_open_chk") is None

        # Simulate accepting ScriptEditorDialog with pasted AI code
        fake_editor = MagicMock()
        fake_editor.exec.return_value = QDialog.DialogCode.Accepted
        fake_editor.get_selected_disk_path.return_value = None
        fake_editor.get_script_code.return_value = (
            "# Очистка логов\nGet-ChildItem *.log"
        )
        fake_editor.get_selected_extension.return_value = ".ps1"
        fake_editor.get_keep_console_open.return_value = True

        with patch(
            "app.views.windows.dialogs.link_dialog.handlers_mixins.script_editor_mixin.ScriptEditorDialog",
            return_value=fake_editor,
        ):
            dialog.handlers._on_browse()

        created_url = dialog._get_url_le().text().strip()
        assert created_url
        created_path = Path(created_url)
        assert created_path.is_file()
        assert dialog._get_name_le().text() == "Очистка логов"
        assert browse_btn.text() in ("Edit", "Изменить", "Редактировать")

        form_data = dialog.handlers._collect_form_data()
        assert "--keep-open" in form_data["args"]

        # Rejecting the LinkDialog must clean up the uncommitted script file
        dialog.reject()
        assert not created_path.exists()


def test_frozen_python_script_resolves_uv_and_never_calls_startfile(
    tmp_path: Path, monkeypatch
):
    import logging

    from app.utils.links.link_utils import (
        LinkInfo,
        ScriptLinkHandler,
    )
    from app.utils.links.link_utils import (
        LinkType as UtilLinkType,
    )

    # Simulate uv Python installation in %APPDATA%\uv\python\cpython-3.12.13-...
    uv_dir = tmp_path / "Roaming" / "uv" / "python" / "cpython-3.12.13-windows-x86_64"
    uv_dir.mkdir(parents=True)
    fake_uv_py = uv_dir / "python.exe"
    fake_uv_py.write_bytes(b"MZ\x00\x00")

    script_file = tmp_path / "scripts" / "ai_script.py"
    script_file.parent.mkdir(parents=True)
    script_file.write_text("print('Hello')", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("SystemRoot", str(tmp_path / "FakeWin"))
    monkeypatch.setattr("sys.frozen", True, raising=False)

    logger = logging.getLogger("test_frozen_py")
    handler = ScriptLinkHandler(logger, powershell_path="powershell.exe")
    handler.python_path = None

    with (
        patch("platform.system", return_value="Windows"),
        patch("shutil.which", return_value=None),
        patch.object(handler, "_find_python_in_windows_registry", return_value=None),
        patch("subprocess.Popen") as mock_popen,
        patch("os.startfile", create=True) as mock_startfile,
    ):
        resolved = handler._resolve_python_executable(str(script_file))
        assert resolved == str(fake_uv_py)

        # Launch with --keep-open: must execute via cmd.exe /k, never os.startfile
        info = LinkInfo(
            id=10,
            link_type=UtilLinkType.SCRIPT,
            path=str(script_file),
            args="--keep-open",
        )
        handler.open(info)
        mock_startfile.assert_not_called()
        mock_popen.assert_called_once()
        cmd_arg = mock_popen.call_args[0][0]
        assert isinstance(cmd_arg, str)
        assert cmd_arg.startswith("cmd.exe /k ")
        assert str(fake_uv_py) in cmd_arg
        assert str(script_file.resolve()) in cmd_arg


def test_python_script_without_interpreter_raises_instead_of_opening_editor(
    tmp_path: Path,
):
    import logging

    from app.utils.links.link_utils import (
        LinkInfo,
        ScriptLinkHandler,
    )
    from app.utils.links.link_utils import (
        LinkType as UtilLinkType,
    )

    script_file = tmp_path / "orphan.py"
    script_file.write_text("print(1)", encoding="utf-8")

    handler = ScriptLinkHandler(
        logging.getLogger("test_no_py"), powershell_path="powershell.exe"
    )
    with (
        patch("platform.system", return_value="Windows"),
        patch.object(handler, "_resolve_python_executable", return_value=None),
        patch("os.startfile", create=True) as mock_startfile,
    ):
        with pytest.raises(RuntimeError, match="Python interpreter not found"):
            handler.open(
                LinkInfo(
                    id=11,
                    link_type=UtilLinkType.SCRIPT,
                    path=str(script_file),
                    args="--keep-open",
                )
            )
        mock_startfile.assert_not_called()


def test_powershell_skips_broken_windowsapps_pwsh_stub(tmp_path: Path):
    import logging

    from app.utils.links.link_utils import ScriptLinkHandler

    # 0-byte WindowsApps stub
    stub_dir = tmp_path / "Microsoft" / "WindowsApps"
    stub_dir.mkdir(parents=True)
    pwsh_stub = stub_dir / "pwsh.exe"
    pwsh_stub.write_bytes(b"")

    real_ps = tmp_path / "System32" / "powershell.exe"
    real_ps.parent.mkdir(parents=True)
    real_ps.write_bytes(b"MZ\x90\x00")

    def fake_which(name: str):
        if name in ("pwsh.exe", "pwsh"):
            return str(pwsh_stub)
        if name in ("powershell.exe", "powershell"):
            return str(real_ps)
        return None

    with (
        patch("platform.system", return_value="Windows"),
        patch("shutil.which", side_effect=fake_which),
    ):
        handler = ScriptLinkHandler(logging.getLogger("test_ps_stub"))
        assert handler.powershell_path == str(real_ps)

def test_read_and_save_cmd_file_preserves_cmd_extension(tmp_path: Path):
    cmd_file = tmp_path / "custom_tool.cmd"
    cmd_file.write_text("@echo off\necho 123\n", encoding="utf-8")

    code, ext = ScriptStorageService.read_script(cmd_file)
    assert ext == ".cmd"
    assert "@echo off" in code

    saved = ScriptStorageService.save_script(code, ext=".cmd", existing_path=cmd_file)
    assert saved == cmd_file
    assert saved.suffix == ".cmd"


def test_save_bat_with_non_ascii_adds_chcp_65001(tmp_path: Path):
    bat_file = tmp_path / "cyrillic.bat"
    code = "@echo off\necho Привет мир\n"
    saved = ScriptStorageService.save_script(code, ext=".bat", existing_path=bat_file)
    content = saved.read_text(encoding="utf-8")
    assert "@chcp 65001 >nul" in content
    assert "Привет мир" in content


def test_read_oem_cp866_bat_file_decodes_correctly(tmp_path: Path):
    bat_file = tmp_path / "legacy_oem.bat"
    # Encode with cp866
    oem_bytes = "@echo off\r\necho Привет\r\n".encode("cp866")
    bat_file.write_bytes(oem_bytes)

    code, ext = ScriptStorageService.read_script(bat_file)
    assert ext == ".bat"
    assert "Привет" in code


def test_editing_existing_script_defers_disk_write_until_accepted(qapp, tmp_path: Path):
    user_file = tmp_path / "my_production_script.ps1"
    original_code = "Write-Host 'Original production code'"
    user_file.write_text(original_code, encoding="utf-8-sig")

    init_data = {"category_hierarchy": {}, "spheres": []}
    mock_controller = MagicMock()

    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=mock_controller,
        link={"type": "script", "url": str(user_file)},
    )

    fake_editor = MagicMock()
    fake_editor.exec.return_value = QDialog.DialogCode.Accepted
    fake_editor.get_selected_disk_path.return_value = None
    fake_editor.get_script_code.return_value = "Write-Host 'Draft modification'"
    fake_editor.get_selected_extension.return_value = ".ps1"
    fake_editor.get_keep_console_open.return_value = True

    with patch(
        "app.views.windows.dialogs.link_dialog.handlers_mixins.script_editor_mixin.ScriptEditorDialog",
        return_value=fake_editor,
    ):
        dialog.handlers._on_script_editor()

    # While LinkDialog is still open (unconfirmed), file on disk MUST NOT be modified!
    assert user_file.read_text(encoding="utf-8-sig") == original_code

    # If user cancels the LinkDialog, file on disk MUST REMAIN UNTOUCHED!
    dialog.reject()
    assert user_file.read_text(encoding="utf-8-sig") == original_code


def test_windowsapps_usable_alias_caching():
    from app.utils.links.link_utils import ScriptLinkHandler

    ScriptLinkHandler._alias_status_cache.clear()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("pathlib.Path.is_file", return_value=True), patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=0)
            alias_path = r"C:\Users\test\AppData\Local\Microsoft\WindowsApps\pwsh.exe"

            # First check: runs subprocess.run
            is_broken = ScriptLinkHandler._is_windowsapps_stub(alias_path)
            assert not is_broken
            assert mock_run.call_count == 1

            # Second check: cached, subprocess.run is NOT called again
            is_broken_again = ScriptLinkHandler._is_windowsapps_stub(alias_path)
            assert not is_broken_again
            assert mock_run.call_count == 1

