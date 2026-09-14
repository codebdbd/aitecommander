from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from app.utils.links.link_utils import LinkInfo, LinkType, ScriptLinkHandler


@pytest.fixture
def logger():
    return logging.getLogger("test_script_handler")


def test_script_handler_uses_configured_python_path(logger, tmp_path):
    fake_python = tmp_path / "custom_python.exe"
    fake_python.write_text("", encoding="utf-8")
    script = tmp_path / "script.py"
    script.write_text("print(1)", encoding="utf-8")

    handler = ScriptLinkHandler(logger, python_path=str(fake_python))
    cmd = handler._create_python_command(str(script), ["--arg1", "val1"])

    assert cmd == [str(fake_python), str(script), "--arg1", "val1"]


def test_script_handler_detects_local_venv(logger, tmp_path):
    # Setup a project directory with .venv/Scripts/python.exe
    project_dir = tmp_path / "my_project"
    venv_scripts = project_dir / ".venv" / "Scripts"
    venv_scripts.mkdir(parents=True)
    venv_python = venv_scripts / "python.exe"
    venv_python.write_text("", encoding="utf-8")

    script = project_dir / "app.py"
    script.write_text("print('hello')", encoding="utf-8")

    handler = ScriptLinkHandler(logger)
    resolved = handler._resolve_python_executable(str(script))

    assert resolved == str(venv_python)
    cmd = handler._create_python_command(str(script), [])
    assert cmd == [str(venv_python), str(script)]


def test_script_handler_detects_py_launcher_when_no_venv(logger, tmp_path):
    script = tmp_path / "test.py"
    script.write_text("print(1)", encoding="utf-8")

    handler = ScriptLinkHandler(logger)
    with patch("shutil.which", side_effect=lambda name: "C:\\Windows\\py.exe" if name == "py" else None):
        with patch("platform.system", return_value="Windows"):
            resolved = handler._resolve_python_executable(str(script))
            assert resolved == "C:\\Windows\\py.exe"


def test_script_handler_raises_helpful_error_when_no_python(logger, tmp_path):
    script = tmp_path / "nofound.py"
    script.write_text("print(1)", encoding="utf-8")

    handler = ScriptLinkHandler(logger)
    with patch.object(handler, "_resolve_python_executable", return_value=None):
        with patch("platform.system", return_value="Linux"):
            with pytest.raises(FileNotFoundError, match="Python interpreter not found"):
                handler._create_python_command(str(script), ["--arg"])

def test_script_handler_open_passes_cwd_and_handles_pyw(logger, tmp_path):
    script = tmp_path / "gui_app.pyw"
    script.write_text("import sys", encoding="utf-8")

    link_info = LinkInfo(
        id=1,
        link_type=LinkType.SCRIPT,
        path=str(script),
        args="",
    )

    handler = ScriptLinkHandler(logger)
    with patch.object(handler, "_resolve_python_executable", return_value="C:\\fake\\python.exe"), \
         patch("subprocess.Popen") as mock_popen:
        handler.open(link_info)
        mock_popen.assert_called_once_with(
            ["C:\\fake\\python.exe", str(script)],
            creationflags=0,
            cwd=str(tmp_path.resolve()),
        )

def test_script_handler_creates_powershell_command_with_file_flag(logger, tmp_path):
    script = tmp_path / "deploy.ps1"
    script.write_text("Write-Host 1", encoding="utf-8")

    handler = ScriptLinkHandler(logger, powershell_path="powershell.exe")
    cmd = handler._create_powershell_command(str(script), ["-Verbose", "-Force"])

    assert cmd == [
        "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Verbose",
        "-Force",
    ]
