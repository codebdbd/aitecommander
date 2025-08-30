# app/controllers/link_operations_controller.py

import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog

from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    DeleteLinkCmd,
    SaveLinkCmd,
)
from app.controllers.ui.undo.stack import UndoManager
from app.views.dialogs.link_dialog.link_dialog import LinkDialog

# Константы для макросов отмены/повтора
MACRO_DELETE_LINKS_TEXT = "Удаление {count} ссылок"


logger = logging.getLogger(__name__)


class LinkOperationsController(QObject):
    """Контроллер для операций со ссылками: создание, редактирование, удаление."""

    def __init__(self, db, undo_stack: UndoManager, main_window):
        super().__init__()
        self.db = db
        self.undo_stack = undo_stack
        self.main_window = main_window

    # --- Сигналы внешним слушателям ---
    # Сигнал о том, что данные ссылок в категории изменились и требуется перезагрузка таблицы
    links_changed = pyqtSignal(int)  # category_id
    # Сигнал о том, что состояние избранного изменилось (требуется refresh верхней панели)
    favorites_changed = pyqtSignal()
    # Новый сигнал: список недавних ссылок изменился (например, при открытии ссылки)
    recents_changed = pyqtSignal()
    # Новый сигнал: конкретная ссылка создана/обновлена (payload с category_id, id и др.)
    link_saved = pyqtSignal(dict)
    # Новый сигнал: ссылка удалена (payload с category_id, id и др.)
    link_deleted = pyqtSignal(dict)

    # --- Централизованные методы эмиссии сигналов ---
    def emit_links_changed(self, category_id: int) -> None:
        """Сообщить подписчикам, что изменились ссылки для категории."""
        try:
            if isinstance(category_id, int) and category_id > 0:
                self.links_changed.emit(category_id)
        except Exception:
            pass

    def emit_favorites_changed(self) -> None:
        """Сообщить о смене состояния избранного."""
        try:
            self.favorites_changed.emit()
        except Exception:
            pass

    def emit_recents_changed(self) -> None:
        """Сообщить об изменении списка недавних ссылок."""
        try:
            self.recents_changed.emit()
        except Exception:
            pass

    def emit_link_saved(self, payload: dict) -> None:
        try:
            if isinstance(payload, dict):
                self.link_saved.emit(payload)
        except Exception:
            pass

    def emit_link_deleted(self, payload: dict) -> None:
        try:
            if isinstance(payload, dict):
                self.link_deleted.emit(payload)
        except Exception:
            pass

    def get_dialog_initialization_data(self, category_id=None):
        """Получить данные для инициализации диалога ссылки."""
        data = {"spheres": self._prepare_spheres_data(), "category_hierarchy": None}

        if category_id:
            data["category_hierarchy"] = self._get_category_hierarchy(category_id)

        return data

    def _prepare_spheres_data(self):
        """Подготовить данные сфер для диалога."""
        return self.db.spheres.get_spheres()

    def _get_category_hierarchy(self, category_id):
        """Получить иерархию категории (сфера -> раздел -> категория)."""
        return self.db.categories.get_category_hierarchy(category_id)

    def get_sections_for_sphere(self, sphere_id):
        """Получить разделы для сферы."""
        return self.db.sections.get_sections(sphere_id)

    def get_categories_for_section(self, section_id):
        """Получить категории для раздела."""
        return self.db.categories.get_categories(section_id)

    def get_database(self):
        """Получить ссылку на базу данных для валидации."""
        return self.db

    def show_link_dialog(self, link=None, category_id=None):
        """Показать диалог создания/редактирования ссылки."""
        # Гарантировать, что всегда передаём валидный category_id
        cat_id = category_id or self.main_window.get_current_category_id()
        if not cat_id:
            # Попробовать взять первую доступную категорию из базы
            first_cat_id = self.db.categories.get_first_category_id()
            if first_cat_id:
                cat_id = first_cat_id

        # Создаем контроллер для диалога
        from .link_dialog_controller import LinkDialogController

        link_controller = LinkDialogController(self.db)

        # Получаем данные для инициализации через контроллер
        init_data = link_controller.get_initialization_data(cat_id, link)

        dlg = LinkDialog(
            initialization_data=init_data,
            dialog_controller=self,
            link=link,
            category_id=cat_id,
            parent=self.main_window,
            link_controller=link_controller,
        )

        result = dlg.exec() == QDialog.DialogCode.Accepted
        if result:
            # Получаем данные через контроллер
            links_to_save = link_controller.get_result_data()
            logger.debug(
                f"show_link_dialog: got {len(links_to_save) if links_to_save else 0} links to save"
            )
            if links_to_save:
                for i, link in enumerate(links_to_save):
                    logger.debug(
                        f"show_link_dialog: link {i}: name={link.get('name')}, browser_key={link.get('browser_key')}"
                    )

            if not links_to_save:
                return False
            # ВАЖНО: определяем обновление/создание по самим результатам, а не по факту редактирования
            # Если результат содержит id, это обновление существующей записи; иначе — создание новой

            # Используем пакетную команду для множественных ссылок
            if len(links_to_save) > 1:
                # Для множественных ссылок (профили) всегда создаются новые записи
                logger.debug(
                    f"show_link_dialog: using BatchSaveLinksCmd for {len(links_to_save)} links"
                )
                cmd = BatchSaveLinksCmd(
                    links_data=links_to_save,
                    old_link_data=None,  # Всегда None для множественных ссылок
                    main_window=self.main_window,
                )
                self.undo_stack.push(cmd)

                # Устанавливаем фокус на первую добавленную ссылку
                if hasattr(self.main_window, "links_actions") and hasattr(
                    self.main_window.links_actions, "focus_on_link"
                ):
                    # Используем QTimer для отложенной фокусировки после обновления UI
                    from PyQt6.QtCore import QTimer

                    first_link_id = (
                        cmd.created_ids[0]
                        if hasattr(cmd, "created_ids") and cmd.created_ids
                        else None
                    )
                    if first_link_id:
                        QTimer.singleShot(
                            200,
                            lambda: self.main_window.links_actions.focus_on_link(
                                first_link_id
                            ),
                        )
                # Эмит событий о сохранённых ссылках (пакетно)
                try:
                    for payload in links_to_save:
                        if isinstance(payload, dict):
                            self.link_saved.emit(payload)
                except Exception:
                    pass
            else:
                # Для одиночных ссылок используем обычную команду
                data = links_to_save[0]
                logger.debug(
                    f"show_link_dialog: using SaveLinkCmd for single link: name={data.get('name')}, browser_key={data.get('browser_key')}"
                )
                if data.get("_action") == "delete":
                    # Используем Undo-команду, которая делегирует удаление в сервисный слой
                    cmd = DeleteLinkCmd(
                        link_to_delete=data, main_window=self.main_window
                    )
                    self.undo_stack.push(cmd)
                else:
                    # Переопределяем признак обновления для одиночного результата:
                    # если у данных нет id — это создание новой ссылки, не передаём old_data
                    is_update_single = bool(data.get("id"))
                    cmd = SaveLinkCmd(
                        new_data=data,
                        old_data=(link if is_update_single else None),
                        main_window=self.main_window,
                    )
                    self.undo_stack.push(cmd)

                    # Устанавливаем фокус на добавленную ссылку (только для новых ссылок)
                    logger.debug(
                        f"Focus check: is_update={is_update_single}, has_links_actions={hasattr(self.main_window, 'links_actions')}"
                    )
                    if hasattr(self.main_window, "links_actions"):
                        logger.debug(
                            f"LinksActions exists, has_focus_method={hasattr(self.main_window.links_actions, 'focus_on_link')}"
                        )

                    if (
                        not is_update_single
                        and hasattr(self.main_window, "links_actions")
                        and hasattr(self.main_window.links_actions, "focus_on_link")
                    ):
                        # Используем QTimer для отложенной фокусировки после обновления UI
                        from PyQt6.QtCore import QTimer

                        link_id = cmd.created_id or data.get("id")
                        logger.info(
                            f"Attempting to focus on link: cmd.created_id={cmd.created_id}, data.id={data.get('id')}, final_link_id={link_id}"
                        )
                        if link_id:
                            logger.info(
                                f"Scheduling focus on link ID {link_id} in 200ms"
                            )
                            QTimer.singleShot(
                                200,
                                lambda: self.main_window.links_actions.focus_on_link(
                                    link_id
                                ),
                            )
                        else:
                            logger.warning("No link ID available for focusing")
                    # Эмит события о сохранении одиночной ссылки
                    try:
                        if isinstance(data, dict):
                            self.link_saved.emit(data)
                    except Exception:
                        pass

            # Сигнализируем о необходимости перезагрузки таблицы текущей категории
            try:
                if isinstance(cat_id, int) and cat_id > 0:
                    self.links_changed.emit(cat_id)
            except Exception:
                pass

        return result

    def delete_links_with_confirmation(self, links):
        """Удалить ссылки БЕЗ подтверждения.

        Приводим поведение к единому сценарию: как в контекстном меню —
        выполняем немедленное удаление. Для нескольких ссылок используем
        пакетную команду, для одной — одиночную команду. Диалогов
        подтверждения больше нет.
        """
        if not links:
            return

        # Одиночное удаление — без подтверждения
        if len(links) == 1:
            cmd = DeleteLinkCmd(link_to_delete=links[0], main_window=self.main_window)
            # Подавляем внутренние обновления UI, внешний перезагрузчик/статусбар уже вызываются
            try:
                cmd._suppress_ui = True
            except Exception:
                pass
            self.undo_stack.push(cmd)
            # Эмитим сигналы вместо прямых обновлений UI
            try:
                cat_id = links[0].get("category_id")
                if isinstance(cat_id, int) and cat_id > 0:
                    self.links_changed.emit(cat_id)
                # Удаление может повлиять на список недавних — триггерим его обновление
                self.recents_changed.emit()
                # Точечный сигнал об удалении
                if isinstance(links[0], dict):
                    self.link_deleted.emit(links[0])
            except Exception:
                pass
            return

        # Пакетное удаление — без подтверждения, с макросом для Undo
        with self.undo_stack.macro(MACRO_DELETE_LINKS_TEXT.format(count=len(links))):
            cmd = BatchDeleteLinksCmd(
                links_to_delete=links, main_window=self.main_window
            )
            # Внутренний UI подавляется, внешний reload выполняется единоразово
            try:
                cmd._suppress_ui = True
            except Exception:
                pass
            self.undo_stack.push(cmd)
        # После батч-удаления оповещаем слушателей о необходимости обновления
        try:
            cat_id = (links[0] if links else {}).get("category_id")
            if isinstance(cat_id, int) and cat_id > 0:
                self.links_changed.emit(cat_id)
            # Удаление может повлиять на список недавних — триггерим его обновление
            self.recents_changed.emit()
            # Точечные сигналы об удалении для каждой ссылки
            try:
                for payload in links:
                    if isinstance(payload, dict):
                        self.link_deleted.emit(payload)
            except Exception:
                pass
        except Exception:
            pass
