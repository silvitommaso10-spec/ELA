"""The one shape every failure of the API takes (ADR 0023 §10)."""

from __future__ import annotations

__all__ = ["problem"]


def problem(code: str, message: str) -> dict[str, dict[str, str]]:
    """``{"error": {"code": …, "message": …}}`` — a code to branch on, a message to read."""
    return {"error": {"code": code, "message": message}}
