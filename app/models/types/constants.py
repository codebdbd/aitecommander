"""Константы для работы с моделями базы данных."""

# SQLite параметры и ограничения
SQLITE_MAX_VARIABLES = 999  # Максимальное количество переменных в запросе SQLite по умолчанию
SQLITE_SAFE_BATCH_SIZE = 400  # Безопасный размер батча для операций с 2+ параметрами на запись
SQLITE_SAFE_SELECT_CHUNK = 900  # Безопасный размер чанка для SELECT запросов

# Резервное копирование
DEFAULT_MAX_BACKUPS = 10  # Количество резервных копий по умолчанию
BACKUP_RETRY_ATTEMPTS = 3  # Количество попыток удаления старых бэкапов
BACKUP_RETRY_DELAY = 0.1  # Задержка между попытками (секунды)

# Производительность
PERFORMANCE_WARNING_THRESHOLD_MS = 50.0  # Порог предупреждения о медленных операциях (мс)
DEFAULT_QUERY_TIMEOUT = 30  # Таймаут запросов по умолчанию (секунды)

# Значения по умолчанию
DEFAULT_ICON_PATH = "default.ico"
EMPTY_ICON_PATH = ""

# Валидные таблицы для операций с позициями
VALID_POSITION_TABLES = frozenset({"sphere", "section", "category", "link"})
