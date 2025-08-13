import importlib
import os
import sys
import time
import types
from pathlib import Path

import pytest

# Target module under test
MODULE_PATH = 'app.utils.icon.path_service'


@pytest.fixture(autouse=True)
def reload_module(monkeypatch, tmp_path):
    """Reload the path_service module with a stubbed app_config.
    Each test gets a clean module state and isolated UI icons directory.
    """
    # Build a stub app_config with required attributes
    class PathsStub:
        def __init__(self, ui_dir: Path):
            self._ui = ui_dir
        def get_ui_icons_dir(self) -> Path:
            return self._ui
        # Unused in these tests but referenced in module
        def get_qss_dir(self) -> Path:
            return self._ui
        def get_themes_manifest_path(self) -> Path:
            return self._ui / 'themes.json'
        def get_user_data_dir(self) -> Path:
            return self._ui
        def get_link_icons_dir(self) -> Path:
            return self._ui
        def ensure_user_data_dirs(self):
            os.makedirs(self._ui, exist_ok=True)

    class AppConfigStub:
        def __init__(self, ui_dir: Path):
            self.paths = PathsStub(ui_dir)
            # Configurable knobs
            self.icon_index_ttl = 0.1
            self.icon_negative_cache_ttl = 0.1
            self.icon_negative_cache_ttl_max = 0.2
            self.icon_metrics_report_interval_s = 3600.0
            self.icon_slow_convert_threshold_ms = 1_000.0
        def get_default_icons(self):
            return {"category": "category.png"}
        def get_default_icon_size(self):
            return 16

    ui_root = tmp_path / 'ui'
    (ui_root / 'light').mkdir(parents=True)

    # Ensure module is freshly imported with our stubs
    if MODULE_PATH in list(sys.modules.keys()):
        del sys.modules[MODULE_PATH]
    module = importlib.import_module(MODULE_PATH)

    # Patch app_config inside the module
    monkeypatch.setattr(module, 'app_config', AppConfigStub(ui_root), raising=True)

    yield module  # provide module to tests


def test_png_freshness_prefers_existing_up_to_date_png(reload_module, tmp_path):
    module = reload_module
    theme_dir = module.icon_path_service.get_ui_icons_dir() / 'light'

    svg = theme_dir / 'sample.svg'
    png = theme_dir / 'sample.png'

    svg.write_text('<svg/>')
    png.write_bytes(b'PNG')

    # Make PNG newer than SVG
    os.utime(svg, (time.time() - 5, time.time() - 5))
    os.utime(png, None)

    path = module.get_icon_path('sample.svg', 'light')
    assert path is not None
    assert Path(path) == png


def test_mtime_invalidation_rebuilds_index(reload_module, tmp_path):
    module = reload_module
    theme_dir = module.icon_path_service.get_ui_icons_dir() / 'light'

    # Initially one icon
    (theme_dir / 'a.svg').write_text('<svg/>')
    p1 = module.get_icon_path('a.svg', 'light')
    assert p1 is not None

    # Add a new icon and ensure directory mtime changes; create png to avoid conversion path
    time.sleep(0.02)  # ensure mtime differs
    (theme_dir / 'b.svg').write_text('<svg/>')
    (theme_dir / 'b.png').write_bytes(b'PNG')

    p2 = module.get_icon_path('b.svg', 'light')
    assert p2 is not None
    assert Path(p2).name == 'b.svg' or Path(p2).name == 'b.png'


def test_negative_cache_backoff_returns_none_quickly(reload_module, tmp_path):
    module = reload_module

    start = time.time()
    p = module.get_icon_path('missing.svg', 'light')
    assert p is None
    first = time.time()

    # Immediate second call should hit negative cache and also return None
    p2 = module.get_icon_path('missing.svg', 'light')
    assert p2 is None
    second = time.time()

    # The second call should be very fast compared to the first resolution
    assert (second - first) < 0.05


def test_metrics_collect_and_reset(reload_module, tmp_path):
    module = reload_module

    # Ensure clean metrics
    module.reset_icon_metrics()

    # Miss/not found
    assert module.get_icon_path('nofile.svg', 'light') is None

    # Create an icon, then hit
    theme_dir = module.icon_path_service.get_ui_icons_dir() / 'light'
    (theme_dir / 'hit.svg').write_text('<svg/>')
    assert module.get_icon_path('hit.svg', 'light') is not None
    # Second time should be cache hit
    assert module.get_icon_path('hit.svg', 'light') is not None

    stats = module.get_icon_metrics_stats()
    # We expect at least one hit and one miss
    assert int(stats['hits']) >= 1
    assert int(stats['misses']) >= 1

    # Reset and verify counters go to zero
    module.reset_icon_metrics()
    stats2 = module.get_icon_metrics_stats()
    assert int(stats2['hits']) == 0
    assert int(stats2['misses']) == 0
