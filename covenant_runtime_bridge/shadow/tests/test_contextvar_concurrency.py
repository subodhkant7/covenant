"""Section 9: ContextVar Concurrency, Thread Isolation, and Lifecycle Validation."""

import asyncio
import pytest

from covenant.synthetic_data.store import (
    SyntheticWorkspaceStore,
    _current_workspace_store,
    workspace_store,
)
from covenant_runtime_bridge.shadow.isolation import (
    clone_workspace_store,
    compute_workspace_fingerprint,
    scoped_workspace_store,
)


@pytest.mark.asyncio
async def test_asyncio_tasks_cross_task_isolation():
    """Verify concurrent async tasks interleaving execution never observe each other's workspace."""
    store_a = clone_workspace_store(workspace_store)
    store_b = clone_workspace_store(workspace_store)
    store_a.emails.clear()
    store_b.emails.clear()

    async def task_a():
        with scoped_workspace_store(store_a):
            workspace_store.send_email("task_a@covenant.local", ["recv@local"], "Subject A1", "Body A1")
            await asyncio.sleep(0.01)
            # Invariant: Only store_a emails visible
            assert len(workspace_store.emails) == 1
            assert workspace_store.emails[0]["from"] == "task_a@covenant.local"
            await asyncio.sleep(0.01)
            workspace_store.send_email("task_a@covenant.local", ["recv@local"], "Subject A2", "Body A2")
            assert len(workspace_store.emails) == 2

    async def task_b():
        with scoped_workspace_store(store_b):
            await asyncio.sleep(0.005)
            workspace_store.send_email("task_b@covenant.local", ["recv@local"], "Subject B1", "Body B1")
            await asyncio.sleep(0.01)
            # Invariant: Only store_b emails visible
            assert len(workspace_store.emails) == 1
            assert workspace_store.emails[0]["from"] == "task_b@covenant.local"
            await asyncio.sleep(0.01)
            workspace_store.send_email("task_b@covenant.local", ["recv@local"], "Subject B2", "Body B2")
            assert len(workspace_store.emails) == 2

    await asyncio.gather(task_a(), task_b())

    assert len(store_a.emails) == 2
    assert len(store_b.emails) == 2
    assert store_a.emails[0]["from"] == "task_a@covenant.local"
    assert store_b.emails[0]["from"] == "task_b@covenant.local"


@pytest.mark.asyncio
async def test_asyncio_to_thread_isolation():
    """Verify asyncio.to_thread worker threads inherit the active contextvar without cross-thread pollution."""
    store_a = clone_workspace_store(workspace_store)
    store_b = clone_workspace_store(workspace_store)
    store_a.emails.clear()
    store_b.emails.clear()

    def sync_thread_worker(worker_id: str):
        workspace_store.send_email(f"{worker_id}@covenant.local", ["recv@local"], f"Subject {worker_id}", "Body")
        return len(workspace_store.emails)

    async def runner_a():
        with scoped_workspace_store(store_a):
            res = await asyncio.to_thread(sync_thread_worker, "worker_a")
            assert res == 1
            assert workspace_store.emails[0]["from"] == "worker_a@covenant.local"

    async def runner_b():
        with scoped_workspace_store(store_b):
            res = await asyncio.to_thread(sync_thread_worker, "worker_b")
            assert res == 1
            assert workspace_store.emails[0]["from"] == "worker_b@covenant.local"

    await asyncio.gather(runner_a(), runner_b())

    assert len(store_a.emails) == 1
    assert len(store_b.emails) == 1
    assert store_a.emails[0]["from"] == "worker_a@covenant.local"
    assert store_b.emails[0]["from"] == "worker_b@covenant.local"


def test_nested_workspace_contexts():
    """Verify nested scoped_workspace_store properly pushes and pops context stacks."""
    store_outer = clone_workspace_store(workspace_store)
    store_inner = clone_workspace_store(workspace_store)
    store_outer.emails = [{"id": "OUTER"}]
    store_inner.emails = [{"id": "INNER"}]

    assert _current_workspace_store.get() is None

    with scoped_workspace_store(store_outer):
        assert workspace_store.emails[0]["id"] == "OUTER"
        with scoped_workspace_store(store_inner):
            assert workspace_store.emails[0]["id"] == "INNER"
        # Restores to outer
        assert workspace_store.emails[0]["id"] == "OUTER"

    # Restores to default
    assert _current_workspace_store.get() is None


def test_exception_exit_restoration():
    """Verify context token is cleanly reset when an exception is raised inside scoped context."""
    store = clone_workspace_store(workspace_store)
    assert _current_workspace_store.get() is None

    with pytest.raises(RuntimeError):
        with scoped_workspace_store(store):
            assert _current_workspace_store.get() is store
            raise RuntimeError("Deliberate failure inside context")

    assert _current_workspace_store.get() is None


@pytest.mark.asyncio
async def test_cancellation_restoration():
    """Verify context token is cleanly reset when an asyncio Task is cancelled."""
    store = clone_workspace_store(workspace_store)
    cancelled_observed = False

    async def long_running_task():
        with scoped_workspace_store(store):
            assert _current_workspace_store.get() is store
            await asyncio.sleep(5)

    task = asyncio.create_task(long_running_task())
    await asyncio.sleep(0.01)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        cancelled_observed = True

    assert cancelled_observed is True
    assert _current_workspace_store.get() is None


def test_thread_pool_executor_context_propagation():
    """
    SECTION 15: ThreadPoolExecutor Context Propagation Validation.
    Proves:
    1. Unpropagated executor.submit() does NOT inherit the active contextvar (falls back to default store).
    2. Explicit contextvars.copy_context().run() safely inherits the scoped isolated workspace.
    """
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    isolated_store = clone_workspace_store(workspace_store)
    isolated_store.emails = [{"id": "EML_THREAD_ISOLATED", "from": "isolated@northstar.local"}]

    def inspect_workspace_emails():
        return workspace_store.emails

    with scoped_workspace_store(isolated_store):
        with ThreadPoolExecutor(max_workers=2) as executor:
            # 1. Unpropagated execution -> observes default global store
            f_unprop = executor.submit(inspect_workspace_emails)
            emails_unprop = f_unprop.result()
            assert len(emails_unprop) != 1 or emails_unprop[0].get("id") != "EML_THREAD_ISOLATED"

            # 2. Propagated execution via contextvars.copy_context().run -> observes isolated store
            ctx = contextvars.copy_context()
            f_prop = executor.submit(ctx.run, inspect_workspace_emails)
            emails_prop = f_prop.result()
            assert len(emails_prop) == 1
            assert emails_prop[0]["id"] == "EML_THREAD_ISOLATED"
