"""Perception Core: the first ring of §10 — local detection, and nothing beyond it (M10.1).

ELA looks at the machine it runs on, names what it sees in the vocabulary of §11, and notices
what changed since the last look. It does not analyse, does not read content, and sends nothing
anywhere: the second ring of §10 — analysis when necessary — is a later milestone, and the first
reading of *content* (a screenshot, an OCR, a second of audio) is born with its own ``MEDIUM``
capability rather than inheriting this one's silence (ADR 0028 §9).

The package is pure: it decides, and it never touches the operating system. What touches the
operating system is :mod:`ela.infrastructure.machine`, behind the
:class:`~ela.ports.PerceptionProbe` port.
"""

from ela.perception.core import (
    AUTHORIZATION_STATUS,
    UNCOMPARED,
    UNKNOWN,
    PerceptionCore,
    PerceptionView,
    detect,
    fingerprint,
    interpret,
    merge,
    unobserved,
)
from ela.perception.settings import (
    DEFAULT_INTERVALS,
    DEFAULT_PROBE_TIMEOUT_SECONDS,
    PerceptionSettings,
)

__all__ = [
    "AUTHORIZATION_STATUS",
    "DEFAULT_INTERVALS",
    "DEFAULT_PROBE_TIMEOUT_SECONDS",
    "UNCOMPARED",
    "UNKNOWN",
    "PerceptionCore",
    "PerceptionSettings",
    "PerceptionView",
    "detect",
    "fingerprint",
    "interpret",
    "merge",
    "unobserved",
]
