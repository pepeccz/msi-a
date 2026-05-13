"""
MSI Automotive — API service-layer custom exceptions.

These exceptions are raised by service classes and mapped to HTTP error codes
at the route boundary. They carry enough context to produce a useful error
response without leaking implementation details.

Exception → HTTP mapping (applied in the route layer):
  EscalationNotFoundError         → 404
  EscalationAlreadyAssignedError  → 409
  EscalationAlreadyResolvedError  → 409
  InvalidAssigneeError            → 422
  CaseNotFoundError               → 404
  CaseNotInPendingReviewError     → 400
  InvalidStateForUnassignError    → 409
"""


class EscalationNotFoundError(Exception):
    """Raised when an Escalation row cannot be found by ID."""

    def __init__(self, escalation_id: object) -> None:
        self.escalation_id = escalation_id
        super().__init__(f"Escalation {escalation_id} not found")


class EscalationAlreadyAssignedError(Exception):
    """
    Raised when an Escalation is already assigned to a different agent.

    This signals a 409 Conflict to callers. The route layer should advise the
    client to refresh and retry with current data.
    """

    def __init__(self, escalation_id: object, current_assignee_id: object | None = None) -> None:
        self.escalation_id = escalation_id
        self.current_assignee_id = current_assignee_id
        super().__init__(
            f"Escalation {escalation_id} is already assigned to {current_assignee_id}"
        )


class EscalationAlreadyResolvedError(Exception):
    """
    Raised when an operation that requires a non-resolved Escalation is
    attempted on one that is already resolved.
    """

    def __init__(self, escalation_id: object) -> None:
        self.escalation_id = escalation_id
        super().__init__(f"Escalation {escalation_id} is already resolved")


class InvalidAssigneeError(Exception):
    """
    Raised when the target assignee does not exist or is not active.

    Maps to HTTP 422 Unprocessable Entity since the request is structurally
    valid but references an invalid entity.
    """

    def __init__(self, assignee_user_id: object, reason: str = "not found or inactive") -> None:
        self.assignee_user_id = assignee_user_id
        self.reason = reason
        super().__init__(
            f"Invalid assignee {assignee_user_id}: {reason}"
        )


class InvalidStateForUnassignError(Exception):
    """
    Raised when unassign is attempted on an Escalation that is not currently
    in 'assigned' state (e.g. still pending or already resolved).

    Maps to HTTP 409 Conflict.
    """

    def __init__(self, escalation_id: object, current_status: str) -> None:
        self.escalation_id = escalation_id
        self.current_status = current_status
        super().__init__(
            f"Escalation {escalation_id} cannot be unassigned from status '{current_status}'"
        )


class CaseNotFoundError(Exception):
    """Raised when a Case row cannot be found by ID. Maps to HTTP 404."""

    def __init__(self, case_id: object) -> None:
        self.case_id = case_id
        super().__init__(f"Case {case_id} not found")


class CaseNotInPendingReviewError(Exception):
    """
    Raised when take_case_internal is called on a Case whose status is not
    'pending_review' (and not 'in_progress' for idempotency). Maps to HTTP 400.
    """

    def __init__(self, case_id: object, current_status: str) -> None:
        self.case_id = case_id
        self.current_status = current_status
        super().__init__(
            f"Case {case_id} cannot be taken from status '{current_status}'. "
            "Must be 'pending_review'."
        )
