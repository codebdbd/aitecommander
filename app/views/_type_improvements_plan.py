"""План улучшения type hints для app/views.

Приоритет: ВЫСОКИЙ
Сложность: НИЗКАЯ
Риск: МИНИМАЛЬНЫЙ
"""

# ================================================================================
# ПРИМЕРЫ УЛУЧШЕНИЙ
# ================================================================================

# ❌ БЫЛО (base_widgets.py, line 502):
def _get_drop_positions(self, event) -> tuple:
    """Возвращает позиции источника и цели для drop-операции."""
    ...

# ✅ СТАЛО:
from typing import List
from PyQt6.QtGui import QDropEvent

def _get_drop_positions(self, event: QDropEvent) -> tuple[List[int], int]:
    """Возвращает позиции источника и цели для drop-операции.
    
    Returns:
        tuple[List[int], int]: (source_rows, target_row)
    """
    ...


# ❌ БЫЛО (links_model.py, line 265):
def mimeData(self, items):
    """Создаёт MIME-данные для перетаскивания."""
    ...

# ✅ СТАЛО:
from typing import Optional, Iterable
from PyQt6.QtCore import QModelIndex, QMimeData

def mimeData(self, items: Iterable[QModelIndex]) -> Optional[QMimeData]:
    """Создаёт MIME-данные для перетаскивания.
    
    Args:
        items: Список индексов модели для перетаскивания
        
    Returns:
        QMimeData объект или None при ошибке
    """
    ...


# ❌ БЫЛО (structure_tree_model.py, line 10):
NodeType = str  # "section" | "category" | "root"

# ✅ СТАЛО:
from typing import Literal

NodeType = Literal["section", "category", "root"]


# ❌ БЫЛО (link_dialog.py, line 139):
def __init__(
    self,
    initialization_data: Dict,  # что внутри?
    dialog_controller: DialogControllerProtocol,
    link: Optional[Dict] = None,  # что внутри?
    ...
)

# ✅ СТАЛО:
from typing import TypedDict, NotRequired

class LinkData(TypedDict):
    """Структура данных ссылки."""
    id: NotRequired[int]
    name: str
    url: str
    type: str
    icon_path: NotRequired[str]
    category_id: NotRequired[int]
    is_favorite: NotRequired[bool]
    notes: NotRequired[str]
    args: NotRequired[str]

class InitializationData(TypedDict):
    """Данные инициализации LinkDialog."""
    spheres: List[Dict[str, Any]]
    category_hierarchy: NotRequired[Dict[str, int]]

def __init__(
    self,
    initialization_data: InitializationData,
    dialog_controller: DialogControllerProtocol,
    link: Optional[LinkData] = None,
    ...
)


# ================================================================================
# ПЛАН ВНЕДРЕНИЯ (по файлам, от простого к сложному)
# ================================================================================

FILES_PRIORITY = [
    # Уровень 1: Простые утилиты (30 мин)
    "app/views/status_bar.py",              # Простые функции
    "app/views/effects/neon_effect.py",     # Маленький файл
    
    # Уровень 2: Базовые виджеты (1 час)
    "app/views/base_panel_widgets.py",
    "app/views/link_button_mixin.py",
    
    # Уровень 3: Модели (2 часа)
    "app/views/link/links_model.py",        # ⚠️ Важно - используется везде
    "app/views/models/structure_tree_model.py",
    
    # Уровень 4: View компоненты (2 часа)
    "app/views/custom_widgets.py",
    "app/views/link/base_table.py",
    
    # Уровень 5: Сложные компоненты (3 часа)
    "app/views/base_widgets.py",           # Много DnD логики
    "app/views/main_window.py",
    
    # Уровень 6: Диалоги (2 часа)
    "app/views/dialogs/base_dialog.py",
    "app/views/dialogs/link_dialog/link_dialog.py",
    "app/views/dialogs/link_dialog/link_dialog_ui.py",
]

# ================================================================================
# НАСТРОЙКА MYPY
# ================================================================================

# Создать файл: mypy.ini (или обновить существующий)
MYPY_CONFIG = """
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False  # Пока False, потом True
disallow_incomplete_defs = True
check_untyped_defs = True
no_implicit_optional = True
warn_redundant_casts = True
warn_unused_ignores = True
warn_unreachable = True
strict_equality = True

# Для PyQt6 (нет stubs)
[mypy-PyQt6.*]
ignore_missing_imports = True

# Для app.config_data
[mypy-app.config_data]
ignore_missing_imports = False
"""

# ================================================================================
# СКРИПТ ДЛЯ АВТОМАТИЧЕСКОЙ ПРОВЕРКИ
# ================================================================================

CHECK_SCRIPT = """
#!/usr/bin/env python3
'''Проверка качества type hints в app/views.'''

import subprocess
import sys
from pathlib import Path

def check_types():
    '''Запускает mypy для app/views.'''
    result = subprocess.run(
        ['mypy', 'app/views'],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    
    if result.returncode != 0:
        print("❌ Найдены проблемы с типами")
        return False
    
    print("✅ Все типы корректны")
    return True

if __name__ == '__main__':
    sys.exit(0 if check_types() else 1)
"""
