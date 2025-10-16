# Руководство по обработке исключений

## Проблема

В кодовой базе обнаружено множество случаев подавления исключений:

```python
except Exception:
    pass  # ❌ Плохо: скрывает реальные проблемы
```

Это затрудняет диагностику ошибок и может скрывать критичные проблемы в runtime.

## Категории обработки исключений

### 1️⃣ **Критичные операции** - ВСЕГДА логировать

```python
# ❌ Плохо
try:
    self.window.destroyed.connect(self._disconnect_language_service)
except Exception:
    pass

# ✅ Хорошо
try:
    self.window.destroyed.connect(self._disconnect_language_service)
except (TypeError, RuntimeError) as e:
    logger.warning(
        "WindowUISetup: failed to connect destroyed cleanup: %s",
        e,
        exc_info=True
    )
```

**Когда применять:**
- Подключение сигналов/слотов
- Инициализация компонентов
- Cleanup операции

### 2️⃣ **Операции с Qt объектами** - Специфичные исключения

```python
# ❌ Плохо
try:
    widget.setVisible(False)
except Exception:
    pass

# ✅ Хорошо
try:
    widget.setVisible(False)
except (RuntimeError, AttributeError) as e:
    # RuntimeError: wrapped C/C++ object has been deleted
    # AttributeError: widget is None
    logger.debug(
        "NarrowMode: failed to hide widget (may be deleted): %s",
        e
    )
```

**Типичные Qt исключения:**
- `RuntimeError` - объект удалён
- `AttributeError` - атрибут отсутствует
- `TypeError` - неверный тип

### 3️⃣ **Вычисления и конверсии** - Fallback значения

```python
# ❌ Плохо
try:
    spacing = int(ctx.top_bar.spacing() or 0)
except Exception:
    spacing = 6

# ✅ Хорошо
try:
    spacing = int(ctx.top_bar.spacing() or 0)
except (TypeError, ValueError, AttributeError) as e:
    logger.debug(
        "LayoutService: failed to get spacing, using fallback: %s",
        e
    )
    spacing = C.LAYOUT_SPACING_FALLBACK  # Из констант
```

### 4️⃣ **Метрики и диагностика** - Можно подавлять

```python
# ✅ Допустимо (некритичная операция)
try:
    dur = (time.perf_counter() - t_start) * 1000.0
    logger.info("TopPanelMetrics: setup_search_widget: %.1f ms", dur)
except Exception:
    pass  # Метрики не критичны
```

**Когда допустимо:**
- Логирование метрик
- Debug-диагностика
- Опциональные фичи

### 5️⃣ **Defensive programming** - С комментариями

```python
# ✅ Хорошо (с объяснением)
try:
    if b.isVisible():
        visible += 1
except (RuntimeError, AttributeError):
    # Кнопка может быть удалена во время итерации
    pass
```

## Иерархия логирования

### По уровню критичности

```python
# 🔴 CRITICAL/ERROR - Неожиданные ошибки
except Exception as e:
    logger.error("Unexpected error: %s", e, exc_info=True)

# 🟡 WARNING - Ожидаемые проблемы
except (RuntimeError, AttributeError) as e:
    logger.warning("Expected Qt error: %s", e)

# 🟢 DEBUG - Некритичные проблемы
except (TypeError, ValueError) as e:
    logger.debug("Minor issue: %s", e)

# ⚪ PASS - Только для некритичных операций
except Exception:
    pass  # Только если действительно некритично!
```

## Паттерны исправления

### Паттерн 1: Сужение типов

```python
# До
except Exception:
    pass

# После
except (RuntimeError, AttributeError):
    pass
```

### Паттерн 2: Добавление логирования

```python
# До
except Exception:
    pass

# После
except Exception as e:
    logger.debug("Operation failed: %s", e, exc_info=True)
```

### Паттерн 3: Разделение на ожидаемые/неожиданные

```python
# До
except Exception as e:
    logger.debug("Failed: %s", e)

# После
except (RuntimeError, AttributeError) as e:
    # Ожидаемые Qt ошибки
    logger.debug("Qt object error (expected): %s", e)
except Exception as e:
    # Неожиданные ошибки
    logger.error("Unexpected error: %s", e, exc_info=True)
```

## Примеры исправлений

### Пример 1: Подключение сигналов

```python
# ❌ До (window_ui_setup.py:505)
try:
    self._language_service.languageChanged.disconnect(self._on_language_changed)
except Exception:
    pass

# ✅ После
try:
    self._language_service.languageChanged.disconnect(self._on_language_changed)
except (TypeError, RuntimeError) as e:
    # TypeError: signal not connected
    # RuntimeError: object deleted
    logger.debug(
        "WindowUISetup: failed to disconnect languageChanged (already disconnected): %s",
        e
    )
```

### Пример 2: Операции с виджетами

```python
# ❌ До (narrow_mode_service.py:97)
try:
    widget.setVisible(False)
except Exception:
    pass

# ✅ После
try:
    widget.setVisible(False)
except (RuntimeError, AttributeError) as e:
    logger.debug(
        "NarrowMode: failed to hide widget %s (may be deleted): %s",
        getattr(widget, 'objectName', lambda: 'unknown')(),
        e
    )
```

### Пример 3: Вычисления

```python
# ❌ До (search_manager.py:224)
try:
    w_hint = int(widget.sizeHint().width())
except Exception:
    w_hint = 0

# ✅ После
try:
    w_hint = int(widget.sizeHint().width())
except (RuntimeError, AttributeError, TypeError) as e:
    # RuntimeError: widget deleted
    # AttributeError: sizeHint() unavailable
    # TypeError: width() returned non-int
    logger.debug(
        "SearchWidgetManager: failed to get widget width, using 0: %s",
        e
    )
    w_hint = 0
```

### Пример 4: Итерация по коллекциям

```python
# ❌ До (top_bar_layout_manager.py:320)
try:
    if b.isVisible():
        visible += 1
except Exception:
    pass

# ✅ После
try:
    if b.isVisible():
        visible += 1
except (RuntimeError, AttributeError):
    # Кнопка удалена во время итерации или b is None
    logger.debug(
        "TopBarLM: button unavailable during iteration (deleted or None)"
    )
```

## Контрольный список

При обработке исключений проверьте:

- [ ] **Тип исключения**: Используются ли специфичные типы вместо `Exception`?
- [ ] **Логирование**: Есть ли логирование для неожиданных ошибок?
- [ ] **Уровень логирования**: Соответствует ли уровень критичности?
- [ ] **Контекст**: Достаточно ли информации для диагностики?
- [ ] **Fallback**: Есть ли безопасное значение по умолчанию?
- [ ] **Комментарий**: Объяснено ли, почему исключение подавляется?

## Рекомендуемые типы исключений

### Qt-специфичные

```python
RuntimeError       # Qt object deleted
AttributeError     # Missing attribute/method
TypeError          # Wrong type passed to Qt
ValueError         # Invalid value for Qt property
```

### Python стандартные

```python
KeyError           # Missing dict key
IndexError         # Invalid list index
ZeroDivisionError  # Division by zero
FileNotFoundError  # File operations
```

### Сигналы/слоты

```python
TypeError          # Signal not connected
RuntimeError       # Object deleted during signal
```

## Инструменты для проверки

### Поиск проблемных мест

```bash
# Найти все "except Exception: pass"
ruff check --select=BLE001,S110

# Найти все голые except
ruff check --select=E722
```

### Автоматическое исправление

```bash
# Добавить логирование
ruff check --select=BLE001 --fix
```

## Метрики качества

### Целевые показатели

- **Голые `except:`** → 0
- **`except Exception: pass`** → < 5% (только для метрик/диагностики)
- **`except Exception:` с логированием** → > 95%
- **Специфичные типы исключений** → > 80%

### Текущее состояние (до исправлений)

Обнаружено ~50+ случаев подавления исключений в topbar модуле.

## Приоритеты исправления

### 🔴 Высокий приоритет

1. Подключение сигналов/слотов
2. Инициализация компонентов
3. Cleanup операции
4. Операции с данными

### 🟡 Средний приоритет

5. Операции с виджетами
6. Вычисления с fallback
7. Итерации по коллекциям

### 🟢 Низкий приоритет

8. Метрики и диагностика
9. Debug-логирование
10. Опциональные фичи

## Связанные документы

- Python PEP 8: Error handling
- Qt Best Practices: Exception safety
- Logging Best Practices

## Заключение

**Золотое правило**: Если вы пишете `except Exception: pass`, спросите себя:

1. Действительно ли эта операция некритична?
2. Не скрою ли я реальный баг?
3. Смогу ли я продиагностировать проблему позже?

Если хотя бы на один вопрос ответ "нет" → добавьте логирование!
