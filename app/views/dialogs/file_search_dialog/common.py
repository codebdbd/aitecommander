import datetime
import fnmatch
import os
import stat
from typing import Optional
from re import Pattern


def check_file_content(
    config: dict, filepath: str, content_regex: Optional[Pattern[str]]
) -> bool:
    """Проверка содержимого файла согласно config.
    content_regex: скомпилированный regex или None, если нужен простой поиск подстроки.
    Возвращает True, если файл соответствует содержимому.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if content_regex:
            return bool(content_regex.search(content))
        else:
            search_text = config["content"]
            if not isinstance(search_text, str) or not search_text.strip():
                return False
            if not config.get("case_sensitive"):
                content = content.lower()
                search_text = search_text.lower()
            return search_text in content
    except (OSError, UnicodeDecodeError):
        return False


def matches_criteria(
    config: dict,
    filepath: str,
    filename: str,
    name_regex: Optional[Pattern[str]],
    content_regex: Optional[Pattern[str]],
) -> bool:
    """Проверяет файл по всем критериям из config.
    Совмещает ранее дублируемую логику из FileSearchDialog и FileSearchWorker.
    """
    try:
        file_stat = os.stat(filepath)

        # 1. Маска имени
        if not fnmatch.fnmatch(filename, config["pattern"]):
            return False

        # 2. Regex имени
        if name_regex and not name_regex.search(filename):
            return False

        # 3. Размер (КБ)
        size_kb = file_stat.st_size // 1024
        size_min = config.get("size_min")
        size_max = config.get("size_max")
        if size_min is not None and size_kb < size_min:
            return False
        if size_max is not None and size_kb > size_max:
            return False

        # 4. Дата модификации
        mtime = datetime.date.fromtimestamp(file_stat.st_mtime)
        if not (config["date_from"] <= mtime <= config["date_to"]):
            return False

        # 5. Атрибуты
        if config.get("hidden"):
            if os.name == "posix" and not filename.startswith("."):
                return False
            elif os.name == "nt":
                try:
                    attrs = os.stat(filepath).st_file_attributes
                    if not (attrs & stat.FILE_ATTRIBUTE_HIDDEN):
                        return False
                except (AttributeError, OSError):
                    pass

        if config.get("readonly"):
            if os.access(filepath, os.W_OK):
                return False

        # 6. Содержимое
        if config.get("content"):
            if not check_file_content(config, filepath, content_regex):
                return False

        return True
    except OSError:
        return False
