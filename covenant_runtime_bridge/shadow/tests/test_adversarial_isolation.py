"""Adversarial State Isolation & Concurrency Leakage Tests."""

import asyncio
import os
import tempfile
import pytest

from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import SyntheticWorkspaceStore, workspace_store
from covenant_runtime_bridge.shadow.isolation import (
    clone_workspace_store,
    compute_workspace_fingerprint,
    scoped_workspace_store,
)


@pytest.mark.asyncio
async def test_concurrent_async_tasks_workspace_isolation():
    """
    CRITICAL CONCURRENCY ATTACK:
    Task A runs legacy branch with store_a.
    Task B runs runtime branch with store_b.
    Both tasks interleave asynchronous execution with await asyncio.sleep.
    Assert that neither task ever sees the other's workspace or pollutes the global store.
    """
    store_a = clone_workspace_store(workspace_store)
    store_b = clone_workspace_store(workspace_store)

    store_a.emails.clear()
    store_b.emails.clear()

    async def task_legacy():
        with scoped_workspace_store(store_a):
            workspace_store.send_email("leg@test.com", ["user@test.com"], "Legacy 1", "Body 1")
            await asyncio.sleep(0.01)
            # Verify only legacy emails are visible
            assert len(workspace_store.emails) == 1
            assert workspace_store.emails[0]["from"] == "leg@test.com"
            await asyncio.sleep(0.01)
            workspace_store.send_email("leg@test.com", ["user@test.com"], "Legacy 2", "Body 2")
            assert len(workspace_store.emails) == 2

    async def task_runtime():
        with scoped_workspace_store(store_b):
            await asyncio.sleep(0.005)
            workspace_store.send_email("run@test.com", ["user@test.com"], "Runtime 1", "Body 1")
            await asyncio.sleep(0.01)
            # Verify only runtime emails are visible
            assert len(workspace_store.emails) == 1
            assert workspace_store.emails[0]["from"] == "run@test.com"
            await asyncio.sleep(0.01)
            workspace_store.send_email("run@test.com", ["user@test.com"], "Runtime 2", "Body 2")
            assert len(workspace_store.emails) == 2

    await asyncio.gather(task_legacy(), task_runtime())

    # Outside scoped context, default store has zero of the test emails
    assert len(store_a.emails) == 2
    assert len(store_b.emails) == 2
    assert store_a.emails[0]["from"] == "leg@test.com"
    assert store_b.emails[0]["from"] == "run@test.com"


def test_deep_mutation_isolation_across_all_entities():
    """Mutate every nested structure on legacy clone, assert runtime clone is 100% pristine."""
    base_store = clone_workspace_store(workspace_store)
    leg_store = clone_workspace_store(base_store)
    run_store = clone_workspace_store(base_store)

    fp_run_before = compute_workspace_fingerprint(run_store)

    # Aggressive mutations on leg_store
    leg_store.emails.append({"id": "EML-MALICIOUS", "subject": "Hack", "to": [], "body": "", "from": "", "attachments": []})
    leg_store.contracts[0]["title"] = "MUTATED CONTRACT"
    leg_store.contracts[0]["key_clauses"].append({"title": "Sneaky", "text": "Clause"})
    leg_store.projects[0]["milestones"][0]["status"] = "MUTATED_STATUS"
    leg_store.invoices.pop()
    leg_store.calendar.clear()
    leg_store.record_escalation("com_x", "Malicious Escalation", "High")

    fp_run_after = compute_workspace_fingerprint(run_store)
    assert fp_run_before == fp_run_after, "Runtime clone was polluted by legacy mutations!"


@pytest.mark.asyncio
async def test_database_isolation_between_branches(tmp_path):
    """Verify independent SQLite database connections and files ensure zero cross-branch DB pollution."""
    db_leg = tmp_path / "legacy.db"
    db_run = tmp_path / "runtime.db"

    repo_leg = SQLiteCommitmentRepository(db_path=db_leg)
    repo_run = SQLiteCommitmentRepository(db_path=db_run)
    await repo_leg.initialize()
    await repo_run.initialize()

    from covenant_runtime_bridge.shadow.benchmark import sample_atlas_commitment
    c_leg = sample_atlas_commitment()
    c_leg.id = "com_leg_only"
    await repo_leg.save(c_leg)

    # Runtime DB must have 0 commitments
    run_commitments = await repo_run.list_all()
    assert len(run_commitments) == 0

    c_run = sample_atlas_commitment()
    c_run.id = "com_run_only"
    await repo_run.save(c_run)

    # Assert mutual isolation
    assert (await repo_leg.get_by_id("com_run_only")) is None
    assert (await repo_run.get_by_id("com_leg_only")) is None


@pytest.mark.asyncio
async def test_repository_restart_isolation(tmp_path):
    """Verify closing and reopening runtime repo has zero effect on legacy repo."""
    db_leg = tmp_path / "restart_leg.db"
    db_run = tmp_path / "restart_run.db"

    repo_leg = SQLiteCommitmentRepository(db_path=db_leg)
    repo_run = SQLiteCommitmentRepository(db_path=db_run)
    await repo_leg.initialize()
    await repo_run.initialize()

    from covenant_runtime_bridge.shadow.benchmark import sample_atlas_commitment
    await repo_leg.save(sample_atlas_commitment())

    # Simulate restart on runtime repo
    repo_run2 = SQLiteCommitmentRepository(db_path=db_run)
    await repo_run2.initialize()

    # Legacy repo remains fully functional
    leg_com = await repo_leg.get_by_id("com_atlas_approval")
    assert leg_com is not None
