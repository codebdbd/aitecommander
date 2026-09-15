# Анализ поведения верхней панели при сжатии окна

> Дата: 2026-09-15
> Статус: **АКТУАЛЬНО** — проверено против реального кода

---

## Что сейчас происходит (поток выполнения)

При изменении размера окна **три независимых механизма** реагируют без какой-либо координации:

### 1. `_AutoHideTreeFilter` — грубое скрытие по порогу
Файл: [`window_ui_setup.py`](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L179-L340)

```
Resize событие на окне
├─> Сразу (без throttle): w <= threshold?
│   ├─ ДА (узкое окно):
│   │   ├─ Сохранить состояние splitter/stack
│   │   ├─ splitter.setSizes([0, w]) — схлопнуть дерево
│   │   ├─ Переключиться на table view (опционально)
│   │   └─ top_bar_toolbar.setVisible(False) — ПОЛНОСТЬЮ скрыть ВСЮ панель кнопок (опционально)
│   └─ НЕТ (широкое окно, если было схлопнуто):
│       ├─ Восстановить splitter sizes
│       ├─ top_bar_toolbar.setVisible(True) — показать панель
│       └─ Восстановить stack index
```

Код (строки 331-334):
```python
if w <= self.threshold:
    self._handle_narrow_window(splitter, stack, table, w)
elif w > self.threshold and self._is_collapsed:
    self._handle_wide_window(splitter, stack)
```
⚠️ **Нет гистерезиса** — одинаковый порог `threshold` для входа и выхода.

### 2. Встроенный `QToolBar` overflow (троеточие)
Файл: [`top_bar_setup.py`](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L139-L170)

`QToolBar` имеет встроенный механизм переполнения: когда места не хватает, не поместившиеся `QAction` попадают в выпадающее меню по кнопке `qt_toolbar_ext_button` (троеточие).

### 3. `_ExtButtonAligner` — хак выравнивания троеточия
Файл: [`top_bar_setup.py`](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L22-L61)

EventFilter на `LayoutRequest/Resize` → `QTimer.singleShot(0)` → вручную двигать геометрию `qt_toolbar_ext_button`, потому что Qt не центрирует его правильно.

### 4. `_WindowSettingsFilter` — сохранение геометрии
Файл: [`window_ui_setup.py`](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L342-L400)

Resize → 300ms debounce → сохранить размеры/позицию в SettingsManager.

---

## КРИТИЧЕСКОЕ: Неиспользуемая адаптивная логика

В [`_init_and_schedule_topbar_manager()`](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L522-L561):

```python
def _init_and_schedule_topbar_manager(self) -> None:
    if self._uses_toolbar_topbar():
        self.window._topbar_manager = None  # <-- ВСЯ СЛОЖНАЯ ЛОГИКА ОТКЛЮЧЕНА
        return
    # ... TopBarLayoutManager создается только для legacy-варианта без QToolBar
```

✅ **Подтверждено кодом** (строка 524): при использовании `QToolBar`-based верхней панели `TopBarLayoutManager` и вся его сложная адаптивная логика **НЕ ИСПОЛЬЗУЕТСЯ** — `_topbar_manager = None`.

**Весь стек сервисов** (`TopBarLayoutManager` → `LayoutOrchestrator` → `NarrowModeService`, `VisibilitySolver`, `HysteresisService`, `SearchWidgetManager` и ещё ~10 сервисов) написан, протестирован, но **не активируется** при текущей `QToolBar`-реализации. Это **15+ файлов кода**, которые мертвым грузом лежат в проекте.

---

## Отличия от лучших практик

### 🔴 Проблема 1: Бинарное поведение вместо градиентного
**Что есть:** При достижении `threshold_width` верхняя панель **целиком исчезает** (`setVisible(False)`). Переход резкий, бинарный — нет промежуточных состояний.

**Best Practice:** Плавная деградация по стадиям:
1. **Широкое окно** → все кнопки видны
2. **Среднее окно** → менее приоритетные группы (Recent → Favorites) постепенно убираются в overflow одной за другой
3. **Узкое окно** → остаются только Quick Add + Search, остальные в overflow
4. **Очень узкое** → только Search, остальные доступны через единый overflow button

**Почему это плохо:** Пользователь теряет доступ ко всем быстрым действиям сразу, даже если для части из них место ещё есть.

---

### 🔴 Проблема 2: Нет координации между обработчиками
Три независимых слушателя на `Resize`:
- `_AutoHideTreeFilter` — срабатывает **мгновенно**
- Встроенный QToolBar overflow — работает **сам по себе**
- `_WindowSettingsFilter` — 300ms debounce

**Риск гонок:** `_AutoHideTreeFilter` вызывает `setSizes()` / `setVisible()`, что триггерит **вторую волну** Layout/Resize событий. Эти вторичные события снова попадают в те же фильтры. Нет единого источника истины о том, как должен выглядеть top bar при текущей ширине.

**Best Practice:** Единственный координатор resize-логики, который принимает решения на основе ширины и **последовательно** применяет изменения:
```
Window resize → Throttle (16ms) → Single Coordinator → Decision → Atomic apply
```

---

### 🔴 Проблема 3: Неправильный приоритет скрытия (QToolBar default)
Встроенный `QToolBar` overflow убирает кнопки **справа налево** в порядке добавления. У вас порядок:
```
[Quick Add] | [Favorites] | [Recent]
```
При нехватке места сначала пропадут **Recent**, потом **Favorites** — и это правильно по неявному приоритету. Но нет **явных гарантий** и **настраиваемых приоритетов**.

**Best Practice:** Явный priority-order на каждую группу/кнопку + стратегия (round-robin / weighted / ranked):
| Приоритет | Группа | Политика |
|---|---|---|
| 1 (последним убирать) | Quick Add | Всегда виден или в overflow последним |
| 2 | Favorites | Убирать по одной с конца |
| 3 (первым убирать) | Recent | Убирать в overflow первым |

---

### 🔴 Проблема 4: Отсутствие гистерезиса на верхнем уровне
У `TopBarLayoutManager` есть продуманный `HysteresisService`, но он не используется. А у `_AutoHideTreeFilter` его **вообще нет**.

**Проблема:** При ширине окна ровно на границе `threshold_width` происходит **дребезг**: пользователь слегка двигает границу окна на 1px — панель показывается/скрывается многократно.

✅ **Подтверждено кодом** (window_ui_setup.py, стр. 331-334): используется одиночный порог `self.threshold` без гистерезиса.

**Best Practice:**
```python
# Пороги должны быть разными для входа и выхода из narrow mode
ENTER_NARROW = 500   # w <= 500 → включаем
EXIT_NARROW = 560    # w >= 560 → выключаем (гистерезис 60px)
```

Это уже реализовано в `HysteresisService`, но не задействовано.

---

### 🔴 Проблема 5: Поисковая строка не адаптируется при toolbar-варианте
В неиспользуемом `TopBarLayoutManager` есть `SearchWidgetManager.clamp_width()` — он зажимает ширину поиска в диапазон `[min_search_width, max_search_width]`, перераспределяя свободное место между поиском и кнопками.

**Что сейчас есть при QToolBar:** Поисковая строка сжимается **до тех пор, пока не исчезнет совсем** или пока тулбар не скроется целиком. Нет минимальной гарантированной ширины поиска.

**Best Practice:** Приоритет ширины:
1. Поисковая строка держится в `[MIN_SEARCH, MAX_SEARCH]` (например [180px, 400px])
2. Если не хватает места — сначала убираем кнопки в overflow
3. Только когда все кнопки в overflow — начинаем сжимать поиск ниже MIN_SEARCH

---

### 🔴 Проблема 6: Отсутствие анимаций — резкие скачки
`setVisible(True/False)` происходит мгновенно. Визуально это выглядит как "мигание" при пересечении порога.

**Best Practice:** Плавный переход через:
- `QPropertyAnimation` на `windowOpacity` (0→1 за 150ms)
- Или анимация `maximumWidth` с 0 → target для "выкатывания"
- Или `QGraphicsOpacityEffect` для отдельных элементов

В Qt это стандартная практика — даже в File Explorer, VS Code, Finder элементы тулбара исчезают плавно.

---

### 🟡 Проблема 7: Хак с `_ExtButtonAligner`
EventFilter + `singleShot(0)` + ручное `setGeometry()` для `qt_toolbar_ext_button`. Это workaround для известного бага Qt, но:
- Вызывает лишний layout pass
- Может сломаться при обновлении версии PyQt6
- Объект `qt_toolbar_ext_button` — внутренний detail реализации Qt

**Best Practice:**
- Либо использовать собственный overflow button (добавить `QToolButton` с `popupMode=InstantPopup`)
- Либо сделать override `resizeEvent()` у кастомного `QToolBar` наследника и вызывать `updateGeometry()`

---

### 🟡 Проблема 8: `threading.Lock` в GUI потоке
✅ **Подтверждено кодом** в двух местах:
1. [`layout_orchestrator.py:89`](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/services/layout_orchestrator.py#L89-L90)
2. [`topbar_controller.py:90`](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/controllers/topbar_controller.py#L90-L91)

```python
self._adjust_lock = threading.Lock()
self._adjust_running = False
```

GUI Qt работает строго в одном потоке. `threading.Lock` здесь избыточен и добавляет лишний оверхед. Достаточно простого `self._adjust_running: bool`.

---

### 🟡 Проблема 9: Жадный алгоритм по умолчанию
✅ **Подтверждено кодом** ([visibility_solver.py:15](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/services/visibility_solver.py#L15)):
```python
def __init__(self, width_calculator: WidthCalculator, use_binary_search: bool = False) -> None:
```

Бинарный поиск (`O(log N)` width вычислений) реализован, но по умолчанию используется жадный алгоритм с пошаговым отниманием по одной кнопке — `O(K)` вычислений width, где K — общее число кнопок. При ~20 кнопках это 20x больше расчётов на каждый resize pass.

---

## Идеальный пайплайн (как лучше сделать)

```
┌─────────────────────────────────────────────────────────────┐
│                    Window Resize Event                      │
└────────────────────────────────┬────────────────────────────┘
                                 │
                                 ▼
                Throttle / Frame Align (16ms timer)
                ╘══> Один таймер на ВСЕ обработчики
                                 │
                                 ▼
                    Single Coordinator (LayoutService)
                    ├─ Считывает текущую ширину контейнера
                    ├─ Применяет hysteresis (два порога)
                    ├─ Приоритезационная упаковка:
                    │   1. Резервируем MIN_SEARCH_WIDTH для поиска
                    │   2. Резервируем MIN_VISIBLE для каждой панели
                    │   3. Оставшееся место распределяем по приоритетам
                    │      (Quick Add → Fav → Recent)
                    │   4. Если места всё ещё мало → включаем Narrow Mode
                    │      (скрываем ThemeSelector, разделители, Fav/Recent)
                    │   5. При крайней необходимости сжимаем поиск < MIN
                    │
                    ├─ Сокращает N панелей за 1 проход (binary search)
                    └─ Генерирует Immutable LayoutState (counts, widths, flags)
                                 │
                                 ▼
                    Atomic Apply (в одном event loop tick)
                    ├─ VisibilityManager.set_visible_counts(counts)
                    │   ╘══> Без setState-протаскивания, просто setVisible
                    ├─ SearchWidgetManager.clamp_width(search, target_w)
                    ├─ SeparatorService.apply(visible_separators)
                    ├─ NarrowModeService.apply(is_narrow)
                    └─ ★ QVariantAnimation на opacity (0.15s ease-out)
                                 │
                                 ▼
                    Debounced Persist (300ms)
                    ╘══> WindowSettingsFilter сохраняет геометрию
```

---

## Шаги исправления (приоритеты)

| Приоритет | Действие | Файлы для изменений |
|---|---|---|
| **P0** | **Подключить `TopBarLayoutManager`/`TopBarController` к `QToolBar`-варианту** — убрать `_uses_toolbar_topbar()` проверку или адаптировать `WidgetAccessor` под QToolBar | [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L522) |
| **P0** | **Добавить гистерезис** в `_AutoHideTreeFilter` или убрать его дублирование логики | [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L179-L340) |
| **P1** | Установить **единый throttle-таймер** на все resize-обработчики | `window_ui_setup.py`, `TopBarLayoutManager` |
| **P1** | Гарантировать **MIN_SEARCH_WIDTH** для поиска при QToolBar варианте | `top_bar_setup.py` + `WidgetAccessor` |
| **P2** | Добавить **анимации opacity** при смене видимости групп | `PanelVisibilityManager` |
| **P2** | Включить **binary search** по умолчанию в VisibilitySolver | [visibility_solver.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/services/visibility_solver.py#L15) |
| **P3** | Заменить `_ExtButtonAligner` хак на кастомный overflow button | [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L22-L61) |
| **P3** | Убрать `threading.Lock` в пользу простого bool-флага | `layout_orchestrator.py`, `topbar_controller.py` |

---

## Улучшения с точки зрения пользователей (UX)

Анализ сценариев использования и пользовательских болей на основе [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py), [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py) и [ui_config.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py).

---

### 🔴 КРИТИЧЕСКИЕ UX-проблемы (блокируют сценарии)

#### UX-1. Резкое исчезновение всей панели = потеря контекста
**Сценарий:** Пользователь работает с избранными ссылками, сужает окно, чтобы сравнить с другим приложением. **Все кнопки Fav/Recent исчезают мгновенно.**

**Проблема:**
- Нет промежуточных состояний — либо ВСЕ кнопки, либо НИ ОДНОЙ
- Переход не обратим легко: пользователь не помнит, какие ссылки были на панели
- Мышь была наведена на кнопку → исчезла → промах (fat finger)

**Данные из кода:** В [window_ui_setup.py:331-334](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L331-L334) бинарный порог без гистерезиса:
```python
if w <= self.threshold:
    _handle_narrow_window(...)  # setVisible(False) ВСЕЙ панели
elif w > self.threshold and self._is_collapsed:
    _handle_wide_window(...)
```

**Решение для пользователей:** 5 стадий градиентной деградации вместо 2:
| Уровень | Ширина | Состав top bar |
|---|---|---|
| 1 | 800px+ | Quick Add \| Fav (max 8) \| Recent (max 6) \| Поиск 320px \| Theme |
| 2 | 640-800px | Quick Add \| Fav 5 \| Recent 3 \| Поиск 240px \| Theme |
| 3 | 500-640px | Quick Add \| Fav 3 \| Поиск 200px \| ☰ overflow |
| 4 | 400-500px | Quick 2 \| Поиск 180px \| ☰ (Fav+Recent+Theme внутри) |
| 5 | <400px | Только Поиск + ☰ (всё остальное внутри) |

Каждый переход — плавная анимация opacity 0.15s (не мгновенное `setVisible`).

---

#### UX-2. Дребезг на границе порога — пользователь видит "мигание"
**Сценарий:** Пользователь тянул край окна и остановился ровно на `min_width` (280px по конфигу). Из-за погрешности отрисовки окно на 1px прыгает вокруг порога.

**Проблема:** Top bar мигает видимым/невидимым 5-10 раз в секунду — отвлекает, вызывает раздражение.

**Данные из кода:**
- Порог входа и выхода — **один и тот же** `self.threshold`
- У `_AutoHideTreeFilter` нет `debounce/throttle` — каждый Resize тут же применяет изменения

**Решение:** Двойной порог (гистерезис):
```
Вход в "узкий режим":  width ≤ 480
Выход из "узкого":    width ≥ 540  (запас 60px)
```

Это уже **написано** в `HysteresisService`, просто не подключен.

---

#### UX-3. Поисковая строка сжимается до неработоспособности
**Сценарий:** Пользователь хочет найти ссылку в узком окне.

**Проблема:** Search `min_width=148px` по конфигу ([ui_config.py:365-367](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py#L365-L367)). Но при `<280px` окне + Quick Add кнопки занимают ~180px → поиск реально становится **меньше 100px**, в нём не видно даже 10 символов ввода.

**Пользовательская боль:**
- Введённый текст не читается
- Иконка поиска (`search.svg`) + крестик очистки `search_off.svg` занимают ~40px → текстовая зона ~60px

**Решение:**
- Гарантированный **жесткий минимум поиска: 160px**. Если места нет — сначала убираем Fav/Recent, потом Theme, потом Quick (кроме 1 главной кнопки).
- При `<400px` окне — **поиск на всю ширину** (`Expanding`), а Quick/Fav/Recent — только в overflow меню ☰.

---

### 🟡 СРЕДНИЕ UX-проблемы (ухудшают опыт, но не блокируют)

#### UX-4. Переполненное меню троеточия — нет группировки
**Сценарий:** На панели 5 Fav + 5 Recent = 10 кнопок, окно сжато. 8 кнопок попали в overflow (троеточие).

**Проблема:** Встроенный `QToolBar` overflow показывает **плоский список** без разделения на группы. Пользователь не различает Fav/Recent/Quick/Theme.

**Решение:** Кастомное overflow меню с разделителями и заголовками групп:
```
┌─ ☰ ─────────────────────┐
│  Быстрые действия       │
│  ─────────────────      │
│  ➕ Добавить ссылку     │
│  📁 Добавить раздел     │
│                          │
│  ⭐ Избранное            │
│  ─────────────────      │
│  📁 Работа              │
│  💼 Финансы             │
│  … +5 ещё               │  ← счётчик скрытых
│                          │
│  🕐 Недавнее             │
│  ─────────────────      │
│  📄 Договор.docx        │
│  … +3 ещё               │
│                          │
│  🎨 Тема: Dark          │
└─────────────────────────┘
```

Реализуется заменой встроенного `qt_toolbar_ext_button` на собственный `QToolButton` с `setMenu(...)`.

---

#### UX-5. Tooltip показывает только имя — не хватает деталей
**Сценарий:** Пользователь видит незнакомую иконку, наводит курсор.

**Проблема:** В [toolbar_adapters.py:333](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L333) тултип = только имя ссылки:
```python
action.setToolTip(name)  # "Рабочие документы"
```

Нет **пути** (раздел/категория), нет **даты открытия**, нет **URL/пути к файлу**. Имена ссылок часто совпадают — приходится кликать, чтобы понять что это.

**Решение (идеальный тултип):**
```
┌─────────────────────────────────────────────┐
│ 📄 Договор с ООО "Ромашка"                  │  ← жирный заголовок
│ ─────────────────────────────────           │
│ 📁 Раздел:  Работа → Документы → 2024       │  ← breadcrumb
│ 🕐 Открыто: Вчера, 17:42                     │  ← человеческое время
│ 📂 Путь:    C:\Docs\dogovor_romashka.docx   │  ← или URL
│                                              │
│ 🔗 F1 — открыть     Ctrl+C — копировать     │  ← шорткаты
└─────────────────────────────────────────────┘
```

В `toolbar_adapters.py:333` вместо `name` собираем многострочный `setToolTip()` с HTML-форматированием.

---

#### UX-6. Горячие клавиши на Fav/Recent не отражены и не работают
**Сценарий:** Опытный пользователь хочет открывать топ-5 избранных с клавиатуры.

**Проблема:** В [accessibility_manager.py:120-122](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/services/accessibility_manager.py#L120-L122) код предлагает шорткаты `Alt+N`, но это только **в AccessibleDescription**, **не реальные привязки**. Нет реального `QShortcut` → пользователь нажимает Alt+1 и ничего не происходит — разочарование.

**Решение:**
- Для первых 9 кнопок Fav + Recent сделать **реальные шорткаты**:
  - `Alt+1`…`Alt+5` → избранное 1-5
  - `Alt+Shift+1`…`Alt+Shift+4` → недавнее 1-4
- Отразить шорткат **в правом нижнем углу тултипа** (как показано в UX-5)
- Отобразить подсказку на самой кнопке при зажатом Alt (поверх иконки цифра-бейдж ⓵ ⓶ ⓷)

---

#### UX-7. Нет индикации загрузки/ошибок иконок
**Сценарий:** Пользователь только что добавил ссылку на `.docx` с кастомной иконкой.

**Проблема:** Иконки подгружаются лениво через `icon_loading_service`. Пока иконки нет — кнопка **пустая/системная fallback**, пользователь думает что сломалось. Нет спиннера/скелетона.

В [toolbar_adapters.py:25-36](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L25-L36) сейчас при ошибке просто возвращается пустой `QIcon()` → пользователь не в курсе.

**Решение:**
- На время загрузки иконки показывать **QMovie-спиннер** или **skeleton-block** (серый прямоугольник с pulse-анимацией)
- При ошибке загрузки иконки (например, файл удалён) — показать **⚠️ значок ошибки**, а в tooltip причину: "Не удалось загрузить иконку: файл не найден"

---

#### UX-8. ThemeSelector занимает ценное место — можно компактнее
**Сценарий:** Узкое окно, ThemeSelector занимает ~110px (combobox с текстом "Dark" + иконка).

**Проблема:** Тема меняется **в среднем раз в неделю/месяц**, а занимает место как 3 кнопки Fav.

**Решение:**
- В нормальном режиме: только **иконка палитры** (круглая кнопка, как в Telegram) без текста → 36px вместо 110px
- При клике → всплывашка `QMenu` с превью тем (миниатюры Light/Dark/Matrix/Violet)
- В overflow (узкий режим) переносим ThemeSelector **в меню ☰ последним пунктом**

Экономия: **+74px места** под поиск или ещё 2 кнопки Fav.

---

### 🟢 НИЗКИЙ приоритет (делают интерфейс "вкусным")

#### UX-9. Нет Drag-and-Drop переупорядочивания Fav/Recent
**Сценарий:** Пользователь хочет, чтобы самый важный избранный был **всегда первым**.

**Проблема:** Сейчас порядок Fav задаётся только через диалог редактирования (сортировка в БД). Нет прямого DnD на самой панели.

**Решение:**
- В `ToolbarActionAdapter` включить `setMovable(True)` для Fav-группы (или собственный drag-start на `mousePressEvent`)
- После drop пользователем — **сохранить новый порядок** в БД (обновить поле `sort_order`)
- Тултип при наведении + зажатии Shift: "Перетащите, чтобы изменить порядок"

---

#### UX-10. Счётчики количества и "ещё N" на кнопках групп
**Сценарий:** У пользователя 12 Fav, но показывается только 5. Он не знает, что ещё 7 скрыто.

**Решение:**
- Вместо разделителя `|` между группами — **компактная кнопка-группа с бейджем**:
  ```
  [➕ ➕ ➕]  ⭐ Fav [×5+]  🕐 Recent [×3+]  [🔍_______]
                         ↑ бейдж "ещё 5"
  ```
- Бейдж = `(total_buttons - visible_buttons)`. Если 0 — бейдж не показывать.
- Клик по бейджу открывает overflow меню сразу с фильтром по группе.

---

#### UX-11. Контекстное меню (ПКМ) на каждой кнопке
**Сценарий:** Пользователь хочет удалить ссылку из избранного, не открывая её.

**Проблема:** Сейчас `QAction.triggered` в [toolbar_adapters.py:335](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L335) только открывает ссылку. ПКМ — ничего не делает (стандартное меню тулбара Qt).

**Решение:** Подключить `setContextMenuPolicy(Qt.CustomContextMenu)` на каждый `QToolButton`:
```
┌──────────────────────────┐
│ 📁 Открыть (Enter)       │  ← дефолтное действие
│ 📂 Открыть в новой панели│
│ ───────────────────────  │
│ 📋 Копировать (Ctrl+C)   │
│ 🔗 Копировать URL/путь   │
│ ✏️ Редактировать… (F2)   │
│ ⭐ Убрать из избранного  │
│ 🗑️ Удалить…              │
└──────────────────────────┘
```

Экономия: 2-3 клика на каждую операцию.

---

#### UX-12. Нет "pin/unpin" для Recent → переход в Fav
**Сценарий:** Пользователь часто открывает один и тот же недавний документ. Хочет закрепить его, чтобы не исчез через N открытий.

**Решение:** В контекстном меню Recent добавить пункт:
- `📌 Закрепить в избранном` — при клике ссылка **копируется** из Recent в Fav (с тем же именем/иконкой), а из Recent удаляется или остаётся, но с значком 📌

На самой кнопке Recent при наведении появляется маленькая кнопка-пин 📌 в углу (как в Chrome).

---

#### UX-13. Анимация добавления/удаления кнопок
**Сценарий:** Пользователь только что добавил новую ссылку в Fav.

**Проблема:** Кнопка появляется мгновенно — пользователь не видит, куда она встала, приходится сканить глазами всю панель.

**Решение:**
- Появление: `QVariantAnimation` на `maximumWidth` 0 → 36px (0.2s ease-out) + opacity 0→1
- Удаление: наоборот, сначала сжатие в 0, потом удаление из layout
- Встряска: при ошибке (например, не удалось открыть ссылку) — небольшая shake-анимация кнопки влево-вправо, как при неверном пароле macOS

---

### 🎯 UX-приоритетная матрица реализации

| Impact / Effort → | Low (1-2 дня) | Medium (3-5 дней) | High (1-2 нед) |
|---|---|---|---|
| **🔴 Critical** | **UX-1 + UX-2.** Гистерезис + 5 стадий сжатия (подключить TopBarLayoutManager) | **UX-3.** Жесткий минимум поиска 160px | — |
| **🟡 Medium** | **UX-7.** Индикатор загрузки иконок | **UX-4.** Группировка overflow меню<br>**UX-5.** Детальные тултипы<br>**UX-6.** Реальные Alt+N шорткаты<br>**UX-8.** Компактный ThemeSelector | — |
| **🟢 Low** | **UX-11.** Контекстное меню ПКМ<br>**UX-12.** Pin Recent | **UX-9.** DnD переупорядочивание<br>**UX-10.** Бейджи "+N ещё" | **UX-13.** Анимации появления |

---

### 💡 Самое важное первым (за 1-2 дня)

Если взяться только за **Low Effort + Critical**:
1. **Подключить уже написанный** `TopBarLayoutManager` к QToolBar (вместо `_topbar_manager = None`)
2. **Включить гистерезис** + 5 стадий сжатия вместо бинарного скрытия
3. **Жесткий минимум поиска 160px**, ThemeSelector в overflow

Это даст **80% ощущения "продуманного интерфейса"** за самые минимальные трудозатраты — и использует код, который уже есть в проекте (15+ сервисов, просто не подключенных).

---

## Итог

Текущая реализация страдает от **двух взаимоисключающих архитектур**:
1. **Простая QToolBar-based** (активирована сейчас) — грубое бинарное поведение, без адаптивности
2. **Сложная сервис-ориентированная** (TopBarLayoutManager, 15+ файлов) — с гистерезисом, солвером, анимациями — **но отключена**

Самое эффективное исправление — **P0: подключить уже написанную адаптивную логику** к текущему QToolBar, вместо того чтобы заново изобретать её в `_AutoHideTreeFilter`. Код сервисного слоя выглядит продуманным и готовым к использованию, он просто не подключен из-за проверки `_uses_toolbar_topbar()`.

---

## Чек-лист верификации анализа

| Утверждение | Статус | Доказательство |
|---|---|---|
| При QToolBar TopBarLayoutManager = None | ✅ Подтверждено | `window_ui_setup.py:523-524` |
| Нет гистерезиса в _AutoHideTreeFilter | ✅ Подтверждено | `window_ui_setup.py:331-334` (один порог) |
| threading.Lock используется в GUI потоке | ✅ Подтверждено | `layout_orchestrator.py:89`, `topbar_controller.py:90` |
| Binary search отключен по умолчанию | ✅ Подтверждено | `visibility_solver.py:15` (`False`) |
| _ExtButtonAligner через setGeometry hack | ✅ Подтверждено | `top_bar_setup.py:49-60` |
| Tooltip содержит только имя ссылки | ✅ Подтверждено | `toolbar_adapters.py:333` (`action.setToolTip(name)`) |
| Search min_width в конфиге = 148px | ✅ Подтверждено | `ui_config.py:365-367` |
| Window min_width в конфиге = 280px | ✅ Подтверждено | `ui_config.py:80-82` |
| Alt+N шорткаты только в AccessibleDescription (не работают) | ✅ Подтверждено | `accessibility_manager.py:120-122` |
| ThemeSelector — полноценный combobox, не иконка | ✅ Подтверждено | `top_bar_setup.py:250-258` добавляет ThemeSelector как виджет |
| При ошибке загрузки иконки возвращается пустой QIcon без индикации | ✅ Подтверждено | `toolbar_adapters.py:25-36` |
