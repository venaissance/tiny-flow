"""Dual ThreadPoolExecutor — scheduler + execution pools."""
from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ExecutorPool:
    """Dual-pool executor.

    Scheduler pool: orchestration, timeout management.
    Execution pool: actual task execution.
    Separated to avoid deadlock when scheduler waits on execution.
    """

    def __init__(self, scheduler_workers: int = 3, execution_workers: int = 3):
        self._scheduler = ThreadPoolExecutor(max_workers=scheduler_workers, thread_name_prefix="scheduler")
        self._executor = ThreadPoolExecutor(max_workers=execution_workers, thread_name_prefix="executor")
        self._active = True

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> Future:
        if not self._active:
            raise RuntimeError("Pool is shut down")
        return self._executor.submit(fn, *args, **kwargs)

    def submit_scheduled(self, fn: Callable, timeout: float, *args: Any, **kwargs: Any) -> Future:
        outer_future: Future = Future()

        def _schedule():
            exec_future = self._executor.submit(fn, *args, **kwargs)
            try:
                result = exec_future.result(timeout=timeout)
                outer_future.set_result(result)
            except TimeoutError:
                exec_future.cancel()
                outer_future.set_exception(TimeoutError(f"Task timed out after {timeout}s"))
            except Exception as e:
                outer_future.set_exception(e)

        self._scheduler.submit(_schedule)
        return outer_future

    def shutdown(self, wait: bool = True):
        self._active = False
        self._executor.shutdown(wait=wait)
        self._scheduler.shutdown(wait=wait)


_pool: ExecutorPool | None = None
_pool_lock = Lock()


def get_executor_pool() -> ExecutorPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ExecutorPool()
    return _pool


def reset_executor_pool():
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False)
        _pool = None
