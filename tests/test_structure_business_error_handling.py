import logging
import types

import pytest

from app.models.db import Database
from app.controllers.business.structure_business import StructureBusinessLogic


@pytest.fixture()
def sb_instance():
    # Instantiate default Database (project uses configured DB path in tests)
    db = Database()
    logger = logging.getLogger("test.structure_business")
    return StructureBusinessLogic(db, logger=logger)


def test_set_top_panels_controller_injection_attribute_errors_raises_value_error(sb_instance):
    sb = sb_instance

    class BadAssign:
        def __init__(self):
            # allow other attrs
            self.ok = True

        def __setattr__(self, name, value):
            if name == "top_panels":
                raise AttributeError("inject fail")
            return super().__setattr__(name, value)

    sb.async_operations = BadAssign()
    sb._async_handlers = BadAssign()

    with pytest.raises(ValueError) as ei:
        sb.set_top_panels_controller(object())

    msg = str(ei.value)
    assert "Failed to inject TopPanelsController" in msg
    assert "AsyncOperations" in msg
    assert "AsyncSignalHandlers" in msg


def test_set_current_sphere_handles_bad_switch_token_and_sets_suppress_flag(sb_instance):
    sb = sb_instance
    sb._switch_token = "bad"
    sb.set_current_sphere(123)
    assert getattr(sb, "_suppress_category_restore_once", False) is True


def test_on_structure_loaded_warm_cache_deferred_and_preload_errors_logged(monkeypatch, sb_instance, caplog):
    sb = sb_instance

    # Force immediate invocation of QTimer.singleShot
    from app.controllers.business import structure_business as sbm

    class DummyTimer:
        @staticmethod
        def singleShot(_delay, func):
            func()

    monkeypatch.setattr(sbm, "QTimer", DummyTimer)

    # 1) Make deferred warmup raise -> should log debug
    def bad_get_target_section_id(**_kwargs):
        raise RuntimeError("boom")

    sb.utility_service.get_target_section_id = bad_get_target_section_id  # type: ignore

    # 2) Make preload raise -> should log debug
    class BadOps:
        def load_categories_async(self, *_a, **_k):
            raise RuntimeError("preload boom")

    sb.async_operations = BadOps()

    # Patch app_config UI limits used in preload branch
    class DummyUI:
        def get_preload_categories_limit(self):
            return 1

        def get_preload_delay_step_ms(self):
            return 0

    dummy_app_config = types.SimpleNamespace(ui=DummyUI())
    # structure_business imports app_config via 'from app.config_data import app_config'
    import app.config_data as config_module
    monkeypatch.setattr(config_module, "app_config", dummy_app_config)

    # Prepare payload with one section (id valid) and no categories to force deferred, then preload
    payload = [{"id": 10, "categories": []}]

    # Capture logs from the specific logger used by StructureBusinessLogic
    caplog.set_level("DEBUG", logger=sb.logger.name)
    # Ensure sphere_id is valid so handler does not return early
    sb.current_sphere_id = 1
    sb._on_structure_loaded_warm_cache(payload)

    msgs = [rec.message for rec in caplog.records]
    assert any("Deferred warm cache failed" in m for m in msgs)
    assert any("Preload categories failed" in m for m in msgs)
