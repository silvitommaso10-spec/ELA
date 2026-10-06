"""The guard of the tests that need the OS to refuse, guarded in turn (ADR 0031 §6; M14.1).

``PERMISSIONS_BITE`` lets a test that needs ``chmod`` to deny say so in the summary when this
process is the user who is allowed anyway — root, in a container — instead of failing for a reason
that has nothing to do with the code under test. A guard that measured wrong would skip those tests
where they must run, and a skip there is a defence that does not exist. The runners are where they
must run: each job is the ``runner`` user, and there the guard answers ``True`` or this fails.
"""

from __future__ import annotations

import os

import pytest

from tests.tools.support import PERMISSIONS_BITE

ON_A_RUNNER = os.environ.get("GITHUB_ACTIONS") == "true"
"""What GitHub Actions sets on every runner, and nothing else this suite runs on sets."""


@pytest.mark.skipif(not ON_A_RUNNER, reason="GITHUB_ACTIONS is not set: this is not a runner")
def test_on_the_runners_the_permissions_bite() -> None:
    assert PERMISSIONS_BITE, "chmod does not deny the runner's user: the guarded tests would skip"
