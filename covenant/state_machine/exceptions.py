"""Exceptions for the Commitment State Machine."""


class StateMachineError(Exception):
    """Base class for state machine exceptions."""
    pass


class InvalidStateTransitionError(StateMachineError):
    """Raised when an illegal transition is attempted."""

    def __init__(self, current_state: str, target_state: str, reason: str = ""):
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason
        message = f"Illegal transition from {current_state} to {target_state}."
        if reason:
            message += f" Reason: {reason}"
        super().__init__(message)


class GuardConditionFailedError(StateMachineError):
    """Raised when a state transition guard condition fails."""
    pass
