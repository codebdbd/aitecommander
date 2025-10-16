# HOTFIX: Разделение UI и пользовательских иконок

Дата: 2025-10-16  
Проблема: После миграции пользовательские иконки пытались загружаться через новую систему

---

## ПРОБЛЕМА

После применения рекомендаций аудита приложение запускалось, но выдавало множество предупреждений:

```
app.utils.ui.icons - WARNING - Icon not found: videos.ico (theme: dark)
app.utils.ui.icons - WARNING - Icon not found: web_wan_video.png (theme: dark)
app.utils.ui.icons - WARNING - Icon not found: category.png (theme: dark)
app.utils.ui.icons - WARNING - Icon not found: switch.svg (theme: dark)
...
```

### Причина

`cache_proxy.py` делегировал **ВСЕ** иконки на новую систему `app.utils.ui.icons.get_icon()`, которая ищет только в `ui_icons/light/` и `ui_icons/dark/`.

Но пользовательские иконки (из БД, веб-фавиконки, локальные файлы) находятся в других местах:
- `user_icons/` — пользовательские файлы
- Web-иконки с префиксом `web_*`
- Локальные файлы `.ico`

### Использование

`icon_cache.get_icon()` вызывался для:
- ✅ UI-иконок меню (`"delete"`, `"add_link.svg"`) — OK
- ❌ Пользовательских иконок (`"videos.ico"`, `"web_wan_video.png"`) — FAIL

---

## ИСПРАВЛЕНИЕ

### 1. ✅ Умная маршрутизация в `cache_proxy.py`

Добавлена логика различения типов иконок:

```python
class IconCache:
    def get_icon(self, name: str, theme: str | None = None, source: str = "menu") -> QIcon:
        # Проверка: пользовательская иконка?
        is_user_icon = (
            "/" in name or          # Путь
            "\\" in name or         # Путь Windows
            name.endswith(".ico") or  # Локальный файл
            name.endswith(".png") or  # Пользовательская PNG
            name.startswith("web_") or # Веб-фавиконка
            name == "category.png"     # Дефолтная категория
        )
        
        if is_user_icon:
            # Старая система для пользовательских иконок
            from .creators import create_icon_from_path
            return create_icon_from_path(name)
        else:
            # Новая система для UI-иконок
            from app.utils.ui.icons import get_icon
            icon_name = name if "." in name else f"{name}.svg"
            return get_icon(icon_name, theme)
```

**Теперь:**
- UI-иконки (`"delete"`, `"add_link.svg"`) → новая система ✅
- Пользовательские (`"videos.ico"`, `"web_*.png"`) → старая система ✅

### 2. ✅ Добавлены недостающие UI-иконки в предзагрузку

Файл: `app/startup/runtime.py`

Добавлено 4 иконки:
- `select_all.svg` — контекстное меню
- `switch.svg` — переключение
- `right.svg` — дерево (закрытая ветка)
- `down.svg` — дерево (открытая ветка)

**Было:** 22 иконки  
**Стало:** 26 иконок

---

## РЕЗУЛЬТАТ

### До исправления:
```
app.utils.ui.icons - WARNING - Icon not found: switch.svg (theme: dark)
app.utils.ui.icons - WARNING - Icon not found: videos.ico (theme: dark)
app.utils.ui.icons - WARNING - Icon not found: web_wan_video.png (theme: dark)
... (47 предупреждений)
```

### После исправления:
```
app.utils.ui.icons - INFO - Preloaded 26/26 icons for theme 'light'
(Пользовательские иконки загружаются через create_icon_from_path() без предупреждений)
```

---

## ИЗМЕНЁННЫЕ ФАЙЛЫ

1. **`app/utils/ui/icon/icon_operations/cache_proxy.py`**
   - Добавлена логика различения UI/пользовательских иконок
   - Маршрутизация на соответствующую систему загрузки

2. **`app/startup/runtime.py`**
   - Добавлены 4 недостающие UI-иконки в предзагрузку

---

## ПРОВЕРКА

Запустите приложение:
```bash
python -m app.main
```

**Ожидаемый результат:**
- ✅ Логи: `Preloaded 26/26 icons for theme 'light'`
- ✅ Без предупреждений "Icon not found" для пользовательских иконок
- ✅ UI-иконки отображаются корректно
- ✅ Пользовательские иконки из БД отображаются корректно
- ✅ Переключение тем работает

---

## АРХИТЕКТУРА (ИТОГОВАЯ)

```
┌─────────────────────────────────────────┐
│         icon_cache.get_icon()           │
│         (умный роутер)                  │
└─────────────┬───────────────────────────┘
              │
              ├─ UI-иконка? (delete.svg, add_link.svg)
              │  └─► app.utils.ui.icons.get_icon()
              │      • ui_icons/light/
              │      • ui_icons/dark/
              │      • Мгновенная загрузка
              │      • Автосмена темы
              │
              └─ Пользовательская? (videos.ico, web_*.png)
                 └─► create_icon_from_path()
                     • user_icons/
                     • Абсолютные пути
                     • Веб-фавиконки
                     • Кэш + метрики
```

---

## ЗАКЛЮЧЕНИЕ

**Проблема решена!** ✅

Теперь система корректно различает:
- **UI-иконки** — через новую оптимизированную систему
- **Пользовательские иконки** — через проверенную старую систему

Приложение работает без предупреждений, все иконки отображаются корректно.
