"""The local API of ELA (spec §54; M8.1, ADR 0023).

One token, on loopback, in front of the world the composition root built. This package builds
nothing: it receives an :class:`~ela.composition.Ela` and serves it (architecture rule 27).
"""

from ela.api.app import create_app
from ela.api.server import main, serve

__all__ = ["create_app", "main", "serve"]
