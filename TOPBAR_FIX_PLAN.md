# План исправлений: Top Panel (верхняя панель)

> Дата актуализации: 2026-09-16  
> Статус: **Согласовано под реальный код** (верифицировано по кодовой базе)  
> База: [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py), [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py), [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py), [ui_config.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py)

---

## Оглавление
1. [Общие сведения](#1-общие-сведения)
2. [Методология оценки](#2-методология-оценки)
3. [Исправления P0 — Критические](#3-исправления-p0--критические)
4. [Исправления P1 — Серьёзные](#4-исправления-p1--серьёзные)
5. [Исправления P2 — Средние](#5-исправления-p2--средние)
6. [Исправления P3 — Косметика](#6-исправления-p3--косметика)
7. [План выполнения по этапам (Roadmap)](#7-план-выполнения-по-этапам-roadmap)
8. [Чек-лист приёмки](#8-чек-лист-приёмки)
9. [Сопутствующие работы и тесты](#9-сопутствующие-работы-и-тесты)

---

## 1. Общие сведения

| Параметр | Значение |
|---|---|
| Компонент | Top Panel / Верхняя панель (QToolBar-based реализация) |
| Ключевые файлы | [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py) |
|  | [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py) |
|  | [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py) |
|  | [ui_config.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py) |
|  | [constants.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/common/constants.py) |
|  | Темы оформления в `app/resources/qss/` |
| Объём работ (оценка) | **~24–30 часов** |
| Количество задач | 24 (3 P0 + 6 P1 + 8 P2 + 7 P3) |

> [!NOTE]
> Бывшая задача P0-4 (актуализация `TOPBAR_RESIZE_ANALYSIS.md`) исключена из плана, так как устаревший документ анализа и сервисная архитектура `TopBarLayoutManager` уже были полностью удалены из репозитория в коммитах `6ac9021f` и `7f20eecc`.

---

## 2. Методология оценки

### Шкала приоритетов (P0 → P3)
| Уровень | Определение | Блокировка релиза |
|---|---|---|
| **P0 — Critical** | Ломает основной сценарий, деградация UI/UX, мёртвые заглушки в активных ветках | **Блокирует** |
| **P1 — Major** | Серьёзные UX-недочёты, избыточные O(N) вызовы в event loop, дублирование логики | Желательно исправить |
| **P2 — Minor** | Чистота типизации, читаемость кода, сужение исключений | Не блокирует |
| **P3 — Cosmetic** | Именование, стандартизация логов, удаление избыточных try/except | Не блокирует |

---

## 3. Исправления P0 — Критические

---

### P0-1. Гарантия MIN_SEARCH_WIDTH и применение `_normalize_top_bar_stretches` на этапе сборки — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). `_normalize_top_bar_stretches` подключен в `TopBarBuilder.build()`, тулбару выставлен `QSizePolicy.Policy.Maximum`, гарантированная ширина поиска `max(160, val)` закреплена в `_resolve_search_min_width()`. Тесты в `test_top_bar_layout_spacings.py` подтверждают корректность распределения stretch и сохранение минимальной ширины.

**Описание проблемы**
При сжатии окна QToolBar занимает фиксированное пространство под кнопки, а поле поиска (`mainSearchPlaceholder` / `mainSearch`) сжимается ниже допустимого предела. При этом метод нормализации stretch-факторов [window_ui_setup.py:1023](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L1023) вызывается **только** после материализации поиска ([L965](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L965)), а во время первичного [TopBarBuilder.build()](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L215-L260) все виджеты имеют дефолтный `stretch = 0`.

**План реализации**
1. В [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py) в методе `build()` сразу после добавления всех виджетов в `top_bar` вызывать:
   ```python
   self.ui._normalize_top_bar_stretches(top_bar)
   ```
2. Для тулбара задать ограничение горизонтального расширения:
   ```python
   toolbar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
   ```
3. Гарантировать, что `placeholder.minimumWidth()` и `search.minimumWidth()` не могут быть меньше константы `MIN_SEARCH_WIDTH_GUARANTEED = 160` px при сжатии окна до 280–360 px.
4. Расширить тесты в [test_top_bar_layout_spacings.py](file:///d:/01_Codebdbd/01_projects/aitecommander/tests/test_top_bar_layout_spacings.py) проверкой сохранения минимальной ширины поиска при ресайзе окна.

**Затрагиваемые файлы**
- [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py)
- [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py)
- [test_top_bar_layout_spacings.py](file:///d:/01_Codebdbd/01_projects/aitecommander/tests/test_top_bar_layout_spacings.py)

**Усилие**: **M (2–3 ч)** | **Риск**: *Средний*

---

### P0-2. Удалить мёртвые заглушки `_hide_topbar_panels` / `_show_topbar_panels` и ключ `auto_hide_manage_topbar` — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). Удалены заглушки `_hide_topbar_panels`, `_show_topbar_panels` и чтение `_manage_topbar_panels` из `window_ui_setup.py`, удален метод `get_auto_hide_manage_topbar()` из `ui_config.py`, удалена константа `UI_AUTO_HIDE_MANAGE_TOPBAR` из `constants.py`. Кодовая база очищена от мертвого кода.

**Описание проблемы**
В [window_ui_setup.py:247-248, 262-263](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L247-L263) объявлены пустые методы-заглушки:
```python
def _hide_topbar_panels(self) -> None:
    pass

def _show_topbar_panels(self) -> None:
    pass
```
Они вызываются в `_handle_narrow_window` и `_handle_wide_window` ([L280, L284](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L280-L284)), но ничего не делают. Атрибут `self._manage_topbar_panels` считывается из конфига, но нигде не используется. Скрытие и переполнение кнопок верхней панели штатно берёт на себя `QToolBar` (overflow extension button).

**План реализации**
1. В [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py) удалить:
   - чтение `self._manage_topbar_panels` в `_AutoHideTreeFilter.__init__` ([L194-L198](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L194-L198));
   - заглушки `_hide_topbar_panels()` и `_show_topbar_panels()`;
   - вызовы этих методов в `_handle_narrow_window` и `_handle_wide_window`.
2. В [ui_config.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py) удалить метод `get_auto_hide_manage_topbar()` ([L1072-L1077](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py#L1072-L1077)).
3. В [constants.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/common/constants.py) удалить константу `UI_AUTO_HIDE_MANAGE_TOPBAR` ([L178](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/common/constants.py#L178)).

**Затрагиваемые файлы**
- [window_ui_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py)
- [ui_config.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/config_data/ui_config.py)
- [constants.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/common/constants.py)

**Усилие**: **S (1 ч)** | **Риск**: *Низкий*

---

### P0-3. Убрать инлайновый `setStyleSheet` из Python-кода и перенести стилизацию кнопок в QSS — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). Полностью удален инлайновый вызов `toolbar.setStyleSheet(...)` из `top_bar_setup.py`. Базовые размеры и отступы кнопок тулбара (`32px` / `4px`) перенесены в общий `common.qss`, действующий для всех 16 тем. Динамические пользовательские настройки размеров кнопок и отступов из `app_config.ui` интегрированы в генератор оверрайдов `ThemeStylesheetService._build_config_overrides_qss()`. Покрыто тестами.

**Описание проблемы**
Метод `_apply_toolbar_spacing()` в [top_bar_setup.py:287-297](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L287-L297) вызывает `toolbar.setStyleSheet(...)`. Инлайновый стиль виджета перебивает глобальные темы из `app/resources/qss/*.qss`.

> [!CAUTION]
> **Техническое ограничение Qt:** Движок Qt Style Sheets (QSS) основан на CSS 2.1 и **НЕ поддерживает CSS-переменные** (`var(--...)`). Попытка внедрить переменные приведет к сбою парсера стилей Qt.

**План реализации**
1. В файлах тем `app/resources/qss/` (включая базовые и пользовательские темы) стандартизировать селекторы:
   ```css
   QToolBar#topBarToolbar {
       border: none;
       background: transparent;
   }
   QToolBar#topBarToolbar QToolButton[toolbar_btn="true"] {
       min-width: 32px;
       max-width: 32px;
       min-height: 32px;
       max-height: 32px;
       margin-right: 4px;
   }
   QToolBar#topBarToolbar QToolButton[toolbar_last="true"] {
       margin-right: 0px;
   }
   ```
2. Удалить метод `TopBarBuilder._apply_toolbar_spacing()` и инлайновый вызов `toolbar.setStyleSheet()` из [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py).
3. Для кастомных размеров кнопок (если пользователь меняет размер в настройках) выставлять динамическое Qt-свойство кнопки `btn.setProperty("buttonSize", size)` с селектором в QSS либо передавать размер напрямую через `setIconSize` / `setFixedSize` без жесткого перетирания stylesheet всего тулбара.

**Затрагиваемые файлы**
- [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py)
- Файлы тем в `app/resources/qss/*.qss`

**Усилие**: **M (2–3 ч)** | **Риск**: *Средний* (визуальная проверка тем)

---

## 4. Исправления P1 — Серьёзные

---

### P1-1. Заменить хак `_ExtButtonAligner` на класс-наследник `TopBarToolBar(QToolBar)` — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). Реализован класс `TopBarToolBar(QToolBar)` с синхронным центрированием кнопки переполнения `qt_toolbar_ext_button` в `resizeEvent`. Удален класс `_ExtButtonAligner`, устранены отложенные вызовы `QTimer.singleShot(0)`. Поведение подтверждено тестом `test_topbar_toolbar_ext_button_alignment`.

**Описание проблемы**
Класс `_ExtButtonAligner` ([top_bar_setup.py:22-61](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L22-L61)) ловит события `LayoutRequest` / `Resize` через `eventFilter`, откладывает вызов через `QTimer.singleShot(0, self._centre)` и ищет приватный дочерний виджет Qt по имени `"qt_toolbar_ext_button"`.

**План реализации**
1. Создать класс `TopBarToolBar(QToolBar)`:
   ```python
   class TopBarToolBar(QToolBar):
       def __init__(self, parent: QWidget | None = None, button_height: int = 32) -> None:
           super().__init__(parent)
           self._button_height = button_height

       def resizeEvent(self, event: QResizeEvent) -> None:
           super().resizeEvent(event)
           self._centre_ext_button()

       def _centre_ext_button(self) -> None:
           btn = self.findChild(QToolButton, "qt_toolbar_ext_button")
           if btn is not None and btn.isVisible():
               target_y = max(0, (self.height() - self._button_height) // 2)
               geo = btn.geometry()
               if geo.y() != target_y or geo.height() != self._button_height:
                   btn.setGeometry(geo.x(), target_y, geo.width(), self._button_height)
   ```
2. Использовать `TopBarToolBar` вместо стандартного `QToolBar` в `TopBarBuilder.build()`.
3. Удалить класс `_ExtButtonAligner` и отложенные таймеры `singleShot(0)`.

**Затрагиваемые файлы**
- [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py)

**Усилие**: **S (1–1.5 ч)** | **Риск**: *Низкий*

---

### P1-2. Обогатить tooltip для избранных и недавних ссылок — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). В `LinksToolbarAdapter.set_data()` формируется расширенный HTML-тултип с именем, целевым путем (`📍`), категорией (`📁`) и временем последнего открытия (`🕐`). Протестировано.

### P1-3. Fallback-иконка по типу ссылки при сбое загрузки — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). В функции `_icon_from_path()` внедрен каскадный fallback через `resolve_link_type_icon(link_type)`. Предотвращено появление пустых кнопок при битых путях к иконкам. Протестировано.

### P1-4. Устранить тройное дублирование чтения `min_search_width` — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). Реализован статический метод `WindowUISetup._resolve_search_min_width()`, устранено дублирование во всех 3 местах (`PanelMetrics.from_config()`, `setup_search_widget()`, `_materialize_search_widget()`).

### P1-5. Ограничить максимальную ширину ThemeSelector — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). Для `ThemeSelector` установлена политика `QSizePolicy.Policy.Maximum` и `setMaximumWidth(120)` в `top_bar_setup.py`.

### P1-6. Оптимизировать вызовы `_update_global_last_button` (1 проход вместо 3) — ✅ ВЫПОЛНЕНО

**Статус:** ✅ **Выполнено** (2026-09-16). Алгоритм переписан на обратный поиск `reversed(actions())` со сложностью O(1), маркер предыдущей кнопки сохраняется в `toolbar._global_last_button`, исключены повторные полные обходы.

---

## 5. Исправления P2 — Средние

---

### P2-1. Устранить `ui: Any` в `TopBarBuilder` через `TYPE_CHECKING` — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). В [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py) `ui: Any` заменен на `ui: WindowUISetup` под защитой `if TYPE_CHECKING:`.

### P2-2. Заменить `lambda _=False` на именованный `lambda checked=False` — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). В `toolbar_adapters.py` аргумент сигнала переименован в `checked=False`.

### P2-3. Сузить широкие блоки `except Exception` — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). В `top_bar_setup.py` и `toolbar_adapters.py` обобщенные блоки сужены до `(TypeError, ValueError, RuntimeError, AttributeError, OSError)`.

### P2-4. Добавить документацию и хелпер для action-якоря `end_marker` — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). В `top_bar_setup.py` добавлен docstring, разъясняющий роль `end_marker` как анкерного действия для вставки группы Recent.

### P2-5. Задокументировать или заменить `QTimer.singleShot(0)` — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). В `window_ui_setup.py` задокументированы намеренные вызовы `singleShot(0)` для отложенной материализации поиска на следующем витке event loop без блокировки начального рендера.

### P2-6. Переименовать `ToolbarActionAdapter.setVisible` во избежание путаницы с QWidget — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). Метод переименован в `set_actions_visible(visible: bool)`, сохранен compatibility-псевдоним `setVisible`.

### P2-7. Заменить 9 per-counter замеров `perf_counter` на контекстный менеджер — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). В `top_bar_setup.py` ручные тайминги заменены на лаконичный контекстный менеджер `_StageTimer`.

### P2-8. Вынести fallback `container_parent` в хелпер — ✅ ВЫПОЛНЕНО
- **Статус:** ✅ **Выполнено** (2026-09-16). Логика определения родителя вынесена в метод `_resolve_container_parent()`.

---

## 6. Исправления P3 — Косметика

| ID | Задача | Файлы | Статус |
|---|---|---|---|
| **P3-1** | Унифицировать константы по умолчанию (`_DEFAULT_SPACING = 4`, `_DEFAULT_BUTTON_SIZE = 32`) в начале файла | `top_bar_setup.py` | ✅ **Выполнено** |
| **P3-2** | Добавить явный `__all__` список экспорта | `toolbar_adapters.py` | ✅ **Выполнено** |
| **P3-3** | Убрать инлайновый импорт `ThemeSelector` в top-level | `top_bar_setup.py` | ✅ **Выполнено** |
| **P3-4** | Добавить type hints к замыканиям `_apply() -> None:` | `window_ui_setup.py` | ✅ **Выполнено** |
| **P3-5** | Убрать избыточный `try/except` вокруг `toolbar.setContentsMargins(0, 0, 0, 0)` | `top_bar_setup.py` | ✅ **Выполнено** |
| **P3-6** | Стандартизировать уровни логирования: `warning` для конфигурации, `debug` для штатных проверок Qt | `toolbar_adapters.py`, `window_ui_setup.py` | ✅ **Выполнено** |
| **P3-7** | Добавить `logger.info` при срабатывании узкого режима в `_AutoHideTreeFilter` | `window_ui_setup.py` | ✅ **Выполнено** |

---

## 7. План выполнения по этапам (Roadmap)

### Спринт 1: Критические исправления (P0) — ✅ Завершён
1. **[P0-2]** Удаление заглушек `_hide_topbar_panels` и устаревшего ключа — ✅ **Выполнено**
2. **[P0-1]** Вызов `_normalize_top_bar_stretches()` в `TopBarBuilder.build()` и фиксация минимальной ширины поиска — ✅ **Выполнено**
3. **[P0-3]** Перенос стилей из инлайнового `setStyleSheet` в QSS-темы — ✅ **Выполнено**

### Спринт 2: Архитектурные улучшения и надёжность (P1) — ✅ Завершён
1. **[P1-1]** Класс `TopBarToolBar` взамен `_ExtButtonAligner` — ✅ **Выполнено**
2. **[P1-4]** Единый хелпер `_resolve_search_min_width()` — ✅ **Выполнено**
3. **[P1-5]** Ограничение максимальной ширины `ThemeSelector` — ✅ **Выполнено**
4. **[P1-3]** Корректный fallback для иконок в `_icon_from_path` — ✅ **Выполнено**
5. **[P1-2]** Обогащённый tooltip для Fav и Recent — ✅ **Выполнено**
6. **[P1-6]** Объединение обходов в `_update_global_last_button` — ✅ **Выполнено**

### Спринт 3: Чистота кода и косметика (P2 + P3) — ✅ Завершён
1. **[P2-1 – P2-8]** Типизация, сужение исключений, `_StageTimer`, `end_marker`, `set_actions_visible` — ✅ **Выполнено**
2. **[P3-1 – P3-7]** Константы, экспорт `__all__`, type hints, уровни логов — ✅ **Выполнено**
3. Прогон тестов (22/22 passed) — ✅ **Выполнено**

---

## 8. Чек-лист приёмки

- [x] Тесты [tests/test_top_bar_layout_spacings.py](file:///d:/01_Codebdbd/01_projects/aitecommander/tests/test_top_bar_layout_spacings.py) проходят успешно (9/9 passed).
- [x] Тесты [tests/test_startup_regression_guards.py](file:///d:/01_Codebdbd/01_projects/aitecommander/tests/test_startup_regression_guards.py) проходят успешно (13/13 passed).
- [x] При ширине окна от 280 до 1920 px поле поиска остаётся читаемым и кликабельным (ширина не менее 160 px).
- [x] При уменьшении ширины окна кнопки тулбара уходят в меню переполнения (`qt_toolbar_ext_button`), кнопка меню отцентрована.
- [x] В коде отсутствуют вызовы `toolbar.setStyleSheet(...)` внутри `top_bar_setup.py`.
- [x] Ключ `auto_hide_manage_topbar` и пустые заглушки полностью удалены из кодовой базы.
- [x] Тултипы кнопок избранного и недавнего показывают целевой путь/URL, категорию и время открытия.
- [x] Отсутствуют необработанные предупреждения при запуске приложения.

---

## 9. Сопутствующие работы и тесты

1. **Тест на сохранение минимальной ширины поиска:**  
   В `tests/test_top_bar_layout_spacings.py` подтверждено сохранение stretch и минимальной ширины `>= 160` px.
2. **Тест на корректность fallback-иконки:**  
   Покрыт тестом `test_icon_from_path_fallback_by_link_type`.
3. **Тест на расширенные тултипы и видимость actions:**  
   Покрыт тестом `test_links_toolbar_adapter_rich_tooltip_and_visibility`.

