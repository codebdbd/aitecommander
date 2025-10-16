import types

from app.utils.links.parser import icon_candidates as ic


def test_atexit_handlers_do_not_accumulate_on_recreate(monkeypatch):
    # Track registered and unregistered handlers
    registered = []
    unregistered = []

    def fake_register(fn):
        registered.append(fn)
        return fn  # real atexit.register returns the function

    def fake_unregister(fn):
        unregistered.append(fn)
        try:
            registered.remove(fn)
        except ValueError:
            pass

    monkeypatch.setattr(ic.atexit, "register", fake_register)
    monkeypatch.setattr(ic.atexit, "unregister", fake_unregister)

    # Force creation via async path to ensure executor is used in flow
    html = """
    <html><head>
      <link rel=\"manifest\" href=\"/site.webmanifest\">  
    </head></html>
    """

    def _soup(html: str):
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser")

    soup = _soup(html)
    base_url = "https://example.com/"

    # Stub http_request to avoid network
    monkeypatch.setattr(
        ic, "http_request", lambda *a, **k: types.SimpleNamespace(ok=False, text="{}")
    )

    # Also make coordinator thread run synchronously
    class DummyThread:
        def __init__(self, target, name=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(ic.threading, "Thread", DummyThread)

    # 1st create
    ic.find_favicon_candidates(
        soup,
        base_url,
        config=types.SimpleNamespace(),
        on_manifest_icons=lambda urls: None,
    )
    assert len(registered) == 1

    # shutdown must unregister
    ic.shutdown_manifest_executor()
    assert len(registered) == 0, "Handler must be unregistered after shutdown"

    # 2nd create
    ic.find_favicon_candidates(
        soup,
        base_url,
        config=types.SimpleNamespace(),
        on_manifest_icons=lambda urls: None,
    )
    assert len(registered) == 1, (
        "Exactly one handler should be registered after recreation"
    )

    # Another shutdown leaves no handlers
    ic.shutdown_manifest_executor()
    assert len(registered) == 0
