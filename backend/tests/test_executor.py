"""Tests for the dual-pool executor."""
import time
import pytest
from core.executor.pool import ExecutorPool, get_executor_pool, reset_executor_pool
from core.executor.task import TaskSpec, TaskResult, SubagentStatus


class TestTaskTypes:
    def test_task_spec_defaults(self):
        t = TaskSpec()
        assert t.type == "subagent"
        assert t.timeout == 300
        assert t.id.startswith("task_")

    def test_subagent_status_values(self):
        assert SubagentStatus.COMPLETED.value == "completed"
        assert SubagentStatus.TIMED_OUT.value == "timed_out"


class TestExecutorPool:
    def test_submit_and_collect(self):
        pool = ExecutorPool(scheduler_workers=2, execution_workers=2)
        def simple_task(desc: str) -> str:
            return f"done: {desc}"
        future = pool.submit(simple_task, "test-1")
        result = future.result(timeout=5)
        assert result == "done: test-1"
        pool.shutdown()

    def test_concurrent_submit(self):
        pool = ExecutorPool(scheduler_workers=2, execution_workers=2)
        def slow_task(n: int) -> int:
            time.sleep(0.1)
            return n * 2
        futures = [pool.submit(slow_task, i) for i in range(3)]
        results = [f.result(timeout=5) for f in futures]
        assert sorted(results) == [0, 2, 4]
        pool.shutdown()

    def test_timeout_handling(self):
        pool = ExecutorPool(scheduler_workers=1, execution_workers=1)
        def forever_task():
            time.sleep(100)
        future = pool.submit(forever_task)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        pool.shutdown(wait=False)

    def test_singleton(self):
        reset_executor_pool()
        p1 = get_executor_pool()
        p2 = get_executor_pool()
        assert p1 is p2
        reset_executor_pool()
