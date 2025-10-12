# 📄 Предложение текста для диалога "О программе"

## Текущая версия (в app_config.json)

```json
{
  "app": {
    "about_title": "О программе",
    "about_text": "Link Manager\nВерсия 1.0\n© MyCompany"
  }
}
```

---

## 🎨 Предлагаемые варианты

### Вариант 1: Минималистичный (рекомендуемый)

```json
{
  "app": {
    "about_title": "О программе Aite Commander",
    "about_text": "Aite Commander - профессиональный менеджер ссылок\n\nВерсия 1.0.0\n\nОрганизуйте свои ссылки, файлы и приложения в удобной древовидной структуре.\n\n© 2025 Codebdbd. Все права защищены."
  }
}
```

**Как выглядит:**
```
┌─────────────────────────────────────┐
│  О программе Aite Commander          │
├─────────────────────────────────────┤
│                                      │
│  Aite Commander - профессиональный   │
│  менеджер ссылок                     │
│                                      │
│  Версия 1.0.0                        │
│                                      │
│  Организуйте свои ссылки, файлы и   │
│  приложения в удобной древовидной    │
│  структуре.                          │
│                                      │
│  © 2025 Codebdbd.                    │
│  Все права защищены.                 │
│                                      │
│  Спасибо, что используете наше       │
│  приложение!                         │
│                                      │
│  Версия: 1.0.0                       │
│                                      │
│        [ OK ]                        │
└─────────────────────────────────────┘
```

---

### Вариант 2: Подробный с особенностями

```json
{
  "app": {
    "about_title": "О программе Aite Commander",
    "about_text": "🚀 Aite Commander v1.0.0\n\nПрофессиональный менеджер ссылок и ресурсов\n\n✨ Основные возможности:\n• Древовидная структура организации (Сферы → Разделы → Категории)\n• Поддержка различных типов ссылок (веб, файлы, программы, скрипты)\n• Избранное и история недавних\n• Быстрый поиск по всей базе\n• Профили браузеров\n• Импорт/экспорт закладок\n• Резервное копирование\n\n📊 Текущая база данных:\n• 3837 ссылок\n• Производительность оптимизирована (миграция 0005)\n• 10 индексов для быстрого доступа\n\n🛠 Технологии: Python 3.11, PyQt6, SQLite\n\n© 2025 Codebdbd. Все права защищены.\nСделано с ❤️ для повышения продуктивности."
  }
}
```

---

### Вариант 3: Деловой стиль

```json
{
  "app": {
    "about_title": "Aite Commander - Информация о программе",
    "about_text": "Aite Commander\nПрофессиональный менеджер ссылок и ресурсов\n\nВерсия: 1.0.0\nСборка: 2025-09-30\n\nПрограмма предназначена для организации и быстрого доступа к веб-ссылкам, файлам, программам и скриптам в единой иерархической структуре.\n\nКлючевые функции:\n- Многоуровневая организация (Сферы/Разделы/Категории)\n- Полнотекстовый поиск\n- Управление избранным\n- Синхронизация с браузерами\n- Автоматическое резервное копирование\n\nРазработчик: Codebdbd\nПоддержка: https://codebdbd.com/support\n\n© 2025 Codebdbd. Все права защищены."
  }
}
```

---

### Вариант 4: Краткий и современный

```json
{
  "app": {
    "about_title": "Aite Commander",
    "about_text": "Ваш персональный центр управления ссылками 🎯\n\nВерсия 1.0.0 (Build 2025.09.30)\n\nOrganize • Search • Access\n\n🌐 Веб-ссылки\n📁 Файлы и папки\n⚡ Программы и скрипты\n🔖 Закладки браузеров\n\nПроизводительность оптимизирована для работы с тысячами ссылок.\n\nСделано в 2025 | Codebdbd"
  }
}
```

---

## 📝 Рекомендации по выбору

### ✅ Вариант 1 - Используйте если:
- Нужен чистый профессиональный вид
- Минимум текста, максимум понятности
- **Рекомендую для production**

### ✅ Вариант 2 - Используйте если:
- Хотите показать все возможности
- Демонстрация статистики (3837 ссылок)
- Для внутреннего использования

### ✅ Вариант 3 - Используйте если:
- Корпоративное приложение
- Нужна официальная информация
- Важны контакты поддержки

### ✅ Вариант 4 - Используйте если:
- Современный продукт для пользователей
- Акцент на UX и visual appeal
- Молодая аудитория

---

## 🔧 Как применить

### Способ 1: Редактирование конфига (рекомендуется)

Отредактируйте `app/config_data/app_config.json`:

```json
{
  "app": {
    "name": "Aite Commander",
    "org_name": "Codebdbd",
    "version": "1.0.0",
    "about_title": "О программе Aite Commander",
    "about_text": "Aite Commander - профессиональный менеджер ссылок\n\nВерсия 1.0.0\n\nОрганизуйте свои ссылки, файлы и приложения в удобной древовидной структуре.\n\n© 2025 Codebdbd. Все права защищены."
  }
}
```

### Способ 2: Динамическое формирование

Создайте метод для генерации текста с актуальной статистикой:

```python
# app/config_data/settings_config.py

def get_about_text(self) -> str:
    """Получение текста диалога 'О программе' с динамической информацией."""
    # Базовый текст из конфига
    base_text = self.get("app.about_text")
    
    if base_text is None:
        # Формируем текст динамически
        app_name = self.get("app.name", "Aite Commander")
        version = self.get("app.version", "1.0.0")
        org = self.get("app.org_name", "Codebdbd")
        
        # Можно добавить статистику из БД
        # from app.models.db import Database
        # db = Database()
        # link_count = db.links.count_all()
        
        base_text = f"""{app_name} - профессиональный менеджер ссылок

Версия {version}

Организуйте свои ссылки, файлы и приложения 
в удобной древовидной структуре.

© 2025 {org}. Все права защищены."""
    
    return base_text
```

---

## 🎨 Дополнительные улучшения

### 1. Добавить иконку в диалог

```python
# app/controllers/ui/dialogs/system_dialog_controller.py

def show_about_dialog(self):
    """Показать диалог О программе."""
    from PyQt6.QtWidgets import QMessageBox
    from PyQt6.QtGui import QIcon
    
    msg_box = QMessageBox(self.main_window)
    msg_box.setWindowTitle(app_config.get_about_title())
    msg_box.setText(app_config.get_about_text())
    msg_box.setInformativeText("Спасибо, что используете наше приложение!")
    
    # Добавляем иконку приложения
    icon_path = Path(__file__).parent.parent.parent / "views" / "resources" / "app_icon.ico"
    if icon_path.exists():
        msg_box.setWindowIcon(QIcon(str(icon_path)))
    
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()
```

### 2. Добавить кнопки "Сайт" и "Поддержка"

```python
def show_about_dialog(self):
    """Показать диалог О программе с дополнительными кнопками."""
    from PyQt6.QtWidgets import QMessageBox
    
    msg_box = QMessageBox(self.main_window)
    msg_box.setWindowTitle(app_config.get_about_title())
    msg_box.setText(app_config.get_about_text())
    msg_box.setInformativeText("Спасибо, что используете наше приложение!")
    
    # Добавляем кнопки
    website_btn = msg_box.addButton("Сайт", QMessageBox.ButtonRole.ActionRole)
    support_btn = msg_box.addButton("Поддержка", QMessageBox.ButtonRole.ActionRole)
    msg_box.addButton(QMessageBox.StandardButton.Ok)
    
    msg_box.exec()
    
    # Обработка нажатий
    if msg_box.clickedButton() == website_btn:
        QDesktopServices.openUrl(QUrl("https://codebdbd.com"))
    elif msg_box.clickedButton() == support_btn:
        QDesktopServices.openUrl(QUrl("https://codebdbd.com/support"))
```

### 3. Добавить лицензионную информацию

```python
details = f"""Версия: {app_config.get('app.version', '1.0.0')}
Сборка: 2025-09-30
Схема БД: v5 (миграция 0005 применена)

Технологии:
• Python 3.11+
• PyQt6 6.4+
• SQLite 3.x

Производительность:
• 10 оптимизированных индексов
• Поддержка 100k+ ссылок
• Асинхронные операции БД

Лицензия: Proprietary
© 2025 Codebdbd. Все права защищены."""

DialogManager.show_info(
    self.main_window,
    title,
    text,
    informative_text="Спасибо, что используете наше приложение!",
    details=details,
)
```

---

## 💡 Мой финальный выбор

**Рекомендую Вариант 1 с небольшими улучшениями:**

```json
{
  "app": {
    "name": "Aite Commander",
    "org_name": "Codebdbd",
    "version": "1.0.0",
    "about_title": "О программе Aite Commander",
    "about_text": "Aite Commander — профессиональный менеджер ссылок\n\nВерсия 1.0.0\n\nОрганизуйте свои ссылки, файлы и приложения в удобной древовидной структуре с мощным поиском и избранным.\n\n© 2025 Codebdbd. Все права защищены."
  }
}
```

**Почему:**
- ✅ Профессиональный, но не перегруженный
- ✅ Ясно описывает назначение
- ✅ Содержит всю необходимую информацию
- ✅ Не требует частого обновления
- ✅ Универсален для любой аудитории

---

**Готово к применению!** 🎉
