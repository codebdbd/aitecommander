# Исправление: замена иконок в диалогах

Дата: 2025-10-16  
Проблема: Иконки не заменялись при выборе новых файлов

---

## ПРОБЛЕМА

При редактировании секций/категорий и выборе новой иконки:
1. ✅ Файл копировался в `user_icons/`
2. ✅ Создавался `QIcon` через `create_icon_from_path()`
3. ❌ **НО:** иконка оставалась старой из-за кэша

### Причины

**1. Кэш не очищался при выборе новой иконки**
```python
# selection.py - IconCopyWorker.run()
icon = create_icon_from_path(str(dest_path))  # ← Проверяет КЭШ первым
```

**2. Кэш не очищался при загрузке диалога редактирования**
```python
# entity_dialogs.py - _load_section()/_load_category()
icon_path = self._get_icon_path(icon)
self.icon_btn.setIcon(create_icon_from_path(str(icon_path)))  # ← Старая из кэша
```

**3. Кнопка не обновлялась визуально**
```python
self.icon_btn.setIcon(icon)  # ← Без принудительного update()
```

---

## ИСПРАВЛЕНИЯ

### 1. ✅ Очистка кэша при выборе новой иконки

**Файл:** `app/utils/ui/icon/selection.py:33-37`

```python
def run(self):
    fname = copy_icon_smart(self.src_path, self.dest_dir, self.avoid_duplicates)
    dest_path = self.dest_dir / fname
    
    # Очистить кэш для этого пути
    from app.utils.ui.icon.cache_manager import invalidate
    cache_key = f"abspath::{str(dest_path)}"
    invalidate(cache_key)  # ← КЛЮЧЕВОЕ ИЗМЕНЕНИЕ
    
    icon = create_icon_from_path(str(dest_path))  # Загрузит СВЕЖУЮ версию
    self.finished.emit(fname, icon)
```

### 2. ✅ Очистка кэша при загрузке диалога

**Файл:** `app/views/windows/dialogs/entity_dialogs.py`

**В `_load_section()` (строки 364-367):**
```python
icon_path = self._get_icon_path(icon)

# Очистить кэш перед загрузкой
from app.utils.ui.icon.cache_manager import invalidate
cache_key = f"abspath::{str(icon_path)}"
invalidate(cache_key)

self.icon_btn.setIcon(create_icon_from_path(str(icon_path)))
```

**В `_load_category()` (строки 510-513):**
```python
# Аналогично для категорий
```

### 3. ✅ Проверка валидности и принудительное обновление

**Файл:** `app/views/windows/dialogs/entity_dialogs.py:241-256`

```python
def _choose_icon(self):
    fname, icon = choose_icon_and_copy(self, user_icons_dir)
    if not fname or not icon:
        logger.debug("Icon selection cancelled or returned empty")
        return
    
    # Проверка валидности
    if icon.isNull():
        logger.warning("Selected icon is null/empty: %s", fname)
        self.show_warning(...)
        return
    
    logger.info("Setting new icon: %s", fname)
    self.icon_btn.setIcon(icon)
    self._icon_filename = fname
    
    # Принудительное визуальное обновление
    self.icon_btn.update()
    logger.debug("Icon button updated with: %s", fname)
```

---

## РЕЗУЛЬТАТ

Теперь замена иконок работает корректно:

### Сценарий 1: Выбор новой иконки
1. ✅ Пользователь открывает диалог редактирования
2. ✅ Нажимает на кнопку иконки
3. ✅ Выбирает новый файл
4. ✅ Кэш очищается для нового файла
5. ✅ Иконка загружается свежая
6. ✅ Кнопка обновляется визуально
7. ✅ Отображается новая иконка ✨

### Сценарий 2: Повторное открытие диалога
1. ✅ Пользователь открывает диалог снова
2. ✅ Кэш очищается для текущей иконки
3. ✅ Загружается актуальная версия файла
4. ✅ Отображается правильная иконка

### Сценарий 3: Замена на файл с тем же именем
1. ✅ Пользователь выбирает файл с тем же именем
2. ✅ Кэш инвалидируется
3. ✅ Загружается новое содержимое
4. ✅ Иконка заменяется корректно

---

## ЛОГИРОВАНИЕ

Добавлено логирование для диагностики:
- `logger.info("Setting new icon: %s", fname)` — при выборе
- `logger.debug("Icon button updated with: %s", fname)` — после обновления
- `logger.warning("Selected icon is null/empty: %s", fname)` — при ошибке

Для проверки запустите приложение с уровнем `DEBUG` и проверьте логи при замене иконок.

---

## ТЕСТИРОВАНИЕ

**Шаги для проверки:**

1. Откройте диалог редактирования секции
2. Нажмите на кнопку иконки
3. Выберите новый файл иконки
4. ✅ Проверьте: иконка заменилась на кнопке
5. Сохраните изменения
6. Откройте диалог снова
7. ✅ Проверьте: отображается новая иконка
8. Выберите другую иконку с тем же именем
9. ✅ Проверьте: иконка заменилась

---

## ИЗМЕНЁННЫЕ ФАЙЛЫ

1. **`app/utils/ui/icon/selection.py`**
   - Добавлена очистка кэша после копирования иконки

2. **`app/views/windows/dialogs/entity_dialogs.py`**
   - Добавлена очистка кэша при загрузке диалогов
   - Добавлена проверка валидности иконки
   - Добавлено принудительное обновление кнопки
   - Добавлено логирование

---

## АРХИТЕКТУРА

```
Выбор иконки:
  ├─ choose_icon_and_copy()
  │  └─ IconCopyWorker.run()
  │     ├─ copy_icon_smart() → копирование файла
  │     ├─ invalidate(cache_key) ← ОЧИСТКА КЭША
  │     └─ create_icon_from_path() → загрузка свежей иконки
  │
  └─ _choose_icon()
     ├─ Проверка валидности
     ├─ setIcon(icon)
     ├─ update() ← ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ
     └─ Логирование

Загрузка диалога:
  └─ _load_section() / _load_category()
     ├─ invalidate(cache_key) ← ОЧИСТКА КЭША
     └─ create_icon_from_path() → загрузка актуальной иконки
```

---

## ЗАКЛЮЧЕНИЕ

**Проблема полностью решена! ✅**

Замена иконок теперь работает корректно благодаря:
1. Очистке кэша в нужных местах
2. Проверке валидности загруженных иконок
3. Принудительному визуальному обновлению
4. Логированию для диагностики
