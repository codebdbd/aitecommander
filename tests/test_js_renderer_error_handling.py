import importlib



def reload_js():
    from app.utils.links.parser import js_renderer as jsr

    importlib.reload(jsr)
    return jsr


def test_render_returns_none_when_playwright_missing(monkeypatch, caplog):
    jsr = reload_js()

    # Simulate missing playwright
    monkeypatch.setattr(jsr, "sync_playwright", None)

    class Cfg:
        PLAYWRIGHT_HEADLESS = True

    caplog.set_level("WARNING")
    html = jsr.render_html("https://example.com", Cfg())
    assert html is None
    assert any("Playwright is not installed" in rec.message for rec in caplog.records)


def test_init_logs_and_returns_false_on_runtime_error(monkeypatch, caplog):
    jsr = reload_js()

    class DummyPL:
        def start(self):  # pragma: no cover
            raise RuntimeError("boom")

    monkeypatch.setattr(jsr, "sync_playwright", lambda: DummyPL())

    class Cfg:
        PLAYWRIGHT_HEADLESS = True

    caplog.set_level("WARNING")
    ok = jsr._init_browser(Cfg())
    assert ok is False
    assert any("Playwright init failed" in rec.message for rec in caplog.records)


def test_render_logs_on_error_and_returns_none(monkeypatch, caplog):
    jsr = reload_js()

    # Fake successful init
    class Page:
        def set_default_navigation_timeout(self, *_):
            pass

        def set_default_timeout(self, *_):
            pass

        def goto(self, *_a, **_k):
            raise RuntimeError("nav fail")

        def wait_for_timeout(self, *_):
            pass

        def content(self):  # pragma: no cover
            return "<html/>"

        def close(self):
            pass

    class Ctx:
        def new_page(self):
            return Page()

        def route(self, *_a, **_k):
            pass

        def close(self):
            pass

    class Browser:
        def new_context(self, *_a, **_k):
            return Ctx()

        def close(self):
            pass

    class PL:
        class chromium:
            @staticmethod
            def launch(**_kwargs):
                return Browser()

        def start(self):
            return self

        def stop(self):
            pass

    monkeypatch.setattr(jsr, "sync_playwright", lambda: PL())

    class Cfg:
        PLAYWRIGHT_HEADLESS = True
        JS_RENDER_MAX_WAIT_MS = 1

    assert jsr._init_browser(Cfg()) is True

    caplog.set_level("WARNING")
    out = jsr.render_html("https://example.com", Cfg())
    assert out is None
    # Should log render failure
    assert any("Playwright render failed" in rec.message for rec in caplog.records)
