# План исправлений: Top Panel (верхняя панель)

> Дата: 2026-09-16
> База: Код-ревью реализации топ-панели (QToolBar-based)
> Статус: **Черновик** — требует подтверждения перед выполнением

---

## Оглавление
1. [Общие сведения](#1-общие-сведения)
2. [Методология оценки](#2-методология-оценки)
3. [Исправления P0 — Критические (должны быть в следующем релизе)](#3-исправления-p0--критические)
4. [Исправления P1 — Серьёзные (ближайший спринт)](#4-исправления-p1--серьёзные)
5. [Исправления P2 — Средние (текущий релиз, если есть время)](#5-исправления-p2--средние)
6. [Исправления P3 — Косметика (backlog)](#6-исправления-p3--косметика)
7. [План выполнения по этапам (Roadmap)](#7-план-выполнения-по-этапам-roadmap)
8. [Чек-лист приёмки](#8-чек-лист-приёмки)
9. [Сопутствующие работы](#9-сопутствующие-работы)

---

## 1. Общие сведения

| Параметр | Значение |
|---|---|
| Компонент | Top Panel / Верхняя панель (QToolBar-based реализация) |
| Ключевые файлы | [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py) |
|  | [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py) |
|  | [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py) |
|  | [ui_config.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py) |
|  | Все `.qss` темы в `app/resources/qss/` (15+ файлов) |
| Объём работ (оценка) | **~28–36 часов** (1.5–2 недели спринта 1 человека) |
| Количество задач | 25 (4 P0 + 6 P1 + 8 P2 + 7 P3) |

---

## 2. Методология оценки

### Шкала приоритетов (P0 → P3)
| Уровень | Определение | Критерий блокировки релиза |
|---|---|---|
| **P0 — Critical** | Ломает основной сценарий, баг с потерей данных, UX-деградация, небезопасное состояние | **Блокирует** |
| **P1 — Major** | Серьёзная UX-проблема, архитектурный долг с риском регрессии, дублирование логики | Не блокирует, но **желательно исправить** |
| **P2 — Minor** | Чистота кода, читаемость, поддерживаемость, нетривиальные типы, нестандартные идиомы | Не блокирует |
| **P3 — Cosmetic** | Style, именование, комментарии, мелкие консистентности | Не блокирует |

### Шкала усилий
| Маркер | Часы | Календарь (1 чел) |
|---|---|---|
| XS | ≤ 0.5 | до получаса |
| S | 0.5 – 1 | час — полдня |
| M | 1 – 3 | полдня — день |
| L | 3 – 8 | день — два |
| XL | 8 – 16 | 2 – 4 дня |
| XXL | > 16 | > недели |

### Регрессионный риск
- **Низкий** — локальное изменение в 1-2 функциях, нет сигнальных связей
- **Средний** — затрагивает несколько модулей / сигнал-слоты / layout
- **Высокий** — изменяет API публичных классов, ломает совместимость с темами или конфигами

---

## 3. Исправления P0 — Критические

---

### P0-1. Гарантия MIN_SEARCH_WIDTH при любом размере окна

**Описание проблемы**
При ширине окна ≤ 360px QToolBar «жадно» забирает ширину под QuickAdd-кнопки + Fav + Recent, а поиск получает меньше `min_width` (148px) или обрезается. В реальности окно можно сжать до 280px по конфигу — в этом случае поиск визуально нечитаем.

**Корневая причина**
Отсутствует явный приоритет аллокации ширины: QHBoxLayout по умолчанию распределяет место между виджетами с `Expanding` линейно, а у QToolBar `SizePolicy.Preferred`.

**План реализации**
1. В `TopBarBuilder.build()` **явно задать stretch-факторы**:
   - `toolbar` (QToolBar) → `stretch = 0` (фиксированная потребность)
   - `mainSearchPlaceholder` / `mainSearch` → `stretch = 1` (забирает всё свободное)
   - `theme_selector` → `stretch = 0` (фиксированная)
   - Разделители → `stretch = 0`
2. **Ограничить toolbar сверху**: для тулбара установить `setSizePolicy(Maximum, Fixed)` по горизонтали, чтобы он не мог поглотить ширину поиска.
3. В `_schedule_topbar_initialization` или новом `_prioritize_search_width()` при каждом resize проверять:
   - Если `toolbar.width() + theme_selector.width() + search.width() > top_bar_host.width() - paddings`:
     - Запросить у toolbar `setMaximumWidth(host.width() - MIN_SEARCH_WIDTH_GUARANTEED - THEME_MAX_WIDTH - separators)` вручную.
   - Минимальные гарантии:
     ```python
     MIN_SEARCH_WIDTH_GUARANTEED = 160   # Жёстче, чем в конфиге (148)
     THEME_MAX_WIDTH          = 80
     SEPARATORS_TOTAL         = 24      # 2 × (4+4) + 2 разделителя
     ```
4. Добавить regression-тест на размерах окна 280 / 320 / 360 / 400 px: проверять, что `search.width() >= 160`.

**Затрагиваемые файлы**
- `app/views/main_components/ui/topbar/top_bar_setup.py` (метод `build`, `_prioritize_search_width` — новый)
- `tests/test_top_bar_layout_spacings.py` — добавить 3 кейса

**Усилие**: **L (4–6 ч)** | **Риск**: *Средний* (layout-правки часто ломают визуальный вид)

**Критерий готовности**
- На всех ширинах окна [280..1920] пиксельная ширина поиска ≥ 160 px.
- Ни один из 15+ QSS-стилей не визуально ломается (сверка с эталонными скриншотами).
- Тесты проходят на 5 размерах окна.

---

### P0-2. Удалить или реализовать заглушки _hide_topbar_panels / _show_topbar_panels

**Описание проблемы**
Флаги `get_auto_hide_manage_topbar()` по умолчанию `False` — но при включении в конфиге срабатывают методы-заглушки:
```python
def _hide_topbar_panels(self) -> None:
    pass   # TODO — не реализовано!
```
И аналогично `_show_topbar_panels()`. Опция документирована, но не работает — это бомба замедленного действия.

**Варианты решения**
- **Вариант A (рекомендуется)**: Удалить флаг `auto_hide_manage_topbar` из конфига и UI-логики. Причина: поведение полного скрытия top bar при узком окне заменяется встроенным overflow в QToolBar.
- **Вариант B**: Реализовать методы, вызывая `self.window.top_bar_host.setVisible(False/True)` **только** при включённом флаге.

**Решение принято**: **Вариант A** — удалить неиспользуемую опцию, чтобы не вводить в заблуждение.

**План реализации**
1. Удалить из `ui_config.py` геттер `get_auto_hide_manage_topbar()` и ключ по умолчанию из `app_config.json`.
2. Удалить из `window_ui_setup.py` атрибуты `_manage_topbar_panels`, заглушки `_hide_topbar_panels`, `_show_topbar_panels` и вызовы из `_handle_narrow_window`/`_handle_wide_window`.
3. Удалить из i18n `.ts`-файлов строки, связанные с этой опцией (поиском по ключу `auto_hide_manage_topbar`).
4. Добавить миграцию конфига: при загрузке, если ключ присутствует — вывести `logger.warning` и удалить.

**Затрагиваемые файлы**
- `app/views/main_components/ui/window_ui_setup.py`
- `app/config_data/ui_config.py`
- `app/config_data/app_config.json`
- 6× i18n файлов: `i18n/app_{ru,uk,en,de,es,fr}.ts`
- `app/config_data/migrations/` (добавить миграцию, если есть система миграций)

**Усилие**: **S (1 ч)** | **Риск**: *Низкий*

**Критерий готовности**
- Ключ больше нигде не встречается (grep-верфикация по всему репозиторию).
- При старте со старым конфигом нет падений, есть warning в логе.
- Тесты `test_startup_regression_guards.py` проходят.

---

### P0-3. Убрать инлайновые setStyleSheet из Python-кода в .qss темы

**Описание проблемы**
[top_bar_setup.py:287-297](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L287-L297) вызывает `toolbar.setStyleSheet()` с правилами `QToolBar#topBarToolbar QToolButton[...]`. Инлайновый `setStyleSheet` **перебивает все темы** в `resources/qss/*`, потому что Qt применяет их в порядке: global QSS → виджетный setStyleSheet (последний выигрывает).

**Следствия**:
- Темы с кастомными spacing/size кнопок **не работают** на top bar.
- При смене размера кнопок через конфиг нужно **перезапускать инлайновый вызов** — это дополнительный layout-pass.

**План реализации**
1. **Перевести размеры в CSS-переменные**. В каждом `.qss` файле в `:root` / `*` секцию добавить:
   ```css
   * {
       --topbar-btn-size: 36px;
       --topbar-btn-spacing: 4px;
   }
   ```
2. Удалить `TopBarBuilder._apply_toolbar_spacing()` и вызов его из `build()`.
3. В каждый `.qss` добавить секцию:
   ```css
   QToolBar#topBarToolbar {
       padding: 0px var(--topbar-btn-spacing) 0px 0px;
   }
   QToolBar#topBarToolbar QToolButton[toolbar_btn="true"] {
       min-width: var(--topbar-btn-size);
       max-width: var(--topbar-btn-size);
       min-height: var(--topbar-btn-size);
       max-height: var(--topbar-btn-size);
       margin-right: var(--topbar-btn-spacing);
   }
   QToolBar#topBarToolbar QToolButton[toolbar_last="true"] {
       margin-right: 0px;
   }
   ```
4. Если значения в конфиге отличаются от дефолтов (36px / 4px) — **применять их динамически через `QApplication.styleSheet` с подстановкой**, а не через `setStyleSheet` на виджете. Альтернатива: использовать `setProperty("btnSize", ...)` + `QToolButton[btnSize="36"]` селекторы.
5. Для runtime-применения (если пользователь меняет размер кнопки в настройках):
   - Изменить значение CSS-переменной через `QApplication.setStyleSheet()` или полный `repolish()`.
   - Или использовать `button.setStyleSheet()` **только на конкретной кнопке** (индивидуально), а не глобально на тулбаре.

**Затрагиваемые файлы**
- `app/views/main_components/ui/topbar/top_bar_setup.py`
- `app/resources/qss/common.qss` (базовые стили)
- `app/resources/qss/dark.qss`, `light.qss` (стандартные)
- Все пользовательские темы (13 штук): `obsidian_luxe.qss`, `violet_pulse.qss`, `sage_light.qss`, `sakura_anime.qss`, `rasta_royale.qss`, `pearl_gray.qss`, `pastel_bloom.qss`, `nord_light.qss`, `matrix.qss`, `love.qss`, `industrial_yellow.qss`, `ghost_terminal.qss`, `cyberpunk_neon.qss`, `crimson_noir.qss`
- Файл применения тем (где вызывается `qApp.setStyleSheet`)

**Усилие**: **L (3 ч)** | **Риск**: *Средний* (необходима визуальная сверка каждой темы)

**Критерий готовности**
- На 2+ тестовых темах кнопки совпадают по размерам/spacing с референсом (до-после).
- Runtime-смена размера кнопки (если такая опция есть в UI) работает без вызова `setStyleSheet` на toolbar.
- В коде `top_bar_setup.py` больше нет вызова `setStyleSheet()`.

---

### P0-4. Актуализировать TOPBAR_RESIZE_ANALYSIS.md под реальный код

**Описание проблемы**
В текущем анализе 5+ ложных утверждений про несуществующие классы (`TopBarLayoutManager`, `HysteresisService`, `VisibilitySolver`, `LayoutOrchestrator`, `NarrowModeService`, `SearchWidgetManager`, `accessibility_manager.py`) и про «отсутствующий гистерезис», хотя гистерезис в коде **уже есть**.

**Риск**: Новый разработчик будет тратить время на поиск файлов, которых нет, или переносить анализ в таски — и часть работы будет основана на неверной предпосылке.

**План реализации**
1. Пометить все неверные утверждения как **❌ УСТАРЕЛО** со ссылкой на реальный код.
2. Удалить рекомендации, основанные на несуществующих классах («подключить TopBarLayoutManager», «включить binary search по умолчанию в VisibilitySolver»).
3. Добавить раздел **«Разница между анализом и реальностью»** в начало файла.
4. Заменить гистерезис-блок: указать, что он **реализован** на уровне `_AutoHideTreeFilter.exit_threshold`, но **не хватает на уровне самого toolbar overflow**.
5. Добавить в TOPBAR_RESIZE_ANALYSIS.md ссылку на новый ТОТ план исправлений.

**Затрагиваемые файлы**
- `TOPBAR_RESIZE_ANALYSIS.md`

**Усилие**: **S (1 ч)** | **Риск**: *Низкий*

**Критерий готовности**
- В анализе не осталось ссылок на несуществующие в репозитории файлы (grep-верификация: имён файлов, которых нет в FS).
- Все пункты про гистерезис, threading.Lock, binary search, accessibility_manager, _uses_toolbar_topbar помечены как устаревшие с комментариями.

---

## 4. Исправления P1 — Серьёзные

---

### P1-1. Заменить `_ExtButtonAligner` хак на кастомный `QToolBar` наследник

**Описание проблемы**
Код использует внутреннее имя Qt `qt_toolbar_ext_button` для ручного выравнивания overflow-кнопки. Это нестабильное внутреннее API — ломается при апдейте Qt/PyQt.

**План реализации**
1. Создать новый класс `TopBarToolBar(QToolBar)` в отдельном файле `app/views/main_components/ui/topbar/top_bar_toolbar.py` или в начале `top_bar_setup.py`.
2. Переопределить `resizeEvent(self, event)`:
   - Сначала вызвать `super().resizeEvent(event)` для стандартной геометрии.
   - Затем вызвать `self._adjust_ext_button_geometry()` внутри того же метода — без `singleShot(0)`.
3. Удалить `_ExtButtonAligner` класс и `toolbar.installEventFilter(aligner)`.
4. В `_adjust_ext_button_geometry` использовать `self.widgetForAction(self.actions()[-1])` или публичный API вместо поиска по objectName, если возможно. Если нет — **оставить findChild**, но обернуть в дополнительную версионную проверку PyQt.
5. Добавить `# Qt internal: qt_toolbar_ext_button. May break on Qt upgrade.` комментарий с TODO.

**Затрагиваемые файлы**
- `app/views/main_components/ui/topbar/top_bar_setup.py` (удалить `_ExtButtonAligner`, заменить QToolBar → TopBarToolBar)
- Опционально: новый файл `top_bar_toolbar.py`

**Усилие**: **M (2 ч)** | **Риск**: *Низкий* (переопределение resizeEvent — стандартная практика Qt)

**Критерий готовности**
- Overflow-кнопка визуально выровнена по центру (скриншот сравнение до/после).
- При 20+ ресайзах в быстром темпе нет фризов и «прыгающей» кнопки.
- В event loop меньше `singleShot(0)` вызовов (подтвердить профилировщиком).

---

### P1-2. Обогатить tooltip для Fav/Recent

**Описание проблемы**
Тултип [toolbar_adapters.py:333](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L333) содержит только `name` → одинаковые имена ссылок неразличимы.

**План реализации**
1. В `LinksToolbarAdapter.set_data()` собрать HTML-текст тултипа:
   ```html
   <div style='margin:6px 4px;'>
     <b>%NAME%</b><hr style='margin:4px 0;'/>
     <span style='color:%ACCENT%;'>📁 Раздел:</span> %BREADCRUMB%<br/>
     <span style='color:%ACCENT%;'>📍 Путь:</span> %TARGET_PATH%<br/>
     %LAST_OPENED_LINE%
   </div>
   ```
2. Извлечь breadcrumb: запросить у категории путь (служба `breadcrumbs` / `category_service` — определить существующий сервис через поиск по коду).
3. `%TARGET_PATH%`: заполнять из `link_data["path"]` или `link_data["url"]` или `link_data["target"]` в зависимости от типа.
4. `%LAST_OPENED_LINE%`: если `last_opened_at` есть — форматировать как «🕐 Открыто: {humantime}», иначе не показывать.
5. Цвет `%ACCENT%` брать из текущей палитры (`palette().color(QPalette.ColorRole.Link).name()`) — чтобы тултип читался на светлых и тёмных темах.
6. Для QuickAddTooltip тоже обогатить: добавить описание действия и комбинацию клавиш (если шорткаты существуют).

**Затрагиваемые файлы**
- `app/views/main_components/ui/topbar/toolbar_adapters.py` (метод `set_data`)

**Усилие**: **M (2 ч)** | **Риск**: *Низкий*

**Критерий готовности**
- Каждый Fav/Recent показывает breadcrumb + путь/URL + (опционально) время.
- HTML-разметка в тултипе не съезжает на light/dark/matrix темах (сверка 3–4 экзотических тем).
- Пустые поля (`path`/`url`/`last_opened_at`) пропускаются, нет пустых строк в tooltip.

---

### P1-3. Fallback-иконка по типу ссылки при ошибке загрузки

**Описание проблемы**
[toolbar_adapters.py:36](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L36) возвращает `QIcon()` → белая пустая кнопка. Пользователь не понимает, что это.

**План реализации**
1. В `_icon_from_path()` при `fallback=None` заменить возврат `QIcon()` на вызов `resolve_link_type_icon()` с определением типа:
   - `file` / `folder` / `http` / `category`
   - Тип брать из link_data. Для QuickAdd-кнопок определять по `code`.
2. Если и тип неизвестен — использовать дефолтную иконку `default_link.svg` (или `link.svg`) из `resources/icons/ui/`.
3. При ошибке также добавить в tooltip строку `⚠️ Не удалось загрузить иконку` + краткую причину (из exception message).

**Затрагиваемые файлы**
- `app/views/main_components/ui/topbar/toolbar_adapters.py` (`_icon_from_path`)

**Усилие**: **XS (0.5 ч)** | **Риск**: *Низкий*

**Критерий готовности**
- Нет ни одной кнопки с пустой иконкой. Самый худший случай — иконка по умолчанию.
- При намеренно битой ссылке (удалённый файл) показывается fallback и сообщение в tooltip.

---

### P1-4. Вынести дублирование min_search_width в helper

**Описание проблемы**
Логика `try: min_search_w = int(app_config.ui.get_top_panel_search_min_width())` повторяется в 2 местах:
- [window_ui_setup.py:875](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L875) — setup_search_widget (placeholder)
- [window_ui_setup.py:935](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L935) — _materialize_search_widget (materialized)

**План реализации**
1. Добавить статический/приватный метод `_resolve_search_min_width() -> int` в `WindowUISetup`.
2. Заменить оба дубликата на вызов.
3. Аналогично вынести fallback на ошибку в `_get_button_size_fallback()` и `_get_search_height_fallback()` — они тоже дублируются.

**Затрагиваемые файлы**
- `app/views/main_components/ui/window_ui_setup.py`

**Усилие**: **XS (0.5 ч)** | **Риск**: *Низкий*

**Критерий готовности**
- Grep по `get_top_panel_search_min_width` возвращает **ровно 1 occurrence** (в helper).
- Тесты на минимальные размеры проходят.

---

### P1-5. Ограничить максимальную ширину ThemeSelector

**Описание проблемы**
[top_bar_setup.py:251-258](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L251-L258) ThemeSelector — QComboBox без max_width. При «Obsidian Luxe» названии темы отъедает ≥140 px.

**План реализации**
1. Сразу после создания вызвать:
   ```python
   theme_selector.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
   theme_selector.setMaximumWidth(80)  # достаточно только для иконки + 2 буквы
   ```
2. Добавить полный текст темы в tooltip комбобокса: `theme_selector.setToolTip("Тема: " + текущее_имя)`.
3. Опционально: комбобокс показывать **только иконку** без текста (использовать `setItemData(..., Qt.ItemDataRole.DecorationRole)` и `QComboBox.setSizeAdjustPolicy`). Всплывающее меню оставить с названиями.

**Затрагиваемые файлы**
- `app/views/main_components/ui/topbar/top_bar_setup.py`
- `app/views/widgets/theme_selector.py` — если потребуется доработка самого селектора

**Усилие**: **S (0.5 ч)** | **Риск**: *Низкий*

**Критерий готовности**
- Тема «Obsidian Luxe» + самая длинная тема укладываются ≤80 px.
- Всплывающий список тем читаемый, не обрезанный.
- Тултип показывает полное название.

---

### P1-6. Оптимизировать `_update_global_last_button` — один обход вместо 3-х

**Описание проблемы**
Каждый из 3-х адаптеров (`quick`, `fav`, `recent`) вызывает `_update_global_last_button` — обход всех `toolbar.actions()`. Итог: 3 полных обхода O(N) при каждом `set_data()`.

**План реализации**
1. Создать **внешний координатор** (лучше всего внутри `TopBarBuilder`, чтобы не создавать новый класс) — сингл-метод `update_last_button_once(toolbar)`.
2. Заменить вызов `_update_global_last_button()` внутри каждого адаптера на единый вызов из `TopBarBuilder` **после** того, как все три адаптера отработали `set_data` / `build`.
3. Или вынести метод в `ToolbarSeparatorController` (он уже координирует 3 группы) — переименовать в `ToolbarCoordinator`.
4. Заменить `O(N)` обход `actions()` на поддержку `_buttons` списков из адаптеров — собрать финальный список за O(K), где K только toolbar_btn-кнопки.

**Затрагиваемые файлы**
- `app/views/main_components/ui/topbar/toolbar_adapters.py` (удалить `_update_global_last_button` из адаптеров)
- `app/views/main_components/ui/topbar/top_bar_setup.py` (добавить центральный вызов)

**Усилие**: **S (1 ч)** | **Риск**: *Низкий*

**Критерий готовности**
- Последняя видимая кнопка группы имеет `toolbar_last="true"`, а у предыдущей сброшено — как сейчас.
- Профилировщик показывает 1 вызов вместо 3-х на `set_data` для Fav+Recent.

---

## 5. Исправления P2 — Средние

---

### P2-1. Устранить `ui: Any` в `TopBarBuilder` через TYPE_CHECKING

**План**
1. В top_bar_setup.py добавить:
   ```python
   from __future__ import annotations
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from app.views.main_components.ui.window_ui_setup import WindowUISetup
   ```
2. Заменить `ui: Any` → `ui: WindowUISetup`. Проверить в runtime нет циклического импорта (благодаря `TYPE_CHECKING` его не будет).

**Усилие**: **XS (0.5 ч)** | **Файлы**: `top_bar_setup.py` | **Риск**: Низкий

---

### P2-2. Уточнить `lambda _=False` → `lambda checked=False`

**План**
В [toolbar_adapters.py:258](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L258) и [335](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L335) переименовать `_=False` → `checked=False`.

**Усилие**: **XS (5 мин)** | **Файлы**: `toolbar_adapters.py` | **Риск**: Низкий

---

### P2-3. Сузить 10 самых широких `except Exception`

**План**
1. Аудитом пройти по каждому `except Exception:` в 3 ключевых файлах (всего ~30 local occurrence).
2. Заменить на конкретные `(TypeError, ValueError, RuntimeError, AttributeError)` или `(TypeError, ValueError)`, где это возможно.
3. В catch-блоках, где неизвестно что полетит — оставить `Exception`, но добавить в лог **короткое описание контекста** (какой конкретно аргумент вызвал падение).
4. Особое внимание: вызовы runtime_config getter-ов и `widgetForAction`.

**Усилие**: **M (2–3 ч)** | **Файлы**: `top_bar_setup.py`, `toolbar_adapters.py`, `window_ui_setup.py` | **Риск**: Средний (могут всплыть незамеченные ранее ошибки конфигурации)

---

### P2-4. Именовать `end_marker` невидимый action-якорь

**План**
1. Вынести невидимый action-якорь в отдельный helper `_create_invisible_anchor(toolbar) -> QAction`.
2. Добавить docstring с пояснением для чего он (чтобы вставка `insert_before` была корректной у Recent).

**Усилие**: **XS (0.5 ч)** | **Файлы**: `top_bar_setup.py` | **Риск**: Низкий

---

### P2-5. Заменить `QTimer.singleShot(0)` на `QMetaObject.invokeMethod`

**План**
В местах где есть `singleShot(0, fn)` (в `_ExtButtonAligner._centre` после P1-1, возможно его там не останется; в `_schedule_search_widget_materialization`) — заменить на:
```python
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
QMetaObject.invokeMethod(self, fn.__name__ if bound else slot, Qt.ConnectionType.QueuedConnection)
```
Или сохранить singleShot(0), но задокументировать как intentional: `# Defer to next event loop pass — equivalent of QueuedConnection`.

**Усилие**: **S (0.5 ч)** | **Файлы**: `top_bar_setup.py`, `window_ui_setup.py` | **Риск**: Низкий

---

### P2-6. Переименовать `ToolbarActionAdapter.setVisible` во избежание путаницы

**План**
1. Переименовать `setVisible` → `set_actions_visible`.
2. Оставить deprecated-wrapper:
   ```python
   def setVisible(self, visible: bool) -> None:  # pragma: no cover - deprecated
       warnings.warn("setVisible deprecated, use set_actions_visible", DeprecationWarning)
       self.set_actions_visible(visible)
   ```
3. Проверить все call-сайты через grep `setVisible(.*widget` заменить на `set_actions_visible`.

**Усилие**: **S (0.5 ч)** | **Файлы**: `toolbar_adapters.py` + все call-сайты | **Риск**: Средний (нарушение публичного API адаптеров — нужен grep по всем `.py`)

---

### P2-7. Заменить 9 per-counter perf_counter-переменных на Context Manager

**План**
В `TopBarBuilder.build()` убрать 9 локальных `*_start` / `*_ms` и использовать самописный `@contextmanager`:
```python
@contextmanager
def _measure(stats: dict, key: str):
    t0 = perf_counter()
    try:
        yield
    finally:
        stats[key] = (perf_counter() - t0) * 1000.0
```

**Усилие**: **XS (0.5 ч)** | **Файлы**: `top_bar_setup.py` | **Риск**: Низкий

---

### P2-8. Вынести `container_parent` fallback в helper-функцию

**План**
Сейчас две ветки вычисления родителя (115–118 строка). Обернуть в `_resolve_container_parent()`.

**Усилие**: **XS (0.25 ч)** | **Файлы**: `top_bar_setup.py` | **Риск**: Низкий

---

## 6. Исправления P3 — Косметика

| ID | Задача | Описание | Усилие | Файлы |
|---|---|---|---|---|
| P3-1 | Согласовать порядок try/except в `build()` | Где `except Exception`, где `except (TypeError, ValueError)` — унифицировать дефолтные значения в **константы** в начале модуля `_DEFAULT_SPACING = 8`, `_DEFAULT_ICON_SIZE = (32, 32)` | XS | top_bar_setup.py |
| P3-2 | Добавить `__all__` в `toolbar_adapters.py` | Настроить явный экспорт: `__all__ = ["ToolbarSeparatorController", "ToolbarActionAdapter", "QuickAddToolbarAdapter", "LinksToolbarAdapter"]` | XS | toolbar_adapters.py |
| P3-3 | Убрать дублирующий импорт ThemeSelector | `from app.views.widgets.theme_selector import ThemeSelector` внутри try-блока — вынести в top-level с TYPE_CHECKING, если ThemeSelector не нужен при импорте модуля. Если вызывается инлайново — оставить, но добавить `# local import: heavy dependency` комментарий | XS | top_bar_setup.py |
| P3-4 | Добавить type hints в callback-замыкания | `_apply()` внутри `_schedule_search_widget_materialization` — добавить `def _apply() -> None:` (уже есть). Все лямбды проверить. | XS | window_ui_setup.py |
| P3-5 | Убрать бессмысленный `try: setContentsMargins(0,0,0,0)` | [top_bar_setup.py:155-157](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L155-L157) — `setContentsMargins` на QToolBar не должен падать никогда. Убрать try/except или оставить только конкретный AttributeError. | XS | top_bar_setup.py |
| P3-6 | Согласовать уровень логирования | В `toolbar_adapters.py:33` `logger.debug` vs `_schedule_search_widget_materialization` `logger.warning` — стандартизировать: ошибки конфига → warning, неудачи Qt-API без последствий → debug. | XS | Везде |
| P3-7 | Добавить `logger.info` при активации узкого режима | Пользователь включил отладку — видит, почему панель схлопнулась. Сейчас логирование только на failures. | S | window_ui_setup.py (_AutoHideTreeFilter) |

**Итого по P3**: **~2 ч** | **Риск**: *Низкий*

---

## 7. План выполнения по этапам (Roadmap)

Рекомендуем разбивать на **реleases / milestones** вместо одного большого PR:

### Этап 1 — Срез P0 (дедлайн: до 20.09.2026, ~1 день)
```
1. [P0-4] Актуализировать TOPBAR_RESIZE_ANALYSIS.md            (1 ч)
2. [P0-2] Удалить _hide_topbar_panels + auto_hide_manage_topbar (1 ч)
3. [P0-3] Переместить inline QSS в .qss                         (3 ч)
4. [P0-1] Гарантия MIN_SEARCH_WIDTH                             (5 ч)
```
**Итого этап 1**: ~10 ч | 1.5 рабочих дня

### Этап 2 — Срез P1 (дедлайн: до 25.09.2026, ~2 дня)
```
1. [P1-1] Кастомный TopBarToolBar вместо _ExtButtonAligner    (2 ч)
2. [P1-2] Обогатить tooltip Fav/Recent                        (2 ч)
3. [P1-3] Fallback-иконка по типу ссылки                      (0.5 ч)
4. [P1-4] Helper min_search_width + button_size fallback      (0.5 ч)
5. [P1-5] Ограничить ThemeSelector.maxWidth = 80              (0.5 ч)
6. [P1-6] Убрать 3× обход в _update_global_last_button        (1 ч)
```
**Итого этап 2**: ~6.5 ч | 1 рабочий день

### Этап 3 — Срез P2 (дедлайн: до 29.09.2026, ~2 дня)
```
P2-1..P2-8                                                     (7–8 ч)
```

### Этап 4 — Срез P3 + финальная полировка
```
P3-1..P3-7                                                     (~2 ч)
Финальная ручная проверка на 3+ темах                          (1 ч)
Regression-тесты                                               (1 ч)
```

**Общий итог**: **27–32 ч** (в зависимости от темы P2-3 — 10+ проверки QSS).

---

## 8. Чек-лист приёмки

### Для каждой задачи перед закрытием PR:
- [ ] Код-ревью минимум 1 человеком (кроме автора).
- [ ] Добавлены unit-тесты, если задача из P0/P1 и логирует алгоритмическую часть (а не только стили).
- [ ] `python -m pytest tests/test_top_bar*.py tests/test_startup_regression_guards.py` — 100% GREEN.
- [ ] Ручная проверка resize от 280 до 1920 px на тему **Dark + 1 рандомная цветная**.
- [ ] Визуальный осмотр 15+ тем: отсутствуют белые рамки, обрезанные иконки, съехавшие paddings.
- [ ] Нет предупреждений в output `QT_FATAL_WARNINGS=1 python -m aitecommander`.
- [ ] Отсутствуют `grep -R "TODO|FIXME|XXX"` ссылок на закрытую задачу (если не должны остаться).

### Финальный чек-лист перед релизом:
- [ ] Все 4 P0 + 6 P1 + 8 P2 задач закрыты.
- [ ] TOPBAR_RESIZE_ANALYSIS.md в синхронизированном состоянии (ссылка на этот план в разделе «План исправлений»).
- [ ] Итоговый прогон тестов покрывает:
  - Размеры окна 280/320/360/400/480/640/800/1024/1920 px.
  - 0 Fav + 20 Fav сценарии.
  - Быстрое перетаскивание размера окна (5 секунд рандомных размеров) без зацикливания layout.

---

## 9. Сопутствующие работы

### 9.1. Рекомендуемые тесты для добавления

| Сценарий | Файл теста | Уровень |
|---|---|---|
| Ширина окна 280 → search.width ≥ 160 | `test_top_bar_layout_spacings.py` | Обязательный (P0) |
| 0 Fav/0 Recent: разделители скрыты | `test_top_bar_separators.py` (новый) | Обязательный (P1) |
| 20 Fav: overflow-кнопка появляется, все кнопки доступны | Новый | P2 |
| ThemeSelector: самая длинная тема укладывается ≤ 80 px | Новый | P1 |
| Tooltip содержит breadcrumb и путь | Новый | P1 |
| Fallback-иконка работает при битом path_to_icon | Новый | P1 |
| 3 адаптера → 1 вызов update last button | Новый | P2 |

### 9.2. Документация для разработчиков

В `docs/development/top_bar.md` (если принято решение вести internal docs) добавить:
1. Архитектуру компонентов top bar.
2. Как добавить новую группу кнопок (новый LinksToolbarAdapter).
3. Где применяется растягивание/stretch layout.
4. Как работает fallback цепочка min_search_width.

---

## 📎 Приложение A: Быстрый поиск затронутых строк

```bash
# Проверка, что в коде не осталось старых inline QSS
grep -n "setStyleSheet" app/views/main_components/ui/topbar/top_bar_setup.py

# Проверка, что auto_hide_manage_topbar удалён везде
grep -rn "auto_hide_manage_topbar" app/ tests/ i18n/

# Проверка на остатки lambda _=False
grep -rn "lambda _=False" app/views/main_components/ui/topbar/

# Проверка на ссылки в TOPBAR_RESIZE_ANALYSIS.md на несуществующие файлы
for f in "layout_orchestrator.py" "visibility_solver.py" "topbar_controller.py" "accessibility_manager.py" "HysteresisService"; do
  grep -q "$f" TOPBAR_RESIZE_ANALYSIS.md && echo "FOUND: $f in analysis"
done
```

---

## Итоговая сводка

| Приоритет | Количество | Общее усилие | Доля от всего объёма |
|---|---|---|---|
| **P0** | 4 | ~10 ч | **36%** |
| **P1** | 6 | ~6.5 ч | **23%** |
| **P2** | 8 | ~8 ч | **28%** |
| **P3** | 7 | ~2 ч | **7%** |
| **Тесты + ручная проверка** | — | ~2–3 ч | **~8%** |
| **Всего** | **25 задач** | **~28–36 ч** | **100%** |
