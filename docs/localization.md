# Localization Guide

## Структура

```
i18n/
  app_en.ts    # English (базовый язык)
  app_ru.ts    # Russian
  app_de.ts    # German
  app_fr.ts    # French
  app_es.ts    # Spanish
  app_uk.ts    # Ukrainian
```

Формат: Qt `.ts` (XML). Поддержка 6 языков.

## Добавление новой строки

В Python-коде используйте `self.tr()`:

```python
# В классе (QWidget, QDialog, и т.д.)
label.setText(self.tr("Save"))

# С форматированием
self.tr("Deleting {count} links").format(count=5)

# С numerus (множественное число)
self.tr("%n item(s) selected", "", count)
```

После добавления строки запустите:

```bash
pylupdate6 app/**/*.py -ts i18n/app_en.ts
```

Это обновит `.ts` файл, добавив новую строку с пометкой `unfinished`.

## Перевод

### Через Qt Linguist (рекомендуется)

```bash
linguist i18n/app_ru.ts
```

1. Откройте файл
2. Переведите строки с пометкой `unfinished`
3. Сохраните

### Вручную

Откройте `.ts` файл и найдите:

```xml
<message>
  <source>New string</source>
  <translation type="unfinished" />
</message>
```

Замените на:

```xml
<message>
  <source>New string</source>
  <translation>Новая строка</translation>
</message>
```

## Сборка

```bash
lrelease i18n/app_*.ts
```

Генерирует `.qm` файлы — бинарные файлы переводов для Qt.

## Проверка консистентности

### Количество сообщений

Все `.ts` файлы должны содержать **одинаковое количество** `<message>` блоков.

### Проверка через Python

```python
import xml.etree.ElementTree as ET

for lang in ['en', 'ru', 'de', 'fr', 'es', 'uk']:
    tree = ET.parse(f'i18n/app_{lang}.ts')
    total = sum(len(c.findall('message')) for c in tree.getroot().findall('context'))
    print(f'{lang}: {total} messages')
```

### Проверка vanished/unfinished

```python
for lang in ['en', 'ru', 'de', 'fr', 'es', 'uk']:
    tree = ET.parse(f'i18n/app_{lang}.ts')
    root = tree.getroot()
    vanished = sum(1 for c in root.findall('context')
                   for m in c.findall('message')
                   if m.find('translation') is not None
                   and m.find('translation').get('type') == 'vanished')
    unfinished = sum(1 for c in root.findall('context')
                     for m in c.findall('message')
                     if m.find('translation') is not None
                     and m.find('translation').get('type') == 'unfinished')
    print(f'{lang}: vanished={vanished}, unfinished={unfinished}')
```

## Типы переводов

| Тип | Значение | Действие |
|-----|----------|----------|
| (пусто) | Переведено | Оставить как есть |
| `type="unfinished"` | Черновик или нет перевода | Перевести |
| `type="vanished"` | Строка удалена из кода | Удалить запись |

## Контексты

Контекст = имя класса Python, где используется строка:

```xml
<context>
  <name>LinkDialog</name>           <!-- имя класса -->
  <message>
    <source>Save</source>
    <translation>Сохранить</translation>
  </message>
</context>
```

Правила:
- Имя контекста = имя класса (без `Q` префикса)
- Один класс — один контекст
- Нет дублирующих контекстов

## Частые ошибки

### 1. Строка не отображается на целевом языке

Причина: нет перевода или `type="unfinished"`.

Решение: добавить перевод, убрать `type="unfinished"`.

### 2. Количество переводов различается между языками

Причина: забыли добавить перевод для нового языка.

Решение: запустить `lupdate` для всех языков.

### 3. `type="vanished"` в файле

Причина: строка была удалена из кода.

Решение: удалить запись из `.ts` файла.

## Полезные команды

```bash
# Обновить все .ts файлы из кода
pylupdate6 app/**/*.py -ts i18n/app_*.ts

# Собрать .qm файлы
lrelease i18n/app_*.ts

# Открыть Linguist
linguist i18n/app_ru.ts
```
