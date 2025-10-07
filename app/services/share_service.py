import logging
from typing import Optional, Tuple
from urllib.parse import quote_plus

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


def _open_url(url: str) -> bool:
    try:
        ok = QDesktopServices.openUrl(QUrl(url))
        logger.debug("ShareService: openUrl(%s) -> %s", url, ok)
        return bool(ok)
    except Exception:
        logger.exception("ShareService: openUrl failed for %s", url)
        return False


def _clipboard_copy(text: str) -> None:
    try:
        app = QApplication.instance()
        if app is None:
            logger.warning("ShareService: QApplication.instance() is None; cannot copy to clipboard")
            return
        cb = app.clipboard()
        if cb is None:
            logger.warning("ShareService: clipboard is None; cannot copy to clipboard")
            return
        cb.setText(text)
        logger.info("ShareService: text copied to clipboard as fallback")
    except Exception:
        logger.exception("ShareService: clipboard copy failed")


def build_share_text(name: Optional[str], url: str) -> str:
    safe_name = name.strip() if isinstance(name, str) else "Link"
    return f"I recommend: {safe_name}\n{url}"


def share_via_telegram(name: Optional[str], url: str) -> bool:
    text = build_share_text(name, url)
    # First web — guaranteed prefill
    web = f"https://t.me/share/url?url={quote_plus(url)}&text={quote_plus(text)}"
    if _open_url(web):
        return True
    # If for some reason web didn't open — try client via deeplink
    candidates = [
        f"tg://msg?text={quote_plus(text)}",
        f"tg://msg_url?url={quote_plus(url)}&text={quote_plus(text)}",
        f"tg://share?url={quote_plus(url)}&text={quote_plus(text)}",
    ]
    for deep in candidates:
        if _open_url(deep):
            return True
    return False


# --- Social networks: X(Twitter), Facebook, LinkedIn ---
def share_via_x(name: Optional[str], url: str) -> bool:
    """Open X(Twitter) intent with prefill."""
    text = build_share_text(name, url)
    x_url = f"https://twitter.com/intent/tweet?text={quote_plus(text)}&url={quote_plus(url)}"
    # Modern X domain also supports redirect
    if _open_url(x_url):
        return True
    x_alt = f"https://x.com/intent/tweet?text={quote_plus(text)}&url={quote_plus(url)}"
    return _open_url(x_alt)


def share_via_facebook(name: Optional[str], url: str) -> bool:
    """Open Facebook sharer (requires browser authentication)."""
    fb = f"https://www.facebook.com/sharer/sharer.php?u={quote_plus(url)}"
    return _open_url(fb)


def share_via_linkedin(name: Optional[str], url: str) -> bool:
    """Open LinkedIn share offsite."""
    li = f"https://www.linkedin.com/sharing/share-offsite/?url={quote_plus(url)}"
    return _open_url(li)


def share_via_pinterest(name: Optional[str], url: str) -> bool:
    """Open Pinterest create pin with prefill (url, description)."""
    text = build_share_text(name, url)
    pin = f"https://pinterest.com/pin/create/button/?url={quote_plus(url)}&description={quote_plus(text)}"
    return _open_url(pin)


def open_default_apps_settings() -> Tuple[bool, Optional[str]]:
    """Open Windows settings for default apps (mailto association).
    
    ✅ FIX: Returns status and message instead of showing QMessageBox.
    
    Returns:
        Tuple[bool, Optional[str]]: (success, user_message)
    """
    try:
        ok = QDesktopServices.openUrl(QUrl("ms-settings:defaultapps"))
        if not ok:
            # Alternatively: general settings if specific page is unavailable
            ok = QDesktopServices.openUrl(QUrl("ms-settings:"))
        if not ok:
            raise RuntimeError("Failed to open ms-settings")
        
        message = (
            "Open the Default Apps section and associate the mailto protocol "
            "with your email application."
        )
        return True, message
    except Exception as e:
        logger.exception("ShareService: failed to open Windows default apps settings")
        return False, f"Failed to open settings: {e}"
    


def share_via_whatsapp(name: Optional[str], url: str) -> bool:
    text = build_share_text(name, url)
    # First web — wa.me is stable for prefill
    web_primary = f"https://wa.me/?text={quote_plus(text)}"
    if _open_url(web_primary):
        return True
    web_alt = f"https://api.whatsapp.com/send?text={quote_plus(text)}"
    if _open_url(web_alt):
        return True
    # As a last resort — try to open desktop client
    deep = f"whatsapp://send?text={quote_plus(text)}"
    return _open_url(deep)


def share_via_viber(name: Optional[str], url: str) -> Tuple[bool, Optional[str]]:
    """Share via Viber.
    
    ✅ FIX: Returns status and message instead of showing QMessageBox.
    
    Returns:
        Tuple[bool, Optional[str]]: (success, user_message)
    """
    text = build_share_text(name, url)
    primary = f"viber://forward?text={quote_plus(text)}"
    if _open_url(primary):
        return True, None
    
    # Fallback for Viber: copy to clipboard
    _clipboard_copy(text)
    logger.warning("ShareService: Viber fallback — copied to clipboard")
    
    message = (
        "Message text copied to clipboard.\n"
        "Open Viber and paste (Ctrl+V) into chat manually."
    )
    return False, message


def share_via_email(name: Optional[str], url: str) -> bool:
    subject = "Share link"
    body = build_share_text(name, url)
    mailto = f"mailto:?subject={quote_plus(subject)}&body={quote_plus(body)}"
    if _open_url(mailto):
        return True
    # Web fallback: open Gmail compose
    gmail = f"https://mail.google.com/mail/?view=cm&fs=1&su={quote_plus(subject)}&body={quote_plus(body)}"
    return _open_url(gmail)


def share_via_email_client(name: Optional[str], url: str) -> bool:
    """Open system email client via mailto: with prefill.

    In Windows this behavior depends on associations. If mailto is associated with browser,
    browser may not create draft. In this case suggest Gmail option.
    """
    subject = "Share link"
    body = build_share_text(name, url)
    mailto = f"mailto:?subject={quote_plus(subject)}&body={quote_plus(body)}"
    return _open_url(mailto)


def share_via_email_gmail(name: Optional[str], url: str) -> bool:
    """Open Gmail compose in browser with prefilled subject and body."""
    subject = "Share link"
    body = build_share_text(name, url)
    gmail = f"https://mail.google.com/mail/?view=cm&fs=1&su={quote_plus(subject)}&body={quote_plus(body)}"
    return _open_url(gmail)


def copy_email_template(name: Optional[str], url: str) -> Tuple[bool, Optional[str]]:
    """Copy email template to clipboard (Subject + Body).
    
    ✅ FIX: Returns status and message instead of showing QMessageBox.
    
    Returns:
        Tuple[bool, Optional[str]]: (success, user_message)
    """
    subject = "Поделиться ссылкой"
    body = build_share_text(name, url)
    template = f"Subject: {subject}\n\n{body}"
    _clipboard_copy(template)
    
    message = "Email template copied to clipboard. Open any email and paste (Ctrl+V)."
    return True, message
