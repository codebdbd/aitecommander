import builtins
import types

import pytest


class DummyDB:
    def __init__(self):
        # Достаточно наличия атрибута links для конструктора
        self.links = None


def test_pending_tasks_cleared_on_error(monkeypatch):
    # Импортируем после того, как подготовим monkeypatch точки
    from app.controllers.business import links_business as lb_mod

    # Подменяем run_db так, чтобы он сразу вызывал on_error и не выполнял _fetch
    def fake_run_db(func, description=None, on_finished=None, on_error=None):
        if on_error:
            # Имитируем ошибку воркера
            on_error(Exception("boom"))

    monkeypatch.setattr(lb_mod, "run_db", fake_run_db)

    # Создаем экземпляр бизнес-логики с фиктивной БД (она не используется в этом тесте)
    logic = lb_mod.LinksBusinessLogic(db=DummyDB())

    # До вызова задач нет
    assert len(logic.pending_tasks) == 0

    # Запускаем загрузку — задача должна добавиться, затем ошибка должна её удалить
    logic.load_links(123)

    # После ошибки задача должна быть очищена
    assert len(logic.pending_tasks) == 0


def test_worker_error_without_task_id_does_not_crash():
    from app.controllers.business.links_business import LinksBusinessLogic

    logic = LinksBusinessLogic(db=DummyDB())
    # Добавим фиктивный task_id и убедимся, что вызов без task_id не изменяет набор
    logic.pending_tasks.add(1)
    logic._on_worker_error("err without id")
    assert 1 in logic.pending_tasks
