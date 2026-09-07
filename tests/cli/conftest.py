"""Fixtures of the CLI tests: a real ELA, served in this process, and a runner over it."""

from __future__ import annotations

from tests.cli.support import cli  # noqa: F401 — re-exported as a fixture
from tests.composition.support import (  # noqa: F401 — re-exported as fixtures
    _only_the_declared_environment,
    ela,
    settings,
)
