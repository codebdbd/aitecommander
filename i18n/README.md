# Инструкция по работе с переводами

## Генерация файлов переводов (.ts)

1. Установите Qt Linguist tools (если ещё не установлены):
```bash
pip install PyQt6-tools
```

2. Перейдите в папку i18n:
```bash
cd i18n
```

3. Сгенерируйте файлы переводов:
```bash
pylupdate6 app.pro
```

Это создаст файлы `app_ru.ts` и `app_uk.ts` с извлечёнными строками для перевода.

## Редактирование переводов

1. Откройте файлы .ts в Qt Linguist:
```bash
linguist app_ru.ts
```

2. Переведите все строки на русский/украинский язык

3. Сохраните файлы

## Компиляция переводов (.qm)

После редактирования переводов скомпилируйте их в бинарный формат:

```bash
lrelease app_ru.ts -qm app_ru.qm
lrelease app_uk.ts -qm app_uk.qm
```

## Структура файлов

- `app.pro` - файл проекта для pylupdate
- `app_ru.ts` - исходный файл переводов на русский (XML)
- `app_uk.ts` - исходный файл переводов на украинский (XML)
- `app_ru.qm` - скомпилированный файл переводов на русский (бинарный)
- `app_uk.qm` - скомпилированный файл переводов на украинский (бинарный)
- `language_service.py` - сервис переключения языков
- `locale_utils.py` - утилиты локализации дат/чисел

## Использование в коде

### В классах QObject/QWidget:
```python
self.tr("Text to translate")
```

### В обычных функциях:
```python
from PyQt6.QtCore import QCoreApplication
QCoreApplication.translate("ContextName", "Text to translate")
```

### Множественное число:
```python
QCoreApplication.translate("Context", "%n item", None, count)
```

## Переключение языка в приложении

Язык переключается через виджет `LanguageSelector` или программно:

```python
from i18n import language_service
language_service().set_language("ru")  # или "uk", "en"
```
