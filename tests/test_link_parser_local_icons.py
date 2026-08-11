from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.links.link_parser import parse_local_link


def test_parse_local_link_creates_preview_for_image_files(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGBA", (640, 360), (255, 0, 0, 255)).save(image_path)
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()

    from app.utils.links import link_parser as link_parser_module

    original_dir = link_parser_module.icon_path_service.get_user_icons_dir
    link_parser_module.icon_path_service.get_user_icons_dir = lambda: icons_dir
    try:
        info = parse_local_link("file", str(image_path), app_config)
    finally:
        link_parser_module.icon_path_service.get_user_icons_dir = original_dir

    icon_path = Path(info["icon"])
    assert icon_path.exists()
    assert icon_path.name.startswith("file_preview_sample_")

