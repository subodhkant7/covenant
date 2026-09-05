"""Autonomous Background Monitor Service for Covenant with Safe Shadow Execution Support."""

import asyncio
import logging
from typing import Any, Optional
from uuid import uuid4

from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import CommitmentStatus
from covenant.persistence.repository import AbstractCommitmentRepository, AbstractEventRepository

logger = logging.getLogger(__name__)


class BackgroundMonitor:
    """
    Autonomous background service that continuously monitors commitment health,
    detects drift, runs specialist investigations, and verifies outcomes.
    Supports development-only SHADOW execution mode alongside authoritative legacy runs.
    """

    def __init__(
        self,
        supervisor: SupervisorAgent,
        commitment_repo: AbstractCommitmentRepository,
        event_repo: AbstractEventRepository,
        interval_seconds: int = 15,
        shadow_mode: str = "LEGACY",  # "OFF", "LEGACY", or "SHADOW"
        shadow_harness: Optional[Any] = None,
    ):
        self.supervisor = supervisor
        self.commitment_repo = commitment_repo
        self.event_repo = event_repo
        self.interval_seconds = interval_seconds
        self.shadow_mode = shadow_mode.upper()
        self.shadow_harness = shadow_harness
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.cycle_count = 0
        self.shadow_runs_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the background monitor task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Covenant BackgroundMonitor started (interval: {self.interval_seconds}s, mode: {self.shadow_mode}).")

    async def stop(self) -> None:
        """Gracefully stop the background monitor task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Covenant BackgroundMonitor stopped.")

    async def _monitor_loop(self) -> None:
        """Internal asynchronous polling loop."""
        while self._running:
            try:
                await self.scan_cycle()
            except Exception as e:
                logger.error(f"Error in BackgroundMonitor cycle: {e}", exc_info=True)
            await asyncio.sleep(self.interval_seconds)

    async def scan_cycle(self) -> int:
        """
        Execute an autonomous evaluation pass across all active commitments.
        Returns the number of commitments evaluated.
        """
        self.cycle_count += 1
        workflow_id = f"wkfl_{uuid4().hex[:8]}"

        # Load all active commitments
        commitments = await self.commitment_repo.list_all(limit=500)
        evaluated_count = 0

        for c in commitments:
            # Skip closed commitments
            if c.status in [CommitmentStatus.RESOLVED, CommitmentStatus.CANCELLED, CommitmentStatus.REJECTED]:
                continue

            evaluated_count += 1
            ctx = AgentContext(session_id=workflow_id, target_commitment_id=c.id)

            # Scenario A: Exceeded deadline without resolution -> Transition to OVERDUE and investigate
            if c.is_overdue and c.status in [CommitmentStatus.ACTIVE, CommitmentStatus.WAITING, CommitmentStatus.DUE]:
                logger.info(f"BackgroundMonitor: Drift detected on commitment {c.id} ({c.title}). Exceeded due date.")
                c.status = CommitmentStatus.OVERDUE
                await self.commitment_repo.save(c)

                # Optional Development Shadow Run (Isolated & Non-authoritative)
                if self.shadow_mode == "SHADOW" and self.shadow_harness:
                    try:
                        await self.shadow_harness.execute_scenario_b_approval_gated(
                            commitment=c,
                            scenario_name="Monitor Live Shadow Run",
                        )
                        self.shadow_runs_count += 1
                    except Exception as shadow_err:
                        logger.warning(f"BackgroundMonitor: SHADOW_SKIPPED reason = {shadow_err}")

                # Authoritative Legacy Execution Pipeline
                await self.supervisor.evidence_agent.run(ctx)
                await self.supervisor.resolution_agent.run(ctx)
                await self.supervisor.policy_agent.run(ctx)

            # Scenario B: Commitment in VERIFYING state -> independently verify if response arrived
            elif c.status == CommitmentStatus.VERIFYING:
                logger.info(f"BackgroundMonitor: Checking independent verification for commitment {c.id}...")
                await self.supervisor.verification_agent.run(ctx)

            # Scenario C: Freshly discovered -> Activate
            elif c.status == CommitmentStatus.DISCOVERED:
                c.status = CommitmentStatus.ACTIVE
                await self.commitment_repo.save(c)

        return evaluated_count
