import types
import pytest

from app.utils.browser.import_browser_html import BrowserBookmarksImporter


def make_html_with_icon(tmp_path, base64_data: str) -> str:
    html = f"""
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3>Folder</H3>
    <DL><p>
        <DT><A HREF="https://example.com" ICON="data:image/png;base64,{base64_data}">Example</A>
    </DL><p>
</DL><p>
"""
    p = tmp_path / "bookmarks.html"
    p.write_text(html, encoding="utf-8")
    return str(p)


def test_parse_bookmarks_oserror_raises(tmp_path):
    importer = BrowserBookmarksImporter()
    # path that does not exist
    missing = tmp_path / "no_such_file.html"
    with pytest.raises(OSError):
        importer.parse_bookmarks(str(missing))


def test_parse_bookmarks_invalid_icon_base64_logs_debug(tmp_path, caplog, monkeypatch):
    importer = BrowserBookmarksImporter()
    path = make_html_with_icon(tmp_path, base64_data="INVALID")

    # Ensure icons directory points to tmp_path so file doesn't preexist
    import app.utils.browser.import_browser_html as ibm

    class DummyPaths:
        def get_link_icons_dir(self):
            return tmp_path

    dummy_app_config = types.SimpleNamespace(paths=DummyPaths())
    monkeypatch.setattr(ibm, "app_config", dummy_app_config)

    caplog.set_level("DEBUG", logger=importer.__class__.__module__)
    categories = importer.parse_bookmarks(path)

    # Should parse without raising and produce at least one link
    assert categories
    total = sum(len(v) for v in categories.values())
    assert total == 1

    # We expect a debug from save_icon_from_base64 failure path
    msgs = [rec.message for rec in caplog.records]
    assert any("save_icon_from_base64 failed" in m for m in msgs)


def test_sync_to_db_resolve_icon_warning_and_bulk_create_exception(monkeypatch, caplog):
    importer = BrowserBookmarksImporter()

    # Force resolve_icon_for_link to raise; patch the symbol used in module under test
    import app.utils.browser.import_browser_html as ibm

    def bad_resolve(_):
        raise ValueError("resolver boom")

    monkeypatch.setattr(ibm, "resolve_icon_for_link", bad_resolve)

    # Fake structure business that raises on bulk create
    class SB:
        def __init__(self):
            self.calls = []

        def get_categories(self, section_id):
            # before bulk and after bulk
            return []

        def create_categories_bulk(self, items):
            raise RuntimeError("bulk boom")

    sb = SB()

    caplog.set_level("DEBUG", logger=importer.__class__.__module__)
    ok, msg, added = importer.sync_to_db({"Folder": []}, section_id=1, structure_business_logic=sb)
    assert ok is True
    assert added == 0

    msgs = [rec.message for rec in caplog.records]
    assert any("resolve_icon_for_link failed" in m for m in msgs)
    assert any("Пакетное создание категорий завершилось ошибкой" in m for m in msgs)


def test_sync_to_db_add_link_exception_logged(caplog):
    importer = BrowserBookmarksImporter()

    class LinksBL:
        def get_links(self, category_id):
            return []

        def create_link_for_import(self, link_data):
            raise RuntimeError("create boom")

    class SB:
        def __init__(self):
            self.links_business = LinksBL()

        def get_categories(self, section_id):
            return [{"id": 1, "name": "Folder"}]

    sb = SB()

    caplog.set_level("DEBUG", logger=importer.__class__.__module__)
    ok, msg, added = importer.sync_to_db({"Folder": [{"name": "N", "url": "U"}]}, section_id=1, structure_business_logic=sb)
    assert ok is True
    assert added == 0

    msgs = [rec.message for rec in caplog.records]
    assert any("Не удалось добавить ссылку" in m for m in msgs)
