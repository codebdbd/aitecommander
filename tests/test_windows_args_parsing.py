from __future__ import annotations

import logging
import sys
from unittest.mock import patch

import pytest

from app.utils.links.link_utils import (
    LinkInfo,
    LinkType,
    ProgramLinkHandler,
    ScriptLinkHandler,
    SecurityValidator,
)


def test_split_cmdline_preserves_windows_backslashes() -> None:
    # 1. Backslashes in unquoted paths must not disappear
    args = r"C:\Data\input.txt --dir=D:\Out\Folder"
    parsed = SecurityValidator.split_cmdline(args)
    assert parsed == [r"C:\Data\input.txt", r"--dir=D:\Out\Folder"]

    # 2. Quoted paths with spaces and backslashes
    args = r'"C:\Program Files\My App\file.txt" --output="D:\My Data\res.csv"'
    parsed = SecurityValidator.split_cmdline(args)
    assert parsed == [r"C:\Program Files\My App\file.txt", r"--output=D:\My Data\res.csv"]

    # 3. Empty or whitespace
    assert SecurityValidator.split_cmdline("") == []
    assert SecurityValidator.split_cmdline("   ") == []


def test_split_cmdline_raises_valueerror_on_unclosed_quotes() -> None:
    # Unclosed quotes must raise ValueError rather than silently truncating or failing open
    with pytest.raises(ValueError, match="Unclosed quotation mark"):
        SecurityValidator.split_cmdline(r'C:\Data\input.txt "unclosed quote')


def test_programlinkhandler_preserves_backslashes_and_rejects_malformed_args() -> None:
    logger = logging.getLogger("test_program_args")
    handler = ProgramLinkHandler(logger)

    # 1. Normal execution with backslashes
    link = LinkInfo(
        id=1,
        link_type=LinkType.PROGRAM,
        path=sys.executable,
        args=r"C:\Data\script.py --dir=D:\Folder",
    )
    with patch("subprocess.Popen") as mock_popen:
        handler.open(link)
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == sys.executable
        assert cmd[1] == r"C:\Data\script.py"
        assert cmd[2] == r"--dir=D:\Folder"

    # 2. Unclosed quotes must raise ValueError and abort launch (subprocess.Popen NOT called)
    malformed_link = LinkInfo(
        id=2,
        link_type=LinkType.PROGRAM,
        path=sys.executable,
        args=r'--dir="C:\Invalid unclosed',
    )
    with patch("subprocess.Popen") as mock_popen:
        with pytest.raises(ValueError, match="Invalid program arguments"):
            handler.open(malformed_link)
        mock_popen.assert_not_called()


def test_scriptlinkhandler_rejects_malformed_args(tmp_path) -> None:
    logger = logging.getLogger("test_script_args")
    handler = ScriptLinkHandler(logger)

    fake_bat = tmp_path / "test.bat"
    fake_bat.write_text("@echo off\n", encoding="utf-8")

    malformed_link = LinkInfo(
        id=3,
        link_type=LinkType.SCRIPT,
        path=str(fake_bat),
        args=r'--param="unclosed quote',
    )
    with patch("subprocess.Popen") as mock_popen:
        with pytest.raises(ValueError, match="Invalid script arguments"):
            handler.open(malformed_link)
        mock_popen.assert_not_called()
