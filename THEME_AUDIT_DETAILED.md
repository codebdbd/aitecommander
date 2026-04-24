# Детальный Аудит Светлой Темы - Сравнение с Тёмной

## 1. ОСНОВНЫЕ ЦВЕТА И ТЕКСТ
**Тёмная (правильная логика)**:
- Текст: #E0E0E0 (светлый)
- Основной фон: #1A1F26 (тёмный)

**Светлая (текущая)**:
- Текст: #1F2430 (тёмный) ✓
- Основной фон: #FDFDFE (светлый) ✓

✓ **ЛОГИКА OK**

---

## 2. SPHERES BAR - КНОПКИ ВЫБОРА СФЕР
**Тёмная**:
```qss
QWidget#spheres_bar QToolButton:hover          → border #2ea8ff, background transparent
QWidget#spheres_bar QToolButton:checked         → border #2ea8ff, background #2ea8ff
QWidget#spheres_bar QToolButton:pressed         → border #FFFFFF, gradient (#0C4B78 → #1D79B8)
```

**Светлая (ОШИБКА)**:
```qss
QWidget#spheres_bar QToolButton:hover          → border #0078D7, background transparent  ✓
QWidget#spheres_bar QToolButton:checked         → border #E0E0E0, background #E0E0E0  ❌ ОШИБКА
QWidget#spheres_bar QToolButton:pressed         → border #FFFFFF, gradient (#00427A → #0061B0)  ✓
```

**ПРОБЛЕМА**: `:checked` состояние использует #E0E0E0 (светлый серый) вместо яркого синего. В тёмной теме яркий синий (#2ea8ff), в светлой должен быть яркий цвет (как #0078D7), но NOT серый!

---

## 3. MENU BAR
**Тёмная**:
```qss
QMenuBar                                    → background #1A1F26, border #3A3E44
QMenuBar::item                              → color #C9D1DA
QMenuBar::item:hover/selected               → background #252D3A, border левый/правый #3A3E44
QMenuBar::item:pressed                      → background #2C2F36, border левый/правый #3A3E44
```

**Светлая (ОШИБКА)**:
```qss
QMenuBar                                    → background #F0F0F0  ❌
QMenuBar::item                              → color #444444
QMenuBar::item:selected                     → background #E6E6E6, color #000000
QMenuBar::item:pressed                      → background #0F6FD6  ❌❌ ЯРКИЙ СИНИЙ - НЕПРАВИЛЬНАЯ ЛОГИКА
```

**ПРОБЛЕМЫ**: 
- Фон MenuBar #F0F0F0 - слишком тёмный для светлой темы (должен быть светлее или как topBarHost)
- `:pressed` состояние - синий #0F6FD6 вместо нейтрального цвета (должен быть похожим на :selected)
- Нет бордеров слева/справа как в тёмной теме

---

## 4. TOP BAR HOST - INPUT FIELDS И BUTTONS
**Тёмная**:
```qss
QWidget#topBarHost                          → background #1A1F26
QLineEdit                                   → border #3A3E44
QLineEdit:focus                             → border #0194F0 (синий акцент)
QToolButton:hover / QPushButton:hover       → border #0194F0 (синий акцент)
```

**Светлая**:
```qss
QWidget#topBarHost                          → background #F5F5F5
QLineEdit                                   → border #B3B3B3
QLineEdit:hover / focus                     → border #B3B3B3  ❌ НЕ МЕНЯЕТСЯ
QToolButton:hover / QPushButton:hover       → border #B3B3B3  ❌ НЕ МЕНЯЕТСЯ
```

**ПРОБЛЕМА**: В светлой теме при фокусе/ховере бордер не меняется. Должно быть яркое состояние (похожее на #0078D7 как в тёмной #0194F0).

---

## 5. PUSH BUTTONS
**Тёмная**:
```qss
QPushButton                                 → background #252D3A, border #252D3A
QPushButton:hover                           → background #2E4066, border #0194F0
```

**Светлая (ЛОГИКА СЛАБАЯ)**:
```qss
QPushButton                                 → background #FFFFFF, border #B3B3B3
QPushButton:hover                           → background #E6E6E6, border #B3B3B3  ❌
```

**ПРОБЛЕМА**: Бордер не меняется на акцент-цвет при ховере. Должно быть как в тёмной теме.

---

## 6. TOOL BUTTONS
**Тёмная**:
```qss
QToolButton                                 → background #252D3A, border #2E4066
QToolButton:hover                           → background #2E4066, border #0194F0
QToolButton:checked                         → background #3A6EFF, border #3A6EFF
```

**Светлая (ЛОГИКА СЛАБАЯ)**:
```qss
QToolButton                                 → background #F4F4F4, border #B3B3B3
QToolButton:hover                           → background #E6E6E6, border #B3B3B3  ❌
QToolButton:checked                         → background #1C8FF5, border #B3B3B3  ❌
```

**ПРОБЛЕМЫ**:
- Бордер не меняется на акцент при ховере
- `:checked` состояние имеет #1C8FF5 но бордер остаётся #B3B3B3 (должен быть акцент-цвет)

---

## 7. CATEGORY TILES
**Тёмная**:
```qss
QListWidget#categoryTiles                   → background #1A1F26
QListWidget#categoryTiles::item:hover       → background #1E2633, border #FFFFFF
QListWidget#categoryTiles::item:selected    → background #1E2633, border #0194F0
QListWidget#categoryTiles::item:selected:hover → background #1E2633, border #0194F0
```

**Светлая (ЛОГИКА НАРУШЕНА)**:
```qss
QListWidget#categoryTiles                   → background #F9FAFD
QListWidget#categoryTiles::item:hover       → background #E0E0E0, border #FFFFFF  ❌ БЕЛЫЙ бордер - странно
QListWidget#categoryTiles::item:selected    → background #F0F0F0, border #E0E0E0  ❌ СЕРЫЙ бордер
QListWidget#categoryTiles::item:selected:hover → background #F0F0F0, border #0078D7  ✓
```

**ПРОБЛЕМЫ**:
- `:hover` имеет белый бордер - в тёмной это логично (контраст), в светлой это хлам
- `:selected` имеет серый бордер вместо акцент-цвета (#0078D7)
- Только при `:selected:hover` используется правильный бордер

---

## 8. TABLE VIEW
**Тёмная**:
```qss
QTableView                                  → background #2D2D2D, alternate #1A1F26
QTableView::item:selected                   → background #6A2E44 (розовый), text #FFFFFF
QTreeView::item:!selected:hover             → background #444444
```

**Светлая (ЛОГИКА СТРАННАЯ)**:
```qss
QTableView                                  → background #FFFFFF, alternate #F5F5F5
QTableView::item:selected                   → background #CCE7FF (светло-синий), text #000000 ✓
QTreeView::item:!selected:hover             → background #E6E6E6 ✓
```

✓ **TABLE OK** (хотя не совсем зеркальная логика - в тёмной выбранная строка розовая, в светлой синяя)

---

## 9. DIALOGS
**Тёмная**:
```qss
QDialog                                     → background #1A1F26, color #E0E0E0
QDialog QLineEdit/buttons                   → border #3A3F47
QDialog QPushButton:hover                   → background #2E4066, border #0194F0, color #FFFFFF
QDialog QCheckBox::indicator                → background #1A1F26, border #3A3F47
QDialog QCheckBox::indicator:hover          → border #0194F0
QDialog QCheckBox::indicator:checked        → background #0194F0, border #0194F0
```

**Светлая (ОШИБКИ)**:
```qss
QDialog                                     → background #FFFFFF, color #1F2430 ✓
QDialog QLineEdit/buttons                   → border #B3B3B3, background #F0F0F0
QDialog QPushButton:hover                   → background остаётся #F0F0F0, border #B3B3B3  ❌
QDialog QCheckBox::indicator                → background #FFFFFF, border #B3B3B3
QDialog QCheckBox::indicator:hover          → border #B3B3B3  ❌ НЕ МЕНЯЕТСЯ (в тёмной → #0194F0)
QDialog QCheckBox::indicator:checked        → background #1C8FF5, border #B3B3B3  ❌ бордер не меняется
```

**ПРОБЛЕМЫ**:
- Dialog buttons при hover не меняют background и бордер
- CheckBox не реагирует на hover (бордер не меняется как в тёмной)
- CheckBox:checked имеет неправильный бордер

---

## 10. BOTTOM BAR
**Тёмная**:
```qss
QWidget#bottomBarContainer                  → background #292929
QWidget#bottomBarContainer QPushButton      → color #FFFFFF, border-right #3A3E44 (БЕЗ фона)
QWidget#bottomBarContainer QPushButton:hover → background #2E4066
```

**Светлая (СЛАБАЯ ЛОГИКА)**:
```qss
QWidget#bottomBarContainer                  → background #F0F2FA
QWidget#bottomBarContainer QPushButton      → background #F2F4F7, color #1F2430, border-right #B3B3B3
QWidget#bottomBarContainer QPushButton:hover → border-right #B3B3B3, background #E6E6E6
```

**ПРОБЛЕМА**: Buttons имеют явный background в светлой теме, в то время как в тёмной они прозрачные (только border-right). Логика не соответствует.

---

## 11. SEPARATORS И SPLITTERS
**Тёмная**:
```qss
QWidget[class="separator"]                  → background #3A3E44
QSplitter::handle                           → background #3A3E44
```

**Светлая**:
```qss
QWidget[class="separator"]                  → background #B3B3B3
QSplitter::handle                           → background #B3B3B3
```

✓ **OK** - логика правильная (темные разделители для обеих тем)

---

## ИТОГОВЫЙ СПИСОК ОШИБОК

### Критические (инверсия не работает правильно):
1. ❌ **spheres_bar buttons `:checked`** - используется серый вместо яркого синего
2. ❌ **MenuBar `:pressed`** - использует яркий синий вместо нейтрального
3. ❌ **TopBar inputs** - бордер не меняется при focus/hover (нет акцент-цвета)
4. ❌ **Dialog buttons** - не реагируют на hover
5. ❌ **Dialog CheckBox** - не реагирует на hover

### Средние (логика не соответствует тёмной):
6. ❌ **QPushButton/QToolButton** - бордер не становится акцент-цветом при hover
7. ❌ **Category tiles** - неправильные бордер-цвета для состояний
8. ❌ **CheckBox indicator** - бордер не меняется на акцент при checked

### Низкие (внешние различия):
9. ⚠️ **LeftPanel spheres** - отсутствуют градиенты (плоские цвета)
10. ⚠️ **MenuBar фон** - слишком тёмный (#F0F0F0 вместо более светлого)
11. ⚠️ **Bottom bar buttons** - логика фона отличается от тёмной темы

---

## ГЛАВНАЯ ПРОБЛЕМА: ИНВЕРСИЯ ВЫВЕРЕНА НЕПРАВИЛЬНО

Светлая тема просто **инвертировала цвета без понимания логики**:
- Брала тёмные цвета тёмной темы и делала их светлыми
- Но забыла про **акцент-цвета** (blue #0194F0 / #2ea8ff) которые должны оставаться яркими
- Забыла про **бордеры при при активных состояниях** (hover, focus, checked)
- Забыла про **семантику цветов** (красный для опасности, синий для внимания и т.д.)

**Нужно переделать светлую тему с правильной логикой акцент-цветов и состояний!**
