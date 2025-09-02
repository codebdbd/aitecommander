import os
import re
from typing import List

# Этот тест предотвращает регресс: возврат к старому конструктору LinksBusinessLogic(db=...)
# Сканирует исходники и тесты, исключая кеши/байткод/дистрибутивы.

ROOT_DIRS = ["app", "tests"]
EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "dist",
    ".ruff_cache",
}
INCLUDE_EXTS = {".py"}

# Регулярка ищет любые вызовы конструктора с именованным параметром db=...
LEGACY_PATTERN = re.compile(r"LinksBusinessLogic\([^)]*\bdb\s*=")


def _collect_python_files() -> List[str]:
    files: List[str] = []
    for root in ROOT_DIRS:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Фильтрация директорий на лету
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fname in filenames:
                _, ext = os.path.splitext(fname)
                if ext.lower() in INCLUDE_EXTS:
                    files.append(os.path.join(dirpath, fname))
    return files


def test_no_legacy_links_business_constructor_usage():
    offenders: List[str] = []
    for path in _collect_python_files():
        # Исключаем сам файл теста, чтобы строка в его тексте не ловилась
        try:
            if os.path.samefile(path, __file__):
                continue
        except Exception:
            # samefile может не работать на некоторых платформах/путях —
            # сравним по basename как запасной вариант
            if os.path.basename(path) == os.path.basename(__file__):
                continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if LEGACY_PATTERN.search(content):
                offenders.append(path)
        except Exception:
            # Не должно падать из-за проблем чтения отдельных файлов
            continue

    assert not offenders, (
        "Найдены устаревшие вызовы LinksBusinessLogic(db=...):\n" + "\n".join(offenders)
    )
