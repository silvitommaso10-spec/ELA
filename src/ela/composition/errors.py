"""What ELA says when it cannot be built from the configuration it was given (ADR 0023 §5)."""

from __future__ import annotations

__all__ = ["ConfigurationError"]


class ConfigurationError(Exception):
    """ELA cannot start with this configuration, and the message says what to change.

    Not a ``ValidationError`` and not a stack trace: the person reading it is the person who
    wrote the ``.env``, and what they need is the name of the variable and what to do with it
    (§33). Raised before anything is built, so a misconfigured ELA never half-starts.
    """
