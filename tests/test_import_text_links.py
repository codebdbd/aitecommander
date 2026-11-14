from app.utils.links.import_text_links import (
    TextLinksImporter,
    is_likely_target,
    normalize_import_url,
)


def test_is_likely_target():
    assert is_likely_target("https://google.com")
    assert is_likely_target("http://localhost:8080")
    assert is_likely_target("ftp://files.example.com")
    assert is_likely_target("C:\\Windows\\notepad.exe")
    assert is_likely_target("D:/Projects/app.py")
    assert is_likely_target("\\\\nas\\shared\\folder")
    assert is_likely_target("github.com")
    assert is_likely_target("python.org/doc")
    assert not is_likely_target("Just Some Title")
    assert not is_likely_target("")


def test_normalize_import_url():
    assert normalize_import_url("https://example.com") == "https://example.com"
    assert normalize_import_url("github.com") == "https://github.com"
    assert (
        normalize_import_url("C:\\Windows\\notepad.exe") == "C:\\Windows\\notepad.exe"
    )
    assert normalize_import_url("") == ""


def test_parse_markdown_links():
    importer = TextLinksImporter()
    text = """
    # My Links
    * [Google](https://google.com)
    - [Python](https://python.org "Official site")
    1. [Local App](C:\\Tools\\app.exe)
    """
    links = importer.parse_links_from_text(text)
    assert len(links) == 3
    assert links[0] == {"name": "Google", "url": "https://google.com"}
    assert links[1] == {"name": "Python", "url": "https://python.org"}
    assert links[2] == {"name": "Local App", "url": "C:\\Tools\\app.exe"}


def test_parse_csv_and_tsv():
    importer = TextLinksImporter()
    text = (
        "Google, https://google.com\n"
        "https://github.com, GitHub\n"
        "Python Docs\thttps://docs.python.org\n"
        "https://ya.ru;Yandex\n"
    )
    links = importer.parse_links_from_text(text)
    assert len(links) == 4
    assert links[0] == {"name": "Google", "url": "https://google.com"}
    assert links[1] == {"name": "GitHub", "url": "https://github.com"}
    assert links[2] == {"name": "Python Docs", "url": "https://docs.python.org"}
    assert links[3] == {"name": "Yandex", "url": "https://ya.ru"}


def test_parse_delimited_and_plain():
    importer = TextLinksImporter()
    text = """
    Python :: https://python.org
    Google - https://google.com
    https://github.com | GitHub
    https://habr.com
    C:\\Windows\\notepad.exe
    """
    links = importer.parse_links_from_text(text)
    assert len(links) == 5
    assert links[0] == {"name": "Python", "url": "https://python.org"}
    assert links[1] == {"name": "Google", "url": "https://google.com"}
    assert links[2] == {"name": "GitHub", "url": "https://github.com"}
    assert links[3] == {"name": "", "url": "https://habr.com"}
    assert links[4] == {"name": "", "url": "C:\\Windows\\notepad.exe"}


def test_read_file_with_encoding(tmp_path):
    importer = TextLinksImporter()
    file_cp1251 = tmp_path / "links_1251.txt"
    file_cp1251.write_bytes(
        "Яндекс, https://ya.ru\nХабр, https://habr.com".encode("cp1251")
    )

    content = importer.read_file_with_encoding(str(file_cp1251))
    links = importer.parse_links_from_text(content)
    assert len(links) == 2
    assert links[0] == {"name": "Яндекс", "url": "https://ya.ru"}
    assert links[1] == {"name": "Хабр", "url": "https://habr.com"}


def test_prepare_and_sync_mock():
    importer = TextLinksImporter()
    raw_links = [
        {"name": "GitHub", "url": "github.com"},
        {"name": "", "url": "https://google.com"},
    ]
    p1 = importer.prepare_link_payload(raw_links[0], category_id=42)
    assert p1 is not None
    assert p1["category_id"] == 42
    assert p1["name"] == "GitHub"
    assert p1["url"] == "https://github.com"
    assert p1["type"] == "web"

    p2 = importer.prepare_link_payload(raw_links[1], category_id=42)
    assert p2 is not None
    assert p2["name"] == "google.com"

    class MockLinksBusiness:
        def __init__(self):
            self.created = []

        def create_links_for_import_bulk(self, payloads):
            self.created.extend(payloads)
            return len(payloads)

    mock_b = MockLinksBusiness()
    success, msg, stats = importer.sync_to_db(
        raw_links, category_id=42, links_business=mock_b
    )
    assert success is True
    assert stats["added"] == 2
    assert stats["https_count"] == 2
    assert len(mock_b.created) == 2


def test_system_dialog_controller_import_text_links():
    from unittest.mock import MagicMock, patch

    from app.controllers.ui.dialogs.system_dialog_controller import (
        SystemDialogController,
    )

    main_window = MagicMock()
    main_window.get_current_category_id.return_value = 10
    db_ctrl = MagicMock()
    links_tbl = MagicMock()
    links_biz = MagicMock()

    ctrl = SystemDialogController(
        main_window,
        database_controller=db_ctrl,
        links_table_controller=links_tbl,
        links_business=links_biz,
    )

    with (
        patch(
            "app.utils.links.import_text_links.TextLinksImporter.select_file",
            return_value="dummy.txt",
        ),
        patch(
            "app.utils.links.import_text_links.TextLinksImporter.parse_file",
            return_value=[{"name": "Test", "url": "https://test.com"}],
        ),
        patch.object(ctrl, "_backup_before_import", return_value=True),
        patch.object(ctrl, "_post_import_processing") as mock_post,
    ):
        ctrl.handle_import_text_links()
        assert mock_post.called


def test_parse_space_separated_name_and_url():
    importer = TextLinksImporter()
    text = (
        "NVIDIA NIM https://build.nvidia.com/settings/api-keys\n"
        "Groq https://console.groq.com/keys\n"
        "https://cloud.cerebras.ai/ Cerebras\n"
        "Zro / MoonMath.ai https://zro.moonmath.ai/api-keys\n"
        "Free.ai https://free.ai/account/#api-keys\n"
        '"C:\\Program Files\\App\\app.exe" My Program\n'
        "C:\\Windows\\notepad.exe Notepad\n"
    )
    links = importer.parse_links_from_text(text)
    assert len(links) == 7
    assert links[0] == {
        "name": "NVIDIA NIM",
        "url": "https://build.nvidia.com/settings/api-keys",
    }
    assert links[1] == {"name": "Groq", "url": "https://console.groq.com/keys"}
    assert links[2] == {"name": "Cerebras", "url": "https://cloud.cerebras.ai/"}
    assert links[3] == {
        "name": "Zro / MoonMath.ai",
        "url": "https://zro.moonmath.ai/api-keys",
    }
    assert links[4] == {"name": "Free.ai", "url": "https://free.ai/account/#api-keys"}
    assert links[5] == {"name": "My Program", "url": "C:\\Program Files\\App\\app.exe"}
    assert links[6] == {"name": "Notepad", "url": "C:\\Windows\\notepad.exe"}
