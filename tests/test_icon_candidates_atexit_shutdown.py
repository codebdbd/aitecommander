import types

from app.utils.links.parser import icon_candidates as ic


def _soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def test_atexit_shutdown_safe_after_manual_shutdown(monkeypatch, capsys):
    # Capture atexit handler to simulate interpreter shutdown later
    captured = {}

    def fake_atexit_register(fn):
        captured["handler"] = fn
        return fn

    monkeypatch.setattr(ic.atexit, "register", fake_atexit_register)

    # Prepare HTML with manifest to force creation of global executor via async path
    html = """
    <html><head>
      <link rel="manifest" href="/site.webmanifest">
    </head></html>
    """
    soup = _soup(html)
    base_url = "https://example.com/"

    # Minimal http_request stub (won't be used by the atexit path)
    def fake_http_request(url, *a, **kw):
        return types.SimpleNamespace(ok=False, text="{}")

    monkeypatch.setattr(ic, "http_request", fake_http_request)

    # Call with async callback to ensure _get_manifest_executor() is used
    ic.find_favicon_candidates(
        soup,
        base_url,
        config=types.SimpleNamespace(),
        on_manifest_icons=lambda urls: None,
        use_external=False,
    )

    # Ensure handler registered
    handler = captured.get("handler")
    assert callable(handler), "atexit handler was not registered"

    # Manually shutdown the global executor
    ic.shutdown_manifest_executor(wait=False, cancel_futures=True)

    # Calling the captured atexit handler must not raise, even after manual shutdown
    handler()

    # And calling it again must also be safe (idempotent)
    handler()

    # No output expected
    out, err = capsys.readouterr()
    assert err == ""
