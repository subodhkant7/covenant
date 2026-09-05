"""Exceptions for the runtime state machines."""


class StateMachineError(Exception):
    """Base class for all state machine errors."""
    pass


class InvalidStateTransitionError(StateMachineError):
    """Raised when an illegal transition is attempted."""

    def __init__(self, current_state: str, target_state: str, entity_type: str = "Entity", reason: str = ""):
        self.current_state = current_state
        self.target_state = target_state
        self.entity_type = entity_type
        self.reason = reason
        message = f"Illegal transition for {entity_type} from {current_state} to {target_state}."
        if reason:
            message += f" Reason: {reason}"
        super().__init__(message)


class GuardConditionFailedError(StateMachineError):
    """Raised when a pre-transition guard condition fails."""
    pass
