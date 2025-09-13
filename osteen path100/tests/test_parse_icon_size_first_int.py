from app.utils.links.parser.icon_candidates import parse_icon_size


def test_parse_icon_size_first_integer_fallback():
    assert parse_icon_size("512 some") == 512
    assert parse_icon_size("48") == 48
