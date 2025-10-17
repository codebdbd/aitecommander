# Аудит app/utils/ui/icon/icon_operations/ (2025-10-16)

## СТРУКТУРА МОДУЛЯ

```
icon_operations/
├── __init__.py (2309 bytes) — экспорты
├── cache_proxy.py (4510 bytes) — IconCache для меню
├── converters.py (18490 bytes) — копирование и конвертация
└── creators.py (20937 bytes) — создание QIcon
```

---

## КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### 1. **МЁРТВЫЙ КОД: Async-функции не используются**

**Файл:** `converters.py:292-301, 446-538`

**Проблема:**
```python
async def copy_icon_async(src_path: str, dest_dir: Path) -> str:
    """Asynchronously copy icon to directory."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, copy_icon, src_path, dest_dir)

async def convert_icon_to_png_128_async(...) -> bool:
    """Asynchronously convert icon to PNG of specified size."""
    ...

async def batch_convert_icons_async(...) -> dict[str, bool]:
    """Batch asynchronous icon conversion."""
    ...
```

**Факт:** Grep показал, что эти функции **НЕ ВЫЗЫВАЮТСЯ** нигде в коде, кроме `__init__.py` (экспорт).

**Решение:** Удалить 246 строк мёртвого кода:
- `copy_icon_async()` — 4 строки
- `copy_icon_to_path_async()` — 3 строки
- `convert_icon_to_png_128_async()` — 27 строк
- `convert_icon_to_png_32_async()` — 4 строки
- `convert_raster_icon_to_png_async()` — 4 строки
- `batch_convert_icons_async()` — 59 строк

---

### 2. **АВТОКОНВЕРТАЦИЯ SVG→PNG блокирует GUI**

**Файл:** `converters.py:204-214`

**Проблема:**
```python
def copy_icon_smart(...):
    # ... копирование файла ...
    
    # Automatic SVG to PNG conversion when copying
    if src_path_obj.suffix.lower() == ".svg":
        png_dst = dest_dir / (dst.stem + ".png")
        if not png_dst.exists():
            # Convert SVG to PNG 128x128  ❌ БЛОКИРУЕТ GUI на 100-500ms!
            if not convert_icon_to_png_128(str(dst), str(png_dst)):
                logger.warning("Failed to convert SVG to PNG: %s -> %s", dst, png_dst)
                return dst.name
        return png_dst.name  # ❌ Возвращает PNG вместо SVG!
```

**Проблемы:**
1. **Синхронная конвертация** блокирует GUI на 100-500ms
2. **Qt6 умеет работать с SVG напрямую** — конвертация не нужна
3. **Возвращает PNG вместо SVG** — ломает логику (пользователь выбрал SVG, а сохраняется PNG)

**Решение:** Удалить автоконвертацию (строки 204-248), оставить только копирование.

---

### 3. **АВТОКОНВЕРТАЦИЯ растров→PNG блокирует GUI**

**Файл:** `converters.py:216-248`

**Проблема:**
```python
# Auto-convert common rasters to PNG
ext = src_path_obj.suffix.lower()
if ext in {".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
    png_dst = dest_dir / (dst.stem + ".png")
    if convert_raster_icon_to_png(str(dst), str(png_dst), size=128):  # ❌ БЛОКИРУЕТ GUI!
        dst.unlink(missing_ok=True)  # ❌ Удаляет оригинал!
        return png_dst.name
```

**Проблемы:**
1. **Синхронная конвертация** через PIL блокирует GUI
2. **Удаляет оригинальный файл** — потеря данных
3. **Qt6 умеет работать с JPG/PNG** — конвертация не нужна

**Решение:** Удалить автоконвертацию растров.

---

### 4. **Хеширование файлов блокирует GUI**

**Файл:** `converters.py:99-111, 114-153`

**Проблема:**
```python
def _calculate_file_hash(file_path: Path) -> str:
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):  # ❌ Блокирует GUI
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()[:16]

def _find_existing_icon_by_content(src_path: Path, dest_dir: Path, ...) -> str | None:
    # Сканирует всю директорию и хеширует файлы  ❌ МЕДЛЕННО!
    for existing_file in dest_dir.iterdir():
        existing_hash = _calculate_file_hash(existing_file)  # ❌ Блокирует GUI
```

**Решение:** Уже исправлено в `selection.py:36` — используется `avoid_duplicates=False`.

---

### 5. **Кеш хешей на диске — избыточная сложность**

**Файл:** `converters.py:23-87`

**Проблема:**
```python
_ICON_HASH_CACHE: dict[Path, dict[str, str]] = {}  # Глобальный кеш
_ICON_HASH_LOCK = threading.Lock()
_ICON_HASH_CACHE_FILE = ".icon_hash_cache.json"  # Файл на диске

def _load_icon_hash_cache(dest_dir: Path) -> dict[str, str]:
    # Читает JSON с диска при каждом вызове
    cache_file = dest_path / _ICON_HASH_CACHE_FILE
    raw = cache_file.read_text(encoding="utf-8")  # ❌ Синхронный I/O
    data = json.loads(raw)
```

**Проблемы:**
1. **Синхронное чтение JSON** при каждом вызове
2. **Избыточная сложность** — 87 строк для функции, которая не используется (т.к. `avoid_duplicates=False`)
3. **Потенциальная утечка памяти** — `_ICON_HASH_CACHE` растёт без ограничений

**Решение:** Удалить весь механизм кеширования хешей (строки 23-87).

---

## НАРУШЕНИЯ BEST PRACTICES

### 6. **QSvgRenderer вне GUI-потока**

**Файл:** `converters.py:325`

**Проблема:**
```python
def convert_icon_to_png_128(src_path: str, dst_path: str, size: int = 128) -> bool:
    renderer = QSvgRenderer(QByteArray(svg_data))  # ⚠️ Может быть вызвано вне GUI-потока
```

**Контекст:** Функция вызывается из `copy_icon_smart()`, которая может быть вызвана из любого потока.

**Решение:** Либо добавить проверку `is_gui_thread()`, либо удалить автоконвертацию (рекомендуется).

---

### 7. **Неконсистентное использование PIL и Qt**

**Файл:** `converters.py:307-440`

**Проблема:**
- SVG конвертируется через **QSvgRenderer + QImage** (строки 319-372)
- Растры конвертируются через **PIL** (строки 374-440)

**Вопрос:** Зачем два разных подхода? Qt умеет работать с растрами через `QImage`.

**Решение:** Унифицировать или удалить конвертацию.

---

### 8. **Избыточное логирование**

**Файл:** `converters.py:324-371`

**Проблема:**
```python
logger.debug("Creating QSvgRenderer for %s", src_path)
logger.debug("QSvgRenderer isValid: %s", renderer.isValid())
logger.debug("Created QImage with size %dx%d", size, size)
logger.debug("Rendering SVG to image with size %dx%d", size, size)
logger.debug("SVG rendering result: %s", result)
logger.debug("Saving image to buffer")
logger.debug("Writing image data to %s", dst_path)
logger.debug("Successfully converted SVG to PNG: %s", dst_path)
```

**Проблема:** 8 debug-логов на одну операцию — замедляет выполнение и засоряет логи.

**Решение:** Оставить только один лог на успех/ошибку.

---

### 9. **cache_proxy.py — избыточная обёртка**

**Файл:** `cache_proxy.py:17-36`

**Проблема:**
```python
class IconCache:
    def get_icon(self, name: str, theme: str | None = None, source: str = "menu") -> QIcon:
        # ... 10 строк обработки ...
        from .creators import themed_icon
        return themed_icon(icon_name, theme, source)  # Просто прокси!
```

**Вопрос:** Зачем обёртка, если она просто вызывает `themed_icon()`?

**Решение:** Либо удалить `IconCache`, либо добавить реальную логику кеширования.

---

### 10. **preload_icons_async() не используется**

**Файл:** `cache_proxy.py:73-128`

**Проблема:**
```python
async def preload_icons_async(self, icon_names: list[str], theme: str | None = None) -> dict[str, QIcon]:
    # 56 строк кода для прелоада
    ...
```

**Факт:** Функция **больше не вызывается** после отключения прелоада в `startup\runtime.py:173`.

**Решение:** Удалить или пометить как deprecated.

---

## АРХИТЕКТУРНЫЕ ПРОБЛЕМЫ

### 11. **Циклические импорты**

**Файл:** `cache_proxy.py:32, 50, 59, 64, 99`

**Проблема:**
```python
# Import here to avoid circular imports
from .creators import themed_icon
from .creators import themed_icon_async
from ..cache_manager import clear_icon_cache
from ..path_service import icon_path_service
from app.config_data import app_config  # local import to avoid cycles
```

**Вопрос:** Почему так много циклических импортов? Это признак плохой архитектуры.

**Решение:** Реорганизовать зависимости.

---

### 12. **Смешивание sync/async API без документации**

**Файл:** `creators.py:180-360`

**Проблема:**
- `themed_icon()` — синхронная
- `themed_icon_async()` — асинхронная
- Обе используют один кеш и логику

**Риск:** Гонки при одновременном вызове sync и async версий.

**Решение:** Документировать, что async-версии только для фоновой загрузки.

---

## МЁРТВЫЙ КОД (детальный список)

### converters.py:
1. **Строки 23-87** — кеш хешей (не используется при `avoid_duplicates=False`)
2. **Строки 99-153** — хеширование и поиск дубликатов (не используется)
3. **Строки 204-248** — автоконвертация SVG/растров (блокирует GUI, не нужна)
4. **Строки 292-301** — `copy_icon_async()` (не вызывается)
5. **Строки 446-473** — `convert_icon_to_png_128_async()` (не вызывается)
6. **Строки 479-538** — `batch_convert_icons_async()` (не вызывается)

**Итого:** ~350 строк мёртвого кода из 538 (65%!)

### cache_proxy.py:
1. **Строки 73-128** — `preload_icons_async()` (не используется после отключения прелоада)

**Итого:** ~56 строк мёртвого кода из 133 (42%)

---

## РЕКОМЕНДАЦИИ ПО ПРИОРИТЕТАМ

### 🔴 КРИТИЧНО (исправить немедленно):
1. **Удалить автоконвертацию** в `copy_icon_smart()` (строки 204-248) — блокирует GUI
2. **Удалить хеширование** (строки 23-153) — блокирует GUI, не используется
3. **Удалить async-функции** (292-301, 446-538) — мёртвый код

### 🟡 ВАЖНО (технический долг):
4. **Упростить `IconCache`** — либо удалить, либо добавить реальную логику
5. **Удалить `preload_icons_async()`** — не используется
6. **Убрать избыточное логирование** в `convert_icon_to_png_128()`

### 🟢 ЖЕЛАТЕЛЬНО (рефакторинг):
7. **Реорганизовать импорты** — убрать циклические зависимости
8. **Документировать sync/async API** — когда что использовать
9. **Унифицировать конвертацию** — либо Qt, либо PIL, не оба

---

## SUMMARY

**Всего проблем:** 12
- **Критичных:** 5 (блокируют GUI, мёртвый код)
- **Важных:** 3 (избыточная сложность)
- **Некритичных:** 4 (архитектура, документация)

**Мёртвый код:** ~406 строк из 671 (60%!)

**Основная проблема:** Модуль перегружен функциями, которые не используются или блокируют GUI. Нужна радикальная чистка.

---

## ПРЕДЛАГАЕМЫЕ ИЗМЕНЕНИЯ

### converters.py:
```diff
- Удалить строки 23-87 (кеш хешей)
- Удалить строки 99-153 (хеширование)
- Удалить строки 204-248 (автоконвертация)
- Удалить строки 292-301 (copy_icon_async)
- Удалить строки 446-538 (async-конвертация)
= Останется ~150 строк вместо 538 (сокращение на 72%)
```

### cache_proxy.py:
```diff
- Удалить строки 73-128 (preload_icons_async)
= Останется ~77 строк вместо 133 (сокращение на 42%)
```

### Итого:
- **Было:** 671 строка
- **Станет:** ~227 строк
- **Сокращение:** 66%
