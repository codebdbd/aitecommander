import json
import logging

from PyQt6.QtWidgets import QApplication


def copy_link_to_clipboard(link_or_links):
    clipboard = QApplication.instance().clipboard()
    try:
        clipboard.setText(json.dumps(link_or_links, ensure_ascii=False))
    except Exception as e:
        logging.error(f"Failed to copy link(s) to clipboard: {e}", exc_info=True)
        clipboard.clear()

def get_link_from_clipboard():
    clipboard = QApplication.instance().clipboard()
    try:
        text = clipboard.text()
        data = json.loads(text)
        if isinstance(data, dict) and 'name' in data:
            return data
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        return None
    except Exception as e:
        logging.error(f"Failed to read link from clipboard: {e}", exc_info=True)
        return None
