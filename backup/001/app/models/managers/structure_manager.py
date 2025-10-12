"""Модуль для управления полной структурой данных в БД."""
import copy
import logging
import time
from typing import Dict, List

from ..base.db_base import DatabaseError, db_lock
from ..types.link_type import LinkType

logger = logging.getLogger(__name__)


class StructureManager:
    """Управление получением и импортом полной структуры данных."""

    def __init__(self, db):
        """
        Args:
            db: Экземпляр Database для доступа к соединению и сигналам
        """
        self.db = db

    def get_full_structure(self) -> List[Dict]:
        """Возвращает полную структуру данных в виде вложенных словарей."""
        try:
            # Единичные bulk-выборки по всем уровням, чтобы избежать N+1
            t0 = time.perf_counter()
            with db_lock:
                spheres_rows = self.db.connection.execute(
                    "SELECT * FROM sphere ORDER BY position"
                ).fetchall()
                sections_rows = self.db.connection.execute(
                    "SELECT * FROM section ORDER BY position"
                ).fetchall()
                categories_rows = self.db.connection.execute(
                    "SELECT * FROM category ORDER BY position"
                ).fetchall()
                links_rows = self.db.connection.execute(
                    "SELECT * FROM link ORDER BY position"
                ).fetchall()

            t1 = time.perf_counter()

            # Индексы для сборки иерархии
            spheres_by_id: Dict[int, Dict] = {}
            sections_by_id: Dict[int, Dict] = {}
            categories_by_id: Dict[int, Dict] = {}

            sections_by_sphere: Dict[int, List[Dict]] = {}
            categories_by_section: Dict[int, List[Dict]] = {}

            # Преобразование строк в dict и подготовка контейнеров
            for s in spheres_rows:
                sd = dict(s)
                sd["sections"] = []
                spheres_by_id[int(sd["id"])] = sd

            for sec in sections_rows:
                sc = dict(sec)
                sc["categories"] = []
                sec_id = int(sc["id"])
                sections_by_id[sec_id] = sc
                sections_by_sphere.setdefault(int(sc["sphere_id"]), []).append(sc)

            for cat in categories_rows:
                cd = dict(cat)
                cd["links"] = []
                cat_id = int(cd["id"])
                categories_by_id[cat_id] = cd
                categories_by_section.setdefault(int(cd["section_id"]), []).append(cd)

            # Раскладываем ссылки по категориям
            for ln in links_rows:
                ld = dict(ln)
                cat_id = ld.get("category_id")
                if cat_id is None:
                    continue
                cat_obj = categories_by_id.get(int(cat_id))
                if cat_obj is not None:
                    cat_obj["links"].append(ld)

            # Сборка итоговой структуры, сохраняя порядок по position
            spheres_data: List[Dict] = []
            for s in spheres_rows:
                s_obj = spheres_by_id[int(s["id"])]
                for sc in sections_by_sphere.get(int(s_obj["id"]), []):
                    sc["categories"] = categories_by_section.get(int(sc["id"]), [])
                    s_obj["sections"].append(sc)
                spheres_data.append(s_obj)

            t2 = time.perf_counter()
            total_ms = (t2 - t0) * 1000.0
            db_ms = (t1 - t0) * 1000.0
            build_ms = (t2 - t1) * 1000.0
            logger.debug(
                "get_full_structure: spheres=%d, sections=%d, categories=%d, links=%d, db_ms=%.2f, build_ms=%.2f, total_ms=%.2f",
                len(spheres_rows),
                len(sections_rows),
                len(categories_rows),
                len(links_rows),
                db_ms,
                build_ms,
                total_ms,
            )
            return spheres_data
        except Exception as e:
            logger.error("Ошибка получения полной структуры: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось получить полную структуру: {e}")

    def import_full_structure(self, data: List[Dict]):
        """Очищает базу и импортирует данные из структуры.

        Потокобезопасная операция, которая не изменяет входные данные.

        Args:
            data: Список словарей со структурой данных для импорта.
                  Исходный объект остается неизменным.
        """
        operation = "import_full_structure"
        try:
            t0 = time.perf_counter()
            root = copy.deepcopy(data or [])
            
            # Подсчет элементов для прогресса
            total_items = (
                len(root) +
                sum(len((s or {}).get("sections", [])) for s in root) +
                sum(len((sec or {}).get("categories", []))
                    for s in root for sec in (s or {}).get("sections", [])) +
                sum(len((cat or {}).get("links", []))
                    for s in root for sec in (s or {}).get("sections", [])
                    for cat in (sec or {}).get("categories", []))
            )
            self.db.operation_started.emit(operation, total_items or 1)

            # --- Фаза подготовки: нормализуем вход и строим связи ---
            self.db.operation_progress.emit(operation, 0, total_items or 1, "Подготовка данных...")
            spheres_items: List[Dict] = []  # {ref, id?, name, icon_path, position}
            sections_items: List[Dict] = []  # {ref, id?, name, sphere_ref, icon_path, position}
            categories_items: List[Dict] = []  # {ref, id?, name, section_ref, icon_path, position}
            links_with_id: List[Dict] = []  # готово к executemany
            links_without_id: List[Dict] = []  # поштучные INSERT
            current = 0

            for s_idx, s in enumerate(root):
                if not isinstance(s, dict):
                    continue
                s_ref = id(s)
                s_name = s.get("name", "")
                s_pos = s.get("position", s_idx)
                s_icon = s.get("icon_path", "")
                spheres_items.append(
                    {
                        "ref": s_ref,
                        "id": s.get("id"),
                        "name": s_name,
                        "icon_path": s_icon,
                        "position": s_pos,
                    }
                )

                for c_idx, sec in enumerate((s or {}).get("sections") or []):
                    if not isinstance(sec, dict):
                        continue
                    sec_ref = id(sec)
                    sections_items.append(
                        {
                            "ref": sec_ref,
                            "id": sec.get("id"),
                            "name": sec.get("name", ""),
                            "icon_path": sec.get("icon_path", ""),
                            "position": sec.get("position", c_idx),
                            "sphere_ref": s_ref,
                        }
                    )

                    for k_idx, cat in enumerate((sec or {}).get("categories") or []):
                        if not isinstance(cat, dict):
                            continue
                        cat_ref = id(cat)
                        categories_items.append(
                            {
                                "ref": cat_ref,
                                "id": cat.get("id"),
                                "name": cat.get("name", ""),
                                "icon_path": cat.get("icon_path", ""),
                                "position": cat.get("position", k_idx),
                                "section_ref": sec_ref,
                            }
                        )

                        for l_idx, ln in enumerate((cat or {}).get("links") or []):
                            if not isinstance(ln, dict):
                                continue
                            ld = dict(ln)
                            # Нормализация минимума
                            try:
                                ld["type"] = LinkType.from_value(ld.get("type", "web")).value
                            except Exception:
                                ld["type"] = LinkType.WEB.value
                            ld["is_favorite"] = int(ld.get("is_favorite", 0) or 0)
                            ld.setdefault("icon_path", "")
                            if ld.get("position") is None:
                                ld["position"] = l_idx
                            # Проставим отложенную ссылку на категорию через ref
                            ld["_category_ref"] = cat_ref
                            if ld.get("id"):
                                links_with_id.append(ld)
                            else:
                                links_without_id.append(ld)

            # --- Фаза вставки: одна транзакция, уровни сверху вниз ---
            with db_lock:
                with self.db.connection:
                    # Очистка таблиц в порядке зависимостей
                    self.db.operation_progress.emit(operation, current, total_items or 1, "Очистка таблиц...")
                    self.db.connection.execute("DELETE FROM link")
                    self.db.connection.execute("DELETE FROM category")
                    self.db.connection.execute("DELETE FROM section")
                    self.db.connection.execute("DELETE FROM sphere")

                    # 1) Сферы
                    self.db.operation_progress.emit(operation, current, total_items or 1, f"Вставка сфер: {len(spheres_items)}")
                    spheres_with_id = [x for x in spheres_items if x.get("id")]
                    spheres_no_id = [x for x in spheres_items if not x.get("id")]

                    if spheres_with_id:
                        self.db.connection.executemany(
                            "INSERT INTO sphere (id, name, icon_path, position) VALUES (?, ?, ?, ?)",
                            [
                                (
                                    int(x["id"]),
                                    x.get("name", ""),
                                    x.get("icon_path", ""),
                                    int(x.get("position", 0)),
                                )
                                for x in spheres_with_id
                            ],
                        )

                    sphere_ref_to_id: Dict[int, int] = {}
                    for x in spheres_with_id:
                        sphere_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
                    for x in spheres_no_id:
                        cur = self.db.connection.execute(
                            "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                            (x.get("name", ""), x.get("icon_path", ""), int(x.get("position", 0))),
                        )
                        sphere_ref_to_id[x["ref"]] = int(cur.lastrowid)

                    # 2) Разделы
                    self.db.operation_progress.emit(operation, len(spheres_items), total_items or 1, f"Вставка разделов: {len(sections_items)}")
                    for x in sections_items:
                        x["sphere_id"] = sphere_ref_to_id.get(x["sphere_ref"])  # гарантируем FK
                    sections_with_id = [x for x in sections_items if x.get("id")]
                    sections_no_id = [x for x in sections_items if not x.get("id")]

                    if sections_with_id:
                        self.db.connection.executemany(
                            "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            [
                                (
                                    int(x["id"]),
                                    x.get("name", ""),
                                    int(x.get("sphere_id")),
                                    x.get("icon_path", ""),
                                    int(x.get("position", 0)),
                                )
                                for x in sections_with_id
                            ],
                        )

                    section_ref_to_id: Dict[int, int] = {}
                    for x in sections_with_id:
                        section_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
                    for x in sections_no_id:
                        cur = self.db.connection.execute(
                            "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                            (
                                x.get("name", ""),
                                int(x.get("sphere_id")),
                                x.get("icon_path", ""),
                                int(x.get("position", 0)),
                            ),
                        )
                        section_ref_to_id[x["ref"]] = int(cur.lastrowid)

                    # 3) Категории
                    self.db.operation_progress.emit(operation, len(spheres_items) + len(sections_items), total_items or 1, f"Вставка категорий: {len(categories_items)}")
                    for x in categories_items:
                        x["section_id"] = section_ref_to_id.get(x["section_ref"])  # гарантируем FK
                    categories_with_id = [x for x in categories_items if x.get("id")]
                    categories_no_id = [x for x in categories_items if not x.get("id")]

                    if categories_with_id:
                        self.db.connection.executemany(
                            "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            [
                                (
                                    int(x["id"]),
                                    x.get("name", ""),
                                    int(x.get("section_id")),
                                    x.get("icon_path", ""),
                                    int(x.get("position", 0)),
                                )
                                for x in categories_with_id
                            ],
                        )

                    category_ref_to_id: Dict[int, int] = {}
                    for x in categories_with_id:
                        category_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
                    for x in categories_no_id:
                        cur = self.db.connection.execute(
                            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                            (
                                x.get("name", ""),
                                int(x.get("section_id")),
                                x.get("icon_path", ""),
                                int(x.get("position", 0)),
                            ),
                        )
                        category_ref_to_id[x["ref"]] = int(cur.lastrowid)

                    # 4) Ссылки
                    total_links = len(links_with_id) + len(links_without_id)
                    self.db.operation_progress.emit(operation, len(spheres_items) + len(sections_items) + len(categories_items), total_items or 1, f"Вставка ссылок: {total_links}")
                    # Проставим фактические category_id из карты
                    for link in links_with_id:
                        if not link.get("category_id"):
                            cref = link.get("_category_ref")
                            if cref is not None:
                                link["category_id"] = category_ref_to_id.get(cref)
                        link.pop("_category_ref", None)
                    for link in links_without_id:
                        if not link.get("category_id"):
                            cref = link.get("_category_ref")
                            if cref is not None:
                                link["category_id"] = category_ref_to_id.get(cref)
                        link.pop("_category_ref", None)

                    if links_with_id:
                        cols = [
                            "id",
                            "category_id",
                            "name",
                            "url",
                            "type",
                            "notes",
                            "is_favorite",
                            "last_used",
                            "icon_path",
                            "args",
                            "browser_key",
                            "position",
                        ]
                        placeholders = ",".join(["?"] * len(cols))
                        sql = f"INSERT INTO link ({', '.join(cols)}) VALUES ({placeholders})"
                        self.db.connection.executemany(
                            sql,
                            [
                                (
                                    int(link.get("id")),
                                    int(link.get("category_id")),
                                    link.get("name", ""),
                                    link.get("url", ""),
                                    link.get("type", "web"),
                                    link.get("notes", ""),
                                    int(link.get("is_favorite", 0) or 0),
                                    link.get("last_used"),
                                    link.get("icon_path", ""),
                                    link.get("args", ""),
                                    link.get("browser_key"),
                                    int(link.get("position", 0)),
                                )
                                for link in links_with_id
                            ],
                        )

                    # Уважаем согласованный хотфикс: поштучные INSERT для ссылок без id
                    if links_without_id:
                        cols = [
                            "category_id",
                            "name",
                            "url",
                            "type",
                            "notes",
                            "is_favorite",
                            "last_used",
                            "icon_path",
                            "args",
                            "browser_key",
                            "position",
                        ]
                        placeholders = ", ".join(["?"] * len(cols))
                        sql = f"INSERT INTO link ({', '.join(cols)}) VALUES ({placeholders})"
                        for link in links_without_id:
                            self.db.connection.execute(
                                sql,
                                (
                                    int(link.get("category_id")),
                                    link.get("name", ""),
                                    link.get("url", ""),
                                    link.get("type", "web"),
                                    link.get("notes", ""),
                                    int(link.get("is_favorite", 0) or 0),
                                    link.get("last_used"),
                                    link.get("icon_path", ""),
                                    link.get("args", ""),
                                    link.get("browser_key"),
                                    int(link.get("position", 0)),
                                ),
                            )

            t1 = time.perf_counter()
            logger.info(
                "import_full_structure: spheres=%d (with_id=%d, no_id=%d), sections=%d (with_id=%d, no_id=%d), categories=%d (with_id=%d, no_id=%d), links=%d (with_id=%d, no_id=%d), total_ms=%.2f",
                len(spheres_items),
                sum(1 for x in spheres_items if x.get('id')),
                sum(1 for x in spheres_items if not x.get('id')),
                len(sections_items),
                sum(1 for x in sections_items if x.get('id')),
                sum(1 for x in sections_items if not x.get('id')),
                len(categories_items),
                sum(1 for x in categories_items if x.get('id')),
                sum(1 for x in categories_items if not x.get('id')),
                len(links_with_id) + len(links_without_id),
                len(links_with_id),
                len(links_without_id),
                (t1 - t0) * 1000.0,
            )

            self.db.operation_finished.emit(operation, True)
            
            # Создаем резервную копию асинхронно после большой операции импорта
            try:
                self.db.backup_async(
                    on_error=lambda e, tb: logger.warning(
                        "Не удалось создать резервную копию после импорта: %s", e
                    )
                )
            except Exception as backup_err:
                logger.warning(
                    "Не удалось запустить резервное копирование после импорта: %s",
                    backup_err,
                    exc_info=True,
                )
            
            # Уведомляем UI об успешном импорте структуры
            try:
                self.db.structure_loaded.emit()
            except Exception as signal_err:
                logger.debug(
                    "Ошибка отправки сигнала structure_loaded: %s",
                    signal_err,
                    exc_info=True,
                )
        except Exception as e:
            logger.error("Ошибка импорта структуры: %s", e, exc_info=True)
            self.db.operation_finished.emit(operation, False)
            try:
                self.db.error_occurred.emit("Ошибка импорта", str(e))
            except Exception:
                pass
            raise DatabaseError(f"Не удалось импортировать структуру: {e}")
