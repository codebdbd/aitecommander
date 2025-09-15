# app/controllers/structure/icon_handling.py

from PyQt6.QtCore import Qt, QModelIndex, QTimer, QThread
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
        if not hasattr(IconHandling, "_shared_executor"):
            IconHandling._shared_executor = None
        if not hasattr(IconHandling, "_IconHandling__executor_refcount"):
            IconHandling.__executor_refcount = 0  # type: ignore[attr-defined]
        if not hasattr(IconHandling, "_IconHandling__executor_lock"):
            IconHandling.__executor_lock = threading.RLock()  # type: ignore[attr-defined]

        with IconHandling.__executor_lock:  # type: ignore[attr-defined]
            if IconHandling._shared_executor is None:
                # Небольшой пул, IO-bound операции
                IconHandling._shared_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="icons")
                IconHandling.__executor_refcount = 1  # type: ignore[attr-defined]
            else:
                # Увеличиваем счётчик ссылок
                IconHandling.__executor_refcount = int(IconHandling.__executor_refcount) + 1  # type: ignore[attr-defined]
            self._executor = IconHandling._shared_executor
        self._icon_task_token = 0
        self._icon_future = None
        self._icon_lock = threading.RLock()
        # Карта последних применённых путей иконок, чтобы избегать лишних setData и загрузок
        # Ключ: (item_type, int item_id) → str resolved_path
        self._last_icon_paths: dict[tuple[str, int], str] = {}
        # Состояние итеративного обхода для порционного применения иконок
        self._apply_stack = None  # type: list | None
        self._apply_token = None  # type: int | None
        self._apply_total_steps = 0

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

        Предпочтительно используем перегрузку QTimer.singleShot(ms, receiver, fn)
        для запуска в потоке объекта tree. Поддерживаем тестовые моки без такой
        перегрузки через fallback на QTimer.singleShot(ms, fn). Если доступен метод
        thread() у дерева и мы уже на GUI-потоке — вызываем напрямую.
        """
        try:
            # Пытаемся определить GUI-поток дерева, если доступен
            tree_thread_getter = getattr(self.tree, "thread", None)
            if callable(tree_thread_getter):
                try:
                    if QThread.currentThread() is tree_thread_getter():
                        fn()
                        return
                except Exception:
                    pass
            # Пробуем перегрузку с receiver
            try:
                QTimer.singleShot(0, self.tree, fn)
                return
            except TypeError:
                # В тестах может быть только singleShot(ms, fn)
                pass
            except Exception:
                pass
            # Fallback: без receiver
            try:
                QTimer.singleShot(0, fn)
                return
            except Exception:
                pass
            # Последний резерв: прямой вызов (риски на не-GUI поток берём на себя)
            try:
                fn()
            except Exception:
                logger.debug("IconHandling._schedule_on_gui: direct call failed", exc_info=True)
        except Exception:
            logger.debug("IconHandling._schedule_on_gui failed", exc_info=True)

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
        # Поддержка как метода model(), так и атрибута model
        _macc = getattr(self.tree, "model", None)
        model = _macc() if callable(_macc) else _macc
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

        # Итеративный обход дерева с явным стеком: (parent, next_row, total_rows)
        try:
            root_parent = QModelIndex()
            try:
                root_rows = model.rowCount(root_parent)
            except Exception:
                root_rows = 0
            stack: list[tuple[QModelIndex, int, int]] = [(root_parent, 0, int(root_rows))]

            while stack:
                parent, row, total = stack[-1]
                if row >= total:
                    stack.pop()
                    continue
                # продвинем указатель строки на вершине стека
                stack[-1] = (parent, row + 1, total)
                try:
                    idx = model.index(row, 0, parent)
                except Exception:
                    continue
                if not idx or not idx.isValid():
                    continue

                # Соберём ID
                try:
                    t = get_tree_tuple(idx, 0)
                except Exception:
                    t = None
                if t:
                    it, item_id = t
                    if it == "section" and isinstance(item_id, int):
                        section_ids.add(item_id)
                    elif it == "category" and isinstance(item_id, int):
                        category_ids.add(item_id)

                # Спуск к детям
                try:
                    child_rows = model.rowCount(idx)
                except Exception:
                    child_rows = 0
                if child_rows and child_rows > 0:
                    stack.append((idx, 0, int(child_rows)))
        except Exception:
            # Логируем как debug, чтобы не шуметь в проде
            logger.debug("IconHandling._gather_ids: traversal failed", exc_info=True)

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

        CHUNK_STEPS = 2000
        TOTAL_MAX_STEPS = 1000000

        def _init_traversal(model_local):
            try:
                root_parent = QModelIndex()
                try:
                    root_rows = model_local.rowCount(root_parent)
                except Exception:
                    root_rows = 0
                self._apply_stack = [(root_parent, 0, int(root_rows))]
                self._apply_total_steps = 0
                self._apply_token = int(token_local)
            except Exception:
                self._apply_stack = []
                self._apply_total_steps = 0
                self._apply_token = int(token_local)

        def _apply_chunk():
            try:
                # Сброс при смене токена: прерываем только если токен уже установлен и отличается
                if self._apply_token is not None and self._apply_token != int(token_local):
                    self._apply_stack = None
                    return
                # Поддержка как метода model(), так и атрибута model
                _macc = getattr(self.tree, "model", None)
                model_local = _macc() if callable(_macc) else _macc
                if not model_local:
                    self._apply_stack = None
                    return
                # Гарантируем выполнение на GUI-потоке перед созданием QIcon, если можем это проверить
                try:
                    tree_thread_getter = getattr(self.tree, "thread", None)
                    if callable(tree_thread_getter):
                        if QThread.currentThread() is not tree_thread_getter():
                            self._schedule_on_gui(_apply_chunk)
                            return
                except Exception:
                    # Если не удалось проверить поток — продолжаем (в тестах create_icon_from_path безопасен)
                    pass
                if self._apply_stack is None:
                    _init_traversal(model_local)

                steps = 0
                while self._apply_stack and steps < CHUNK_STEPS:
                    parent, row, total = self._apply_stack[-1]
                    if row >= total:
                        self._apply_stack.pop()
                        continue
                    # продвигаем указатель строки на вершине стека
                    self._apply_stack[-1] = (parent, row + 1, total)
                    try:
                        idx = model_local.index(row, 0, parent)
                    except Exception:
                        idx = None
                    if not idx or not getattr(idx, "isValid", lambda: False)():
                        steps += 1
                        self._apply_total_steps += 1
                        if self._apply_total_steps > TOTAL_MAX_STEPS:
                            logger.warning("IconHandling._apply_resolved_icons: total iteration limit reached (%s), aborting", TOTAL_MAX_STEPS)
                            self._apply_stack = None
                            break
                        continue

                    # Обработка текущего индекса
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
                        # Пропуск, если путь не изменился
                        try:
                            key = (str(item_type), int(item_id)) if isinstance(item_id, int) else None
                        except Exception:
                            key = None
                        if key is not None:
                            prev_path = self._last_icon_paths.get(key, None)
                            if prev_path != (path or ""):
                                try:
                                    icon = create_icon_from_path(path) if path else QIcon()
                                    model_local.setData(idx, icon, Qt.ItemDataRole.DecorationRole)
                                    self._last_icon_paths[key] = path or ""
                                except Exception:
                                    try:
                                        model_local.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
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

                    # Спуск к детям
                    try:
                        child_rows = model_local.rowCount(idx)
                    except Exception:
                        child_rows = 0
                    if child_rows and child_rows > 0:
                        self._apply_stack.append((idx, 0, int(child_rows)))

                    steps += 1
                    self._apply_total_steps += 1
                    if self._apply_total_steps > TOTAL_MAX_STEPS:
                        logger.warning("IconHandling._apply_resolved_icons: total iteration limit reached (%s), aborting", TOTAL_MAX_STEPS)
                        self._apply_stack = None
                        break

                # Планирование следующего чанка или завершение
                if self._apply_stack:
                    self._schedule_on_gui(_apply_chunk)
                else:
                    # Завершено — очистим состояние
                    self._apply_stack = None
                    self._apply_token = None
                    self._apply_total_steps = 0
            except Exception:
                logger.debug("IconHandling._apply_resolved_icons: apply chunk failed", exc_info=True)

        # Стартуем выполнение первой порции на GUI-потоке
        self._schedule_on_gui(_apply_chunk)

    def close(self) -> None:
        """Завершает пул потоков и отменяет незавершённые задачи.

        Вызывать при закрытии контроллера/приложения, чтобы не оставлять висящие потоки.
        Используется общий пул на уровне класса; введён счётчик ссылок, чтобы
        не завершать пул, пока он используется другими инстансами.
        """
        try:
            # Отменим локальную задачу (если есть)
            with self._icon_lock:
                fut = getattr(self, "_icon_future", None)
                try:
                    if fut is not None:
                        fut.cancel()
                except Exception:
                    pass
                self._icon_future = None

            # Уменьшаем ссылку на общий пул и завершаем его только при нуле
            if hasattr(IconHandling, "_IconHandling__executor_lock"):
                lock = IconHandling.__executor_lock  # type: ignore[attr-defined]
            else:
                # На всякий случай создадим
                IconHandling.__executor_lock = threading.RLock()  # type: ignore[attr-defined]
                lock = IconHandling.__executor_lock  # type: ignore[attr-defined]

            with lock:
                # Если общий пул не инициализирован — нечего делать
                if not hasattr(IconHandling, "_shared_executor"):
                    return
                # Инициализация refcount по умолчанию, если отсутствует
                if not hasattr(IconHandling, "_IconHandling__executor_refcount"):
                    IconHandling.__executor_refcount = 0  # type: ignore[attr-defined]

                # Декремент счётчика, не уходя ниже нуля
                try:
                    IconHandling.__executor_refcount = max(0, int(IconHandling.__executor_refcount) - 1)  # type: ignore[attr-defined]
                except Exception:
                    IconHandling.__executor_refcount = 0  # type: ignore[attr-defined]

                if int(IconHandling.__executor_refcount) == 0:  # type: ignore[attr-defined]
                    exec_ = IconHandling._shared_executor
                    IconHandling._shared_executor = None
                    if exec_ is not None:
                        try:
                            exec_.shutdown(wait=False, cancel_futures=True)  # type: ignore[call-arg]
                        except TypeError:
                            exec_.shutdown(wait=False)
                        except Exception:
                            pass

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
    """Готовит снапшот: резолвит icon_path, но НЕ создаёт QIcon в рабочем потоке.

    Примечание: создание QIcon должно выполняться только в GUI-потоке.
    Здесь мы лишь обновляем корректные пути и устанавливаем пустые QIcon(),
    чтобы последующее применение иконок выполнялось на GUI-потоке.
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
    """Возвращает копию item с обновлённым icon_path и пустым 'icon'.

    Создание QIcon здесь запрещено (возможен рабочий поток). Только резолв пути,
    затем выставляем out["icon"] = QIcon() — реальные иконки установятся позже на GUI-потоке.
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
    # Сохраняем резолвнутый путь обратно в элемент — это позволит reload_icons
    # позже создать корректный QIcon по пути
    try:
        out["icon_path"] = resolved or ""
    except Exception:
        pass
    # Не создаём QIcon здесь, оставляем пустой — применится позже в GUI-потоке
    out["icon"] = QIcon()
    return out
