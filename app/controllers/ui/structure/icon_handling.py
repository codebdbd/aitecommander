# app/controllers/structure/icon_handling.py

from PyQt6.QtCore import Qt, QModelIndex, QTimer
from PyQt6.QtGui import QIcon

from concurrent.futures import ThreadPoolExecutor
import threading
import logging

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.qt.roles import get_tree_tuple

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
        # Карта последних применённых путей иконок, чтобы избегать лишних setData и загрузок
        # Ключ: (item_type, int item_id) → str resolved_path
        self._last_icon_paths: dict[tuple[str, int], str] = {}

    def _get_icon_for_item(self, item_type: str, icon_name: str) -> QIcon:
        # Централизованный резолвер: учитывает и заданный icon_name, и тип
        try:
            resolved = resolve_icon_for_link(
                {"type": item_type, "icon_path": icon_name or ""}
            )
            if resolved:
                try:
                    return create_icon_from_path(resolved)
                except (OSError, FileNotFoundError, PermissionError, ValueError) as e:
                    logger.warning(
                        "_get_icon_for_item: filesystem/value error creating icon for %s (path=%r): %s",
                        item_type,
                        resolved,
                        e,
                    )
                except Exception:
                    # Неожиданная ошибка при создании QIcon
                    logger.exception(
                        "_get_icon_for_item: unexpected error creating QIcon for %s (path=%r)",
                        item_type,
                        resolved,
                    )
        except (OSError, FileNotFoundError, PermissionError, ValueError) as e:
            # Ожидаемые ошибки при резолве — логируем и возвращаем пустую иконку
            logger.warning(
                "_get_icon_for_item: filesystem/value error resolving icon for %s (name=%r): %s",
                item_type,
                icon_name,
                e,
            )
        except Exception:
            # Неожиданная ошибка при резолве — логируем стек
            logger.exception(
                "_get_icon_for_item: unexpected error resolving icon for %s (name=%r)",
                item_type,
                icon_name,
            )
        # Пустая иконка, если ничего не найдено
        return QIcon()


    def _schedule_on_gui(self, fn) -> None:
        """Планирует выполнение fn в GUI-потоке дерева.

        В продакшене используем перегрузку QTimer.singleShot(ms, receiver, fn),
        но в тестах QTimer может быть замокан без такой перегрузки — поддержим
        совместимость через fallback на QTimer.singleShot(ms, fn).
        """
        try:
            QTimer.singleShot(0, self.tree, fn)
        except TypeError:
            # Совместимость с тестовыми подменами QTimer
            QTimer.singleShot(0, fn)

    def prepare_snapshot_async(self, data: list[dict] | None, on_ready) -> None:
        """Готовит иконки для снапшота в пуле потоков и вызывает on_ready(prepared) в GUI-потоке.

        Если data пустой/None — колбэк вызывается сразу с исходными данными.
        """
        if not data:
            self._schedule_on_gui(lambda: on_ready(data))
            return

        def _work():
            try:
                return prepare_icons_snapshot(list(data))
            except Exception:
                logger.debug("prepare_snapshot_async: prepare_icons_snapshot failed", exc_info=True)
                return data

        fut = self._executor.submit(_work)

        def _on_done(_f):
            try:
                result = _f.result()
            except Exception:
                result = data
            self._schedule_on_gui(lambda: on_ready(result))

        fut.add_done_callback(_on_done)

    def reload_icons(self) -> None:
        """Асинхронно переустанавливает иконки для всех элементов дерева.

        Оркестрация:
        1) Собрать ID секций и категорий (_gather_ids)
        2) Отправить фоновую задачу на извлечение данных и резолв путей (_fetch_and_resolve)
        3) Применить результат на GUI-потоке (_apply_resolved_icons)
        """
        model = getattr(self.tree, "model", lambda: None)()
        if not model:
            return

        section_ids, category_ids = self._gather_ids(model)

        # Очистим кэш путей иконок от «мертвых» записей (удалённых узлов)
        try:
            current_ids = {("section", int(sid)) for sid in section_ids}
            current_ids.update({("category", int(cid)) for cid in category_ids})
            self._prune_icon_cache(current_ids)
        except Exception:
            logger.debug("IconHandling.reload_icons: prune cache failed", exc_info=True)

        # Отменяем предыдущую задачу, если она еще активна, и только потом обновляем токен
        with self._icon_lock:
            try:
                if self._icon_future is not None and not self._icon_future.done():
                    self._icon_future.cancel()
            except Exception:
                pass
            finally:
                # Сбрасываем ссылку — новая задача будет назначена ниже
                self._icon_future = None
            # Обновляем токен после отмены предыдущей задачи
            self._icon_task_token += 1
            token = self._icon_task_token

        # Запускаем фоновую задачу
        future = self._executor.submit(self._fetch_and_resolve, token, section_ids, category_ids)

        def _on_done(fut):
            try:
                if fut.cancelled():
                    return
                result = fut.result()
            except Exception:
                result = None
            if not result:
                return
            token_local, sec_icon_path, cat_icon_path = result
            if token_local != self._icon_task_token:
                return
            self._apply_resolved_icons(token_local, sec_icon_path, cat_icon_path)
            # Очистим ссылку на future, только если это именно текущая задача
            try:
                with self._icon_lock:
                    if self._icon_future is fut:
                        self._icon_future = None
            except Exception:
                pass

        future.add_done_callback(_on_done)
        with self._icon_lock:
            self._icon_future = future

    def _prune_icon_cache(self, current_ids) -> None:
        """Удаляет из кэша путей иконок записи, которых нет в текущей модели.

        current_ids: set[tuple[str, int]] — множество валидных (type, id) узлов.
        """
        try:
            if not isinstance(self._last_icon_paths, dict):
                return
            to_delete = []
            for key in self._last_icon_paths.keys():
                try:
                    if key not in current_ids:
                        to_delete.append(key)
                except Exception:
                    # Некорректный ключ — удалим
                    to_delete.append(key)
            if to_delete:
                for k in to_delete:
                    try:
                        self._last_icon_paths.pop(k, None)
                    except Exception:
                        pass
        except Exception:
            logger.debug("IconHandling._prune_icon_cache failed", exc_info=True)

    def _gather_ids(self, model) -> tuple[set[int], set[int]]:

        section_ids: set[int] = set()
        category_ids: set[int] = set()

        def _iter(parent_index=None):
            if parent_index is None:
                parent_index = QModelIndex()
            try:
                rows = model.rowCount(parent_index)
            except Exception:
                return
            for r in range(rows):
                idx = model.index(r, 0, parent_index)
                if idx.isValid():
                    yield idx
                    yield from _iter(idx)

        for idx in _iter():
            try:
                t = get_tree_tuple(idx, 0)
            except Exception:
                t = None
            if not t:
                continue
            it, item_id = t
            if it == "section" and isinstance(item_id, int):
                section_ids.add(item_id)
            elif it == "category" and isinstance(item_id, int):
                category_ids.add(item_id)

        return section_ids, category_ids

    def _fetch_and_resolve(self, token_local: int, sec_ids: set[int], cat_ids: set[int]):
        try:
            # Считаем устаревшим только когда локальный токен меньше текущего (есть более новая задача)
            if token_local < getattr(self, "_icon_task_token", 0):
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
                if hasattr(self.business, "get_categories_bulk"):
                    for row in self.business.get_categories_bulk(list(cat_ids)) or []:
                        try:
                            cid = int(row.get("id"))
                            cat_by_id[cid] = row
                        except Exception:
                            continue
            except Exception:
                sec_by_id, cat_by_id = {}, {}

            # Резолв путей (без создания QIcon)
            sec_icon_path: dict[int, str] = {}
            for sid, row in sec_by_id.items():
                if token_local < getattr(self, "_icon_task_token", 0):
                    return None
                try:
                    p = row.get("icon_path") or ""
                    resolved = resolve_icon_for_link({"type": "section", "icon_path": p})
                    sec_icon_path[sid] = resolved or ""
                except Exception:
                    sec_icon_path[sid] = ""
            cat_icon_path: dict[int, str] = {}
            for cid, row in cat_by_id.items():
                if token_local < getattr(self, "_icon_task_token", 0):
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

    def _apply_resolved_icons(
        self, token_local: int, sec_icon_path: dict[int, str], cat_icon_path: dict[int, str]
    ) -> None:

        def _apply():
            try:
                model_local = getattr(self.tree, "model", lambda: None)()
                if not model_local:
                    return

                # Итеративный обход в глубину с ограничением числа шагов
                MAX_ITERS = 200000
                iters = 0
                stack = []
                # Инициализация: корневой уровень
                try:
                    root_parent = QModelIndex()
                    root_rows = model_local.rowCount(root_parent)
                except Exception:
                    root_rows = 0
                stack.append((root_parent, 0, root_rows))  # (parent, next_row, total_rows)

                while stack:
                    parent, row, total = stack[-1]
                    if row >= total:
                        stack.pop()
                        continue
                    # Обновляем указатель строки на вершине стека
                    stack[-1] = (parent, row + 1, total)
                    try:
                        idx = model_local.index(row, 0, parent)
                    except Exception:
                        continue
                    if not idx or not idx.isValid():
                        continue

                    # Обработка текущего индекса
                    iters += 1
                    if iters > MAX_ITERS:
                        logger.warning("IconHandling._apply_resolved_icons: iteration limit reached (%s), aborting traversal", MAX_ITERS)
                        break

                    try:
                        t = get_tree_tuple(idx, 0)
                    except Exception:
                        t = None
                    if not t:
                        try:
                            model_local.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                        except Exception:
                            pass
                    else:
                        item_type, item_id = t
                        path = ""
                        if item_type == "section":
                            path = sec_icon_path.get(int(item_id), "")
                        elif item_type == "category":
                            path = cat_icon_path.get(int(item_id), "")
                        # Пропускаем, если путь не изменился (избегаем лишних dataChanged и загрузок)
                        try:
                            key = (str(item_type), int(item_id)) if isinstance(item_id, int) else None
                        except Exception:
                            key = None
                        if key is not None:
                            prev_path = self._last_icon_paths.get(key, None)
                            if prev_path == (path or ""):
                                pass
                            else:
                                try:
                                    icon = create_icon_from_path(path) if path else QIcon()
                                    model_local.setData(idx, icon, Qt.ItemDataRole.DecorationRole)
                                    if key is not None:
                                        self._last_icon_paths[key] = path or ""
                                except Exception:
                                    try:
                                        model_local.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                                        if key is not None:
                                            self._last_icon_paths[key] = path or ""
                                    except Exception:
                                        pass
                        else:
                            try:
                                icon = create_icon_from_path(path) if path else QIcon()
                                model_local.setData(idx, icon, Qt.ItemDataRole.DecorationRole)
                            except Exception:
                                try:
                                    model_local.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                                except Exception:
                                    pass
                    # Подготовим спуск к детям текущего индекса
                    try:
                        child_rows = model_local.rowCount(idx)
                    except Exception:
                        child_rows = 0
                    if child_rows and child_rows > 0:
                        stack.append((idx, 0, child_rows))
            except Exception:
                # Не роняем GUI поток
                logger.debug("IconHandling._apply_resolved_icons: apply failed", exc_info=True)

        # Гарантируем выполнение в GUI-потоке дерева
        self._schedule_on_gui(_apply)

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
        # Раздел
        try:
            sd = _add_icon(s, "section")
        except Exception:
            logger.debug("prepare_icons_snapshot: _add_icon failed for section; keep original", exc_info=True)
            sd = s
        # Категории
        cats = sd.get("categories") or []
        new_cats: list[dict] = []
        for c in cats:
            try:
                new_cats.append(_add_icon(c, "category"))
            except Exception:
                # На всякий случай, но _add_icon сам логирует все неожиданности
                new_cats.append(c)
        sd["categories"] = new_cats
        result.append(sd)
    return result


def _add_icon(item: dict, item_type: str) -> dict:
    """Возвращает копию item с добавленным ключом 'icon' на основе icon_path.

    Единообразная обработка ошибок:
    - ожидаемые файловые/значимые ошибки логируются как warning, 'icon' = пустой QIcon
    - неожиданные исключения логируются через logger.exception, 'icon' = пустой QIcon
    """
    try:
        out = dict(item)
    except Exception:
        logger.exception("_add_icon: failed to copy item for %s: %r", item_type, item)
        return item
    path = out.get("icon_path") or ""
    try:
        resolved = resolve_icon_for_link({"type": item_type, "icon_path": path})
    except (OSError, FileNotFoundError, PermissionError, ValueError) as e:
        logger.warning(
            "_add_icon: filesystem/value error resolving icon for %s (icon_path=%r): %s",
            item_type,
            path,
            e,
        )
        resolved = None
    except Exception:
        logger.exception(
            "_add_icon: unexpected error resolving icon for %s (icon_path=%r)",
            item_type,
            path,
        )
        resolved = None
    try:
        out["icon"] = create_icon_from_path(resolved) if resolved else QIcon()
    except (OSError, FileNotFoundError, PermissionError, ValueError) as e:
        logger.warning(
            "_add_icon: filesystem/value error creating QIcon for %s (resolved=%r): %s",
            item_type,
            resolved,
            e,
        )
        out["icon"] = QIcon()
    except Exception:
        logger.exception(
            "_add_icon: unexpected error creating QIcon for %s (resolved=%r)",
            item_type,
            resolved,
        )
        out["icon"] = QIcon()
    return out
