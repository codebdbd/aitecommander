import pytest

from app.controllers.ui.links.links_actions import LinksActions


class Dummy:
    pass


def make_actions():
    # links and link_ops are required to be non-None, but not used by share methods
    main = Dummy()
    links = object()
    link_ops = object()
    return LinksActions(main, links, link_ops)


def test__share_returns_false_when_link_missing():
    la = make_actions()

    called = {}

    def handler(name, url):
        called["called"] = True
        return True

    assert la._share(None, handler) is False
    assert not called


def test__share_returns_false_when_url_missing():
    la = make_actions()

    def handler(name, url):  # pragma: no cover - must not be called
        raise AssertionError("handler should not be called")

    assert la._share({"name": "X"}, handler) is False


def test__share_uses_href_when_url_missing_and_returns_handler_result():
    la = make_actions()

    seen = {}

    def handler(name, url):
        seen["name"] = name
        seen["url"] = url
        return True

    link = {"name": "Site", "href": "https://example.com"}
    assert la._share(link, handler) is True
    assert seen == {"name": "Site", "url": "https://example.com"}


def test__share_prefers_url_over_href():
    la = make_actions()

    captured = {}

    def handler(name, url):
        captured["url"] = url
        return True

    link = {"name": "Site", "url": "https://u", "href": "https://h"}
    assert la._share(link, handler) is True
    assert captured["url"] == "https://u"


@pytest.mark.parametrize(
    "method_name, service_attr",
    [
        ("share_via_telegram", "share_via_telegram"),
        ("share_via_whatsapp", "share_via_whatsapp"),
        ("share_via_viber", "share_via_viber"),
        ("share_via_email", "share_via_email"),
        ("share_via_email_client", "share_via_email_client"),
        ("share_via_email_gmail", "share_via_email_gmail"),
        ("share_via_x", "share_via_x"),
        ("share_via_facebook", "share_via_facebook"),
        ("share_via_linkedin", "share_via_linkedin"),
        ("share_via_pinterest", "share_via_pinterest"),
    ],
)
def test_share_methods_delegate_to_service(monkeypatch, method_name, service_attr):
    la = make_actions()

    called = {"args": None}

    # Monkeypatch the service function inside the module under test
    import app.controllers.ui.links.links_actions as mod_links_actions

    def fake_handler(name, url):
        called["args"] = (name, url)
        return True

    monkeypatch.setattr(
        getattr(mod_links_actions, "share_service"), service_attr, fake_handler, raising=True
    )

    link = {"name": "N", "url": "https://u"}
    method = getattr(la, method_name)
    assert method(link) is True
    assert called["args"] == ("N", "https://u")
