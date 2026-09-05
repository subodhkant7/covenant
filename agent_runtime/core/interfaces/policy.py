"""Policy rule and engine interfaces."""

from abc import ABC, abstractmethod
from typing import Optional
from agent_runtime.core.contracts.policy import PolicyDecision, PolicyEvaluationContext


class IPolicyRule(ABC):
    """Individual policy rule."""
    rule_id: str
    description: str

    @abstractmethod
    def evaluate(self, context: PolicyEvaluationContext) -> Optional[PolicyDecision]:
        """Evaluates rule against context; returns PolicyDecision if rule triggers, else None."""
        pass


class IPolicyEngine(ABC):
    """Central policy engine evaluating authorization decisions."""

    @abstractmethod
    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        """Evaluates all rules against context and produces authoritative PolicyDecision."""
        pass
