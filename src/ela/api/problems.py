"""The one shape every failure of the API takes (ADR 0023 §10)."""

from __future__ import annotations

from ela.ports import WireCode

__all__ = ["problem"]


def problem(code: WireCode, message: str) -> dict[str, dict[str, str]]:
    """``{"error": {"code": …, "message": …}}`` — a code to branch on, a message to read.

    ``code`` is a member of :class:`~ela.ports.WireCode` and never a string (M12.4): a code a client
    may branch on that is not in the vocabulary is a code no client can know about.
    """
    return {"error": {"code": code.value, "message": message}}
