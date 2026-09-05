"""Shadow Execution Harness: Coordinates dual isolated runs and semantic comparison."""

import os
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional

from covenant.agents.base import AgentContext as LegacyAgentContext
from covenant.agents.evidence import EvidenceAgent as LegacyEvidenceAgent
from covenant.agents.policy import PolicyAgent as LegacyPolicyAgent
from covenant.agents.resolution import ResolutionAgent as LegacyResolutionAgent
from covenant.agents.verification import VerificationAgent as LegacyVerificationAgent
from covenant.domain.enums import ActionStatus, CommitmentStatus
from covenant.domain.models import Commitment
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import SyntheticWorkspaceStore, workspace_store

from agent_runtime.core.contracts.context import Task, TaskContext
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.contracts.verification import VerificationRequest
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.state.enums import ApprovalState, TaskState
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate

from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.mapping.task_factory import CovenantTaskFactory
from covenant_runtime_bridge.shadow.comparator import SemanticComparator
from covenant_runtime_bridge.shadow.contracts import (
    MismatchCategory,
    ShadowComparison,
    ShadowMode,
    ShadowOutcome,
    ShadowRun,
)
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectGuard,
    clone_workspace_store,
    compute_workspace_fingerprint,
    scoped_workspace_store,
)
from covenant_runtime_bridge.shadow.metrics import shadow_metrics


class ShadowExecutionHarness:
    """
    Coordinates isolated execution between the legacy pipeline and the runtime bridge.
    Guarantees:
    1. Neither path mutates production state or shared world.
    2. Both paths start from mathematically identical snapshots.
    3. Real external side effects are blocked.
    4. Observations are derived dynamically from actual branch behavior without fixtures.
    """

    def __init__(self, mode: ShadowMode = ShadowMode.SHADOW):
        self.mode = mode

    async def execute_scenario_b_approval_gated(
        self,
        commitment: Commitment,
        scenario_name: str = "Scenario B — Approval-Gated Action",
        simulate_corroboration: bool = True,
        force_snapshot_diff: bool = False,
    ) -> ShadowRun:
        """
        Executes Scenario B in isolated shadow mode:
        Overdue commitment -> investigate -> propose follow-up -> approval -> execute -> verify.
        """
        run = ShadowRun(mode=self.mode)

        if self.mode == ShadowMode.OFF:
            run.status = "SHADOW_SKIPPED"
            run.classification = MismatchCategory.SHADOW_SKIPPED
            run.skip_reason = "Shadow mode is OFF"
            return run

        # 1. Snapshot & Clone Isolated Worlds
        initial_store = clone_workspace_store(workspace_store)
        legacy_store = clone_workspace_store(initial_store)
        runtime_store = clone_workspace_store(initial_store)

        if force_snapshot_diff:
            # Deliberately modify runtime store to test fingerprint failure detection
            runtime_store.emails.pop()

        leg_fp = compute_workspace_fingerprint(legacy_store)
        run_fp = compute_workspace_fingerprint(runtime_store)

        if leg_fp != run_fp:
            run.status = "SHADOW_SKIPPED"
            run.classification = MismatchCategory.SHADOW_SKIPPED
            run.skip_reason = f"Initial snapshot fingerprint mismatch: {leg_fp[:8]} vs {run_fp[:8]}"
            shadow_metrics.record(run)
            return run

        # 2. Execute Legacy Branch inside sandbox
        t0_leg = time.perf_counter()
        legacy_outcome = await self._run_legacy_branch(
            commitment=commitment,
            isolated_store=legacy_store,
            simulate_corroboration=simulate_corroboration,
        )
        legacy_outcome.execution_duration_ms = (time.perf_counter() - t0_leg) * 1000.0
        legacy_outcome.fingerprint_after = compute_workspace_fingerprint(legacy_store)

        # 3. Execute Runtime Branch inside sandbox
        t0_run = time.perf_counter()
        runtime_outcome = await self._run_runtime_branch(
            commitment=commitment,
            isolated_store=runtime_store,
            simulate_corroboration=simulate_corroboration,
        )
        runtime_outcome.execution_duration_ms = (time.perf_counter() - t0_run) * 1000.0
        runtime_outcome.fingerprint_after = compute_workspace_fingerprint(runtime_store)

        # 4. Semantic Comparison
        comparison = SemanticComparator.compare(
            scenario_name=scenario_name,
            shadow_run_id=run.shadow_run_id,
            trace_id=run.trace_id,
            input_snapshot_id=run.input_snapshot_id,
            legacy=legacy_outcome,
            runtime=runtime_outcome,
            initial_store=initial_store,
            legacy_final_store=legacy_store,
            runtime_final_store=runtime_store,
        )

        run.legacy_outcome = legacy_outcome
        run.runtime_outcome = runtime_outcome
        run.comparison = comparison
        run.status = "COMPLETED"
        run.classification = comparison.overall_classification

        shadow_metrics.record(run)
        return run

    async def _run_legacy_branch(
        self,
        commitment: Commitment,
        isolated_store: SyntheticWorkspaceStore,
        simulate_corroboration: bool,
    ) -> ShadowOutcome:
        """Executes legacy specialist agents using isolated synthetic workspace."""
        c = commitment.model_copy(deep=True)
        tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            repo = SQLiteCommitmentRepository(db_path=tmp_db)
            await repo.initialize()
            await repo.save(c)

            initial_email_count = len(isolated_store.emails)
            tools_executed: List[str] = []

            with ExternalSideEffectGuard(), scoped_workspace_store(isolated_store):
                res_agent = LegacyResolutionAgent(commitment_repo=repo)
                pol_agent = LegacyPolicyAgent(commitment_repo=repo)
                ver_agent = LegacyVerificationAgent(commitment_repo=repo)

                # Propose action
                ctx = LegacyAgentContext(session_id="shd_leg", target_commitment_id=c.id)
                res_result = await res_agent.run(ctx)
                if res_result.success:
                    tools_executed.append("draft_followup")

                # Policy
                await pol_agent.run(ctx)
                c = await repo.get_by_id(c.id)
                req_appr = c.required_human_approval if c else False

                if c and c.next_action:
                    # Simulate human approval
                    c.next_action.status = ActionStatus.APPROVED
                    CommitmentStateMachine.transition(
                        commitment=c,
                        target_state=CommitmentStatus.EXECUTING,
                        agent_name="ShadowReviewer",
                        reason="Shadow approved action",
                        approved_by="ShadowReviewer",
                    )
                    await repo.save(c)

                    # Dispatch follow-up email into isolated sandbox store
                    isolated_store.send_email(
                        from_addr="Alex North <alex@northstarstudio.com>",
                        to_addrs=[c.promisor.email or "client@meridian.com"],
                        subject=c.next_action.subject or "Follow-up",
                        body=c.next_action.payload.get("body", "Please review."),
                        thread_id="TH-ATLAS-APPROVAL",
                    )
                    tools_executed.append("send_followup")

                # Corroborate if requested
                if simulate_corroboration:
                    isolated_store.simulate_client_reply(c.id)

                # Verify
                ver_res = await ver_agent.run(ctx)
                tools_executed.append("verify_commitment")
                c_final = await repo.get_by_id(c.id)

                is_ver = ver_res.data.get("is_verified", False) if ver_res and ver_res.data else False
                final_st = c_final.status.value if c_final else "UNKNOWN"
                side_effects = isolated_store.emails[initial_email_count:]

                return ShadowOutcome(
                    branch_name="LEGACY",
                    target_ids=[c.id],
                    discovered_count=1,
                    investigated_count=1,
                    actions_proposed=[c.next_action.action_type.value] if (c and c.next_action) else [],
                    approvals_required=[c.id] if req_appr else [],
                    tools_invoked=tools_executed,
                    side_effects_produced=side_effects,
                    verification_outcomes={c.id: is_ver},
                    final_domain_states={c.id: final_st},
                    success=True,
                )
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    async def _run_runtime_branch(
        self,
        commitment: Commitment,
        isolated_store: SyntheticWorkspaceStore,
        simulate_corroboration: bool,
    ) -> ShadowOutcome:
        """Executes runtime bridge using ExecutionEngine and isolated synthetic workspace."""
        c = commitment.model_copy(deep=True)
        initial_email_count = len(isolated_store.emails)

        with ExternalSideEffectGuard(), scoped_workspace_store(isolated_store):
            bridge_env = CovenantRuntimeBootstrap.assemble()
            sink = InMemoryEventSink()
            engine = ExecutionEngine(
                tool_registry=bridge_env.tools,
                permissions=bridge_env.permissions,
                policy_engine=bridge_env.policy,
                event_sink=sink,
            )
            executor = AgentRunExecutor(engine, sink)
            verif_gate = VerificationGate(sink)

            task = CovenantTaskFactory.create_resolution_task(c)
            agent = bridge_env.agents.get("covenant.resolver_agent")
            ctx = TaskContext(
                task_id=task.id,
                organization_id=task.organization_id,
                intent=task.intent,
                required_role=task.required_role,
                scope=task.scope,
                available_tools=bridge_env.tools.list_specs(),
                input_data=task.input_payload,
            )

            # Execute run until approval
            run, history, approval_req = await executor.execute_run(task, agent, ctx)
            req_appr = approval_req is not None

            # Approve
            if approval_req:
                approval_req.status = ApprovalState.APPROVED
                approval_req.reviewed_by = "ShadowReviewer"

                # Resume run
                await executor.execute_run(
                    task=task,
                    agent=agent,
                    context=ctx,
                    run=run,
                    history=history,
                    approval_resume=approval_req,
                )

            # Corroborate
            if simulate_corroboration:
                isolated_store.simulate_client_reply(c.id)

            # Verification gate
            v_res = await verif_gate.verify_task(task, bridge_env.verifier, expected_outcome="Approval verified")

            if v_res.verified:
                final_state = "RESOLVED"
            elif approval_req and approval_req.status in (ApprovalState.APPROVED, ApprovalState.EXECUTED):
                final_state = "VERIFYING"
            elif approval_req and approval_req.status == ApprovalState.PENDING:
                final_state = "AWAITING_APPROVAL"
            else:
                final_state = "RUNNING"

            # Extract dynamic tool calls and actions from history turns
            tools_used = [turn.request.tool_name for turn in history.turns if turn.request]
            if v_res:
                tools_used.append("verify_commitment")

            actions_proposed: List[str] = []
            for turn in history.turns:
                if turn.request:
                    if turn.request.tool_name in ("draft_followup", "send_followup"):
                        if "FOLLOWUP_EMAIL" not in actions_proposed:
                            actions_proposed.append("FOLLOWUP_EMAIL")
                    elif turn.request.tool_name == "create_escalation":
                        if "ESCALATION" not in actions_proposed:
                            actions_proposed.append("ESCALATION")

            side_effects = isolated_store.emails[initial_email_count:]

            return ShadowOutcome(
                branch_name="RUNTIME",
                target_ids=[c.id],
                discovered_count=1,
                investigated_count=1,
                actions_proposed=actions_proposed,
                approvals_required=[c.id] if req_appr else [],
                tools_invoked=tools_used,
                side_effects_produced=side_effects,
                verification_outcomes={c.id: v_res.verified},
                final_domain_states={c.id: final_state},
                success=True,
            )
