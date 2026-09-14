from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.models.workers.bad_url_check_worker import BadUrlCheckWorker


def _worker() -> BadUrlCheckWorker:
    db = SimpleNamespace(connection=sqlite3.connect(":memory:"))
    return BadUrlCheckWorker(db, timeout=1, check_ssl=True)


def test_verify_404_with_get_returns_unreachable_for_connection_refused() -> None:
    worker = _worker()
    error = URLError(ConnectionRefusedError(10061, "refused"))

    with patch("urllib.request.urlopen", side_effect=[error, error]):
        reachable, reason = worker._verify_404_with_get("https://example.com/missing")

    assert reachable is False
    assert reason == worker.ERROR_UNREACHABLE


def test_verify_404_with_get_returns_404_for_http_404() -> None:
    worker = _worker()
    error = HTTPError(
        "https://example.com/missing",
        404,
        "Not Found",
        hdrs=None,
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=error):
        reachable, reason = worker._verify_404_with_get("https://example.com/missing")

    assert reachable is False
    assert reason == worker.ERROR_404


def test_dns_check_handles_ipv4_ipv6_and_strips_brackets() -> None:
    worker = _worker()
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]) as getaddrinfo_mock:
        assert worker._dns_check("127.0.0.1") is True
        assert worker._dns_check("[::1]") is True
        assert worker._dns_check("::1") is True
        assert worker._dns_check("example.com") is True

    # Check that brackets were stripped for "[::1]"
    called_hosts = [call[0][0] for call in getaddrinfo_mock.call_args_list]
    assert "::1" in called_hosts
    assert "[::1]" not in called_hosts


def test_check_url_uses_hostname_for_ports_and_ipv6() -> None:
    worker = _worker()

    with (
        patch.object(worker, "_dns_check", return_value=True) as dns_mock,
        patch.object(worker, "_head_check_and_followups", return_value=(True, "")),
    ):
        # 1. URL with custom port
        ok, err = worker._check_url("https://example.com:8443/dashboard")
        assert ok is True
        dns_mock.assert_called_with("example.com")

        # 2. IPv6 URL with port
        dns_mock.reset_mock()
        ok, err = worker._check_url("http://[2001:db8::1]:8080/status")
        assert ok is True
        dns_mock.assert_called_with("2001:db8::1")

