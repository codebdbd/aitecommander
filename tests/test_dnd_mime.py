from PyQt6.QtCore import QByteArray, QMimeData, QUrl

from app.utils.ui.dnd.mime import MimeDataParser


def test_extract_external_link_targets_deduplicates_browser_url_variants() -> None:
    mime = QMimeData()
    mime.setUrls([QUrl("https://chatgpt.com/")])
    mime.setData("text/uri-list", QByteArray(b"https://chatgpt.com\n"))
    mime.setText("https://chatgpt.com/")

    targets = MimeDataParser.extract_external_link_targets(mime)

    assert targets == ["https://chatgpt.com"]
