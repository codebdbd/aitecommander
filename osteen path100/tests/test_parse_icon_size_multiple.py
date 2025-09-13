from app.utils.links.parser.icon_candidates import parse_icon_size


def test_parse_icon_size_multiple_values():
    # multiple sizes -> max returned
    assert parse_icon_size("16x16 32x32 180x180") == 180
    # whitespace and case-insensitivity
    assert parse_icon_size("  24X24   48x48\t96x96 ") == 96
    # 'any' -> 0
    assert parse_icon_size("any") == 0
    # fallback: first integer when no WxH
    assert parse_icon_size("48 foo") == 48
    # invalid pairs are ignored, but valid ones still considered
    assert parse_icon_size("ax16 32xX 64x64") == 64
