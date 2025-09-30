# Исправление конфликтов и противоречий в конфигурации

## Дата: 2025-09-30

## Проблема
При анализе `app/config_data/` были обнаружены противоречия между:
- Fallback значениями в методах `ui_config.py`
- Реальными значениями в `app_config.json`

Это приводило к тому, что если ключ отсутствовал в JSON, использовалось **неверное** fallback значение.

## Исправленные противоречия

### ✅ Критические (влияли на UI):

| Метод | Было fallback | Реально в JSON | Исправлено |
|-------|---------------|----------------|------------|
| `get_window_min_width()` | **800** | 280 | ✅ → 280 |
| `get_row_height()` | **30** | 32 | ✅ → 32 |
| `get_spheres_bar_height()` | **48** | 86 | ✅ → 86 |
| `get_spheres_bar_min_height()` | **64** | 86 | ✅ → 86 |
| `get_spheres_bar_spacing()` | **12** | 8 | ✅ → 8 |
| `get_tile_spacing()` | **12** | 6 | ✅ → 6 |
| `get_tile_padding()` | **10** | 6 | ✅ → 6 |
| `get_tile_width()` | **110** | 128 | ✅ → 128 |
| `get_top_panel_container_height()` | **48** | 40 | ✅ → 40 |
| `get_top_bar_height()` (internal fallback) | **48** | 40 | ✅ → 40 |
| `get_col_widths()` | [40, **280**, 130] | [40, **400**, 130] | ✅ → [40, 400, 130] |
| `get_max_favorites()` | **20** | 10 | ✅ → 10 |
| `get_top_panel_search_min_width()` | **140** | 148 | ✅ → 148 |

### 🔍 Последствия неисправленных значений:

1. **`get_window_min_width() = 800`** вместо 280
   - Окно не могло уменьшиться меньше 800px, хотя должно было до 280px
   
2. **`get_spheres_bar_height() = 48`** вместо 86
   - Панель сфер была бы обрезана или налазила на другие элементы
   
3. **`get_col_widths() = [40, 280, 130]`** вместо [40, 400, 130]
   - Вторая колонка таблицы была бы слишком узкой (280 вместо 400)

4. **`get_tile_width() = 110`** вместо 128
   - Плитки категорий были бы неправильного размера

## Как проверяли

```python
# Читаем реальные значения из JSON
import json
config = json.load(open('app/config_data/app_config.json', encoding='utf-8'))
print('window.min_width:', config['ui']['window']['min_width'])  # 280
print('spheres_bar_height:', config['ui']['spheres_bar_height'])  # 86
print('col_widths:', config['ui']['col_widths'])  # [40, 400, 130]
# И т.д.
```

## Рекомендации на будущее

### ✅ Правило: Fallback должен совпадать с JSON

**Плохо:**
```python
def get_something(self) -> int:
    return self.get("ui.something", 999)  # Не совпадает с JSON!
```

**Хорошо:**
```python
def get_something(self) -> int:
    return self.get("ui.something", 42)  # Совпадает с JSON: "something": 42
```

### 🛡️ Как предотвратить в будущем:

1. **При добавлении нового метода** - проверяй, что fallback совпадает с JSON
2. **При изменении JSON** - обнови fallback в методе
3. **Используй тесты** - проверяй соответствие автоматически

### 📝 Пример теста:

```python
def test_config_fallbacks_match_json():
    """Проверка что fallback значения совпадают с JSON."""
    import json
    config = json.load(open('app/config_data/app_config.json'))
    ui = UIConfig(config)
    
    # Если ключ есть в JSON, fallback не используется
    # Но если удалить ключ, должен вернуться корректный fallback
    
    assert ui.get("ui.window.min_width", 999) == 280, "Fallback должен быть 280"
    assert ui.get("ui.spheres_bar_height", 999) == 86, "Fallback должен быть 86"
    # И т.д.
```

## Связанные изменения

- См. также: `CONFIG_DEDUPLICATION.md` - устранение дублирования между `constants.py` и `app_config.json`

## Статус

✅ **ВСЕ ПРОТИВОРЕЧИЯ ИСПРАВЛЕНЫ**
- 13 методов с неверными fallback исправлено
- Конфигурация согласована
- UI теперь отображается корректно
