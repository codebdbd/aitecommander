from __future__ import annotations

import dbm
import os
import shutil
import shelve
import unittest
from unittest.mock import patch

from app.utils.links.parser import fetcher
from app.utils.links.parser.domain import base_domain
from app.utils.links.parser.favicon_cache import _file_lock, _open_shelve_with_recovery
from app.utils.links.parser.icon_fallback import (
    clear_domain_failed,
    is_domain_failed,
    mark_domain_failed,
)
from app.utils.links.parser.http_client import _is_fatal_exception, http_request
from app.utils.links.parser.icon_downloader import IconDownloader


class _DummyConfig:
    HTML_FETCH_TIMEOUT = 1.0
    ICON_HTML_TIMEOUT = 1.0


class TestFaviconFetcherNegativeHostCache(unittest.TestCase):
    def setUp(self) -> None:
        fetcher._HOST_FAILURES.clear()

    def tearDown(self) -> None:
        fetcher._HOST_FAILURES.clear()

    def test_repeated_server_failure_short_circuits_before_http(self) -> None:
        config = _DummyConfig()

        with (
            self.assertLogs("favicon_parser", level="INFO") as logs_cm,
            patch(
                "app.utils.links.parser.fetcher.read_cache",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.fetcher.write_cache",
            ) as write_cache_mock,
            patch(
                "app.utils.links.parser.fetcher.resolve_icon_for_link",
                return_value="/default/web.png",
            ),
            patch(
                "app.utils.links.parser.fetcher._fetch_and_parse_html",
                return_value=(None, 503),
            ) as fetch_html_mock,
            patch(
                "app.utils.links.parser.fetcher._resolve_icon_sync",
                return_value=None,
            ),
        ):
            first = fetcher.fetch_web_link_info("https://bad.example.com/a", config)
            second = fetcher.fetch_web_link_info("https://bad.example.com/b", config)

        self.assertEqual("/default/web.png", first["icon"])
        self.assertEqual("/default/web.png", second["icon"])
        self.assertEqual(1, fetch_html_mock.call_count)
        self.assertEqual(2, write_cache_mock.call_count)
        self.assertTrue(
            any("[fetch][host_negative] hit host=example.com" in msg for msg in logs_cm.output)
        )

    def test_opaque_unreachable_html_does_not_poison_host(self) -> None:
        config = _DummyConfig()

        with (
            self.assertLogs("favicon_parser", level="INFO") as logs_cm,
            patch(
                "app.utils.links.parser.fetcher.read_cache",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.fetcher.write_cache",
            ) as write_cache_mock,
            patch(
                "app.utils.links.parser.fetcher.resolve_icon_for_link",
                return_value="/default/web.png",
            ),
            patch(
                "app.utils.links.parser.fetcher.http_request",
                return_value=None,
            ) as http_request_mock,
            patch(
                "app.utils.links.parser.fetcher._resolve_icon_sync",
                return_value=None,
            ),
        ):
            first = fetcher.fetch_web_link_info("https://bad.example.com/a", config)
            second = fetcher.fetch_web_link_info("https://bad.example.com/b", config)

        self.assertEqual("/default/web.png", first["icon"])
        self.assertEqual("/default/web.png", second["icon"])
        self.assertEqual(2, http_request_mock.call_count)
        self.assertEqual(2, write_cache_mock.call_count)
        self.assertTrue(
            any("[fetch][host_negative] skip_mark_unknown host=example.com status=None" in msg for msg in logs_cm.output)
        )

    def test_successful_fetch_clears_host_failure_marker(self) -> None:
        config = _DummyConfig()
        fetcher._mark_host_temporarily_unreachable("example.com")

        with (
            patch(
                "app.utils.links.parser.fetcher.read_cache",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.fetcher.resolve_icon_for_link",
                return_value="/default/web.png",
            ),
            patch(
                "app.utils.links.parser.fetcher._fetch_and_parse_html",
                return_value=object(),
            ),
            patch(
                "app.utils.links.parser.fetcher.get_title",
                return_value="Title",
            ),
            patch(
                "app.utils.links.parser.fetcher._resolve_icon_sync",
                return_value=None,
            ),
            patch("app.utils.links.parser.fetcher.write_cache"),
        ):
            fetcher.fetch_web_link_info("https://good.example.com/a", config, force_refresh=True)

        self.assertFalse(fetcher._is_host_temporarily_unreachable("example.com"))

    def test_deferred_icon_task_skips_host_marked_unreachable(self) -> None:
        config = _DummyConfig()
        fetcher._mark_host_temporarily_unreachable("example.com")
        task = fetcher._create_icon_resolve_task(
            soup=None,
            url="https://bad.example.com/a",
            title="",
            config=config,
            on_icon_ready=None,
        )

        with patch(
            "app.utils.links.parser.fetcher.pick_icon_parallel",
        ) as pick_icon_mock:
            task.run()

        pick_icon_mock.assert_not_called()

    def test_perf_breakdown_log_for_deferred_html_title_path(self) -> None:
        config = _DummyConfig()

        with (
            self.assertLogs("favicon_parser", level="INFO") as logs_cm,
            patch(
                "app.utils.links.parser.fetcher.read_cache",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.fetcher.resolve_icon_for_link",
                return_value="/default/web.png",
            ),
            patch(
                "app.utils.links.parser.fetcher._fetch_and_parse_html",
                return_value=object(),
            ),
            patch(
                "app.utils.links.parser.fetcher.get_title",
                return_value="Title",
            ),
            patch(
                "app.utils.links.parser.fetcher.get_task_scheduler",
            ) as scheduler_mock,
            patch("app.utils.links.parser.fetcher.write_cache"),
        ):
            scheduler_mock.return_value.submit_task.return_value = None
            result = fetcher.fetch_web_link_info(
                "https://example.com/a",
                config,
                defer_icon=True,
            )

        self.assertEqual("Title", result["title"])
        self.assertTrue(
            any(
                "[Perf] fetch_web_link_info url=https://example.com/a source=html_title_deferred_icon"
                in msg
                for msg in logs_cm.output
            )
        )

    def test_unreachable_html_schedules_domain_favicon_fallback_when_deferred(self) -> None:
        config = _DummyConfig()

        with (
            patch(
                "app.utils.links.parser.fetcher.read_cache",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.fetcher.resolve_icon_for_link",
                return_value="/default/web.png",
            ),
            patch(
                "app.utils.links.parser.fetcher._fetch_and_parse_html",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.fetcher.get_task_scheduler",
            ) as scheduler_mock,
            patch("app.utils.links.parser.fetcher.write_cache"),
        ):
            result = fetcher.fetch_web_link_info(
                "https://bad.example.com/a",
                config,
                defer_icon=True,
            )

        self.assertEqual("bad.example.com", result["title"])
        scheduler_mock.return_value.submit_task.assert_called_once()

    def test_unreachable_html_full_icon_pipeline_runs_after_direct_favicon_miss(self) -> None:
        config = _DummyConfig()

        with (
            patch(
                "app.utils.links.parser.fetcher.save_icon",
                return_value=None,
            ) as save_icon_mock,
            patch(
                "app.utils.links.parser.fetcher.pick_icon_parallel",
                return_value="/icons/google-fallback.png",
            ) as pick_icon_mock,
        ):
            icon = fetcher._try_direct_favicon_on_block(
                "https://bad.example.com/a",
                "example.com",
                config,
                force_refresh=False,
            )

        self.assertEqual("/icons/google-fallback.png", icon)
        self.assertEqual(3, save_icon_mock.call_count)
        pick_icon_mock.assert_called_once()

    def test_negative_cache_entry_is_bypassed_and_refetched(self) -> None:
        config = _DummyConfig()

        with (
            self.assertLogs("favicon_parser", level="INFO") as logs_cm,
            patch(
                "app.utils.links.parser.fetcher.read_cache",
                return_value={
                    "url": "https://example.com/a",
                    "title": "",
                    "icon": "/default/web.png",
                },
            ),
            patch(
                "app.utils.links.parser.fetcher.resolve_icon_for_link",
                return_value="/default/web.png",
            ),
            patch(
                "app.utils.links.parser.fetcher._fetch_and_parse_html",
                return_value=object(),
            ) as fetch_html_mock,
            patch(
                "app.utils.links.parser.fetcher.get_title",
                return_value="Recovered Title",
            ),
            patch(
                "app.utils.links.parser.fetcher._resolve_icon_sync",
                return_value=None,
            ),
            patch("app.utils.links.parser.fetcher.write_cache"),
        ):
            result = fetcher.fetch_web_link_info(
                "https://example.com/a",
                config,
            )

        self.assertEqual("Recovered Title", result["title"])
        fetch_html_mock.assert_called_once()
        self.assertTrue(
            any("[cache] BYPASS_EMPTY_TITLE https://example.com/a" in msg for msg in logs_cm.output)
        )

class TestFaviconCacheLockFallback(unittest.TestCase):
    def test_file_lock_yields_when_portalocker_backend_missing(self) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "portalocker":
                raise ImportError("portalocker unavailable")
            return real_import(name, globals, locals, fromlist, level)

        with (
            self.assertLogs("favicon_parser", level="WARNING") as logs_cm,
            patch("app.utils.links.parser.favicon_cache._get_lock_backend", return_value="portalocker"),
            patch("builtins.__import__", side_effect=_fake_import),
        ):
            entered = False
            with _file_lock("dummy.lock"):
                entered = True

        self.assertTrue(entered)
        self.assertTrue(
            any("proceeding without interprocess lock" in msg for msg in logs_cm.output)
        )

    def test_file_lock_yields_when_filelock_backend_missing(self) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "filelock":
                raise ImportError("filelock unavailable")
            return real_import(name, globals, locals, fromlist, level)

        with (
            self.assertLogs("favicon_parser", level="WARNING") as logs_cm,
            patch(
                "app.utils.links.parser.favicon_cache._get_lock_backend",
                return_value="filelock",
            ),
            patch("builtins.__import__", side_effect=_fake_import),
        ):
            entered = False
            with _file_lock("dummy.lock"):
                entered = True

        self.assertTrue(entered)
        self.assertTrue(
            any("proceeding without interprocess lock" in msg for msg in logs_cm.output)
        )

    def test_file_lock_yields_when_filelock_times_out(self) -> None:
        import builtins

        real_import = builtins.__import__

        class _FakeTimeout(Exception):
            pass

        class _FakeFileLock:
            def __init__(self, _path: str) -> None:
                self.released = False

            def acquire(self, timeout: float = 0.0) -> None:
                raise _FakeTimeout(f"timeout={timeout}")

            def release(self) -> None:
                self.released = True

        class _FakeFileLockModule:
            FileLock = _FakeFileLock
            Timeout = _FakeTimeout

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "filelock":
                return _FakeFileLockModule()
            return real_import(name, globals, locals, fromlist, level)

        with (
            self.assertLogs("favicon_parser", level="WARNING") as logs_cm,
            patch(
                "app.utils.links.parser.favicon_cache._get_lock_backend",
                return_value="filelock",
            ),
            patch("builtins.__import__", side_effect=_fake_import),
        ):
            entered = False
            with _file_lock("dummy.lock", timeout=0.25):
                entered = True

        self.assertTrue(entered)
        self.assertTrue(
            any("favicon lock timeout(filelock)" in msg for msg in logs_cm.output)
        )


class TestFaviconCacheRecovery(unittest.TestCase):
    def test_open_shelve_recreates_unreadable_db(self) -> None:
        tmpdir = os.path.join(os.getcwd(), "tests", "_tmp_favicon_cache")
        shutil.rmtree(tmpdir, ignore_errors=True)
        os.makedirs(tmpdir, exist_ok=True)
        try:
            path = os.path.join(tmpdir, "favicon_cache.db")
            with shelve.open(path, flag="n") as original_db:
                original_db["stale"] = {"title": "Old"}

            real_shelve_open = shelve.open
            call_count = 0
            dbm_error_cls = dbm.error[0] if isinstance(dbm.error, tuple) else dbm.error

            def _fake_open(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise dbm_error_cls("db type could not be determined")
                return real_shelve_open(*args, **kwargs)

            with self.assertLogs("favicon_parser", level="WARNING") as logs_cm:
                with patch(
                    "app.utils.links.parser.favicon_cache.shelve.open",
                    side_effect=_fake_open,
                ) as patched_open:
                    with _open_shelve_with_recovery(path) as db:
                        db["url"] = {"title": "Recovered"}

            with shelve.open(path) as db:
                self.assertEqual("Recovered", db["url"]["title"])

            self.assertEqual(2, call_count)
            self.assertEqual("n", patched_open.call_args_list[1].kwargs.get("flag"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertTrue(
            any("unreadable cache db" in msg for msg in logs_cm.output)
        )


class TestHttpClientFatalDns(unittest.TestCase):
    def test_name_resolution_error_is_fatal(self) -> None:
        err = Exception(
            "HTTPSConnectionPool(host='bad.example.com', port=443): "
            "Caused by NameResolutionError(\"Failed to resolve 'bad.example.com' ([Errno 11001] getaddrinfo failed)\")"
        )
        self.assertTrue(_is_fatal_exception(err))

    def test_ssl_error_is_not_fatal(self) -> None:
        err = Exception(
            "HTTPSConnectionPool(host='example.com', port=443): "
            "Caused by SSLError(SSLCertVerificationError(1, "
            "'[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed'))"
        )
        self.assertFalse(_is_fatal_exception(err))

    def test_retries_override_uses_temp_session_path(self) -> None:
        class _Resp:
            status_code = 200
            def raise_for_status(self):
                return None

        class _Session:
            def __init__(self):
                self.request_calls = []
                self.closed = False
            def request(self, method, url, **kwargs):
                self.request_calls.append((method, url, kwargs))
                return _Resp()
            def close(self):
                self.closed = True
            def mount(self, *args, **kwargs):
                return None

        temp_session = _Session()
        shared_session = _Session()
        config = _DummyConfig()

        with (
            self.assertLogs("favicon_parser", level="DEBUG") as logs_cm,
            patch("app.utils.links.parser.http_client.requests.Session", return_value=temp_session),
            patch("app.utils.links.parser.http_client.get_session", return_value=shared_session),
            patch("app.utils.links.parser.http_client.get_cloudscraper", return_value=None),
        ):
            resp = http_request("https://example.com", config, retries=0)

        self.assertIsNotNone(resp)
        self.assertEqual(1, len(temp_session.request_calls))
        self.assertTrue(temp_session.closed)
        self.assertEqual(0, len(shared_session.request_calls))
        self.assertTrue(
            any("retry_mode=temp:0" in msg for msg in logs_cm.output)
        )

    def test_http_request_can_use_session_before_cloudscraper(self) -> None:
        call_order = []

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

        class _Session:
            def request(self, method, url, **kwargs):
                call_order.append(("session", method, url))
                return _Resp()

            def mount(self, *args, **kwargs):
                return None

        config = _DummyConfig()
        temp_session = _Session()

        with (
            patch("app.utils.links.parser.http_client.requests.Session", return_value=temp_session),
            patch(
                "app.utils.links.parser.http_client._try_cloudscraper",
                side_effect=lambda *args, **kwargs: call_order.append(("cloud",)) or None,
            ),
        ):
            resp = http_request(
                "https://example.com",
                config,
                retries=0,
                prefer_cloudscraper_primary=False,
            )

        self.assertIsNotNone(resp)
        self.assertEqual(("session", "GET", "https://example.com"), call_order[0])

    def test_fatal_403_does_not_continue_to_cloudscraper_attempt(self) -> None:
        class _Resp:
            status_code = 403

            def raise_for_status(self):
                import requests

                raise requests.exceptions.HTTPError("403", response=self)

        class _Session:
            def request(self, method, url, **kwargs):
                return _Resp()

            def close(self):
                return None

            def mount(self, *args, **kwargs):
                return None

        config = _DummyConfig()

        with (
            patch("app.utils.links.parser.http_client.requests.Session", return_value=_Session()),
            patch(
                "app.utils.links.parser.http_client._attempt_cloud_primary",
                side_effect=AssertionError("cloudscraper path must not be attempted after fatal 403"),
            ),
        ):
            resp = http_request(
                "https://example.com/forbidden",
                config,
                retries=0,
                prefer_cloudscraper_primary=False,
            )

        self.assertIsNone(resp)

    def test_ssl_error_retries_with_insecure_session(self) -> None:
        import requests

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

        class _Session:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("verify", True) is False:
                    return _Resp()
                raise requests.exceptions.SSLError("certificate verify failed")

            def close(self):
                return None

            def mount(self, *args, **kwargs):
                return None

        config = _DummyConfig()

        with patch(
            "app.utils.links.parser.http_client.requests.Session",
            side_effect=lambda: _Session(),
        ):
            resp = http_request(
                "https://example.com/ssl",
                config,
                retries=0,
                prefer_cloudscraper_primary=False,
            )

        self.assertIsNotNone(resp)


class TestDomainNormalization(unittest.TestCase):
    def test_base_domain_uses_non_deprecated_tldextract_field(self) -> None:
        self.assertEqual("example.co.uk", base_domain("www.example.co.uk"))

    def test_failed_domain_cache_is_shared_across_www_variants(self) -> None:
        mark_domain_failed("https://www.example.com/path", 403)
        self.assertTrue(is_domain_failed("https://example.com/other"))
        self.assertTrue(is_domain_failed("https://sub.example.com/else"))

    def test_clear_failed_domain_removes_shared_cache_entry(self) -> None:
        mark_domain_failed("https://www.example.com/path", 403)
        clear_domain_failed("https://example.com/icon.png")
        self.assertFalse(is_domain_failed("https://sub.example.com/else"))

    def test_icon_404_does_not_mark_domain_failed(self) -> None:
        downloader = IconDownloader(_DummyConfig())
        clear_domain_failed("https://example.com/seed")

        class _Resp:
            status_code = 404

        handled, path = downloader._handle_response_status(
            _Resp(),
            "example.com",
            "https://example.com/favicon.ico",
            False,
        )

        self.assertTrue(handled)
        self.assertIsNone(path)
        self.assertFalse(is_domain_failed("https://example.com/other"))


class TestIconDownloaderHttpPolicy(unittest.TestCase):
    def test_icon_fetch_uses_short_session_first_policy(self) -> None:
        downloader = IconDownloader(_DummyConfig())

        class _Resp:
            status_code = 200
            headers = {}

        with patch(
            "app.utils.links.parser.icon_downloader.http_request",
            return_value=_Resp(),
        ) as http_request_mock:
            resp = downloader._fetch_icon_response(
                "https://example.com/favicon.png",
                "example.com",
                {},
                False,
            )

        self.assertIsNotNone(resp)
        http_request_mock.assert_called_once()
        _, kwargs = http_request_mock.call_args
        self.assertEqual(0, kwargs["retries"])
        self.assertFalse(kwargs["prefer_cloudscraper_primary"])


if __name__ == "__main__":
    unittest.main()
