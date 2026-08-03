"""Stable public errors for failures whose internal details belong in logs only."""

from fastapi import HTTPException


def internal_http_error(
    status_code: int,
    *,
    operation: str,
) -> HTTPException:
    """Build a stable client error without accepting exception-shaped input.

    Callers must log the original exception before raising the returned error.
    Keeping ``exc`` out of this function's signature makes accidental string
    interpolation into a public response harder during future maintenance.
    """

    return HTTPException(
        status_code=status_code,
        detail=f"{operation}失败，请稍后重试",
    )


def unavailable_http_error(*, dependency: str = "服务") -> HTTPException:
    """Return a stable 503 without exposing provider or infrastructure text."""

    return HTTPException(
        status_code=503,
        detail=f"{dependency}暂时不可用，请稍后重试",
    )


def dependency_health_failure() -> dict[str, str]:
    """Return the content-minimized administrator dependency state."""

    return {"status": "error", "detail": "连接检查失败"}
