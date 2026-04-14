from __future__ import annotations

from types import SimpleNamespace

from app.controllers.business.structure_business import StructureBusinessLogic


class _CacheManagerStub:
    def __init__(self):
        self.store = {}
        self.invalidate_calls = 0

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def invalidate(self):
        self.invalidate_calls += 1
        self.store.clear()


def _build_business_stub() -> StructureBusinessLogic:
    business = StructureBusinessLogic.__new__(StructureBusinessLogic)
    business._structure_mutation_generation = 0
    business._structure_cache_ready = True
    business._structure_dirty_since_preload = False
    business._cached_spheres = []
    business._cached_sections = {}
    business._cached_categories = {}
    business.cache_manager = _CacheManagerStub()
    business._schedule_preload_structure_async = lambda **kwargs: None
    return business


def test_category_mutation_preserves_primed_section_cache():
    business = _build_business_stub()
    payload = [{"id": 444, "section_id": 514, "name": "new"}]
    business._cached_categories[514] = [dict(item) for item in payload]
    business.cache_manager.set("categories_514", [dict(item) for item in payload])

    business._handle_structure_mutation("category", 514, {"id": 444, "section_id": 514})

    assert business.get_cached_categories(514) == payload
    assert business.cache_manager.get("categories_514") == payload


def test_get_cached_categories_returns_section_cache_when_structure_not_ready():
    business = _build_business_stub()
    business._structure_cache_ready = False
    business._cached_categories[514] = [{"id": 444, "section_id": 514, "name": "new"}]

    assert business.get_cached_categories(514) == [
        {"id": 444, "section_id": 514, "name": "new"}
    ]
