

# Selection/filter building test

def test_choose_icon_and_copy_uses_configured_extensions(monkeypatch, tmp_path):
    from app.config_data import app_config
    from app.utils.ui.icon import selection

    # Ensure supported formats contain a custom set we can assert against
    exts = [".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp"]

    # Patch config getter to return our extensions deterministically
    monkeypatch.setattr(app_config, "get_supported_icon_formats", lambda: exts)

    # Capture arguments passed to QFileDialog.getOpenFileName
    called = {}

    def fake_get_open_file_name(parent, title, start_dir, file_filter):
        called["title"] = title
        called["start_dir"] = start_dir
        called["file_filter"] = file_filter
        # Return some fake path as if user selected a file
        return str(tmp_path / "picked.png"), ""

    # Stub copy/create to avoid real IO and Qt dependencies
    monkeypatch.setattr(
        selection, "QFileDialog", type("FD", (), {"getOpenFileName": staticmethod(fake_get_open_file_name)})
    )
    monkeypatch.setattr(selection, "copy_icon_smart", lambda src, dest, avoid_duplicates=True: "picked.png")
    fake_icon = object()
    monkeypatch.setattr(selection, "create_icon_from_path", lambda p: fake_icon)

    user_icons_dir = tmp_path
    fname, icon = selection.choose_icon_and_copy(parent=None, user_icons_dir=user_icons_dir)

    # Asserts
    assert fname == "picked.png"
    assert icon is fake_icon

    # Filter should be built from exts, order preserved
    expected_patterns = " ".join(f"*{e}" for e in exts)
    assert called["file_filter"].startswith("Изображения (")
    assert expected_patterns in called["file_filter"]
    assert called["file_filter"].endswith(")")


# Conversion to PNG test

def test_copy_icon_smart_converts_jpeg_to_png(tmp_path):
    from PIL import Image

    from app.utils.ui.icon.icon_operations.converters import copy_icon_smart

    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    # Create a small RGB JPEG image
    jpg_path = src_dir / "sample.jpg"
    img = Image.new("RGB", (16, 16), (123, 200, 50))
    img.save(jpg_path, format="JPEG")

    result_name = copy_icon_smart(str(jpg_path), dst_dir)

    # Should return PNG name and create PNG file
    assert result_name.endswith(".png")
    png_path = dst_dir / result_name
    assert png_path.exists()

    # Original copied raster should be removed after successful conversion
    # Name of the temporary copied file equals to original stem/suffix
    copied_src = dst_dir / jpg_path.name
    assert not copied_src.exists()


def test_copy_icon_smart_reuses_existing_png(tmp_path):
    from PIL import Image

    from app.utils.ui.icon.icon_operations.converters import copy_icon_smart

    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    # Prepare existing PNG
    png_existing = dst_dir / "icon.png"
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    img.save(png_existing, format="PNG")

    # Prepare a JPEG with the same stem
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    jpg_path = src_dir / "icon.jpg"
    img2 = Image.new("RGB", (16, 16), (10, 20, 30))
    img2.save(jpg_path, format="JPEG")

    result_name = copy_icon_smart(str(jpg_path), dst_dir)

    # Should reuse existing PNG and not leave copied JPEG
    assert result_name == "icon.png"
    assert (dst_dir / "icon.png").exists()
    assert not (dst_dir / "icon.jpg").exists()
