import logging
from unittest.mock import patch
import pytest

from app.models.types.link_type import LinkType
from app.utils.links.link_utils import LinkInfo, ProgramLinkHandler, SecurityValidator


def test_security_validator_appsfolder_paths():
    # Valid AUMID paths
    assert SecurityValidator.is_safe_path(
        r"shell:AppsFolder\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
    )
    # Valid GUID-style path
    assert SecurityValidator.is_safe_path(
        r"shell:AppsFolder\{6D809377-6AF0-444B-8957-A3773F02200E}\Photoshop.exe"
    )
    # Rejection of command injection attempts in shell:AppsFolder paths
    assert not SecurityValidator.is_safe_path(r"shell:AppsFolder\App & calc.exe")
    assert not SecurityValidator.is_safe_path(r"shell:AppsFolder\App | dir")
    assert not SecurityValidator.is_safe_path(r"shell:AppsFolder\App; echo 1")
    assert not SecurityValidator.is_safe_path(r"shell:AppsFolder\App > output.txt")


def test_program_link_handler_appsfolder():
    handler = ProgramLinkHandler(logger=logging.getLogger("test"))
    link = LinkInfo(
        id=1,
        link_type=LinkType.PROGRAM,
        path=r"shell:AppsFolder\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    )
    assert handler.can_handle(link)

    with patch("os.startfile") as mock_startfile:
        handler.open(link)
        mock_startfile.assert_called_once_with(
            r"shell:AppsFolder\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
        )
