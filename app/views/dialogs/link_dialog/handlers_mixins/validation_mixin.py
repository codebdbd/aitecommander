"""
Миксин для валидации и обработки ошибок сохранения формы LinkDialog.
"""
from typing import Any, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ValidationMixin:
    def _validate_and_save_data(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Проверяет и сохраняет данные формы."""
        if hasattr(self.dialog, "link_controller") and self.dialog.link_controller:
            return self.dialog.link_controller.validate_and_save(form_data)
        else:
            return self.dialog.dialog_controller.validate_and_save(form_data)

    def _handle_validation_errors(self, form_data: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Обрабатывает ошибки валидации и показывает соответствующие сообщения."""
        # Специальный мягкий сценарий: пустая форма (без URL и имени)
        name_empty = not (form_data.get("name") or "").strip()
        url_empty = not (form_data.get("url") or "").strip()

        if name_empty and url_empty:
            self._show_empty_form_message()
        else:
            errors = result.get("errors", [])
            problems = self._extract_problematic_fields(errors)
            self._show_validation_error_message(errors, problems)
            self._focus_problematic_field(problems)

    def _show_empty_form_message(self) -> None:
        """Показывает сообщение для пустой формы."""
        self.dialog.show_info(
            "Пусто, как холодильник в конце месяца 🥶 — добавьте хоть адрес или название, и будет что сохранить!",
            "Подсказка",
            informative_text="Введите URL или имя и попробуйте снова.",
            silent=True,
        )

    def _extract_problematic_fields(self, errors: List[str]) -> set:
        """Извлекает проблемные поля из списка ошибок."""
        problems = set()
        lower_errors = [e.lower() for e in errors]
        field_map = {
            "name": "Название",
            "url": "Адрес",
            "link_type": "Тип ссылки",
            "type": "Тип ссылки",
            "category": "Категория",
            "category_id": "Категория",
            "args": "Аргументы",
        }
        for key, label in field_map.items():
            if any(key in e for e in lower_errors):
                problems.add(label)
        return problems

    def _generate_error_messages(self, problems: set) -> Tuple[str, str]:
        """Генерирует сообщения об ошибках на основе проблемных полей."""
        hint_map = {
            "Название": "Укажите понятное название (например, 'Документация API').",
            "Адрес": "Введите корректный URL вида https://example.com.",
            "Тип ссылки": "Выберите тип ссылки (веб, файл, папка и т.д.).",
            "Категория": "Выберите категорию для ссылки.",
            "Аргументы": "Проверьте аргументы запуска — допустимы только безопасные значения.",
        }
        hints = [hint_map[p] for p in sorted(problems) if p in hint_map]
        # Ограничим длину подсказок, чтобы не перегружать окно
        short_hints = hints[:2]

        if problems:
            main_msg = f"Заполните/исправьте: {', '.join(sorted(problems))}."
            extra = (" " + " ".join(short_hints)) if short_hints else ""
            info_msg = (
                "Проверьте подсказки возле полей." + extra + " Полный список замечаний — в подробностях."
            )
        else:
            main_msg = "Пожалуйста, проверьте данные перед сохранением."
            info_msg = "Проверьте выделенные поля и всплывающие подсказки."

        return main_msg, info_msg

    def _show_validation_error_message(self, errors: List[str], problems: set) -> None:
        """Показывает сообщение об ошибках валидации."""
        error_text = "\n".join(errors)
        main_msg, info_msg = self._generate_error_messages(problems)

        self.dialog.show_info(
            main_msg,
            "Небольшая подсказка",
            informative_text=info_msg,
            details=error_text,
            silent=True,
        )

    def _focus_problematic_field(self, problems: set) -> None:
        """Устанавливает фокус на первое проблемное поле."""
        try:
            if "Адрес" in problems:
                self.dialog.ui.get_widget("url_le").setFocus()
            elif "Название" in problems:
                self.dialog.ui.get_widget("name_le").setFocus()
            elif "Категория" in problems:
                self.dialog.ui.get_widget("category_cb").setFocus()
            elif "Аргументы" in problems:
                self.dialog.ui.get_widget("args_le").setFocus()
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"Ошибка установки фокуса на проблемное поле: {e}")
