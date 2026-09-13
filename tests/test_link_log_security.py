from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch
import pytest

from app.utils.links.link_utils import (
    BrowserConfig,
    LinkInfo,
    LinkType,
    ProgramLinkHandler,
    WebLinkHandler,
    sanitize_url_for_logging,
)


def test_sanitize_url_for_logging_removes_secrets() -> None:
    # Query parameters with sensitive tokens
    url = "https://example.com/api/v1?token=super_secret_123&user=admin#fragment_data"
    sanitized = sanitize_url_for_logging(url)
    assert "super_secret_123" not in sanitized
    assert "fragment_data" not in sanitized
    assert sanitized == "https://example.com/api/v1?"

    # Userinfo / password in URL
    url_with_auth = "https://admin:p%40ssword@internal.corp.com:8443/dashboard?key=val"
    sanitized_auth = sanitize_url_for_logging(url_with_auth)
    assert "p%40ssword" not in sanitized_auth
    assert "admin" not in sanitized_auth
    assert sanitized_auth == "https://internal.corp.com:8443/dashboard?"

    # Safe URL without query or auth
    safe_url = "https://example.com/docs/readme.html"
    assert sanitize_url_for_logging(safe_url) == "https://example.com/docs/readme.html"

    # Empty string or local path
    assert sanitize_url_for_logging("") == ""
    assert sanitize_url_for_logging("C:\\tools\\app.exe") == "C:\\tools\\app.exe"


def test_weblinkhandler_does_not_log_sensitive_args_in_info(caplog: pytest.LogCaptureFixture) -> None:
    test_logger = logging.getLogger("test_weblink_logger")
    browser_config = MagicMock(spec=BrowserConfig)
    browser_config.get_browser_command.return_value = ["chrome.exe", "https://secret-service.com/login?token=topsecret456"]
    handler = WebLinkHandler(test_logger, browser_config)

    link_info = LinkInfo(
        id=1,
        link_type=LinkType.WEB,
        path="https://secret-service.com/login?token=topsecret456",
        args="--custom-auth=secret_token",
        browser_key="chrome",
    )

    with patch("subprocess.Popen") as mock_popen:
        with caplog.at_level(logging.INFO, logger="test_weblink_logger"):
            handler.open(link_info)

    # In INFO log: raw args, full command and query secrets must NOT appear
    info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    combined_info = "\n".join(info_messages)

    assert "topsecret456" not in combined_info
    assert "secret_token" not in combined_info
    assert "BROWSER LAUNCH DIAGNOSTICS" not in combined_info
    assert "Final exact command" not in combined_info
    assert "Successfully opened URL https://secret-service.com/login? with chrome" in combined_info


def test_programlinkhandler_does_not_log_args_in_info(caplog: pytest.LogCaptureFixture) -> None:
    test_logger = logging.getLogger("test_programlink_logger")
    handler = ProgramLinkHandler(test_logger)

    link_info = LinkInfo(
        id=2,
        link_type=LinkType.PROGRAM,
        path=sys.executable,
        args="--password SuperSecretPass --target D:\\Backups",
    )

    with patch("subprocess.Popen") as mock_popen:
        with caplog.at_level(logging.INFO, logger="test_programlink_logger"):
            handler.open(link_info)

    info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    combined_info = "\n".join(info_messages)

    assert "SuperSecretPass" not in combined_info
    assert f"Successfully launched program: {sys.executable}" in combined_info
