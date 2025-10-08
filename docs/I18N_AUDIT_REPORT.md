# 🔍 ПОЛНЫЙ АУДИТ СИСТЕМЫ ИНТЕРНАЦИОНАЛИЗАЦИИ

**Дата аудита:** 2025-10-08  
**Версия системы:** i18n v2.0  
**Статус:** ⚠️ КРИТИЧЕСКИЕ ПРОБЛЕМЫ ОБНАРУЖЕНЫ

---

## 📊 EXECUTIVE SUMMARY

### Общая статистика
- **Поддерживаемые языки:** 6 (en, ru, uk, de, es, fr)
- **Средняя готовность переводов:** 32.7%
- **Общее количество строк:** 170-184 (варьируется по языкам)
- **Контексты (классы):** 16-18

### Критичность проблем
🔴 **КРИТИЧЕСКИЕ:** 5 проблем  
🟠 **ВЫСОКИЕ:** 3 проблемы  
🟡 **СРЕДНИЕ:** 4 проблемы  
🟢 **НИЗКИЕ:** 2 проблемы

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### 1. Битые переводы в app_uk.ts (BLOCKER)
**Приоритет:** P0 - КРИТИЧЕСКИЙ  
**Файл:** `i18n/app_uk.ts:37, 42`

**Проблема:**
```xml
<!-- НЕПРАВИЛЬНО -->
<source>⚠️ Operation cancelled</source>
<translation>⚠️ Operation скасуватиled</translation>

<source>Cancelling operation…</source>
<translation>Скасуватиling operation…</translation>
```

**Причина:** Автоматический перевод (`auto_translate.py`) некорректно заменил части английских слов украинскими эквивалентами.

**Влияние:** Пользователи видят искажённый текст при отмене операций.

**Решение:**
```xml
<!-- ПРАВИЛЬНО -->
<source>⚠️ Operation cancelled</source>
<translation>⚠️ Операцію скасовано</translation>

<source>Cancelling operation…</source>
<translation>Скасування операції…</translation>
```

---

### 2. Отсутствие скомпилированных .qm файлов для 4 языков
**Приоритет:** P0 - КРИТИЧЕСКИЙ  
**Файлы:** `app_de.qm`, `app_en.qm`, `app_es.qm`, `app_fr.qm`

**Проблема:**
```
app_de.qm:     16 bytes  ← ПУСТОЙ (только заголовок)
app_en.qm:     33 bytes  ← ПУСТОЙ
app_es.qm:     16 bytes  ← ПУСТОЙ
app_fr.qm:     16 bytes  ← ПУСТОЙ
app_ru.qm:  17604 bytes  ✓ OK
app_uk.qm:  18694 bytes  ✓ OK
```

**Причина:** Файлы .ts не переведены (0% completion), lrelease создаёт пустые .qm.

**Влияние:** Переключение на de/en/es/fr не работает — UI остаётся на исходном языке.

**Решение:**
1. Перевести .ts файлы в Qt Linguist
2. Перекомпилировать: `python i18n/update_and_report.py --compile`

---

### 3. Отсутствие resources_rc.py
**Приоритет:** P0 - КРИТИЧЕСКИЙ  
**Файл:** `i18n/resources_rc.py` (не существует)

**Проблема:**
```python
# app/main.py:18-22
try:
    from i18n import resources_rc  # type: ignore  # noqa: F401
except Exception:
    # Fallback: LanguageService will try filesystem i18n/app_*.qm
    pass
```

Файл `resources_rc.py` не найден в проекте. Qt-ресурсы не компилируются.

**Причина:** Отсутствует команда компиляции `.qrc → .py`:
```bash
pyrcc6 i18n/resources.qrc -o i18n/resources_rc.py
```

**Влияние:** 
- Переводы загружаются только из файловой системы (медленнее)
- При упаковке приложения (PyInstaller) переводы могут не работать
- Путь `:/i18n/app_*.qm` в `LanguageService:166` не работает

**Решение:**
```bash
# Установить pyrcc6 (если нет)
pip install PyQt6

# Скомпилировать ресурсы
pyrcc6 i18n/resources.qrc -o i18n/resources_rc.py
```

---

### 4. Несогласованность атрибута language в .ts файлах
**Приоритет:** P1 - ВЫСОКИЙ  
**Файлы:** `app_uk.ts`, `app_de.ts`, `app_es.ts`, `app_fr.ts`

**Проблема:**
```xml
<!-- app_en.ts -->
<TS version="2.1" language="en_US">  ✓ OK

<!-- app_ru.ts -->
<TS version="2.1" language="ru" sourcelanguage="en">  ✓ OK

<!-- app_uk.ts, app_de.ts, app_es.ts, app_fr.ts -->
<TS version="2.1">  ✗ ОТСУТСТВУЕТ language=
```

**Влияние:** Qt Linguist может некорректно определять язык, множественные формы могут не работать.

**Решение:**
```xml
<!-- app_uk.ts -->
<TS version="2.1" language="uk_UA" sourcelanguage="en">

<!-- app_de.ts -->
<TS version="2.1" language="de_DE" sourcelanguage="en">

<!-- app_es.ts -->
<TS version="2.1" language="es_ES" sourcelanguage="en">

<!-- app_fr.ts -->
<TS version="2.1" language="fr_FR" sourcelanguage="en">
```

---

### 5. Незавершённые переводы с type="unfinished" содержат текст
**Приоритет:** P1 - ВЫСОКИЙ  
**Файл:** `app_ru.ts` (16 строк)

**Проблема:**
```xml
<!-- Противоречие: перевод есть, но помечен как unfinished -->
<source>Save</source>
<translation type="unfinished">Сохранить</translation>
```

**Найдено в контекстах:**
- BrowserProfileDialog (2 строки)
- BaseEntityDialog (5 строк)  
- MoveOperationsHandler (9 строк)

**Влияние:** Статистика показывает 91.3% готовности, но реально ~100%. Переводы работают, но помечены как незавершённые.

**Решение:** Удалить атрибут `type="unfinished"` из всех переводов с текстом.

---

## 🟠 ВЫСОКИЕ ПРОБЛЕМЫ

### 6. Разное количество строк в .ts файлах
**Приоритет:** P2 - ВЫСОКИЙ

**Проблема:**
```
app_en.ts:  180 messages (18 contexts)  ← ЭТАЛОН
app_ru.ts:  184 messages (16 contexts)  ← +4 лишних
app_uk.ts:  173 messages (17 contexts)  ← -7 отсутствует
app_de.ts:  170 messages (16 contexts)  ← -10 отсутствует
app_es.ts:  170 messages (16 contexts)  ← -10 отсутствует
app_fr.ts:  170 messages (16 contexts)  ← -10 отсутствует
```

**Причина:** Файлы обновлялись в разное время, `pylupdate6` не синхронизирован.

**Решение:**
```bash
# Пересоздать все .ts файлы с нуля
cd i18n
pylupdate6 app.pro
```

---

### 7. Отсутствие numerusform для множественного числа
**Приоритет:** P2 - ВЫСОКИЙ  
**Файл:** `app_en.ts:73-75`

**Проблема:**
```xml
<message numerus="yes">
  <source>%n item selected</source>
  <translation type="unfinished">
    <numerusform />  ← ПУСТО, нужно 2 формы для EN
  </translation>
</message>
```

**Влияние:** Текст "%n item selected" не изменяется для 1/2/5 элементов.

**Решение:**
```xml
<translation>
  <numerusform>%n item selected</numerusform>
  <numerusform>%n items selected</numerusform>
</translation>
```

---

### 8. Устаревшие (vanished) переводы в app_uk.ts
**Приоритет:** P2 - СРЕДНИЙ  
**Файл:** `app_uk.ts:78-82`

**Проблема:**
```xml
<message numerus="yes">
  <source>%n элемент выбран</source>
  <translation type="vanished">
    <numerusform />
  </translation>
</message>
```

**Причина:** Исходный текст изменился с русского на английский, старый перевод остался.

**Решение:** Удалить блоки с `type="vanished"` (они не используются).

---

## 🟡 СРЕДНИЕ ПРОБЛЕМЫ

### 9. Отсутствие валидации .ts файлов в CI/CD
**Приоритет:** P3 - СРЕДНИЙ

**Проблема:** Нет автоматической проверки:
- Битых переводов (как в п.1)
- Незавершённых переводов
- Синхронизации количества строк

**Решение:** Добавить в `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: validate-translations
      name: Validate i18n .ts files
      entry: python i18n/validate_translations.py
      language: python
      files: '^i18n/.*\.ts$'
```

---

### 10. Неполное покрытие app.pro
**Приоритет:** P3 - СРЕДНИЙ  
**Файл:** `i18n/app.pro`

**Проблема:** В `app.pro` только 60+ файлов, но в проекте ~300+ Python файлов с UI.

**Отсутствуют:**
- `app/controllers/business/*` (90 файлов)
- `app/models/workers/*` (34 файла)
- `app/utils/*` (70+ файлов)
- `app/services/*` (5+ файлов)

**Решение:** Добавить все файлы с `self.tr()` в `SOURCES`.

---

### 11. Отсутствие документации по множественным формам
**Приоритет:** P3 - СРЕДНИЙ  
**Файл:** `i18n/README.md`

**Проблема:** В README нет примеров для разных языков:
- Английский: 2 формы (1 item / 2 items)
- Русский/Украинский: 3 формы (1 элемент / 2 элемента / 5 элементов)
- Французский: 2 формы (0-1 item / 2+ items)

**Решение:** Добавить секцию "Plural Forms Guide" в README.

---

### 12. Отсутствие fallback для отсутствующих переводов
**Приоритет:** P3 - СРЕДНИЙ  
**Файл:** `i18n/language_service.py:133-138`

**Проблема:** Если перевод не загружается, fallback на `en`, но если `en` тоже пуст?

**Решение:** Добавить цепочку fallback: `requested → en → source text`.

---

## 🟢 НИЗКИЕ ПРОБЛЕМЫ

### 13. Emoji в исходных строках
**Приоритет:** P4 - НИЗКИЙ

**Проблема:**
```python
self.tr("✅ Operation completed successfully")
self.tr("❌ Error: {error}")
self.tr("⚠️ Operation cancelled")
```

**Влияние:** Emoji могут не отображаться в некоторых шрифтах/ОС.

**Рекомендация:** Использовать иконки вместо emoji или добавить текстовый fallback.

---

### 14. Отсутствие автоматической компиляции .qm при изменении .ts
**Приоритет:** P4 - НИЗКИЙ

**Проблема:** После редактирования .ts в Qt Linguist нужно вручную запускать компиляцию.

**Решение:** Добавить file watcher или pre-commit hook:
```yaml
- id: compile-translations
  name: Compile .ts to .qm
  entry: python i18n/update_and_report.py --compile
  files: '^i18n/.*\.ts$'
```

---

## 📋 ПЛАН ИСПРАВЛЕНИЙ

### Фаза 1: Критические исправления (1-2 часа)
- [ ] **P0.1** Исправить битые переводы в `app_uk.ts` (строки 37, 42)
- [ ] **P0.2** Создать `resources_rc.py`: `pyrcc6 i18n/resources.qrc -o i18n/resources_rc.py`
- [ ] **P0.3** Добавить атрибуты `language=` в `app_uk.ts`, `app_de.ts`, `app_es.ts`, `app_fr.ts`
- [ ] **P0.4** Удалить `type="unfinished"` из переведённых строк в `app_ru.ts`

### Фаза 2: Синхронизация и переводы (2-4 часа)
- [ ] **P1.1** Пересоздать все .ts файлы: `pylupdate6 app.pro`
- [ ] **P1.2** Добавить numerusform для английского языка
- [ ] **P1.3** Удалить vanished переводы из `app_uk.ts`
- [ ] **P2.1** Перевести `app_en.ts` (180 строк)
- [ ] **P2.2** Перевести `app_de.ts`, `app_es.ts`, `app_fr.ts` (по 170 строк каждый)

### Фаза 3: Инфраструктура (1-2 часа)
- [ ] **P3.1** Создать `i18n/validate_translations.py` для проверки .ts файлов
- [ ] **P3.2** Добавить валидацию в `.pre-commit-config.yaml`
- [ ] **P3.3** Расширить `app.pro` для полного покрытия
- [ ] **P3.4** Добавить секцию "Plural Forms" в README

### Фаза 4: Улучшения (опционально)
- [ ] **P4.1** Заменить emoji на иконки
- [ ] **P4.2** Настроить автокомпиляцию .qm
- [ ] **P4.3** Добавить fallback chain в `LanguageService`

---

## 🛠️ КОМАНДЫ ДЛЯ БЫСТРОГО ИСПРАВЛЕНИЯ

### 1. Исправить критические проблемы
```bash
# 1. Создать resources_rc.py
pyrcc6 i18n/resources.qrc -o i18n/resources_rc.py

# 2. Пересоздать все .ts файлы
cd i18n
pylupdate6 app.pro

# 3. Скомпилировать .qm
python update_and_report.py --compile

# 4. Проверить результат
python update_and_report.py --report
```

### 2. Исправить битые переводы вручную
Открыть `i18n/app_uk.ts` в текстовом редакторе и заменить:
```xml
<!-- Строка 37 -->
<translation>⚠️ Операцію скасовано</translation>

<!-- Строка 42 -->
<translation>Скасування операції…</translation>
```

### 3. Добавить language атрибуты
```bash
# Для каждого файла добавить в строку 3:
# app_uk.ts
<TS version="2.1" language="uk_UA" sourcelanguage="en">

# app_de.ts
<TS version="2.1" language="de_DE" sourcelanguage="en">

# app_es.ts
<TS version="2.1" language="es_ES" sourcelanguage="en">

# app_fr.ts
<TS version="2.1" language="fr_FR" sourcelanguage="en">
```

---

## 📈 МЕТРИКИ КАЧЕСТВА

### Текущее состояние
| Метрика | Значение | Цель | Статус |
|---------|----------|------|--------|
| Покрытие переводами (RU) | 91.3% | 100% | 🟡 |
| Покрытие переводами (UK) | 99.4% | 100% | 🟢 |
| Покрытие переводами (EN) | 5.6% | 100% | 🔴 |
| Покрытие переводами (DE/ES/FR) | 0% | 100% | 🔴 |
| Качество переводов (UK) | 60% | 100% | 🔴 |
| Наличие resources_rc.py | ❌ | ✅ | 🔴 |
| Синхронизация .ts файлов | ❌ | ✅ | 🔴 |
| Валидация в CI/CD | ❌ | ✅ | 🟡 |

### После исправлений (прогноз)
| Метрика | Значение | Статус |
|---------|----------|--------|
| Покрытие переводами (все языки) | 100% | 🟢 |
| Качество переводов | 100% | 🟢 |
| Наличие resources_rc.py | ✅ | 🟢 |
| Синхронизация .ts файлов | ✅ | 🟢 |
| Валидация в CI/CD | ✅ | 🟢 |

---

## 🔗 СВЯЗАННЫЕ ДОКУМЕНТЫ

- `i18n/README.md` - Инструкция по работе с переводами
- `docs/I18N_IMPLEMENTATION_REPORT.md` - Отчёт о внедрении i18n (Phase 1)
- `i18n/app.pro` - Конфигурация проекта для pylupdate6
- `i18n/update_and_report.py` - Скрипт автоматизации

---

## ✅ ЧЕКЛИСТ ДЛЯ РЕВЬЮ

Перед релизом убедитесь:

- [ ] Все .ts файлы имеют атрибут `language=`
- [ ] Все .ts файлы содержат одинаковое количество строк (±2)
- [ ] Нет переводов с `type="unfinished"` и заполненным текстом
- [ ] Нет битых переводов (смешанные языки в одной строке)
- [ ] Все .qm файлы > 1KB (не пустые)
- [ ] `resources_rc.py` существует и импортируется в `main.py`
- [ ] Все numerus messages имеют корректное количество форм
- [ ] Нет vanished переводов в production .ts файлах
- [ ] `python i18n/update_and_report.py --report` показывает 100% для основных языков

---

**Подготовлено:** Cascade AI  
**Дата:** 2025-10-08  
**Версия отчёта:** 1.0
