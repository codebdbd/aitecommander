import logging
from datetime import datetime

from PyQt6.QtCore import QCoreApplication, QLocale

_TR_CONTEXT = "DateUtils"

_DATE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "Never": "Never",
        "Just now": "Just now",
        "min": "min",
        "hr": "hr",
        "day": "day",
        "days": "days",
        "week": "week",
        "weeks": "weeks",
        "{0} {1} ago": "{0} {1} ago",
        "Unknown": "Unknown",
    },
    "ru": {
        "Never": "Никогда",
        "Just now": "Только что",
        "min": "мин",
        "hr": "ч",
        "day": "день",
        "days": "дней",
        "week": "неделя",
        "weeks": "недель",
        "{0} {1} ago": "{0} {1} назад",
        "Unknown": "Неизвестно",
    },
    "uk": {
        "Never": "Ніколи",
        "Just now": "Щойно",
        "min": "хв",
        "hr": "год",
        "day": "день",
        "days": "днів",
        "week": "тиждень",
        "weeks": "тижнів",
        "{0} {1} ago": "{0} {1} тому",
        "Unknown": "Невідомо",
    },
    "de": {
        "Never": "Nie",
        "Just now": "Gerade eben",
        "min": "Min.",
        "hr": "Std.",
        "day": "Tag",
        "days": "Tage",
        "week": "Woche",
        "weeks": "Wochen",
        "{0} {1} ago": "vor {0} {1}",
        "Unknown": "Unbekannt",
    },
    "es": {
        "Never": "Nunca",
        "Just now": "Ahora mismo",
        "min": "min",
        "hr": "h",
        "day": "día",
        "days": "días",
        "week": "semana",
        "weeks": "semanas",
        "{0} {1} ago": "hace {0} {1}",
        "Unknown": "Desconocido",
    },
    "fr": {
        "Never": "Jamais",
        "Just now": "À l'instant",
        "min": "min",
        "hr": "h",
        "day": "jour",
        "days": "jours",
        "week": "semaine",
        "weeks": "semaines",
        "{0} {1} ago": "il y a {0} {1}",
        "Unknown": "Inconnu",
    },
}


def _tr(text: str) -> str:
    locale = QLocale()
    lang = locale.name().split("_", 1)[0].lower()
    localized = _DATE_TRANSLATIONS.get(lang, {}).get(text)
    if localized:
        return localized
    return QCoreApplication.translate(_TR_CONTEXT, text)

logger = logging.getLogger(__name__)


def format_last_used(last_used: str) -> str:
    if not last_used:
        return _tr("Never")

    def pluralize(n, one, few, many):
        if n % 10 == 1 and n % 100 != 11:
            return one
        elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
            return few
        else:
            return many

    try:
        last_time = datetime.fromisoformat(last_used)
        now = datetime.now(last_time.tzinfo)
        delta = now - last_time
        if delta.total_seconds() < 60:
            return _tr("Just now")
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            unit = pluralize(minutes, _tr("min"), _tr("min"), _tr("min"))
            return _tr("{0} {1} ago").format(minutes, unit)
        hours = int(minutes / 60)
        if hours < 24:
            unit = pluralize(hours, _tr("hr"), _tr("hr"), _tr("hr"))
            return _tr("{0} {1} ago").format(hours, unit)
        days = delta.days
        if days < 7:
            unit = pluralize(days, _tr("day"), _tr("days"), _tr("days"))
            return _tr("{0} {1} ago").format(days, unit)
        elif days < 30:
            weeks = days // 7
            unit = pluralize(weeks, _tr("week"), _tr("weeks"), _tr("weeks"))
            return _tr("{0} {1} ago").format(weeks, unit)
        return last_time.strftime("%d.%m.%Y")
    except (ValueError, TypeError) as e:
        logger.error(f"[format_last_used] Time formatting error: {e}", exc_info=True)
        return _tr("Unknown")
