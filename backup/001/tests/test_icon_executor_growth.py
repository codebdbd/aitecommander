from concurrent.futures import ThreadPoolExecutor

from app.utils.links.parser import icon_downloader as mod
from app.config_data import app_config


def test_executor_initial_creation_and_growth(monkeypatch):
    # Ensure clean state
    mod._shutdown_icon_executor(wait=False)
    assert mod._ICON_EXECUTOR is None
    assert mod._ICON_EXECUTOR_SIZE == 0

    # Limit max workers via config
    monkeypatch.setattr(app_config, "ICON_MAX_WORKERS", 4, raising=False)

    # First creation with hint=2
    ex1 = mod._get_icon_executor(2)
    assert isinstance(ex1, ThreadPoolExecutor)
    assert mod._ICON_EXECUTOR is ex1
    assert mod._ICON_EXECUTOR_SIZE == 2

    # Request smaller or equal shouldn't recreate
    ex_same = mod._get_icon_executor(1)
    assert ex_same is ex1
    assert mod._ICON_EXECUTOR_SIZE == 2

    # Growth with hint=3 (<= limit 4)
    ex2 = mod._get_icon_executor(3)
    assert isinstance(ex2, ThreadPoolExecutor)
    assert mod._ICON_EXECUTOR is ex2
    assert mod._ICON_EXECUTOR_SIZE == 3
    assert ex2 is not ex1

    # Growth capped by config (hint=10 -> 4)
    ex3 = mod._get_icon_executor(10)
    assert mod._ICON_EXECUTOR is ex3
    assert mod._ICON_EXECUTOR_SIZE == 4
    assert ex3 is not ex2

    # Cleanup
    mod._shutdown_icon_executor(wait=False)
    assert mod._ICON_EXECUTOR is None
    mod._ICON_EXECUTOR_SIZE = 0
