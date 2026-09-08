"""How much of each list reaches a snapshot (spec §44; M10.4, ADR 0032 §9-bis).

Limits, and nothing that decides anything: a limit says how much is read, never what any of it
means. What makes them safe to have is the rule that comes with them — a truncated list declares
its own truncation (``shown`` and ``total``), so a limit that bites is visible instead of being
mistaken for the world.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["ContextSettings"]


class ContextSettings(BaseSettings):
    """Context configuration, read from ``ELA_CONTEXT_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    context_tasks_limit: Annotated[int, Field(ge=1)] = 20
    """``ELA_CONTEXT_TASKS_LIMIT``: how many live tasks a snapshot carries, oldest first.

    Measured rather than guessed — see ADR 0032 §9-bis for the number and the date. What is
    **not** configurable is that the section says how many it is showing out of how many exist.
    """

    context_deadlines_limit: Annotated[int, Field(ge=1)] = 10
    """``ELA_CONTEXT_DEADLINES_LIMIT``: how many deadlines a snapshot carries, soonest first."""

    context_events_limit: Annotated[int, Field(ge=1)] = 10
    """``ELA_CONTEXT_EVENTS_LIMIT``: how many recent task events a snapshot carries."""
