"""The Context Core (spec §44): what ELA can say about now, and what it cannot (ADR 0032)."""

from ela.context.core import ContextCore, held, questions, snapshot_fields
from ela.context.settings import ContextSettings

__all__ = ["ContextCore", "ContextSettings", "held", "questions", "snapshot_fields"]
