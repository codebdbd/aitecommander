# План рефакторинга размерной архитектуры панелей (Уровень 3 — Архитектурный идеал)

> Дата: 2026-09-20  
> Контекст: Левая панель фактически 332 px вместо 320 из-за `QWidget.sizeHint()`, который растиражировался из `StructureTreeView` + `QLayout.contentsMargins` (L=6 + R=6 = +12 px).  
> Цель: вынести все размерные политики панелей в единый семантический слой, стандартизировать сохранение оконного состояния, закрыть юнит-тестами. Для long-term поддержки и команд от 5+ человек.

---

## 0. Коренная причина (без неё все решения — латание симптомов)

В Qt есть строгая цепочка вычисления размеров. По умолчанию работает так:

```
QTreeView.sizeHint() ≈ 320 px   («желание» самого дерева)
        +
QLayout.contentsMargins = [6, 6, 6, 0]   (добавляет 12 px по горизонтали)
        =
QWidget#LeftPanel.sizeHint() = 332 px   (желание родителя)
        ↕ конфликтует с
QSplitter.setSizes([320, 704])   (наше пожелание)
```

Qt **всегда** выбирает в пользу `sizeHint`, чтобы не обрезать контент. В этом не баг Qt — это правильное поведение. Проблема у нас: мы не дали виджету корректный sizeHint, соответствующий нашим намерениям.

---

## 1. Общая схема изменений (8 artefacts)

| # | Artefact | Тип | Назначение |
|---|---|---|---|
| 1 | `app/config_data/app_config.json` | ✏️ правка | Новый семантический блок `ui.panels.{left,right,bottom}` |
| 2 | `app/config_data/ui_config.py` | ✏️ правка | Датакласс `PanelSizePolicy` + `UIConfig.get_panel_size_policy(name)` |
| 3 | `app/views/main_components/common/protocols.py` | ✏️ правка | Протокол `PanelSizeControlled` + ре-экспорт `PanelSizePolicy` |
| 4 | **новое** `app/views/widgets/base/panel.py` | ➕ файл | Базовый класс `PanelWidget(QWidget, PanelSizeControlled)` — перехватывает sizeHint |
| 5 | **новое** `app/controllers/system/window_state_manager.py` | ➕ файл | `WindowStateManager.save()/load()` — атомарное хранение geometry + splitter states + stack index |
| 6 | `app/views/main_components/ui/window_ui_setup.py` | ✏️ правка | `setup_left_panel` использует `PanelWidget`; удалить `WindowSettings._store_state` в пользу state_mgr |
| 7 | `app/views/main_components/ui/right_panel_setup.py` | ✏️ правка | Регистрирует сплиттер, убирает `_get_initial_splitter_sizes`, интегрирует `WindowStateManager` |
| 8 | **новое** `tests/test_panel_sizes.py` | ➕ файл | 3 юнит-теста: `sizeHint == initial_width`, `min_width respected`, graceful fallback |

---

## 2. Детализация по файлам

---

### 2.1 `app/config_data/app_config.json` — новая схема `ui.panels.*`

**Где вставлять:** сразу под существующим ключом `splitter_sizes` (старый ключ **не удалять** — он нужен для миграции, будет вычищен через 1–2 релиза).

```json
{
  "ui": {
    ...
    "splitter_handle_width": 1,
    "splitter_stretch_factors": [0, 1],
    "splitter_sizes": [320, 704],

    "panels": {
      "left": {
        "initial_width": 320,
        "min_width":     240,
        "max_width":     480
      },
      "right": {
        "initial_width": 704,
        "min_width":     400,
        "max_width":     0
      },
      "bottom": {
        "initial_height": 140,
        "min_height":     80,
        "max_height":     400
      }
    },

    "main_layout_margins": [0, 0, 0, 0],
    ...
  }
}
```

**Семантика полей:**
- `initial_*` — размер при **ПЕРВОМ** запуске (пока нет сохранённого пользовательского состояния). Для левой панели это ровно та ширина, которую вы хотите «от края до края» виджета `#LeftPanel`. Margins L=6 + R=6 будут вычитаться **внутрь** неё.
- `min_*` — ниже не сжимать (спасёт от случайного удушения панели при High DPI или большой системе шрифтов).
- `max_*` — верхняя граница. `0` означает «нет потолка» (Qt: 16777215 = `QWIDGETSIZE_MAX`).

---

### 2.2 `app/config_data/ui_config.py` — `PanelSizePolicy` + `get_panel_size_policy`

**В самый верх файла** (после `from __future__ import annotations`):

```python
from dataclasses import dataclass
from typing import Optional
```

**Далее** (рядом с прочими dataclass‑подобными сущностями, например после класса UIConfig или перед ним):

```python
@dataclass(frozen=True)
class PanelSizePolicy:
    """Семантическое описание размерной политики панели.

    0 в max_* означает «без ограничения сверху» (Qt: QWIDGETSIZE_MAX = 16_777_215).
    initial_* — желаемый размер при ПЕРВОМ запуске (пока нет сохранённого состояния).
    """
    panel_name: str
    initial_width:  Optional[int] = None
    min_width:      Optional[int] = None
    max_width:      Optional[int] = None
    initial_height: Optional[int] = None
    min_height:     Optional[int] = None
    max_height:     Optional[int] = None

    _QWIDGETSIZE_MAX = 16_777_215

    def effective_max_width(self)  -> int:  return self.max_width  or self._QWIDGETSIZE_MAX
    def effective_max_height(self) -> int:  return self.max_height or self._QWIDGETSIZE_MAX
```

**Внутри класса `UIConfig`** (в конец секции размерных/лейаутных геттеров, после `get_splitter_sizes`):

```python
def get_panel_size_policy(self, panel_name: str) -> PanelSizePolicy:
    """Вернуть размерную политику для именованной панели.

    При отсутствии в конфиге подставляет разумные дефолты, ссылаясь
    на устаревший ``splitter_sizes`` для сохранения обратной совместимости.
    """
    raw: dict = self.get(f"ui.panels.{panel_name}", {}) or {}
    if not isinstance(raw, dict):
        raw = {}

    # дефолты: для left/right — наследуем от устаревшего splitter_sizes[0]/[1]
    legacy_sizes: list = self.get("ui.splitter_sizes", [250, 750]) or [250, 750]

    if panel_name == "left":
        defaults = dict(initial_width=legacy_sizes[0], min_width=200, max_width=0)
    elif panel_name == "right":
        defaults = dict(initial_width=legacy_sizes[1], min_width=320, max_width=0)
    elif panel_name == "bottom":
        defaults = dict(initial_height=140, min_height=80, max_height=0)
    else:
        defaults = {}

    merged = {**defaults, **raw}
    return PanelSizePolicy(panel_name=panel_name, **merged)
```

---

### 2.3 `app/views/main_components/common/protocols.py` — `PanelSizeControlled`

**Добавить в импорты** (в `TYPE_CHECKING`):

```python
if TYPE_CHECKING:
    from app.config_data.ui_config import PanelSizePolicy
```

**Добавить протокол** в конец файла (или рядом с `MainWindowProtocol`):

```python
@runtime_checkable
class PanelSizeControlled(Protocol):
    """Контракт: виджет, являющийся «панелью» окна (левая, правая, нижняя, …).

    За гарантированное применение политики отвечает базовый ``PanelWidget``;
    протокол нужен для стороннего кода, который хочет её запросить/поменять.
    """

    def panel_size_policy(self) -> "PanelSizePolicy":
        """Вернуть текущую размерную политику панели."""
        ...

    def apply_panel_size_policy(self, policy: "PanelSizePolicy") -> None:
        """Применить политику к виджету (sizeHint, min/maxSize)."""
        ...
```

---

### 2.4 🆕 `app/views/widgets/base/panel.py` — базовый класс `PanelWidget`

(Новый файл, соседка к `base_widgets.py` и `base_panel_widgets.py`.)

```python
"""Базовый класс панели (левая, правая, нижняя) с контролируемой размерной политикой.

Motivation
----------
QWidget.sizeHint() по умолчанию собирается из sizeHint() вложенных
виджетов + layout margins. Из-за этого дерево StructureTreeView «раздувает»
левую панель до 332 px (320 + left_layout margins 6+6), несмотря на
``QSplitter.setSizes([320, ...])``.

``PanelWidget`` явно возвращает ``initial_width`` из ``PanelSizePolicy``
как sizeHint, не давая дочерним виджетам диктовать размер родителю.

При этом сохраняется гибкость QSplitter: min_* / max_* задают диапазон,
но пользователь всё ещё может двигать разделитель в этих пределах.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QWidget

from app.config_data.runtime_config import runtime_app_config as _cfg
from app.config_data.ui_config import PanelSizePolicy
from app.views.main_components.common.protocols import PanelSizeControlled


class PanelWidget(QWidget, PanelSizeControlled):
    def __init__(self, panel_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._panel_name = panel_name
        self._policy: PanelSizePolicy = _cfg.ui.get_panel_size_policy(panel_name)
        self._apply_policy()

    # ── реализация PanelSizeControlled ────────────────────────────
    def panel_size_policy(self) -> PanelSizePolicy:
        return self._policy

    def apply_panel_size_policy(self, policy: PanelSizePolicy) -> None:
        self._policy = policy
        self._apply_policy()
        self.updateGeometry()

    # ── override размеров (основная суть) ─────────────────────────
    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        w = self._policy.initial_width  if self._policy.initial_width  is not None else base.width()
        h = self._policy.initial_height if self._policy.initial_height is not None else base.height()
        return QSize(int(w), int(h))

    def minimumSizeHint(self) -> QSize:
        base = super().minimumSizeHint()
        w = self._policy.min_width  or base.width()
        h = self._policy.min_height or base.height()
        # не зажимаем ниже Qt-дефолта, если он оказался жёстче
        return QSize(max(w, base.width()), max(h, base.height()))

    # ── internal ───────────────────────────────────────────────────
    def _apply_policy(self) -> None:
        p = self._policy
        if p.min_width is not None:
            self.setMinimumWidth(p.min_width)
        if p.max_width is not None and p.max_width > 0:
            self.setMaximumWidth(p.max_width)
        else:
            self.setMaximumWidth(PanelSizePolicy._QWIDGETSIZE_MAX)

        if p.min_height is not None:
            self.setMinimumHeight(p.min_height)
        if p.max_height is not None and p.max_height > 0:
            self.setMaximumHeight(p.max_height)
        else:
            self.setMaximumHeight(PanelSizePolicy._QWIDGETSIZE_MAX)
```

---

### 2.5 🆕 `app/controllers/system/window_state_manager.py` — `WindowStateManager`

(Новый файл, соседка к `wiring.py` и другим system-контроллерам.)

```python
"""Управление сохранением/восстановлением оконного состояния.

Заменяет прежний подход с набором разрозненных SettingsManager ключей
(window.width, window.splitter_left, window.maximized, …)
на единый атомарный словарь ``window_state``, сохраняющий:

  * ``version``     — схема данных (int), для будущих миграций
  * ``maximized``   — развёрнуто ли окно
  * ``geometry``    — [x, y, w, h] (при maximized=True хранит normalGeometry)
  * ``splitter_states`` — {имя: bytes}, где bytes = QSplitter.saveState()
  * ``stack_index`` — активный индекс QStackedLayout (tiles / table view)

Философия
---------
* ``save()`` — снимок состояния в ``SettingsManager['window_state']`` + flush
* ``load()`` — попытка восстановить всё; при невозможности fallback на defaults
* ``register_splitter(name, splitter)`` — семантическая регистрация по имени
  ('main_splitter', 'top_level_splitter', …). Позволяет иметь >1 сплиттер.
* ``migrate_from_legacy_if_needed()`` — один раз собирает State из устаревших
  ключей ``window.splitter_left`` / ``window.width`` / …, если ``window_state``
  ещё не существует. Гарантирует обратную совместимость «по умолчанию».
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from PyQt6.QtCore import QByteArray, QObject, pyqtSignal
from PyQt6.QtWidgets import QSplitter, QStackedLayout, QWidget

from app.core.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

STATE_KEY = "window_state"
STATE_VERSION = 1


@dataclass
class WindowState:
    version:         int = STATE_VERSION
    maximized:       bool = False
    # x, y, width, height — normal (non-maximized) геометрия окна
    geometry:        list[int] = field(default_factory=lambda: [0, 0, 1024, 768])
    splitter_states: dict[str, bytes] = field(default_factory=dict)
    stack_index:     int | None = None


class WindowStateManager(QObject):
    """Единая точка сохранения/загрузки размерного состояния главного окна."""

    state_restored = pyqtSignal()
    state_saved = pyqtSignal()

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._splitters: dict[str, QSplitter] = {}

    # ── registration API ─────────────────────────────────────────
    def register_splitter(self, name: str, splitter: QSplitter) -> None:
        """Зарегистрировать сплиттер по семантическому имени.

        Пример::

            state_mgr.register_splitter("main_splitter", splitter)
            state_mgr.register_splitter("top_bottom_splitter", outer_splitter)
        """
        self._splitters[name] = splitter

    def registered_splitters(self) -> list[str]:
        return list(self._splitters.keys())

    # ── save ─────────────────────────────────────────────────────
    def save(self) -> None:
        """Снять снимок состояния и записать в SettingsManager + flush."""
        state = WindowState()
        w = self._window

        try:
            state.maximized = bool(w.isMaximized())
            if not state.maximized:
                g = w.geometry()
                state.geometry = [int(g.x()), int(g.y()),
                                  int(g.width()), int(g.height())]
            else:
                normal = w.normalGeometry()
                state.geometry = [int(normal.x()), int(normal.y()),
                                  int(normal.width()), int(normal.height())]
        except Exception:
            logger.debug("WindowState: geometry snapshot failed", exc_info=True)

        for name, sp in self._splitters.items():
            try:
                state.splitter_states[name] = sp.saveState().data()
            except Exception:
                logger.debug("WindowState: save splitter %r failed", name, exc_info=True)

        stack = getattr(w, "stack", None)
        if isinstance(stack, QStackedLayout):
            state.stack_index = stack.currentIndex()

        SettingsManager.set(STATE_KEY, asdict(state))
        try:
            SettingsManager.save()
        except Exception:
            logger.debug("WindowState: SettingsManager.save() failed", exc_info=True)
        self.state_saved.emit()

    # ── load ─────────────────────────────────────────────────────
    def load(self, apply_geometry: bool = True) -> WindowState:
        """Восстановить состояние.

        ``apply_geometry=False`` полезно в тестах, где окно не отображается.
        """
        raw: dict[str, Any] | None = SettingsManager.get(STATE_KEY)
        state = self._parse_state(raw)

        # splitter states — до geometry, сплиттер должен быть заполнен
        for name, sp in self._splitters.items():
            blob = state.splitter_states.get(name)
            if blob:
                try:
                    sp.restoreState(QByteArray(blob))
                except Exception:
                    logger.debug(
                        "WindowState: restore splitter %r failed — fallback to defaults",
                        name, exc_info=True,
                    )

        if apply_geometry:
            self._apply_geometry(state)

        stack = getattr(self._window, "stack", None)
        if isinstance(stack, QStackedLayout) and state.stack_index is not None:
            try:
                stack.setCurrentIndex(max(0, min(state.stack_index, stack.count() - 1)))
            except Exception:
                logger.debug("WindowState: restore stack index failed", exc_info=True)

        self.state_restored.emit()
        return state

    # ── migration from legacy keys ───────────────────────────────
    def migrate_from_legacy_if_needed(self) -> None:
        """Если ``window_state`` отсутствует — собрать его из старых ключей.

        Срабатывает **один раз** при апгрейде на новую архитектуру.
        Старые ключи не удаляются (можно вычистить через 1–2 релиза вручную).
        """
        if SettingsManager.get(STATE_KEY) is not None:
            return  # новое состояние уже есть — миграция не требуется

        has_legacy = any(
            SettingsManager.get(k) is not None
            for k in ("window.width", "window.splitter_left", "window.maximized")
        )
        if not has_legacy:
            return  # чистый первый запуск, нечего мигрировать

        state = WindowState()
        try:
            state.maximized = bool(SettingsManager.get("window.maximized", False))
            state.geometry = [
                int(SettingsManager.get("window.x", 50)),
                int(SettingsManager.get("window.y", 50)),
                int(SettingsManager.get("window.width",  1024)),
                int(SettingsManager.get("window.height", 768)),
            ]
            s_left  = SettingsManager.get("window.splitter_left")
            s_right = SettingsManager.get("window.splitter_right")
            if (isinstance(s_left, int) and isinstance(s_right, int)
                    and "main_splitter" in self._splitters):
                # saveState утерян — хотя бы поставить sizes по старым значениям
                self._splitters["main_splitter"].setSizes([s_left, s_right])
        except Exception:
            logger.debug("WindowState: legacy migration failed", exc_info=True)

        SettingsManager.set(STATE_KEY, asdict(state))

    # ── internals ────────────────────────────────────────────────
    @staticmethod
    def _parse_state(raw: dict[str, Any] | None) -> WindowState:
        if not raw or not isinstance(raw, dict):
            return WindowState()
        try:
            return WindowState(
                version=    int(raw.get("version", 1)),
                maximized=  bool(raw.get("maximized", False)),
                geometry=   list(raw.get("geometry") or [0, 0, 1024, 768]),
                splitter_states=dict(raw.get("splitter_states") or {}),
                stack_index=raw.get("stack_index"),
            )
        except Exception:
            logger.debug("WindowState: parse failed — using clean defaults", exc_info=True)
            return WindowState()

    def _apply_geometry(self, state: WindowState) -> None:
        w = self._window
        x, y, gw, gh = (list(state.geometry) + [0, 0, 0, 0])[:4]
        try:
            if state.maximized:
                w.setGeometry(int(x), int(y), int(gw), int(gh))
                w.showMaximized()
            else:
                w.resize(int(gw), int(gh))
                w.move(int(x), int(y))
        except Exception:
            logger.debug("WindowState: apply geometry failed", exc_info=True)
```

---

### 2.6 `app/views/main_components/ui/window_ui_setup.py` — интеграция левой панели

#### 2.6.1 Импорт `PanelWidget`

В самый верх, в блок импортов из `app/views/widgets`:

```python
from app.views.widgets.base.panel import PanelWidget
```

#### 2.6.2 `setup_left_panel` — подменить `QWidget` → `PanelWidget`

Метод [setup_left_panel](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/window_ui_setup.py#L1061-L1086):

```diff
 def setup_left_panel(self, mid: QHBoxLayout) -> None:
-    left_panel = QWidget(self.window)
+    left_panel = PanelWidget(panel_name="left", parent=self.window)
     self.window.left_panel = left_panel
     left_panel.setObjectName("LeftPanel")
     left_panel.setAutoFillBackground(True)
```

> **Эффект сразу:** `left_panel.sizeHint().width()` вернёт **320** (initial_width из `PanelSizePolicy`). Margins L=6 + R=6 вычтутся **внутрь** этих 320 (контент‑дерево получит 308 px по ширине). `QSplitter.setSizes([320, …])` больше не будет «спорить» с sizeHint виджета — пожелание совпадает.

#### 2.6.3 Класс `WindowSettings` — заменить `_store_state` → `WindowStateManager.save()`

Сейчас в классе (строки ~330–372) метод `_store_state()` вручную пишет 7 отдельных ключей в `SettingsManager`. Вместо этого вызвать state manager:

```python
def _store_state(self) -> None:
    """Единый снимок состояния: geometry + splitter states + stack index."""
    mgr = getattr(self.window, "window_state_mgr", None)
    if mgr is not None:
        try:
            mgr.save()
        except Exception:
            self._logger.debug("WindowSettings: state_mgr.save() failed", exc_info=True)
```

Метод `_flush()` (вызывает `SettingsManager.save()`) становится **опциональным** — внутри `WindowStateManager.save()` flush уже делается. Если есть желание сохранить защиту от частых I/O — оставьте, он не повредит.

---

### 2.7 `app/views/main_components/ui/right_panel_setup.py` — интеграция сплиттера

Файл: `build_shell()` [строки 37–83](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/right_panel_setup.py#L37-L83).

#### Шаг 1: правый виджет тоже `PanelWidget`

```diff
 def build_shell(self, mid: QHBoxLayout) -> None:
     ...
-    right_panel = QWidget(self.window)
+    from app.views.widgets.base.panel import PanelWidget
+    right_panel = PanelWidget(panel_name="right", parent=self.window)
     right_panel.setObjectName("RightPanel")
```

#### Шаг 2: убрать устаревшие `splitter_sizes` + метод `_get_initial_splitter_sizes`

```diff
     splitter_sizes = self._get_initial_splitter_sizes()   # УДАЛИТЬ
     splitter.setSizes(splitter_sizes)                     # УДАЛИТЬ
     self.window._first_structure_load = True
```

**Весь метод `_get_initial_splitter_sizes()` (строки ~195–208) — удалить целиком.**  
Его функцию теперь выполняют: `WindowStateManager.load()` → при отсутствии состояния: `PanelSizePolicy.initial_width`.

#### Шаг 3: интеграция `WindowStateManager`

**После** `splitter.addWidget(right_panel)` и **до** завершения метода вставить:

```python
# ── WindowStateManager: create/attach + register splitter ─────────
state_mgr: WindowStateManager | None = getattr(self.window, "window_state_mgr", None)
if state_mgr is None:
    from app.controllers.system.window_state_manager import WindowStateManager
    state_mgr = WindowStateManager(self.window)
    self.window.window_state_mgr = state_mgr

state_mgr.register_splitter("main_splitter", splitter)

# Попытка миграции из legacy → потом восстановление state → иначе fallback на initial
state_mgr.migrate_from_legacy_if_needed()
loaded = state_mgr.load(apply_geometry=False)

if "main_splitter" not in loaded.splitter_states:
    # Чистый первый запуск — применить initial размеры из PanelSizePolicy
    left_pol  = (self.window.left_panel.panel_size_policy()
                 if hasattr(self.window.left_panel, "panel_size_policy") else None)
    right_pol = right_panel.panel_size_policy()
    splitter.setSizes([
        left_pol.initial_width  if left_pol  and left_pol.initial_width  is not None else 320,
        right_pol.initial_width if right_pol and right_pol.initial_width is not None else 704,
    ])
```

---

### 2.8 🆕 `tests/test_panel_sizes.py` — юнит-тесты

```python
"""Проверки на семантику панелей: sizeHint, min/max размеры.

Регрессионный сценарий (fixed bug):
    Без PanelWidget StructureTreeView.sizeHint() ≈ 320 px +
    left_layout.contentsMargins [6,6,6,0] + 12 px →
    LeftPanel.sizeHint() = 332 px, несмотря на setSizes([320, ...]).

    С PanelWidget sizeHint контролируется явно через PanelSizePolicy.initial_width.
"""
from __future__ import annotations

import os

import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QWidget,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.config_data.runtime_config import runtime_app_config
from app.views.main_components.ui.window_ui_setup import WindowUISetup
from app.views.widgets.base.panel import PanelWidget


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_left_panel_sizehint_matches_config_initial_width(qapp: QApplication) -> None:
    """Left panel sizeHint().width() == ui.panels.left.initial_width ВСЕГДА."""
    expected = int(runtime_app_config.ui.get_panel_size_policy("left").initial_width)

    window = QMainWindow()
    mid = QHBoxLayout()
    host = QWidget(); host.setLayout(mid); window.setCentralWidget(host)

    initializer = type("I", (), {"window": window})()
    ui = WindowUISetup(initializer)
    ui.setup_left_panel(mid)          # создаёт PanelWidget + наполняет деревом/сферами

    lp = window.left_panel
    assert lp is not None
    assert lp.sizeHint().width() == expected, (
        f"left_panel sizeHint width {lp.sizeHint().width()} "
        f"!= expected {expected} (ui.panels.left.initial_width)"
    )


def test_left_panel_min_width_respected(qapp: QApplication) -> None:
    """PanelWidget.setMinimumWidth() соответствует PanelSizePolicy.min_width."""
    cfg = runtime_app_config.ui.get_panel_size_policy("left")
    expected_min = int(cfg.min_width or 0)

    p = PanelWidget("left")
    assert p.minimumWidth() >= expected_min, (
        f"left_panel minWidth {p.minimumWidth()} < policy min_width {expected_min}"
    )


def test_unknown_panel_falls_back_gracefully(qapp: QApplication) -> None:
    """Панель с неизвестным именем не падает и создаётся без исключений."""
    p = PanelWidget("nonexistent_panel_xyz")
    hint = p.sizeHint()
    assert hint.isValid()
    # Без initial_width sizeHint.height() не должен быть отрицательным
    assert hint.height() >= 0
```

**Запуск:**

```bash
pytest tests/test_panel_sizes.py -v
```

Ожидается 3 passed.

---

## 3. Обратная совместимость (миграция)

Сделана **без участия пользователя** внутри `WindowStateManager.migrate_from_legacy_if_needed()`.

| Состояние настроек пользователя | Что происходит |
|---|---|
| Есть `window_state` (новая архитектура уже применялась) | Ничего не делаем, живём по-новому |
| Нет `window_state`, но есть старые ключи `window.splitter_left` / `window.width` / `window.maximized` / … | Один раз собираем `WindowState` из них, сохраняем в новый ключ. **Старые ключи не трогаем** (можно вычистить через 1–2 релиза рутинной уборкой) |
| Ничего нет (чистый первый запуск) | Используем `ui.panels.left.initial_width` = 320 — как и задумано |

### Когда чистить legacy (план после релиза)
Через 1–2 публичных релиза, когда уверены, что 99% пользователей хотя бы раз запустили новую версию:
- Удалить из кодовой базы упоминания ключей:
  - `window.splitter_left`, `window.splitter_right`
  - `window.x`, `window.y`, `window.width`, `window.height`, `window.maximized`
- Удалить `get_splitter_sizes()` из `ui_config.py` и ключ `ui.splitter_sizes` из `app_config.json`
  (оставить дефолтную ветку в `get_panel_size_policy` ещё на один релиз «на всякий пожарный»)
- Удалить тело `migrate_from_legacy_if_needed()` или сделать его no-op.

---

## 4. Верификация после внедрения

### 4.1 Unit-тесты
```bash
pytest tests/test_panel_sizes.py tests/test_top_bar_layout_spacings.py -v
```
→ все пройдены.

### 4.2 Ручные проверки

| Проверка | Ожидание |
|---|---|
| Чистый старт (удалить `settings.json`): `left_panel.width()` | **320** ✔ |
| Чистый старт: `left_panel.sizeHint().width()` | **320** ✔ |
| Чистый старт: `window.tree.width()` (дерево внутри) | **308 = 320 − 6 − 6** ✔ |
| Двигнуть сплиттер на 350 / 674 → перезапустить | Размеры восстановились без изменений ✔ |
| High DPI / масштаб 150% / большой системный шрифт | Панель не удушается ниже `min_width=240`, нет обрезки контента ✔ |
| isinstance(left_panel, PanelSizeControlled) | **True** (контракт enforced) ✔ |
| Новая панель «quick_access_bottom» | Создаёшь `PanelWidget("bottom")`, добавляешь ключ `ui.panels.bottom` в конфиг — всё работает автоматически ✔ |

### 4.3 Регрессионный контроль
- Запустить полный test-suite: `pytest tests/ -v`
- Проверить все QSS-стили для `QWidget#LeftPanel` и `#RightPanel` — они применяются без изменений (мы меняли класс родителя, но objectName тот же).

---

## 5. Какое УРОВНИВАНИЕ получаем взамен

| Проблема «до» | Как закрыто «после» |
|---|---|
| Левая панель 332 px вместо 320 ✅ | `PanelWidget.sizeHint()` явно возвращает `initial_width=320`, спорить с `QSplitter` больше не с кем |
| Хардкод размеров в 2–3 местах конфига ✅ | Единый источник истины: `ui.panels.<name>` |
| 7 отдельных `SettingsManager`-ключей без схемы ✅ | Один `window_state` с версионированием, restoreState(QByteArray) вместо вручную собранных sizes |
| Невозможность добавить правую/нижнюю панели без копипаста ✅ | Один базовый класс `PanelWidget`, один контракт `PanelSizeControlled` |
| Случайная поломка размеров при смене тем/шрифтов ✅ | `min_width`/`max_width` задают допустимый диапазон, Qt не выйдет за него |
| Отсутствие тестов на размеры ✅ | 3 юнит-теста как регрессионная страховка |

---

## 6. Риски и точки контроля

| Риск | Вероятность | Контрмера |
|---|---|---|
| `QTreeView` ломает раскладку при добавлении очень широких item'ов | Низкая | `min_width=240` + горизонтальный скроллбар включён по умолчанию |
| Миграция с legacy на новое состояние частично теряет splitter collapsible-флаг | Средняя | Коллапсировать левую панель запрещено (`setCollapsible(0, False)`) на всём протяжении работы приложения — потеря не чувствуется |
| Первый вызов `load(apply_geometry=False)` в `right_panel_setup.py` перебивает внешнюю геометрию | Низкая | apply_geometry=False — трогает **только** splitter states; финальная геометрия применяется позже в lifecycle окна |
| В `settings.json` попадут bytes из QByteArray как base85/строка, а не JSON-сериализуемые bytes | Низкая | `json.dumps(ensure_ascii=True)` сериализует bytes объекты как список int; `QByteArray(blob)` принимает и list[int], и bytes одинаково |

---

## 7. Итог: затраты и порядок выполнения

**Порядок (topological):**  
1 → 2 → 3 → 4 → 5 → 6.1 (импорт) → 7 → 6.2/6.3 (интеграция) → 8 → Запуск тестов.

**Оценка времени:**
- Артефакты 1–5 (новые файлы + схема конфига): 40–50 мин  
- Артефакт 6 (интеграция в WindowUISetup): 15 мин  
- Артефакт 7 (интеграция в RightPanelBuilder): 20 мин  
- Артефакт 8 (тесты + прогон): 15 мин  
- + запас на непредвиденные импорты / проверки mypy/pyright: 20 мин  
**Итого: ≈ 2 часа** на всю реализацию + прогон.

**Объём кода:**
- Новый код: ~450 строк (PanelWidget + WindowStateManager + 3 теста)
- Правки существующего: ~40 строк (5–6 файлов)
- Удаляется устаревшего кода: ~45 строк (`_get_initial_splitter_sizes` + ручной `_store_state` с 7 ключами)
- **Netto: +445 строк, но с ликвидацией 3 видов техдолга.**
