import logging
import types

from app.controllers.business.structure_business import StructureBusinessLogic
from app.controllers.structure_modules.cache_manager import CacheManager
from app.controllers.structure_services.utilities import UtilityService


def _make_business_logic_stub():
    # Создаём "пустой" экземпляр без выполнения __init__ (чтобы избежать тяжёлых зависимостей)
    bl = StructureBusinessLogic.__new__(StructureBusinessLogic)
    # Минимально необходимые атрибуты
    bl.logger = logging.getLogger(__name__)
    bl.current_sphere_id = 1
    bl.cache_manager = CacheManager(logger=bl.logger)
    bl.utility_service = UtilityService()
    # Заглушки для get_sections / get_categories (подменяются в тестах)
    bl.get_sections = types.MethodType(lambda self, sphere_id: [], bl)
    bl.get_categories = types.MethodType(lambda self, section_id: [], bl)
    return bl


def test_warm_cache_sets_first_category_key_when_category_exists(monkeypatch):
    bl = _make_business_logic_stub()

    # Данные: одна секция с одной категорией
    sections = [{"id": 10}]
    categories = {10: [{"id": 100}]}

    bl.get_sections = types.MethodType(lambda self, sid: sections, bl)
    bl.get_categories = types.MethodType(lambda self, sec_id: categories.get(sec_id, []), bl)

    # Шпион на cache_set, простейший cache_get
    set_calls = []

    def spy_set(key, value, *, ttl=None):  # соответствуем сигнатуре CacheManager.set
        set_calls.append((key, value))

    def fake_get(key):
        return None

    bl.cache_manager.set = spy_set  # type: ignore[method-assign]
    bl.cache_manager.get = fake_get  # type: ignore[method-assign]

    # Вызов обработчика прогрева
    StructureBusinessLogic._on_structure_loaded_warm_cache(bl, _payload=[])

    # Проверяем, что записан per-sphere ключ с корректным значением
    assert ("first_category_id:1", 100) in set_calls


def test_warm_cache_sets_none_when_no_categories(monkeypatch):
    bl = _make_business_logic_stub()

    # Данные: секция есть, но без категорий
    sections = [{"id": 11}]
    categories = {11: []}

    bl.get_sections = types.MethodType(lambda self, sid: sections, bl)
    bl.get_categories = types.MethodType(lambda self, sec_id: categories.get(sec_id, []), bl)

    set_calls = []

    def spy_set(key, value, *, ttl=None):
        set_calls.append((key, value))

    def fake_get(key):
        return None

    bl.cache_manager.set = spy_set  # type: ignore[method-assign]
    bl.cache_manager.get = fake_get  # type: ignore[method-assign]

    StructureBusinessLogic._on_structure_loaded_warm_cache(bl, _payload=[])

    # Ожидаем установку None для ключа первой категории, если категорий нет
    assert ("first_category_id:1", None) in set_calls
