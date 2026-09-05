"""End-to-End Lifecycle Test for Covenant Agent Pipeline."""

from pathlib import Path
import pytest

from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import ActionStatus, CommitmentStatus
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.tools import initialize_tools


@pytest.mark.asyncio
async def test_full_commitment_resolution_lifecycle(tmp_path: Path):
    """
    Simulates the full agentic lifecycle:
    Discovery -> Overdue -> Evidence Corroboration -> Action Proposal -> Policy Review -> Human Approval -> Verification -> Resolved
    """
    db_file = tmp_path / "lifecycle_e2e.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)

    # 1. Run Supervisor initial scan cycle
    scan_res = await supervisor.run(AgentContext(session_id="e2e_session_1"))
    assert scan_res.success is True

    # 2. Check that Project Atlas commitment was discovered and evaluated
    atlas_com = await repo.get_by_id("com_atlas_approval")
    assert atlas_com is not None
    assert atlas_com.status == CommitmentStatus.AWAITING_APPROVAL
    assert atlas_com.next_action is not None
    assert atlas_com.next_action.requires_human_approval is True

    # 3. Simulate Human Approval on Decision Surface
    action = atlas_com.next_action
    action.status = ActionStatus.APPROVED

    CommitmentStateMachine.transition(
        commitment=atlas_com,
        target_state=CommitmentStatus.EXECUTING,
        agent_name="HumanUser",
        reason="Human approved follow-up email.",
        approved_by="Alex North",
    )

    # Simulate outbound dispatch
    action.status = ActionStatus.COMPLETED

    CommitmentStateMachine.transition(
        commitment=atlas_com,
        target_state=CommitmentStatus.VERIFYING,
        agent_name="System",
        reason="Action executed; entering verification stage.",
    )
    await repo.save(atlas_com)

    # 4. Trigger Verification Agent pass with confirmed signed approval
    verif_res = await supervisor.verify_commitment(
        "com_atlas_approval",
        simulated_params={"simulated_signed_approval": True},
    )
    assert verif_res.success is True

    # 5. Check final state is RESOLVED with resolution timestamp
    final_com = await repo.get_by_id("com_atlas_approval")
    assert final_com is not None
    assert final_com.status == CommitmentStatus.RESOLVED
    assert final_com.resolution_timestamp is not None
    assert final_com.verification_result is not None
    assert final_com.verification_result.is_verified is True
