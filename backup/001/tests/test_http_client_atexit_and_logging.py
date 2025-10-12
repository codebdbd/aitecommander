import importlib



def test_get_session_atexit_register_once(monkeypatch, caplog):
    # Reload module to reset globals
    from app.utils.links.parser import http_client as hc
    importlib.reload(hc)

    calls = []

    def fake_register(func):
        calls.append(func)
        return func

    monkeypatch.setattr(hc.atexit, "register", fake_register)

    # First call should register cleanup
    s1 = hc.get_session()
    assert s1 is not None
    # Second call should NOT register again
    s2 = hc.get_session()
    assert s2 is s1

    assert len(calls) == 1
    # Ensure registered function is the module's cleanup
    assert calls[0].__name__ == hc._cleanup_thread_local_session.__name__


def test_get_session_headers_update_error_logged_warning(monkeypatch, caplog):
    from app.utils.links.parser import http_client as hc
    importlib.reload(hc)

    class DummySession:
        def __init__(self):
            class H:
                def update(self_inner, *_args, **_kwargs):
                    raise TypeError("boom")

            self.headers = H()

    monkeypatch.setattr(hc.requests, "Session", DummySession)

    caplog.set_level("WARNING")
    hc.get_session()

    assert any(
        "failed to update default session headers" in rec.message
        for rec in caplog.records
    ), "Expected warning about failed headers update"


def test_http_request_cloudscraper_requestexception_fallback_to_session(monkeypatch, caplog):
    from app.utils.links.parser import http_client as hc
    importlib.reload(hc)

    class DummyResp:
        status_code = 200

        def raise_for_status(self):
            return None

    class DummyScraper:
        def request(self, *args, **kwargs):
            from requests.exceptions import RequestException

            raise RequestException("cf fail")

    class DummySession:
        def request(self, *args, **kwargs):
            return DummyResp()

    # Enable cf and make cloudscraper fail with RequestException
    monkeypatch.setattr(hc, "get_cloudscraper", lambda: DummyScraper())
    monkeypatch.setattr(hc, "get_session", lambda: DummySession())

    class Cfg:
        ENABLE_CLOUDSCRAPER_FALLBACK = True
        USER_AGENT = "x"
        TIMEOUT = 1

    caplog.set_level("WARNING")

    resp = hc.http_request("http://example.com", Cfg)
    assert isinstance(resp, DummyResp)

    assert any(
        "Cloudscraper failed" in rec.message for rec in caplog.records
    ), "Expected warning about cloudscraper failure"
