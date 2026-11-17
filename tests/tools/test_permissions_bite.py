"""The guard of the tests that need the OS to refuse, guarded in turn (ADR 0031 §6; M14.1).

``PERMISSIONS_BITE`` (``tests/machines.py`` since M9.5) lets a test that needs ``chmod`` to deny say
so in the summary when this process is the user who is allowed anyway — root, in a container —
instead of failing for a reason that has nothing to do with the code under test. A guard that
measured wrong would skip those tests where they must run, and a skip there is a defence that does
not exist. The runners are where they must run: each job is the ``runner`` user, and there the guard
answers ``True`` or this fails.
"""

from __future__ import annotations

from tests import machines


@machines.needs(machines.ON_A_RUNNER)
def test_on_the_runners_the_permissions_bite() -> None:
    """Read through the one place (``tests/machines.py``, M9.5): on a runner the guard turns every
    test that needs it red if it is missing, and this says it once, by itself."""
    missing = machines.missing_here(machines.PERMISSIONS_BITE)
    assert missing is None, f"the guarded tests would be red on this runner: {missing}"
