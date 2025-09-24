# app/controllers/business/pending_tasks_mixin.py
from threading import Lock

class PendingTasksMixin:
    """Миксин для управления pending_tasks с потокобезопасностью."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tasks_lock = Lock()
        self.pending_tasks = {}

    def _clear_pending_tasks(self):
        with self._tasks_lock:
            self.pending_tasks.clear()
