"""Perception on an operating system that has none of this (M10.1, ADR 0028).

ELA runs on Linux in CI and will run on Windows nodes (§4). Neither has a TCC, and asking
``ctypes`` for CoreGraphics there does not raise — ``find_library`` answers ``None`` and
``CDLL(None)`` loads the process's own symbols, which is a silently wrong thing rather than an
error. So the adapter for "not macOS" is chosen by the composition root and reads nothing at all,
on purpose: every field stays ``None`` and the core says *not observable*, which is the truth.

The value of writing this down as a class instead of an ``if`` somewhere: "ELA on Linux perceives
nothing" becomes a thing with a name, a test and a line in ``/diagnostics``, rather than a gap
somebody discovers.
"""

from __future__ import annotations

from ela.domain import ProbeFamily, RawObservation

__all__ = ["UnsupportedProbe"]


class UnsupportedProbe:
    """Reads nothing, and says so (:class:`~ela.ports.PerceptionProbe`)."""

    __slots__ = ()

    async def read(self, families: frozenset[ProbeFamily]) -> RawObservation:
        """An empty observation, whatever was asked for: here there is nothing to look at."""
        del families
        return RawObservation()
