"""Фоновые задачи: загрузка данных, предпросмотр и генерация не блокируют интерфейс."""

from __future__ import annotations

import logging
import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core import DocFlowError

log = logging.getLogger(__name__)


class TaskSignals(QObject):
    finished = Signal(int, object)  # id задачи, результат
    failed = Signal(int, str)  # id задачи, сообщение для пользователя
    progress = Signal(int, int, int)  # id задачи, сделано, всего


class Task(QRunnable):
    def __init__(self, task_id: int, fn: Callable[..., Any], *args, with_progress: bool = False,
                 **kwargs):
        super().__init__()
        self.task_id = task_id
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = TaskSignals()
        self.cancel_event = threading.Event()
        if with_progress:
            self.kwargs["progress"] = lambda done, total: self.signals.progress.emit(
                self.task_id, done, total)
            self.kwargs["should_cancel"] = self.cancel_event.is_set
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except DocFlowError as exc:
            self.signals.failed.emit(self.task_id, str(exc))
        except Exception:  # noqa: BLE001 — показываем понятную ошибку вместо падения
            log.error("Ошибка фоновой задачи:\n%s", traceback.format_exc(limit=3))
            self.signals.failed.emit(self.task_id, "Непредвиденная ошибка. Подробности в журнале.")
        else:
            self.signals.finished.emit(self.task_id, result)


class TaskRunner(QObject):
    """Запускает задачи в пулах потоков.

    Держит ссылки на задачи до прихода сигнала о завершении: иначе Python
    удалит объект сигналов раньше, чем Qt доставит результат в интерфейс.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self._next = 0
        self._active: set[Task] = set()

    def start(self, fn, *args, on_done=None, on_error=None, on_progress=None,
              with_progress: bool = False, pool: QThreadPool | None = None, **kwargs) -> Task:
        self._next += 1
        task = Task(self._next, fn, *args, with_progress=with_progress, **kwargs)
        if on_done:
            task.signals.finished.connect(on_done)
        if on_error:
            task.signals.failed.connect(on_error)
        if on_progress:
            task.signals.progress.connect(on_progress)
        self._active.add(task)
        task.signals.finished.connect(lambda *_: self._active.discard(task))
        task.signals.failed.connect(lambda *_: self._active.discard(task))
        (pool or self.pool).start(task)
        return task
