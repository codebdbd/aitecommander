# Инструкция по работе с переводами

## 🚀 Быстрый старт

### Автоматизированный способ (рекомендуется)

Используйте helper-скрипт для автоматизации всех операций:

```bash
# Обновить .ts файлы, скомпилировать .qm и показать отчет
python update_and_report.py --all

# Только обновить .ts файлы
python update_and_report.py --update

# Только скомпилировать .qm файлы
python update_and_report.py --compile

# Только показать отчет о переводах
python update_and_report.py --report
```

### Ручной способ

Если предпочитаете ручное управление, следуйте инструкциям ниже.

---

## 📋 Предварительные требования

Установите Qt Linguist tools (если ещё не установлены):
```bash
pip install PyQt6-tools
```

Убедитесь, что `pylupdate6` и `lrelease` доступны в PATH.

---

## 🔄 Рабочий процесс перевода

### Шаг 1: Извлечение строк из кода

Перейдите в папку i18n и запустите:
```bash
cd i18n
pylupdate6 app.pro
```

Это обновит файлы `app_en.ts`, `app_ru.ts`, `app_uk.ts`, `app_de.ts`, `app_es.ts` и `app_fr.ts` с новыми строками для перевода.

**Что происходит:**
- Извлекаются все вызовы `self.tr()` и `QCoreApplication.translate()`
- Обновляются .ts файлы с сохранением существующих переводов

### Шаг 2: Редактирование переводов

Откройте файлы .ts в Qt Linguist:
```bash
linguist app_en.ts
linguist app_ru.ts
linguist app_uk.ts
linguist app_de.ts
linguist app_es.ts
linguist app_fr.ts
```

**В Qt Linguist:**
1. Выберите контекст (класс) слева
2. Для каждой строки введите перевод
3. Отметьте перевод как завершенный (Ctrl+Enter)
4. Сохраните файл (Ctrl+S)

**Советы по переводу:**
- Используйте плейсхолдеры как есть: `%1`, `%2`, `%n`
- Для множественного числа используйте формы: `%n элемент|%n элемента|%n элементов`
- Сохраняйте HTML-теги и специальные символы

### Шаг 3: Компиляция переводов

После завершения переводов скомпилируйте их в бинарный формат:

```bash
lrelease app_en.ts -qm app_en.qm
lrelease app_ru.ts -qm app_ru.qm
lrelease app_uk.ts -qm app_uk.qm
lrelease app_de.ts -qm app_de.qm
lrelease app_es.ts -qm app_es.qm
lrelease app_fr.ts -qm app_fr.qm
```

Или используйте batch-файл:
```bash
compile_translations.bat
```

**Результат:**
- Создаются .qm файлы (бинарные, оптимизированные)
- Приложение загружает .qm файлы при запуске

### Шаг 4: Тестирование

1. Запустите приложение
2. Переключите язык через виджет `LanguageSelector`
3. Проверьте все диалоги и сообщения
4. Убедитесь, что форматирование дат/чисел корректно

---

## 📁 Структура файлов

```
i18n/
├── app.pro                      # Конфигурация проекта для pylupdate6
├── app_en.ts                    # Переводы на английский (XML)
├── app_ru.ts                    # Переводы на русский (XML)
├── app_uk.ts                    # Переводы на украинский (XML)
├── app_de.ts                    # Переводы на немецкий (XML)
├── app_es.ts                    # Переводы на испанский (XML)
├── app_fr.ts                    # Переводы на французский (XML)
├── app_en.qm                    # Скомпилированные переводы EN (бинарные)
├── app_ru.qm                    # Скомпилированные переводы RU (бинарные)
├── app_uk.qm                    # Скомпилированные переводы UK (бинарные)
├── app_de.qm                    # Скомпилированные переводы DE (бинарные)
├── app_es.qm                    # Скомпилированные переводы ES (бинарные)
├── app_fr.qm                    # Скомпилированные переводы FR (бинарные)
├── language_service.py          # Сервис управления языками
├── locale_utils.py              # Утилиты форматирования (даты, числа)
├── update_and_report.py         # Helper-скрипт для автоматизации
├── update_translations.bat      # Batch для обновления .ts
├── compile_translations.bat     # Batch для компиляции .qm
├── resources.qrc                # Qt Resource Collection
└── README.md                    # Эта инструкция
```

---

## 💻 Использование в коде

### В классах QObject/QWidget:
```python
class MyDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("My Dialog"))
        self.label = QLabel(self.tr("Enter your name:"))
```

### В обычных функциях:
```python
from PyQt6.QtCore import QCoreApplication

def show_message():
    text = QCoreApplication.translate("MyContext", "Operation completed")
    print(text)
```

### Множественное число:
```python
# В .ts файле будет создано несколько форм для разных чисел
count = 5
text = self.tr("%n item(s) selected", "", count)
```

### С плейсхолдерами:
```python
name = "John"
text = self.tr("Hello, %1!").arg(name)
# или
text = self.tr("User {name} logged in").format(name=name)
```

### Динамическое обновление UI при смене языка:

```python
from app.ui.retranslatable import ReTranslatable

class MyDialog(QDialog, ReTranslatable):
    def __init__(self):
        QDialog.__init__(self)
        ReTranslatable.__init__(self)  # Автоматически подключится к languageChanged
        self._setup_ui()
        
    def retranslateUi(self):
        """Вызывается автоматически при смене языка"""
        self.setWindowTitle(self.tr("My Dialog"))
        self.ok_button.setText(self.tr("OK"))
        self.cancel_button.setText(self.tr("Cancel"))
```

---

## 🌍 Переключение языка

### Программно:
```python
from i18n import language_service

# Установить язык
language_service().set_language("en")  # или "ru", "uk", "de", "es", "fr"

# Получить текущий язык
current = language_service().current_language()

# Получить список доступных языков
languages = language_service().available_languages()
for lang in languages:
    print(f"{lang.code}: {lang.name}")
```

### Через UI:
```python
from app.views.widgets.language_selector import LanguageSelector

# Добавить виджет выбора языка
lang_selector = LanguageSelector(parent)
toolbar.addWidget(lang_selector)
```

---

## 🔧 Форматирование локализованных данных

### Даты и время:
```python
from i18n.locale_utils import format_date, format_datetime
from datetime import datetime

now = datetime.now()
print(format_datetime(now))  # Автоматически использует текущую локаль
# EN: "January 15, 2025 3:45:30 PM"
# UK: "15 січня 2025 р. 15:45:30"
```

### Числа и валюта:
```python
from i18n.locale_utils import format_number, format_currency

print(format_number(1234567))  # "1,234,567" (EN) или "1 234 567" (UK)
print(format_currency(99.99, "USD"))  # "$99.99" (EN) или "99,99 USD" (UK)
```

---

## 📊 Проверка покрытия переводов

Используйте helper-скрипт для генерации отчета:
```bash
python update_and_report.py --report
```

Отчет покажет:
- Количество переведенных строк
- Количество незавершенных переводов
- Процент завершенности для каждого языка
- Список контекстов (классов)

---

## ✅ Чеклист для разработчиков

При добавлении нового UI-элемента:

- [ ] Обернуть все пользовательские строки в `self.tr()`
- [ ] Если класс - диалог, добавить миксин `ReTranslatable`
- [ ] Реализовать метод `retranslateUi()` для динамического обновления
- [ ] Добавить файл в `app.pro` (если новый модуль)
- [ ] Запустить `python update_and_report.py --update`
- [ ] Перевести новые строки в Qt Linguist
- [ ] Скомпилировать и протестировать

---

## 🐛 Решение проблем

### pylupdate6 не найден
```bash
pip install --upgrade PyQt6-tools
```

### lrelease не найден
Установите полный Qt toolkit или используйте PyQt6-tools.

### Переводы не применяются
1. Убедитесь, что .qm файлы скомпилированы
2. Проверьте, что `LanguageService` инициализирован
3. Убедитесь, что `retranslateUi()` реализован в виджетах

### Строки не извлекаются
1. Проверьте, что файл добавлен в `app.pro`
2. Используйте `self.tr()` вместо обычных строк
3. Убедитесь, что класс наследует `QObject` или `QWidget`

---

## 📚 Дополнительные ресурсы

- [Qt Linguist Manual](https://doc.qt.io/qt-6/qtlinguist-index.html)
- [Internationalization with Qt](https://doc.qt.io/qt-6/internationalization.html)
- [PyQt6 i18n Guide](https://www.riverbankcomputing.com/static/Docs/PyQt6/i18n.html)

---

## 🎯 Текущий статус

**Поддерживаемые языки:**
- 🇬🇧 English (en)
- 🇷🇺 Русский (ru)
- 🇺🇦 Українська (uk)
- 🇩🇪 Deutsch (de)
- 🇪🇸 Español (es)
- 🇫🇷 Français (fr)

**Статистика:** Запустите `python update_and_report.py --report` для актуальных данных.
