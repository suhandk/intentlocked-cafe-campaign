from contextvars import ContextVar

# Correlates calls without replacing the native comparison-run IDs used by B5.
work_id: ContextVar[str | None] = ContextVar("work_id", default=None)
work_guard: ContextVar[object | None] = ContextVar("work_guard", default=None)
