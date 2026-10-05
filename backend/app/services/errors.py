"""Workflow errors raised by services and turned into HTTP responses in app.main.
Messages are safe to show to the user."""


class WorkflowError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(WorkflowError):
    status_code = 404


class PermissionDeniedError(WorkflowError):
    status_code = 403


class ConflictError(WorkflowError):
    status_code = 409


class InvalidRequestError(WorkflowError):
    status_code = 422


class ConfigurationError(WorkflowError):
    """Required configuration (TAT rules, escalation rules, model) is missing."""

    status_code = 503
