import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def format_last_used(last_used: str) -> str:
    if not last_used:
        return "Never"

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
            return "Just now"
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            unit = pluralize(minutes, "min", "min", "min")
            return f"{minutes} {unit} ago"
        hours = int(minutes / 60)
        if hours < 24:
            unit = pluralize(hours, "hr", "hr", "hr")
            return f"{hours} {unit} ago"
        days = delta.days
        if days < 7:
            unit = pluralize(days, "day", "days", "days")
            return f"{days} {unit} ago"
        elif days < 30:
            weeks = days // 7
            unit = pluralize(weeks, "week", "weeks", "weeks")
            return f"{weeks} {unit} ago"
        return last_time.strftime("%d.%m.%Y")
    except (ValueError, TypeError) as e:
        logger.error(
            f"[format_last_used] Time formatting error: {e}", exc_info=True
        )
        return "Unknown"
