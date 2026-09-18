from __future__ import annotations

from app.utils.browser.import_browser_html import BrowserBookmarksImporter


class _FakeStructureBusiness:
    def __init__(self) -> None:
        self._categories = [
            {"id": 10, "name": "Ссылки"},
            {"id": 11, "name": "Brand"},
            {"id": 12, "name": "Риск-менеджмент"},
        ]

    def get_categories(self, section_id: int):
        return list(self._categories)

    def create_categories_bulk(self, items):
        return []


class _FakeLinksBusiness:
    def __init__(self) -> None:
        self.last_payload = []

    def create_links_for_import_bulk(self, payload):
        self.last_payload = list(payload or [])
        return len(self.last_payload)


def test_sync_to_db_matches_categories_case_insensitive_and_stripped() -> None:
    importer = BrowserBookmarksImporter()
    structure_business = _FakeStructureBusiness()
    links_business = _FakeLinksBusiness()

    categories = {
        " Ссылки  ": [{"name": "A", "url": "https://a.test"}],
        "brand": [{"name": "B", "url": "https://b.test"}],
        "Риск-менеджмент ": [{"name": "C", "url": "https://c.test"}],
    }

    ok, _msg, stats = importer.sync_to_db(
        categories=categories,
        section_id=1,
        structure_business_logic=structure_business,
        links_business_logic=links_business,
    )

    assert ok is True
    assert stats["added"] == 3
    assert len(links_business.last_payload) == 3
    assert {item["category_id"] for item in links_business.last_payload} == {10, 11, 12}


def test_sync_to_db_truncates_long_name_and_preserves_in_notes() -> None:
    importer = BrowserBookmarksImporter()
    structure_business = _FakeStructureBusiness()
    links_business = _FakeLinksBusiness()

    long_title = "A" * 312
    categories = {
        "Ссылки": [{"name": long_title, "url": "https://example.com/long"}],
    }

    ok, _msg, stats = importer.sync_to_db(
        categories=categories,
        section_id=1,
        structure_business_logic=structure_business,
        links_business_logic=links_business,
    )

    assert ok is True
    assert stats["added"] == 1
    imported_item = links_business.last_payload[0]
    assert len(imported_item["name"]) == 255
    assert imported_item["notes"] == long_title


def test_parse_bookmarks_handles_nested_folders_and_returns_to_parent(tmp_path) -> None:
    importer = BrowserBookmarksImporter()
    html_content = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
    <DT><H3>Bookmarks bar</H3>
    <DL><p>
        <DT><A HREF="https://a.test">Link A</A>
        <DT><H3>Subfolder</H3>
        <DL><p>
            <DT><A HREF="https://sub.test">Link Sub</A>
        </DL><p>
        <DT><A HREF="https://b.test">Link B</A>
    </DL><p>
</DL><p>
"""
    file_path = tmp_path / "bookmarks.html"
    file_path.write_text(html_content, encoding="utf-8")

    parsed = importer.parse_bookmarks(str(file_path))

    assert "Bookmarks bar" in parsed
    assert "Subfolder" in parsed
    assert [link["name"] for link in parsed["Bookmarks bar"]] == ["Link A", "Link B"]
    assert [link["name"] for link in parsed["Subfolder"]] == ["Link Sub"]

