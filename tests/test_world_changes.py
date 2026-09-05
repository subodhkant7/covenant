"""Tests verifying executable action dispatch and world changes simulation."""

from pathlib import Path
import pytest

from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import ActionStatus, CommitmentStatus
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools


@pytest.fixture
async def setup_env(tmp_path: Path):
    db_file = tmp_path / "world_changes_test.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)
    workspace_store.reset()
    return repo, supervisor, tools


@pytest.mark.asyncio
async def test_action_dispatch_and_world_changes(setup_env):
    """
    Validates:
    1. Action execution actually creates outbound email in workspace.
    2. Before reply, VerificationAgent confirms ACTION_SUCCEEDED but BUSINESS_OUTCOME_NOT_YET_VERIFIED.
    3. External client reply is simulated.
    4. Independent VerificationAgent re-queries workspace, finds new signed approval email, and closes commitment.
    """
    repo, supervisor, tools = setup_env

    # 1. Discover commitments
    await supervisor.run(AgentContext(session_id="init_scan"))
    atlas_com = await repo.get_by_id("com_atlas_approval")
    assert atlas_com is not None
    assert atlas_com.status == CommitmentStatus.AWAITING_APPROVAL

    # 2. Authorize action
    action = atlas_com.next_action
    action.status = ActionStatus.APPROVED

    CommitmentStateMachine.transition(
        commitment=atlas_com,
        target_state=CommitmentStatus.EXECUTING,
        agent_name="HumanUser",
        reason="Human approved follow-up email.",
        approved_by="Alex North",
    )

    # 3. Actually dispatch follow-up via tool
    send_tool = tools.get("send_followup")
    dispatch_res = await send_tool.execute(
        commitment_id=atlas_com.id,
        recipient_email=action.recipient or "sjenkins@meridianglobal.com",
        subject=action.subject or "Follow-up",
        body=action.payload.get("body", "Please review"),
    )
    assert dispatch_res.success is True
    assert dispatch_res.data["action_succeeded"] is True

    # Check that email was genuinely added to workspace
    sent_emails = [e for e in workspace_store.emails if "EML-OUT" in e["id"]]
    assert len(sent_emails) == 1

    # Transition to VERIFYING (awaiting client response)
    CommitmentStateMachine.transition(
        commitment=atlas_com,
        target_state=CommitmentStatus.VERIFYING,
        agent_name="System",
        reason="Follow-up dispatched. Awaiting client response.",
    )
    await repo.save(atlas_com)

    # 4. First verification pass (no client response yet)
    verif_res_1 = await supervisor.verify_commitment("com_atlas_approval")
    assert verif_res_1.data["action_succeeded"] is True
    assert verif_res_1.data["business_outcome_verified"] is False
    # Status must NOT be resolved
    assert verif_res_1.data["status"] == CommitmentStatus.VERIFYING.value

    # 5. External World Changes: Sarah Jenkins sends signed approval
    reply = workspace_store.simulate_client_reply("com_atlas_approval")
    assert reply is not None
    assert "Signed_Atlas_Phase2_Signoff.pdf" in reply["attachments"]

    # 6. Second verification pass (now finds the signed response email)
    verif_res_2 = await supervisor.verify_commitment("com_atlas_approval")
    assert verif_res_2.data["business_outcome_verified"] is True
    assert verif_res_2.data["status"] == CommitmentStatus.RESOLVED.value

    # Check final state in SQLite
    final_com = await repo.get_by_id("com_atlas_approval")
    assert final_com.status == CommitmentStatus.RESOLVED
    assert final_com.resolution_timestamp is not None
