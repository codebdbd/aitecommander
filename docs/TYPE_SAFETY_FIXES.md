# Исправление проблем с типизацией

## Критические места без типов

### 1. Методы DnD возвращают неясные типы

**Файл**: `base_widgets.py:502`
```python
# ❌ Текущее состояние:
def _get_drop_positions(self, event) -> tuple:  # tuple чего?

# ✅ Исправление:
def _get_drop_positions(self, event: QDropEvent) -> tuple[list[int], int]:
    """Returns (source_rows, target_row)."""
```

### 2. Использование Any вместо конкретных типов

**Файл**: `links_model.py:41`
```python
# ❌ Проблема:
def data(self, index: QModelIndex, role: int = ...) -> Any:  # Слишком общий

# ✅ Исправление с Union:
from typing import Union
from PyQt6.QtCore import QVariant
from PyQt6.QtGui import QIcon

def data(
    self, 
    index: QModelIndex, 
    role: int = Qt.ItemDataRole.DisplayRole
) -> Union[str, int, QIcon, dict, None]:
    """Returns display data, icon, or link dict depending on role."""
```

### 3. Строковые типы вместо Literal

**Файл**: `structure_tree_model.py:10`
```python
# ❌ Проблема:
NodeType = str  # Любая строка допустима

# ✅ Исправление:
from typing import Literal
NodeType = Literal["section", "category", "root"]
# Теперь mypy поймает node.type = "wrong_type"
```

## Быстрое исправление: добавить в каждый файл

```python
# В начале каждого файла views:
from __future__ import annotations  # Уже есть в некоторых ✅

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Импорты только для проверки типов (избегаем циклических зависимостей)
    from PyQt6.QtCore import QModelIndex
    from PyQt6.QtGui import QDropEvent
```

## Приоритетные файлы для исправления

1. **links_model.py** - используется везде
2. **base_widgets.py** - базовый функционал DnD
3. **structure_tree_model.py** - ядро навигации
4. **link_dialog.py** - сложный диалог

## Скрипт автопроверки

```bash
# Запустить mypy с строгими настройками
mypy app/views --strict --show-error-codes
```
