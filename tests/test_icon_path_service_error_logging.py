import importlib
from pathlib import Path



def reload_module():
    from app.utils.ui.icon import path_service as ps

    importlib.reload(ps)
    return ps


def test_get_indexed_icon_logs_warning_on_theme_dir_stat_error(monkeypatch, tmp_path, caplog):
    ps = reload_module()

    # Arrange: make ui dir and theme dir
    ui_dir = tmp_path / "ui"
    theme = "light"
    theme_dir = ui_dir / theme
    theme_dir.mkdir(parents=True)

    # Force service to use our tmp ui dir
    monkeypatch.setattr(ps._icon_path_service, "get_ui_icons_dir", lambda: ui_dir)

    # Monkeypatch Path.stat to raise for this theme_dir
    real_stat = Path.stat

    def fake_stat(self: Path, *args, **kwargs):
        if self == theme_dir:
            raise OSError("stat denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(ps.Path, "stat", fake_stat)

    caplog.set_level("WARNING")

    # Act
    res = ps._get_indexed_icon(theme, "any.png")

    # Assert
    assert res is None
    assert any(
        "_get_indexed_icon: failed to stat theme dir for mtime" in rec.message
        for rec in caplog.records
    )


def test_convert_svg_logs_warning_on_mtime_compare_error(monkeypatch, tmp_path, caplog):
    ps = reload_module()

    # Arrange dirs and files
    ui_dir = tmp_path / "ui"
    theme = "dark"
    theme_dir = ui_dir / theme
    theme_dir.mkdir(parents=True)

    icon_name = "test"
    themed_svg = theme_dir / f"{icon_name}.svg"
    themed_png = theme_dir / f"{icon_name}.png"

    themed_svg.write_text("<svg></svg>")
    themed_png.write_bytes(b"PNG")

    # Ensure validation treats files as valid
    monkeypatch.setattr(ps, "is_valid_icon_file", lambda p: True)
    # Force service to use our tmp ui dir
    monkeypatch.setattr(ps._icon_path_service, "get_ui_icons_dir", lambda: ui_dir)

    # Monkeypatch Path.stat to raise for these files only on second and subsequent calls
    real_stat = Path.stat
    call_count: dict[Path, int] = {themed_png: 0, themed_svg: 0}

    def fake_stat(self: Path, *args, **kwargs):
        if self in call_count:
            call_count[self] += 1
            # Allow first stat for each file (used by is_file()), fail on next to hit mtime compare
            if call_count[self] >= 2:
                raise PermissionError("stat denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(ps.Path, "stat", fake_stat)

    caplog.set_level("WARNING")

    resolver = ps.IconPathResolver(ps.icon_path_service)

    # Act
    res = resolver.convert_svg(icon_name, theme)

    # Assert: conversion may proceed or not; we just need warning logged about mtime compare failure
    assert any(
        "convert_svg: failed to compare mtimes for themed files" in rec.message
        for rec in caplog.records
    )
