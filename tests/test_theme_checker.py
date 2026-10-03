from __future__ import annotations

import pytest

from app.utils.theme_checker import parse_color, validate_theme_contrast


def test_parse_color_percentage_rgb():
    # 100% components should parse as 1.0 (pure white), not 100/255 (gray #646464)
    white = parse_color("rgb(100%, 100%, 100%)")
    assert white == pytest.approx((1.0, 1.0, 1.0))

    mixed = parse_color("rgb(0%, 50%, 100%)")
    assert mixed == pytest.approx((0.0, 0.5, 1.0))

    standard = parse_color("rgb(255, 255, 255)")
    assert standard == pytest.approx((1.0, 1.0, 1.0))

    alpha_pct = parse_color("rgba(100%, 100%, 100%, 50%)", bg_rgb=(0.0, 0.0, 0.0))
    assert alpha_pct == pytest.approx((0.5, 0.5, 0.5))

    assert parse_color(None) is None
    assert parse_color(123) is None


def test_validate_theme_contrast_percentage_rgb_light_theme():
    qss = "QDialog { background-color: rgb(100%, 100%, 100%); color: rgb(0%, 0%, 0%); }"
    passed, cr, msg = validate_theme_contrast(qss, is_dark=False)
    assert passed is True
    assert cr >= 4.5
    assert msg == "OK"


def test_validate_theme_contrast_incomplete_tokens_dark_theme_rejects_invisible_selection():
    # Dark theme with selection_bg: #FFFFFF and missing selection_fg
    # Runtime defaults fill selection_fg with #FFFFFF -> contrast 1.0 < 4.5 -> must fail
    qss = "QDialog { background-color: #121212; color: #FFFFFF; }"
    tokens = {"selection_bg": "#FFFFFF"}
    passed, cr, msg = validate_theme_contrast(qss, is_dark=True, tokens=tokens)
    assert passed is False
    assert "Insufficient selection contrast" in msg


def test_validate_theme_contrast_incomplete_tokens_high_contrast_passes():
    # Providing explicit dark selection_fg with white selection_bg should pass
    qss = "QDialog { background-color: #121212; color: #FFFFFF; }"
    tokens = {"selection_bg": "#FFFFFF", "selection_fg": "#000000"}
    passed, cr, msg = validate_theme_contrast(qss, is_dark=True, tokens=tokens)
    assert passed is True
    assert cr >= 4.5
    assert msg == "OK"


def test_validate_theme_contrast_semitransparent_text_blended_per_background():
    # Semi-transparent white text on black canvas blends to gray (contrast 4.58 >= 4.5)
    # Old bug compared that canvas-blended gray with white surface and passed (4.59 >= 4.5)
    # When blended separately over white surface, text is white-on-white (contrast 1:1) and fails
    qss = "QDialog { background-color: #000000; color: #FFFFFF; }"
    tokens = {
        "bg_canvas": "#000000",
        "bg_surface": "#FFFFFF",
        "text_primary": "rgba(255, 255, 255, 0.46)",
    }
    passed, cr, msg = validate_theme_contrast(qss, is_dark=True, tokens=tokens)
    assert passed is False
    assert "Insufficient surface text contrast" in msg


def test_theme_import_service_rejects_null_tokens(tmp_path):
    import json
    from app.services.theme_import_service import ThemeImportService, ThemeValidationError

    theme_dir = tmp_path / "bad_theme"
    theme_dir.mkdir()
    (theme_dir / "theme.qss").write_text(
        "QDialog { background-color: #121212; color: #FFFFFF; }", encoding="utf-8"
    )
    manifest = {
        "id": "bad_theme",
        "name": "Bad Theme",
        "qss": "theme.qss",
        "tokens": {"text_primary": None},
    }
    (theme_dir / "theme.json").write_text(json.dumps(manifest), encoding="utf-8")

    service = ThemeImportService()
    with pytest.raises(ThemeValidationError, match="All token keys and values must be strings"):
        service._validate_theme_root(theme_dir)


def test_theme_import_service_rejects_invalid_token_color(tmp_path):
    import json
    from app.services.theme_import_service import ThemeImportService, ThemeValidationError

    theme_dir = tmp_path / "invalid_color_theme"
    theme_dir.mkdir()
    (theme_dir / "theme.qss").write_text(
        "QDialog { background-color: #121212; color: #FFFFFF; }", encoding="utf-8"
    )
    manifest = {
        "id": "invalid_color_theme",
        "name": "Invalid Color Theme",
        "qss": "theme.qss",
        "tokens": {"selection_bg": "#FFFFFF", "selection_fg": "not-a-color"},
    }
    (theme_dir / "theme.json").write_text(json.dumps(manifest), encoding="utf-8")

    service = ThemeImportService()
    with pytest.raises(ThemeValidationError, match="invalid color for token 'selection_fg'"):
        service._validate_theme_root(theme_dir)


def test_validate_theme_contrast_rejects_unparseable_selection_token():
    qss = "QDialog { background-color: #121212; color: #FFFFFF; }"
    tokens = {"selection_bg": "#FFFFFF", "selection_fg": "not-a-color"}
    passed, cr, msg = validate_theme_contrast(qss, is_dark=True, tokens=tokens)
    assert passed is False
    assert "Cannot parse selection color in tokens" in msg
