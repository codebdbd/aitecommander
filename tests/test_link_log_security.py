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

    with patch("subprocess.Popen"):
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

    with patch("subprocess.Popen"):
        with caplog.at_level(logging.INFO, logger="test_programlink_logger"):
            handler.open(link_info)

    info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    combined_info = "\n".join(info_messages)

    assert "SuperSecretPass" not in combined_info
    assert f"Successfully launched program: {sys.executable}" in combined_info


def test_sanitize_url_for_logging_schemeless_and_custom_schemes() -> None:
    # Schemeless URL with query parameters
    assert sanitize_url_for_logging("example.com/login?token=supersecret") == "example.com/login?"

    # Userinfo without scheme
    assert sanitize_url_for_logging("user:pass@example.com/dashboard") == "example.com/dashboard"

    # Custom chat scheme (Telegram)
    assert sanitize_url_for_logging("tg://msg?text=secret_message") == "tg://msg?"

    # Web share URL with encoded queries
    share_url = "https://t.me/share/url?url=https%3A%2F%2Fsecret.com&text=Check%20this"
    assert sanitize_url_for_logging(share_url) == "https://t.me/share/url?"

    # None and non-string handling
    assert sanitize_url_for_logging(None) == ""  # type: ignore[arg-type]

    # Windows drive paths preserved without query
    assert sanitize_url_for_logging("D:/Backups/app.exe") == "D:/Backups/app.exe"


def test_sanitize_link_dict_for_log() -> None:
    from app.utils.links.link_utils import sanitize_link_dict_for_log

    raw_dict = {
        "id": 10,
        "name": "Secret Service",
        "type": "web",
        "url": "https://service.internal/login?token=sensitive_token_999",
        "path": "https://service.internal/login?token=sensitive_token_999",
        "args": "--auth-bearer=bearer_12345",
        "notes": "My private password is password123",
        "category_id": 5,
    }

    sanitized = sanitize_link_dict_for_log(raw_dict)
    assert sanitized["id"] == 10
    assert sanitized["name"] == "Secret Service"
    assert "sensitive_token_999" not in sanitized["url"]
    assert sanitized["url"] == "https://service.internal/login?"
    assert "sensitive_token_999" not in sanitized["path"]
    assert sanitized["path"] == "https://service.internal/login?"
    assert sanitized["args"] == "<redacted>"
    assert sanitized["notes"] == "<redacted>"
    assert "password123" not in str(sanitized)


def test_link_info_repr_redacts_secrets() -> None:
    link_info = LinkInfo(
        id=42,
        link_type=LinkType.WEB,
        path="https://admin:pass123@portal.corp/panel?session=xyz789#top",
        args="--secret-token=topsecret",
        category_id=7,
        browser_key="chrome",
    )
    rep = repr(link_info)
    assert "pass123" not in rep
    assert "xyz789" not in rep
    assert "topsecret" not in rep
    assert "<redacted>" in rep
    assert "https://portal.corp/panel?" in rep


def test_share_service_logs_sanitized_url(caplog: pytest.LogCaptureFixture) -> None:
    from app.services.share_service import _open_url

    secret_share_url = "https://t.me/share/url?url=https%3A%2F%2Fsecret.corp%2Fapi%3Ftoken%3Dultra_secret&text=Recommended"

    with patch("PyQt6.QtGui.QDesktopServices.openUrl", return_value=True):
        with caplog.at_level(logging.DEBUG, logger="app.services.share_service"):
            _open_url(secret_share_url)

    records = [r.message for r in caplog.records if r.name == "app.services.share_service"]
    combined = "\n".join(records)
    assert "ultra_secret" not in combined
    assert "Recommended" not in combined
    assert "https://t.me/share/url?" in combined


def test_bad_url_check_worker_logs_sanitized_url(caplog: pytest.LogCaptureFixture) -> None:
    from app.models.workers.bad_url_check_worker import BadUrlCheckWorker

    worker = BadUrlCheckWorker(db=MagicMock(), timeout=1)
    sensitive_url = "https://example.org/checkout?user_token=secret_card_token"

    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        with caplog.at_level(logging.DEBUG, logger="app.models.workers.bad_url_check_worker"):
            worker._verify_404_with_get(sensitive_url)

    records = [r.message for r in caplog.records if r.name == "app.models.workers.bad_url_check_worker"]
    combined = "\n".join(records)
    assert "secret_card_token" not in combined
    assert "https://example.org/checkout?" in combined


def test_title_parser_logs_sanitized_url(caplog: pytest.LogCaptureFixture) -> None:
    from app.utils.links.parser.title_parser import _fetch_and_parse_html

    sensitive_url = "https://example.org/api/profile?private_key=secret987"
    mock_config = MagicMock()
    mock_config.HTML_FETCH_RETRIES = 0

    with patch("app.utils.links.parser.title_parser.http_request", return_value=None):
        with caplog.at_level(logging.DEBUG):
            _fetch_and_parse_html(sensitive_url, mock_config, timeout_override=1, retries_override=0)

    combined = "\n".join(r.message for r in caplog.records)
    assert "secret987" not in combined
    assert "https://example.org/api/profile?" in combined


