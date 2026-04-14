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
