# ExplorerHeaderView Architecture Cleanup Plan
## Professional Grade — v2.0 (Updated 2026-09-20)

---

## Table of Contents

1. **Pre-requisites & Baseline Checklist** — что сделать перед любым изменением.
2. **Architectural Decision Record (ADR): Why ProxyStyle-over-paint** — фиксируем эталонные архитектурные решения.
3. **Level 1 — Dead-Code Hygiene (safe, 15–30 min, High)** — удаление неиспользуемого кода и состояния.
4. **Level 2 — Dependency Inversion (encapsulation, 1–2 hr, Medium)** — собственные `pyqtProperty` хедера, инъекция вместо `parent()` reads.
5. **Level 3 — Architectural Ideal (reusable-header, 4–8 hr, Low)** — zero-knowledge о колонках, нативный QStyle-шеврон.
6. **Level 4 — Regression & Acceptance Gates (Definition of Done for each)** — чек-листы с критериями прохождения.
7. **Appendix A — Architecture Data-Flow Diagram (ASCII)** — визуализация Model ⇄ ProxyStyle ⇄ paintEvent.
8. **Appendix B — QSS Contract** — полный контракт цветов/свойств хедера для дизайнеров тем.
9. **Success Criteria & KPIs for the whole migration** — как измерить успех.

---

## 0. Architectural Decision Record (ADR)

**ADR #001: Изменять геометрию субэлементов хедера — через QProxyStyle.subElementRect.**
- Status: ✅ Accepted (актуально).
- Context: Исторически пытались модифицировать `opt.rect` внутри `paintSection` перед вызовом `super()`. Это ломало межсекционные разделители `border-right` и хэндлы `resize-section` (Qt воспринимал rect как границы секции).
- Consequences:
  - ✅ Референсная реализация: `ExplorerHeaderStyle.subElementRect(SE_HeaderLabel)`.
  - 🚫 НИКОГДА не изменять `opt.rect` в `paintSection`.
  - 🚫 НИКОГДА не заменять `super().paintSection()` на ручной `drawControl()` для секций ≥ 1.

**ADR #002: Chevron-compartment width — single class-level constant.**
- Status: ✅ Accepted.
- Implementation: `ExplorerHeaderView.CHEVRON_COMPARTMENT_WIDTH = 24`.
- Consumers:
  1. `ExplorerHeaderStyle.subElementRect` (сужает текст симметрично).
  2. `paintEvent` (геометрия стрелки).
- KPI: Изменение 24 → 28 делается в 1 строке.

**ADR #003: Связь модель ↔ стиль — только через `headerData(role)`.**
- Status: ✅ Accepted.
- Context: `ExplorerHeaderStyle` не может хардкодить индексы колонок `if section in (1, 2, ...)` — иначе класс становится одноразовым.
- Registered custom `UserRole` allocations (in [links_model.py L37](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/links_model.py#L37)):
  ```python
  HEADER_CHEVRON_PADDING_ROLE = int(Qt.ItemDataRole.UserRole) + 101
  HEADER_CENTER_ICON_ROLE    = int(Qt.ItemDataRole.UserRole) + 102   # NEW (Level 3.1)
  ```
- Rule: Все дальнейшие custom header-роли брать +N выше 102, чтобы избежать коллизий.

---

## 1. Pre-requisites & Baseline (ВЫПОЛНИТЬ ПЕРВЫМ)

### 1.1 Git state (mandatory)

```powershell
# 1. Текущий HEAD — после коммита удаления разделителя
git log --oneline -1
# Expected: dbfd7551 (main) style(links table header): remove the vertical divider…

# 2. Рабочая директория — чистая
git status --short
# Expected: (empty output)

# 3. Создать feature-ветку под каждый уровень отдельно
git checkout -b refactor/header-l1-cleanup      # для Level 1
# или для цепочки уровней
git checkout -b refactor/header-l1l2
```

### 1.2 Toolchain baseline (mandatory)

```powershell
# a) Линтер: 0 ошибок до изменений
ruff check app/views/widgets/link/base_table.py

# b) Type-checker (если настроен): 0 ошибок
mypy app/views/widgets/link/base_table.py  --config-file pyproject.toml

# c) GUI smoke test: запустить приложение, открыть вкладку «Ссылки»
python -m app.main
# → проверить визуально: курсор над «Запуском» → стрелка, фон.
```

### 1.3 Atomic Commit Convention (обязательно для всех уровней)

| Область | Префикс коммита | Пример |
|---|---|---|
| Удаление dead-code / чистка импортов | `chore(header): …` | `chore(header): drop unused _hovered_toggle state` |
| Рефакторинг без поведенческих изменений | `refactor(header): …` | `refactor(header): inject hoverHeaderColor via pyqtProperty` |
| Визуальные улучшения (цвета, глифы) | `style(header): …` | `style(header): use native PE_IndicatorArrow for chevron` |
| Тесты / CI | `test(header): …` | `test(header): add regression test for min-section-width gate` |

Rule: **один атомарный шаг = один коммит**. Никаких «всё в одном коммите 100 строк». Rollback обратно к шагу N-1 = `git revert` одного коммита.

---

## Level 1 — Dead-Code Hygiene 🟢 (Safe, 15–30 min)

**Приоритет**: Critical.
**Триггер для rollback**: `ruff check` или GUI smoke-test падает → `git reset --hard HEAD`.
**Expected KPI**: −7 строк чистого кода (`base_table.py` LOC Δ ≈ −7).

---

### 1.1 Удалить избыточное состояние `_hovered_toggle`

**Где (актуальные строки, проверено 2026-09-20)**:
- Поле класса → [ExplorerHeaderView.__init__ L330](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/base_table.py#L330)
- Изменение → [mouseMoveEvent L360–L364](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/base_table.py#L360-L364)
- Сброс → [leaveEvent L369](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/base_table.py#L369)

**Точный diff**:
```python
# --- УДАЛИТЬ ---
# __init__ L330
self._hovered_toggle = False

# mouseMoveEvent L360
on_toggle = bool(sec >= 0 and sec != 0)  # ← всегда True для sec ≥1
# mouseMoveEvent L361–L364
if sec != self._hovered_section or on_toggle != self._hovered_toggle:
    self._hovered_section = sec
    self._hovered_toggle = on_toggle

# leaveEvent L369
self._hovered_toggle = False

# --- ДОБАВИТЬ ---
# mouseMoveEvent (вместо удалённого)
if sec != self._hovered_section:
    self._hovered_section = sec
```

**Definition of Done (DoD)**:
- [ ] `grep -n "_hovered_toggle" app/views/widgets/link/base_table.py` → **0 совпадений** (ни поля, ни чтений/записей).
- [ ] `ruff check app/views/widgets/link/base_table.py` → 0 ошибок.
- [ ] GUI тест: курсор над «Заметки» (секция 4) → стрелка появляется; курсор в «Название» (секция 0) → ничего не рисуется.
- [ ] Regression: нажатие на секцию 2 «Порядок» → сортировка ASC/DESC/сброс цикл работает.

**Risk**: Нет (pure delete).

---

### 1.2 Удалить неиспользуемую локальную `bg = pal.window().color()`

**Где**: [paintEvent L418](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/base_table.py#L418)

**Точный diff**:
```diff
        if table_hover_color is None:
            hc = pal.color(QPalette.ColorRole.Highlight)
            hc.setAlpha(40)
            table_hover_color = hc
-
-       bg = pal.window().color()

        sec = hovered_sec
```

**DoD**:
- [ ] `grep -n "^\s*bg\s*=" app/views/widgets/link/base_table.py` → 0 совпадений внутри paintEvent.
- [ ] `ruff` 0 ошибок.

---

### 1.3 Удалить неиспользуемую локальную `icon_normal`

**Где**: [paintEvent L437](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/base_table.py#L437)

**Точный diff**:
```diff
-       icon_normal, icon_hover = self._get_icon_colors()
+       _icon_normal, icon_hover = self._get_icon_colors()
        chev_color = icon_hover
```

**DoD**:
- [ ] `ruff check --select=F841 app/views/widgets/link/base_table.py` → 0 предупреждений «local variable assigned but never used».
- [ ] Убедиться, что `QPen` импорт **оставлен** (он используется L439). 🚨 КРИТИЧНО.

---

## Level 2 — Dependency Inversion 🟡 (Encapsulation, 1–2 hr)

**Приоритет**: Medium.
**Rollback**: `git revert` коммита(ов) уровня.
**Expected KPI**: `ExplorerHeaderView` больше не читает `parent().property('hoverRowColor')`. Coupling (ExplorerHeader → LinksTableView) = 0 по parent-цепочке.

---

### 2.1 Добавить `hoverHeaderColor: QColor` как pyqtProperty хедера

**Где реализация**:
- Новый блок в `ExplorerHeaderView` (до `__init__`, сразу после `CHEVRON_COMPARTMENT_WIDTH`).

**Шаблон реализации (copy-paste-ready)**:
```python
class ExplorerHeaderView(QHeaderView):

    CHEVRON_COMPARTMENT_WIDTH = 24

    # --- NEW pyqtProperty block ---------------------------------------------
    def _get_hover_header_color(self) -> QColor:
        try:
            return getattr(self, "_hover_header_color", QColor())
        except Exception:
            return QColor()

    def _set_hover_header_color(self, value) -> None:
        try:
            new_color = value if isinstance(value, QColor) else QColor(str(value))
            old_color = self._get_hover_header_color()
            if new_color != old_color:
                self._hover_header_color = new_color
                vp = self.viewport()
                if vp is not None:
                    vp.update()
        except Exception:
            return

    hoverHeaderColor = pyqtProperty(
        QColor, fget=_get_hover_header_color, fset=_set_hover_header_color
    )
    # --- END NEW -------------------------------------------------------------
```

**Использование в paintEvent вместо parent-chain read**:
```python
# --- paintEvent L403–L416. ЗАМЕНИТЬ ---
hc = self._get_hover_header_color()
if isinstance(hc, QColor) and hc.isValid():
    table_hover_color = QColor(hc)
    table_hover_color.setAlpha(70)
else:
    hc2 = pal.color(QPalette.ColorRole.Highlight)
    hc2.setAlpha(40)
    table_hover_color = hc2
```

**Точка инъекции (где передаётся цвет при создании таблицы)**:
Нужно найти, где у `LinksTableView` создаётся `self.setHorizontalHeader(...)`. Скорее всего в `__init__` таблицы или в init-потомке:
```python
# В конструкторе LinksTableView СРАЗУ после ExplorerHeaderView(...)
header = ExplorerHeaderView(Qt.Orientation.Horizontal, self)
header.hoverHeaderColor = self.hoverRowColor  # ← явная инъекция
self.setHorizontalHeader(header)
```

**DoD L2.1**:
- [ ] `grep -n "parent_table" app/views/widgets/link/base_table.py` → 0 совпадений (ссылка на родителя удалена из paintEvent).
- [ ] QSS-тест: добавить в тему `.qss` строку `ExplorerHeaderView { qproperty-hoverHeaderColor: #FF0000; }` → hover фон секций ярко-красный.
- [ ] Удалить `.qss`-строку → при hover вернулся fallback `QPalette.Highlight` alpha 40.
- [ ] Все 3 стандартные темы (common / violet_pulse / sakura_anime) не имеют визуальной регрессии.

---

### 2.2 (Optional) Добавить `sortChevronHoverColor: QColor` (цвета тем без registry)

**Приоритет**: Optional (только если registry-цветы ломаются на кастомных темах).
- DoD: `_get_icon_colors` читает сначала `self.sortChevronHoverColor`, потом `palette.WindowText`, потом `theme_registry` (registry = last-resort fallback, не primary).
- Контракт QSS: аналогично п.2.1, в `.qss` можно задать `qproperty-sortChevronHoverColor: #00FFFF`.

---

## Level 3 — Architectural Ideal 🔵 (Reusable header, 4–8 hr)

**Приоритет**: Low. Выполнять ТОЛЬКО если планируется повторное использование `ExplorerHeaderView` в других таблицах (например, таблица синхронизации, история, таблица групп).
**Зависимость между подпунктами**: L3.3 → requires (L3.1 ✅ AND L3.2 ✅). L3.1 и L3.2 независимы друг от друга.

---

### 3.1 Kill `if section == 0:` в paintSection → через `SE_HeaderIcon` ProxyStyle

**Где**:
- Сейчас [paintSection L373–L392](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/base_table.py#L373-L392) (весь if-блок).
- Добавление: `ExplorerHeaderStyle.subElementRect(SE_HeaderIcon, ...)`.

**Шаг 1. Зарегистрировать custom-роль**:
В [links_model.py L37](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/links_model.py#L37) **добавить строку**:
```python
HEADER_CHEVRON_PADDING_ROLE = int(Qt.ItemDataRole.UserRole) + 101
HEADER_CENTER_ICON_ROLE    = int(Qt.ItemDataRole.UserRole) + 102   # ← NEW
```

И в `headerData()` для секции 0 **вернуть `True`** по этой роли.

**Шаг 2. Добавить override в ExplorerHeaderStyle**:
```python
def subElementRect(self, element, opt: QStyleOptionHeader, widget=None) -> QRect:
    # Сначала SE_HeaderLabel (как сейчас)…
    rect = super().subElementRect(element, opt, widget)
    if element == QStyle.SubElement.SE_HeaderLabel:
        ...  # оставить как есть

    # --- NEW: центрирование иконки секции по запросу модели ---
    elif element == QStyle.SubElement.SE_HeaderIcon:
        section = getattr(opt, "section", -1)
        model = self._header.model() if self._header is not None else None
        if model is not None:
            try:
                center = bool(
                    model.headerData(
                        section, Qt.Orientation.Horizontal, HEADER_CENTER_ICON_ROLE
                    )
                )
            except Exception:
                center = False
            if center:
                parent_rect = opt.rect
                w = rect.width()
                rect.moveLeft(parent_rect.left() + max(0, (parent_rect.width() - w) // 2))
                rect.moveTop(parent_rect.top() + max(0, (parent_rect.height() - rect.height()) // 2))
    return rect
```

**Шаг 3. Удалить if-блок из paintSection**. Оставить:
```python
def paintSection(self, painter, rect, logicalIndex):
    super().paintSection(painter, rect, logicalIndex)
```

**DoD L3.1**:
- [ ] `grep -n "logicalIndex == 0" base_table.py` → 0.
- [ ] Иконка в секции 0 «group launch» находится **строго по центру** (и проверить скриншот-дифф до/после).
- [ ] Размер иконки = стиль-нативный (не хардкод `sz = 20`).
- [ ] Хэндлы изменения размера секций 0 и 1 — тянутся, границы рисуются корректно.

**Risk**: `SE_HeaderIcon` может быть не поддерживается в старых стилях Fusion/Windows → при любом падении exception → fallback к rect super. (try/except уже стоит).

---

### 3.2 Шеврон через нативный `QStyle.drawPrimitive` вместо ручной полилинии

**Где**: [paintEvent L437–L449](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/widgets/link/base_table.py#L437-L449) (весь QPen-QPolygonF-блок).

**Шаблон реализации**:
```python
import Qt.PrimitiveElement  # уже импорт QStyle сделан

# В paintEvent, после fillRect фона:
style_inst = self.style()
arrow_opt = QStyleOption()
arrow_opt.initFrom(self)
arrow_opt.state = (
    QStyle.StateFlag.State_Enabled
    | (QStyle.StateFlag.State_MouseOver if sec == hovered_sec else QStyle.StateFlag.State_None)
)
tx = sec_x + sec_w - toggle_w
full_arrow_rect = QRect(tx, 0, toggle_w, h)
arrow_opt.rect = style_inst.subElementRect(
    QStyle.SubElement.SE_HeaderArrow, arrow_opt, self
)
if arrow_opt.rect.isNull():
    # Fallback: центрировать по компартменту
    aw = toggle_w - 4
    ah = max(8, h // 3)
    arrow_opt.rect = QRect(tx + (toggle_w - aw) // 2, (h - ah) // 2, aw, ah)

prim_dir = (
    QStyle.PrimitiveElement.PE_IndicatorArrowUp
    if sorted_here and self.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
    else QStyle.PrimitiveElement.PE_IndicatorArrowDown
)
style_inst.drawPrimitive(prim_dir, arrow_opt, p, self)
# УДАЛИТЬ весь блок icon_normal→pts→drawPolyline.
```

**DoD L3.2**:
- [ ] `grep -n "QPolygonF\|QPointF(cx" base_table.py` → 0 в paintEvent (ручной глиф удалён).
- [ ] Шеврон при 100% DPI и 150% DPI — не размыт, центрирован.
- [ ] Переключить тему приложения на светлую `common` и тёмную `violet_pulse` → цвет стрелки меняется **автоматически** (без доп. кода).
- [ ] Направление: ASC = ▲, DESC = ▼. Совпадает с направлением стандартного `QHeaderView::down-arrow` в QSS.

---

### 3.3 Перенести hover-фон в paintSection через `State_MouseOver` (убрать overlay fillRect)

**Pre-condition**: L3.1 ✅ (paintSection единый для всех секций) и L3.2 ✅.

**Критическая правка в коде**: initStyleOption сам может выставить MouseOver случайно — мы должны **сначала сбросить** флаг, а потом добавить наш, чтобы избежать конфликтов:
```python
def paintSection(self, painter, rect, logicalIndex):
    opt = QStyleOptionHeader()
    self.initStyleOption(opt)
    opt.rect = rect
    opt.section = logicalIndex
    # --- CRITICAL: deterministic hover-state (not Qt default guess) ---
    opt.state &= ~QStyle.StateFlag.State_MouseOver   # ← СНЯТЬ сначала
    if logicalIndex == self._hovered_section and logicalIndex != 0:
        opt.state |= QStyle.StateFlag.State_MouseOver   # ← ПОСТАВИТЬ наш
    self.style().drawControl(QStyle.ControlElement.CE_Header, opt, painter, self)
    # super().paintSection — НЕ ВЫЗЫВАЕМ. drawControl эквивалент, но с точным state.
```

После этого — **удалить** `p.fillRect(...)` из paintEvent полностью.

**DoD L3.3**:
- [ ] `grep -n "fillRect.*table_hover_color" base_table.py` → 0.
- [ ] При hover цвета не «едут» (отсутствует двойное наложение альфы: alpha 70 × default Qt-hover = 180).
- [ ] Цвет фона hover при указании `QHeaderView::section:hover { background: #00FF00; }` в QSS — зелёный, применяется корректно.

---

## Level 4 — Regression Gates & Acceptance (Definition of Done for levels)

Каждый уровень считается завершённым **только после прохождения всех строк его чек-листа**.

### L4.1 Общий GUI smoke-test (после всех уровней)

- [ ] Курсор над секцией 0 → ничего не рисуется (нет фона, нет стрелки).
- [ ] Курсор над секциями 1–5 → фон ВСЕЙ секции (не 24px) + стрелка справа.
- [ ] Курсор уходит за границы header → фон и стрелка исчезают за <1 кадра (нет задержки).
- [ ] Нажатие в любую точку секции 2 «Порядок» → `sortIndicatorSection()` меняется.
- [ ] Тяга за resize-handle на границе секций 2 и 3 → ширина меняется, хэндл виден.
- [ ] Очень узкая секция (сжать до ширины 60 px, меньше `3*24=72` → guard `min_w`) → **ничего не рисуется** (no chevron, no crash).
- [ ] Смена темы `theme_registry.apply("cyberpunk_neon")` → фон hover и стрелка цвета читаются корректно из palette (не старые цвета).
- [ ] DPI: тест на 100% (96 dpi) и 150% (144 dpi) → стрелка не размыта, 1px разделитель не превратился в 2px.

### L4.2 Static analysis (после каждого уровня)

- [ ] `ruff check` → 0 (`F401` imports, `F841` unused-local, `E501` length).
- [ ] `GetDiagnostics` в IDE → 0 красных/жёлтых.
- [ ] `mypy` (если настроен) → 0.

### L4.3 Theme matrix (end-to-end, опционально но рекомендуется)

| Тема | Chevron цвет при hover | Фон hover | Разделитель (если включён) |
|---|---|---|---|
| `common` (светлая) | | | |
| `violet_pulse` (тёмная) | | | |
| `sakura_anime` | | | |
| `cyberpunk_neon` | | | |
| `rasta_royale` | | | |

---

## Appendix A — Architecture Data-Flow Diagram (ASCII)

```
┌──────────────────────────────────── LinksTableModel ────────────────────────────────────┐
│ headerData(sec, role)                                                                   │
│  • DecorationRole [sec=0]  →  list_start_icon                                          │
│  • TextAlignmentRole        →  AlignCenter / AlignLeft                                  │
│  • HEADER_CHEVRON_PADDING_ROLE (+101) → True/False  (ask from ProxyStyle)              │
│  • HEADER_CENTER_ICON_ROLE   (+102) → True/False  (ask from ProxyStyle, L3.1)          │
└───────────▲──────────────────────────────────────▲──────────────────────────────────────┘
            │ queries custom roles                 │ queries standard roles
            │                                      │
┌───────────┴────────────────┐  initStyleOption    └──────────────────────────────────┐
│  ExplorerHeaderStyle       │──────────────────────────────────────────────────────┐  │
│  (QProxyStyle)             │                                                     │  │
│                            │  SE_HeaderLabel rect → adjust(+24,0,-24,0) if pad  │  │
│                            │  SE_HeaderIcon rect  → center if HEADER_CENTER_*   │  │
└───────────▲────────────────┘                                                     │  │
            │ subElementRect overrides                                             │  │
            │                                                                      │  │
┌───────────┴────────────────────────────┐    drawControl(CE_Header, opt)        │  │
│     ExplorerHeaderView.paintSection    │────────────────────────────────────────┘  │
│     (Level 3.1 → single super() call) │                                           │
└───────────▲────────────────────────────┘                                           │
            │ Qt paints text, borders, selection with correct geometry               │
            │                                                                          │
┌───────────┴────────────────────────────┐   overlay (after super paintEvent)         │
│     ExplorerHeaderView.paintEvent      │────────────────────────────────────────────┘
│  after super():                        │
│   1. fillRect(entire section) → hover  │ ← Level 3.3 удаляет этот шаг
│   2. draw chevron at right 24px        │ ← Level 3.2 меняет на drawPrimitive
└────────────────────────────────────────┘
```

---

## Appendix B — QSS Contract (для дизайнеров тем)

### Public API ExplorerHeaderView после Level 2+3

| Селектор / Свойство | Тип | Описание |
|---|---|---|
| `QHeaderView::section` | QSS state | Стандартный. `:hover`, `:pressed`, `:checked`. **После L3.3 работает 100%**. |
| `QHeaderView::section:first` | QSS state | Секция 0 (иконка «group launch»). |
| `ExplorerHeaderView { qproperty-hoverHeaderColor: ... }` | `QColor` | Цвет overlay-фона при hover секции (используется до L3.3; после L3.3 лучше использовать `:hover` state). |
| `ExplorerHeaderView { qproperty-sortChevronHoverColor: ... }` | `QColor` | Яркий цвет стрелки при hover (используется до L3.2; после L3.2 стиль сам выбирает цвет). |
| `QHeaderView::down-arrow` | QSS subcontrol | **После L3.2** — стандартный subcontrol. Ширина/высота шеврона. |
| `QHeaderView::up-arrow` | QSS subcontrol | **После L3.2** — то же для ASC-сортировки. |

### Примеры

**violet_pulse (тёмно-фиолет)**:
```qss
QHeaderView::section:hover { background: rgba(76, 31, 84, 0.55); }
/* После L3.2 можно кастомизировать стрелку */
QHeaderView::down-arrow { image: url(:icons/chevron_down_violet.svg); }
```

**common (светлая)**:
```qss
ExplorerHeaderView {
    qproperty-hoverHeaderColor: rgba(0, 120, 212, 0.27);  /* Win11 accent × 27% */
}
```

---

## Success Criteria (Whole Migration Done)

| Метрика | Before (dbfd7551) | Target (After L1+L2+L3) | Measurement |
|---|---|---|---|
| Dead code & unused state | 3 items (`bg`, `icon_normal`, `_hovered_toggle`) | 0 | `ruff --select=F841` + manual grep |
| Hardcoded `section == X` в ExplorerHeaderView | 1 (L373) | 0 | `grep "logicalIndex == \|section == "` |
| `parent()` coupling (чтение родительских property) | 1 вызов (L407) | 0 | `grep "parent().property\|parent_table"` |
| Custom painted polyline-based chevron | Да (8×4 px, 2 магические константы) | Нет (QStyle native) | Отсутствие `QPolygonF` в импортах paintEvent |
| QSS controllable colors | 1 (`hoverRowColor` на таблице, не хедере) | 3+ (`hoverHeaderColor`, `sortChevronHoverColor`, `QHeaderView::section:hover`) | Проверка дизайнером: изменение 1 строки QSS → немедленный визуальный эффект |
| Reusability: new-table integration effort | 4–8 ч (распутывание хардкодов) | <30 мин (подключить ExplorerHeaderView + передать 2 pyqtProperty) | Subjective by dev + integration checklist |
