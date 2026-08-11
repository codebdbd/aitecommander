from __future__ import annotations

from app.controllers.business.links_business import LinksBusinessLogic


def test_prepare_link_data_uses_icon_name_as_fallback() -> None:
    logic = LinksBusinessLogic.__new__(LinksBusinessLogic)

    prepared = logic._prepare_link_data(
        {
            "category_id": 3,
            "name": "Image",
            "url": r"C:\\tmp\\image.png",
            "type": "file",
            "icon_name": "file_preview_image.png",
            "icon_path": "",
            "args": "",
            "notes": "",
            "is_favorite": False,
        }
    )

    assert prepared is not None
    assert prepared["icon_path"] == "file_preview_image.png"
