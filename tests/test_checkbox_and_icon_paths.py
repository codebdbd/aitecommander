
import pytest
from PyQt6.QtWidgets import QApplication, QCheckBox

from app.config_data.runtime_config import runtime_app_config
from app.core.paths.path_manager import PathManager
from app.services.theme_stylesheet_service import ThemeStylesheetService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_theme_stylesheet_service_resolves_icon_urls():
    service = ThemeStylesheetService(runtime_app_config)
    qss = service.load_stylesheet("cyberpunk_neon", "cyberpunk_neon.qss")
    assert qss is not None
    assert ":/icons/" not in qss

    icons_dir = PathManager.ui_icons_dir().as_posix()
    assert icons_dir in qss
    assert f"{icons_dir}/dark/check.svg" in qss


def test_common_qss_contains_checkbox_alignment_rules():
    common_path = PathManager.qss_dir() / "common.qss"
    content = common_path.read_text(encoding="utf-8")

    assert "subcontrol-origin: padding;" in content
    assert "subcontrol-position: left center;" in content
    assert "margin-top: 2px;" in content


def test_checkbox_renders_with_resolved_icons(qapp):
    service = ThemeStylesheetService(runtime_app_config)
    qss = service.load_stylesheet("cyberpunk_neon", "cyberpunk_neon.qss")
    assert qss is not None

    chk = QCheckBox("Test checkbox")
    chk.setStyleSheet(qss)
    chk.setChecked(True)
    chk.show()
    qapp.processEvents()

    img = chk.grab().toImage()
    assert img.width() > 0
    assert img.height() > 0
    chk.close()
