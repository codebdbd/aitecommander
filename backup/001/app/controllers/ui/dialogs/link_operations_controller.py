# app/controllers/link_operations_controller.py

import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog

from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    DeleteLinkCmd,
    SaveLinkCmd,
)
from app.controllers.ui.undo.stack import UndoManager
from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog

# Константы для макросов отмены/повтора
MACRO_DELETE_LINKS_TEXT = "Удаление {count} ссылок"


logger = logging.getLogger(__name__)


class LinkOperationsController(QObject):
    """Контроллер для операций со ссылками: создание, редактирование, удаление.

    Подписчики на сигналы обязаны быть корректными и не выбрасывать исключения.
    Любые ошибки подписчиков будут залогированы через logger.exception, но не должны
    полагаться на подавление исключений внутри контроллера.
    """

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
        """Сообщить подписчикам, что изменились ссылки для категории.

        Требование: подписчики не должны выбрасывать исключения. Ошибки будут
        залогированы для диагностики, но не подавляются молча.
        """
        try:
            if isinstance(category_id, int) and category_id > 0:
                self.links_changed.emit(category_id)
        except Exception:
            logger.exception("emit_links_changed: failed to emit signal")

    def emit_favorites_changed(self) -> None:
        """Сообщить о смене состояния избранного.

        Требование: подписчики не должны выбрасывать исключения. Ошибки будут
        залогированы через logger.exception.
        """
        try:
            self.favorites_changed.emit()
        except Exception:
            logger.exception("emit_favorites_changed: failed to emit signal")

    def emit_recents_changed(self) -> None:
        """Сообщить об изменении списка недавних ссылок.

        Требование: подписчики не должны выбрасывать исключения. Ошибки будут
        залогированы через logger.exception.
        """
        try:
            self.recents_changed.emit()
        except Exception:
            logger.exception("emit_recents_changed: failed to emit signal")

    def emit_link_saved(self, payload: dict) -> None:
        try:
            if isinstance(payload, dict):
                self.link_saved.emit(payload)
        except Exception:
            logger.exception("emit_link_saved: failed to emit signal")

    def emit_link_deleted(self, payload: dict) -> None:
        try:
            if isinstance(payload, dict):
                self.link_deleted.emit(payload)
        except Exception:
            logger.exception("emit_link_deleted: failed to emit signal")

    # --- Централизованные обработчики событий операций ---
    def on_link_opened(self, link_data: dict) -> None:
        """Вызвать после успешного открытия ссылки (обновляет недавние и таблицу категории)."""
        try:
            self.emit_recents_changed()
            cat_id = (
                link_data.get("category_id") if isinstance(link_data, dict) else None
            )
            if isinstance(cat_id, int) and cat_id > 0:
                self.emit_links_changed(cat_id)
        except Exception:
            logger.exception("on_link_opened: failed to emit signals")

    def on_favorite_toggled(self, category_id: int | None) -> None:
        """Вызвать после завершения операции переключения избранного."""
        try:
            self.emit_favorites_changed()
            if isinstance(category_id, int) and category_id > 0:
                self.emit_links_changed(category_id)
        except Exception:
            logger.exception("on_favorite_toggled: failed to emit signals")

    def on_link_updated(self, updated_link: dict) -> None:
        """Вызвать после обновления ссылки (влияет на недавние и возможно таблицу)."""
        try:
            self.emit_recents_changed()
            cat_id = (
                updated_link.get("category_id")
                if isinstance(updated_link, dict)
                else None
            )
            if isinstance(cat_id, int) and cat_id > 0:
                self.emit_links_changed(cat_id)
        except Exception:
            logger.exception("on_link_updated: failed to emit signals")

    def on_links_deleted(self, links: list[dict]) -> None:
        """Вызвать после удаления ссылок (батч/одиночные)."""
        try:
            # Обновляем таблицу по категории первой ссылки (как и раньше)
            cat_id = (links[0] if links else {}).get("category_id")
            if isinstance(cat_id, int) and cat_id > 0:
                self.emit_links_changed(cat_id)
            # Удаление может повлиять на недавние
            self.emit_recents_changed()
            # Пробрасываем точечные события удаления
            for payload in links or []:
                if isinstance(payload, dict):
                    self.emit_link_deleted(payload)
        except Exception:
            logger.exception("on_links_deleted: failed to emit signals")

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

                # Если среди сохраняемых ссылок есть изменение признака избранного — уведомим UI централизованно
                try:
                    if any(
                        isinstance(p, dict) and ("is_favorite" in p)
                        for p in links_to_save
                    ):
                        # Передаём None, чтобы не дублировать финальный links_changed ниже
                        self.on_favorite_toggled(None)
                except Exception:
                    logger.exception("show_link_dialog: on_favorite_toggled failed")

                # Устанавливаем фокус на первую добавленную ссылку через планировщик
                if hasattr(self.main_window, "links_actions") and hasattr(
                    self.main_window.links_actions, "focus_on_link"
                ):
                    first_link_id = (
                        cmd.created_ids[0]
                        if hasattr(cmd, "created_ids") and cmd.created_ids
                        else None
                    )
                    if first_link_id:
                        try:
                            schedule_selection_restore(
                                lambda: self.main_window.links_actions.focus_on_link(
                                    first_link_id
                                ),
                                first_link_id,
                            )
                        except Exception:
                            logger.exception(
                                "show_link_dialog(batch): schedule focus failed"
                            )
                # Эмит событий о сохранённых ссылках (пакетно)
                try:
                    for payload in links_to_save:
                        if isinstance(payload, dict):
                            self.link_saved.emit(payload)
                except Exception:
                    logger.exception("show_link_dialog: emit link_saved failed")
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

                    # Если запись содержит поле is_favorite — уведомим централизованно
                    try:
                        if isinstance(data, dict) and ("is_favorite" in data):
                            # Передаём None, чтобы не дублировать финальный links_changed ниже
                            self.on_favorite_toggled(None)
                    except Exception:
                        logger.exception(
                            "show_link_dialog(single): on_favorite_toggled failed"
                        )

                    # Планируем восстановление фокуса на ссылке (для новых и обновлённых)
                    logger.debug(
                        f"Focus check: is_update={is_update_single}, has_links_actions={hasattr(self.main_window, 'links_actions')}"
                    )
                    if hasattr(self.main_window, "links_actions"):
                        logger.debug(
                            f"LinksActions exists, has_focus_method={hasattr(self.main_window.links_actions, 'focus_on_link')}"
                        )

                    if hasattr(self.main_window, "links_actions") and hasattr(
                        self.main_window.links_actions, "focus_on_link"
                    ):
                        link_id = cmd.created_id or data.get("id")
                        logger.info(
                            f"Attempting to focus on link: cmd.created_id={cmd.created_id}, data.id={data.get('id')}, final_link_id={link_id}"
                        )
                        if link_id:
                            try:
                                schedule_selection_restore(
                                    lambda: self.main_window.links_actions.focus_on_link(
                                        link_id
                                    ),
                                    link_id,
                                )
                            except Exception:
                                logger.exception(
                                    "show_link_dialog(single): schedule focus failed"
                                )
                        else:
                            logger.warning("No link ID available for focusing")
                    # Эмит события о сохранении одиночной ссылки
                    try:
                        if isinstance(data, dict):
                            self.link_saved.emit(data)
                    except Exception:
                        logger.exception(
                            "show_link_dialog(single): emit link_saved failed"
                        )

            # Сигнализируем о необходимости перезагрузки таблицы текущей категории
            try:
                if isinstance(cat_id, int) and cat_id > 0:
                    self.links_changed.emit(cat_id)
            except Exception:
                logger.exception("show_link_dialog: emit links_changed failed")

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
                logger.exception(
                    "delete_links_with_confirmation(single): failed to set _suppress_ui"
                )
            self.undo_stack.push(cmd)
            # Централизованный вызов сигналов
            try:
                self.on_links_deleted(links)
            except Exception:
                logger.exception(
                    "delete_links_with_confirmation(single): on_links_deleted failed"
                )
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
        # После батч-удаления централизованно оповещаем слушателей
        try:
            self.on_links_deleted(links)
        except Exception:
            logger.exception(
                "delete_links_with_confirmation(batch): on_links_deleted failed"
            )
