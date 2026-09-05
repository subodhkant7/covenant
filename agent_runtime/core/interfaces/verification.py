"""Verification interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict
from agent_runtime.core.contracts.verification import VerificationRequest, VerificationResult


class IVerifier(ABC):
    """Independent outcome verifier."""

    @abstractmethod
    async def verify(self, request: VerificationRequest, context: Dict[str, Any]) -> VerificationResult:
        """Performs independent verification and corroborates outcome."""
        pass
