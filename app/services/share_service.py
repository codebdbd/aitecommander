import logging
from typing import Optional
from urllib.parse import quote_plus

from typing import cast
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox

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
        app = cast(QApplication | None, QApplication.instance())
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
    safe_name = name.strip() if isinstance(name, str) else "Ссылка"
    return f"Рекомендую: {safe_name}\n{url}"


def share_via_telegram(name: Optional[str], url: str) -> bool:
    text = build_share_text(name, url)
    # Сначала веб — гарантированное предзаполнение
    web = f"https://t.me/share/url?url={quote_plus(url)}&text={quote_plus(text)}"
    if _open_url(web):
        return True
    # Если по какой‑то причине веб не открылся — пробуем клиент через deeplink
    candidates = [
        f"tg://msg?text={quote_plus(text)}",
        f"tg://msg_url?url={quote_plus(url)}&text={quote_plus(text)}",
        f"tg://share?url={quote_plus(url)}&text={quote_plus(text)}",
    ]
    for deep in candidates:
        if _open_url(deep):
            return True
    return False


# --- Соцсети: X(Twitter), Facebook, LinkedIn ---
def share_via_x(name: Optional[str], url: str) -> bool:
    """Открыть X(Twitter) intent с предзаполнением."""
    text = build_share_text(name, url)
    x_url = f"https://twitter.com/intent/tweet?text={quote_plus(text)}&url={quote_plus(url)}"
    # Современный домен X также поддерживает редирект
    if _open_url(x_url):
        return True
    x_alt = f"https://x.com/intent/tweet?text={quote_plus(text)}&url={quote_plus(url)}"
    return _open_url(x_alt)


def share_via_facebook(name: Optional[str], url: str) -> bool:
    """Открыть Facebook шэрер (требует авторизации в браузере)."""
    fb = f"https://www.facebook.com/sharer/sharer.php?u={quote_plus(url)}"
    return _open_url(fb)


def share_via_linkedin(name: Optional[str], url: str) -> bool:
    """Открыть LinkedIn share offsite."""
    li = f"https://www.linkedin.com/sharing/share-offsite/?url={quote_plus(url)}"
    return _open_url(li)


def share_via_pinterest(name: Optional[str], url: str) -> bool:
    """Открыть Pinterest create pin с предзаполнением (url, description)."""
    text = build_share_text(name, url)
    pin = f"https://pinterest.com/pin/create/button/?url={quote_plus(url)}&description={quote_plus(text)}"
    return _open_url(pin)


def open_default_apps_settings() -> bool:
    """Открыть настройки Windows для приложений по умолчанию (mailto-ассоциация)."""
    try:
        ok = QDesktopServices.openUrl(QUrl("ms-settings:defaultapps"))
        if not ok:
            # Альтернативно: общие настройки, если конкретная страница недоступна
            ok = QDesktopServices.openUrl(QUrl("ms-settings:"))
        if not ok:
            raise RuntimeError("Failed to open ms-settings")
        try:
            QMessageBox.information(
                None,
                "Назначить почтовый клиент",
                "Откройте раздел Приложения по умолчанию и свяжите протокол mailto с вашим почтовым приложением.",
            )
        except Exception:
            logger.exception("ShareService: failed to show settings hint message box")
        return True
    except Exception:
        logger.exception("ShareService: failed to open Windows default apps settings")
        return False
    


def share_via_whatsapp(name: Optional[str], url: str) -> bool:
    text = build_share_text(name, url)
    # Сначала веб — wa.me стабилен для предзаполнения
    web_primary = f"https://wa.me/?text={quote_plus(text)}"
    if _open_url(web_primary):
        return True
    web_alt = f"https://api.whatsapp.com/send?text={quote_plus(text)}"
    if _open_url(web_alt):
        return True
    # В качестве крайней меры — попытка открыть десктопный клиент
    deep = f"whatsapp://send?text={quote_plus(text)}"
    return _open_url(deep)


def share_via_viber(name: Optional[str], url: str) -> bool:
    text = build_share_text(name, url)
    primary = f"viber://forward?text={quote_plus(text)}"
    if _open_url(primary):
        return True
    # Fallback для Viber: копируем в буфер обмена и логируем подсказку
    _clipboard_copy(text)
    logger.warning("ShareService: Viber fallback — скопировано в буфер обмена. Откройте Viber и вставьте сообщение вручную.")
    try:
        QMessageBox.information(
            None,
            "Поделиться в Viber",
            "Текст сообщения скопирован в буфер обмена.\nОткройте Viber и вставьте (Ctrl+V) в чат вручную.",
        )
    except Exception:
        logger.exception("ShareService: failed to show QMessageBox for Viber fallback")
    return False


def share_via_email(name: Optional[str], url: str) -> bool:
    subject = "Поделиться ссылкой"
    body = build_share_text(name, url)
    mailto = f"mailto:?subject={quote_plus(subject)}&body={quote_plus(body)}"
    if _open_url(mailto):
        return True
    # Веб‑fallback: открыть Gmail compose
    gmail = f"https://mail.google.com/mail/?view=cm&fs=1&su={quote_plus(subject)}&body={quote_plus(body)}"
    return _open_url(gmail)


def share_via_email_client(name: Optional[str], url: str) -> bool:
    """Открыть системный почтовый клиент через mailto: с предзаполнением.

    В Windows это поведение зависит от ассоциаций. Если mailto связан с браузером,
    браузер может не создать черновик. В этом случае предложите вариант Gmail.
    """
    subject = "Поделиться ссылкой"
    body = build_share_text(name, url)
    mailto = f"mailto:?subject={quote_plus(subject)}&body={quote_plus(body)}"
    return _open_url(mailto)


def share_via_email_gmail(name: Optional[str], url: str) -> bool:
    """Открыть Gmail compose в браузере с предзаполненной темой и телом."""
    subject = "Поделиться ссылкой"
    body = build_share_text(name, url)
    gmail = f"https://mail.google.com/mail/?view=cm&fs=1&su={quote_plus(subject)}&body={quote_plus(body)}"
    return _open_url(gmail)


def copy_email_template(name: Optional[str], url: str) -> bool:
    """Скопировать в буфер обмена шаблон письма (Тема + Тело) и показать подсказку."""
    subject = "Поделиться ссылкой"
    body = build_share_text(name, url)
    template = f"Тема: {subject}\n\n{body}"
    _clipboard_copy(template)
    try:
        QMessageBox.information(
            None,
            "Шаблон письма скопирован",
            "Шаблон письма скопирован в буфер обмена. Откройте любую почту и вставьте (Ctrl+V).",
        )
    except Exception:
        logger.exception("ShareService: failed to show QMessageBox for email template copy")
    return True
