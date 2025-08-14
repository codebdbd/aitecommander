import logging
from datetime import datetime


def format_last_used(last_used: str) -> str:
    if not last_used:
        return "Никогда"
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
            return "Только что"
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            unit = pluralize(minutes, "мин.", "мин.", "мин.")
            return f"{minutes} {unit} назад"
        hours = int(minutes / 60)
        if hours < 24:
            unit = pluralize(hours, "ч.", "ч.", "ч.")
            return f"{hours} {unit} назад"
        days = delta.days
        if days < 7:
            unit = pluralize(days, "д.", "д.", "д.")
            return f"{days} {unit} назад"
        elif days < 30:
            weeks = days // 7
            unit = pluralize(weeks, "нед.", "нед.", "нед.")
            return f"{weeks} {unit} назад"
        return last_time.strftime("%d.%m.%Y")
    except (ValueError, TypeError) as e:
        logging.error(f"[format_last_used] Ошибка форматирования времени: {e}", exc_info=True)
        return "Неизвестно"
