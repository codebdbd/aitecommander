# app/controllers/structure/icon_handling.py

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from concurrent.futures import ThreadPoolExecutor
import threading
import logging

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

logger = logging.getLogger(__name__)


class IconHandling:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business
        # Асинхронная загрузка иконок: пул потоков + токены для дедупликации
        self._executor = getattr(IconHandling, "_shared_executor", None)
        if self._executor is None:
            # Небольшой пул, IO-bound операции
            IconHandling._shared_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="icons")
            self._executor = IconHandling._shared_executor
        self._icon_task_token = 0
        self._icon_future = None
        self._icon_lock = threading.RLock()

    def _get_icon_for_item(self, item_type: str, icon_name: str) -> QIcon:
        # Централизованный резолвер: учитывает и заданный icon_name, и тип
        try:
            resolved = resolve_icon_for_link(
                {"type": item_type, "icon_path": icon_name or ""}
            )
            if resolved:
                return create_icon_from_path(resolved)
        except Exception:
            pass
        # Пустая иконка, если ничего не найдено
        return QIcon()

    def reload_icons(self) -> None:
        """Асинхронно переустанавливает иконки для всех элементов дерева.

        1) В GUI-потоке собираем списки ID секций и категорий.
        2) В бэкграунд-потоке подтягиваем данные и резолвим icon_path → путь (resolve_icon_for_link).
        3) В GUI-потоке создаём QIcon и применяем к модели одним проходом.
        Повторные запросы дедуплицируются: применяется только результат с последним токеном.
        """
        try:
            model = getattr(self.tree, "model", lambda: None)()
            if not model:
                return

            from PyQt6.QtCore import QModelIndex, QTimer
            from app.utils.ui.qt.roles import get_tree_tuple

            # Сбор ID в GUI-потоке
            section_ids: set[int] = set()
            category_ids: set[int] = set()

            def iter_indexes(parent_index=None):
                if parent_index is None:
                    parent_index = QModelIndex()
                rows = model.rowCount(parent_index)
                for r in range(rows):
                    idx = model.index(r, 0, parent_index)
                    if idx.isValid():
                        yield idx
                        yield from iter_indexes(idx)

            for idx in iter_indexes():
                t = get_tree_tuple(idx, 0)
                if not t:
                    continue
                it, item_id = t
                if it == "section" and isinstance(item_id, int):
                    section_ids.add(item_id)
                elif it == "category" and isinstance(item_id, int):
                    category_ids.add(item_id)

            # Обновляем токен и захватываем локально
            with self._icon_lock:
                self._icon_task_token += 1
                token = self._icon_task_token

            # Бэкграунд-задача: получить данные и зарезолвить пути иконок
            def _worker(token_local: int, sec_ids: set[int], cat_ids: set[int]):
                try:
                    # Быстрые выходы при устаревании
                    if token_local != self._icon_task_token:
                        return None
                    sec_by_id: dict[int, dict] = {}
                    cat_by_id: dict[int, dict] = {}
                    try:
                        if hasattr(self.business, "get_sections_bulk"):
                            for row in self.business.get_sections_bulk(list(sec_ids)) or []:
                                try:
                                    sid = int(row.get("id"))
                                    sec_by_id[sid] = row
                                except Exception:
                                    continue
                        if token_local != self._icon_task_token:
                            return None
                        if hasattr(self.business, "get_categories_bulk"):
                            for row in self.business.get_categories_bulk(list(cat_ids)) or []:
                                try:
                                    cid = int(row.get("id"))
                                    cat_by_id[cid] = row
                                except Exception:
                                    continue
                    except Exception:
                        sec_by_id, cat_by_id = {}, {}

                    # Резолвим иконки в пути (IO-bound), без создания QIcon в фоне
                    sec_icon_path: dict[int, str] = {}
                    for sid, row in sec_by_id.items():
                        if token_local != self._icon_task_token:
                            return None
                        try:
                            p = row.get("icon_path") or ""
                            resolved = resolve_icon_for_link({"type": "section", "icon_path": p})
                            sec_icon_path[sid] = resolved or ""
                        except Exception:
                            sec_icon_path[sid] = ""
                    cat_icon_path: dict[int, str] = {}
                    for cid, row in cat_by_id.items():
                        if token_local != self._icon_task_token:
                            return None
                        try:
                            p = row.get("icon_path") or ""
                            resolved = resolve_icon_for_link({"type": "category", "icon_path": p})
                            cat_icon_path[cid] = resolved or ""
                        except Exception:
                            cat_icon_path[cid] = ""
                    return (token_local, sec_icon_path, cat_icon_path)
                except Exception:
                    return None

            future = self._executor.submit(_worker, token, section_ids, category_ids)

            def _on_done(fut):
                try:
                    result = fut.result()
                except Exception:
                    result = None
                if not result:
                    return
                token_local, sec_icon_path, cat_icon_path = result
                # Пропускаем устаревший результат
                if token_local != self._icon_task_token:
                    return

                def _apply():
                    try:
                        model_local = getattr(self.tree, "model", lambda: None)()
                        if not model_local:
                            return
                        from PyQt6.QtCore import QModelIndex
                        from app.utils.ui.qt.roles import get_tree_tuple

                        def iter_indexes_apply(parent_index=None):
                            if parent_index is None:
                                parent_index = QModelIndex()
                            rows = model_local.rowCount(parent_index)
                            for r in range(rows):
                                idx = model_local.index(r, 0, parent_index)
                                if idx.isValid():
                                    yield idx
                                    yield from iter_indexes_apply(idx)

                        for idx in iter_indexes_apply():
                            t = get_tree_tuple(idx, 0)
                            if not t:
                                try:
                                    model_local.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                                except Exception:
                                    pass
                                continue
                            item_type, item_id = t
                            path = ""
                            if item_type == "section":
                                path = sec_icon_path.get(int(item_id), "")
                            elif item_type == "category":
                                path = cat_icon_path.get(int(item_id), "")
                            try:
                                icon = create_icon_from_path(path) if path else QIcon()
                                model_local.setData(idx, icon, Qt.ItemDataRole.DecorationRole)
                            except Exception:
                                try:
                                    model_local.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                # Применяем на GUI-потоке
                try:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, _apply)
                except Exception:
                    _apply()

            future.add_done_callback(_on_done)
            with self._icon_lock:
                self._icon_future = future
        except Exception:
            # В случае любой ошибки не прерываем UI
            pass

    def close(self) -> None:
        """Завершает пул потоков и отменяет незавершённые задачи.

        Вызывать при закрытии контроллера/приложения, чтобы не оставлять висящие потоки.
        Безопасен при повторных вызовах и в присутствии нескольких инстансов: используется
        общий пул на уровне класса и он будет корректно погашен один раз.
        """
        try:
            with self._icon_lock:
                # Попытаемся отменить висящую задачу
                fut = getattr(self, "_icon_future", None)
                try:
                    if fut is not None:
                        fut.cancel()
                except Exception:
                    pass

                # Завершаем общий пул потоков
                exec_ = getattr(IconHandling, "_shared_executor", None)
                if exec_ is not None:
                    try:
                        # Пытаемся использовать cancel_futures=True, если поддерживается
                        exec_.shutdown(wait=False, cancel_futures=True)  # type: ignore[call-arg]
                    except TypeError:
                        exec_.shutdown(wait=False)
                    except Exception:
                        pass
                    finally:
                        IconHandling._shared_executor = None
                # Обнулим ссылку инстанса
                self._executor = None
        except Exception:
            # Закрытие не должно ронять приложение
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def prepare_icons_snapshot(data: list[dict]) -> list[dict]:
    """Преобразует поля icon_path в QIcon для разделов и категорий.

    Использует `resolve_icon_for_link` для выбора корректного пути к иконке
    и `create_icon_from_path` для создания QIcon. Неизвестные/ошибочные пути
    превращаются в пустой `QIcon()`.
    """
    result: list[dict] = []
    for s in data or []:
        try:
            sd = dict(s)
        except Exception:
            logger.exception(
                "prepare_icons_snapshot: не удалось привести элемент раздела к dict: %r",
                s,
            )
            result.append(s)
            continue

        path = sd.get("icon_path") or ""
        try:
            resolved = resolve_icon_for_link({"type": "section", "icon_path": path})
        except Exception:
            # Неожиданная ошибка при разрешении иконки — логируем, используем пустую
            logger.exception(
                "prepare_icons_snapshot: ошибка resolve_icon_for_link для section, path=%r",
                path,
            )
            resolved = None
        try:
            sd["icon"] = create_icon_from_path(resolved) if resolved else QIcon()
        except (OSError, FileNotFoundError, PermissionError) as e:
            logger.warning(
                "prepare_icons_snapshot: файловая ошибка при создании иконки section: %s (path=%r)",
                e,
                resolved,
            )
            sd["icon"] = QIcon()
        except Exception:
            logger.exception(
                "prepare_icons_snapshot: неожиданная ошибка создания QIcon для section (path=%r)",
                resolved,
            )
            sd["icon"] = QIcon()

        cats = sd.get("categories") or []
        new_cats: list[dict] = []
        for c in cats:
            try:
                cd = dict(c)
            except Exception:
                logger.exception(
                    "prepare_icons_snapshot: не удалось привести элемент категории к dict: %r",
                    c,
                )
                new_cats.append(c)
                continue

            cpath = cd.get("icon_path") or ""
            try:
                cresolved = resolve_icon_for_link({"type": "category", "icon_path": cpath})
            except Exception:
                logger.exception(
                    "prepare_icons_snapshot: ошибка resolve_icon_for_link для category, path=%r",
                    cpath,
                )
                cresolved = None
            try:
                cd["icon"] = create_icon_from_path(cresolved) if cresolved else QIcon()
            except (OSError, FileNotFoundError, PermissionError) as e:
                logger.warning(
                    "prepare_icons_snapshot: файловая ошибка при создании иконки category: %s (path=%r)",
                    e,
                    cresolved,
                )
                cd["icon"] = QIcon()
            except Exception:
                logger.exception(
                    "prepare_icons_snapshot: неожиданная ошибка создания QIcon для category (path=%r)",
                    cresolved,
                )
                cd["icon"] = QIcon()
            new_cats.append(cd)

        sd["categories"] = new_cats
        result.append(sd)
    return result
