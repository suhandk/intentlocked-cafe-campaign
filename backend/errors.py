from uuid import uuid4

from backend.contracts import ErrorBody


class ProviderError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.body = ErrorBody(code=code, message=message, trace_id=uuid4().hex, retryable=retryable)
        super().__init__(message)
