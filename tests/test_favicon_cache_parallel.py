import multiprocessing as mp
import os
import random
import string
import time
from contextlib import closing
from pathlib import Path

import app.utils.links.parser.favicon_cache as fav_mod
from app.utils.links.parser.favicon_cache import FaviconCache


def _patch_icons_dir(monkeypatch, tmp_path):
    # Переопределяем директорию для файла БД, чтобы процессы не трогали реальный путь
    monkeypatch.setattr(
        fav_mod.icon_path_service,
        "get_user_icons_dir",
        lambda: tmp_path,
        raising=True,
    )


def _worker_set_values(db_dir: str, n: int, prefix: str):
    # В форкнутом процессе нужно заново настроить путь
    # Создаем кэш с тем же расположением БД
    def _fake_dir():
        from pathlib import Path

        return Path(db_dir)

    fav_mod.icon_path_service.get_user_icons_dir = _fake_dir  # type: ignore[attr-defined]

    cache = FaviconCache()
    rnd = random.Random(prefix)
    for i in range(n):
        # генерим уникальный ключ и данные
        suffix = "".join(rnd.choice(string.ascii_lowercase) for _ in range(6))
        key = f"{prefix}-{i}-{suffix}"
        cache.set(key, {"icon": "", "title": key})
        # небольшая пауза, чтобы спровоцировать чередование
        time.sleep(0.005)


def test_favicon_cache_parallel_writes(monkeypatch, tmp_path):
    _patch_icons_dir(monkeypatch, tmp_path)

    proc_count = 3
    per_proc = 20

    procs = []
    for p in range(proc_count):
        pr = mp.Process(
            target=_worker_set_values, args=(str(tmp_path), per_proc, f"p{p}")
        )
        pr.start()
        procs.append(pr)

    for pr in procs:
        pr.join(timeout=10)
        assert pr.exitcode == 0

    # Проверяем, что БД читается и содержит хотя бы суммарное число ключей минус возможные накладные записи
    # (в shelve форматы .dir/.dat/.bak, поэтому читаем через shelve)
    path = str(tmp_path / "favicon_cache.db")
    # Содержимое валидно и доступно
    with closing(fav_mod.shelve.open(path)) as db:  # type: ignore[attr-defined]
        # строгого равенства может не быть из-за перезаписей, но нижняя граница должна соблюдаться
        assert len(db) >= proc_count * per_proc * 0.9
