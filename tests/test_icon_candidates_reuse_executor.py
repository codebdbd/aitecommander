import types
from concurrent.futures import Future

from app.utils.links.parser import icon_candidates as ic


def _soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


class FakeExecutor:
    def __init__(self):
        self.submit_calls = []

    def submit(self, func, *args):
        # Record call
        self.submit_calls.append((func, *args))
        f: Future = Future()
        if len(args) == 0:
            # Coordinator submit: execute synchronously
            func()
            f.set_result(None)
            return f
        # Per-URL submit: return ready future with deterministic URL list
        (m_url,) = args
        icon_url = m_url.rstrip("/").rsplit("/", 1)[0] + "/icons/from-" + m_url.rsplit("/", 1)[-1]
        f.set_result([icon_url])
        return f


def test_handle_manifests_reuses_global_executor(monkeypatch):
    # HTML with two manifest links to ensure multiple submits
    html = """
    <html><head>
      <link rel=\"manifest\" href=\"/a.webmanifest\">
      <link rel=\"manifest\" href=\"/b.webmanifest\">
    </head></html>
    """
    soup = _soup(html)
    base_url = "https://example.com/page"

    fake_exec = FakeExecutor()
    monkeypatch.setattr(ic, "_get_manifest_executor", lambda: fake_exec)

    # Make the coordinator thread run synchronously
    class DummyThread:
        def __init__(self, target, name=None, daemon=None):
            self._target = target
        def start(self):
            self._target()
    monkeypatch.setattr(ic.threading, "Thread", DummyThread)

    captured = {}
    def on_manifest(urls):
        captured["urls"] = list(urls)

    # Ensure no real HTTP is performed even if code path changes
    monkeypatch.setattr(ic, "http_request", lambda *a, **k: types.SimpleNamespace(ok=False, text="{}"))

    ic.find_favicon_candidates(
        soup,
        base_url,
        config=types.SimpleNamespace(),
        on_manifest_icons=on_manifest,
        use_external=False,
    )

    # submit called exactly for each manifest URL (2)
    assert len(fake_exec.submit_calls) == 2
    # And callback received both synthesized icon URLs
    assert any("/icons/from-a.webmanifest" in u for u in captured.get("urls", []))
    assert any("/icons/from-b.webmanifest" in u for u in captured.get("urls", []))
