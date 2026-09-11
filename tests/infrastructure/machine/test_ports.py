"""``port_holder``: who holds a port, read from ``lsof`` — and nothing guessed when it cannot say.

The command is replaced by a fake here, so every branch is taken on any machine; what ``lsof``
really answers on this one is ``test_ports_smoke.py``, declared with its ``skipif``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from ela.infrastructure.machine import ports
from ela.infrastructure.machine.darwin import TIMED_OUT
from ela.infrastructure.machine.ports import LOOKUP_TIMEOUT_SECONDS, holder_from, port_holder


class Lsof:
    """A fake ``spawn``: what it was asked, and the answer it was told to give."""

    def __init__(self, code: int, output: str) -> None:
        self.answer = (code, output)
        self.asked: list[tuple[list[str], float]] = []

    async def __call__(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
        self.asked.append((list(argv), timeout))
        return self.answer


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ports.shutil, "which", lambda name: f"/usr/sbin/{name}")


def test_the_first_process_that_listens_is_named_with_its_pid() -> None:
    assert holder_from("p4242\ncpython3\nf3\n") == "python3 (pid 4242)"
    assert holder_from("p1\ncfirst\nf3\np2\ncsecond\nf4\n") == "first (pid 1)"


def test_a_process_with_no_name_is_still_named_by_its_pid() -> None:
    assert holder_from("p4242\nf3\n") == "a process (pid 4242)"


def test_an_answer_with_no_process_names_nobody() -> None:
    assert holder_from("") is None
    assert holder_from("cpython3\n") is None


@pytest.mark.usefixtures("installed")
def test_lsof_is_asked_for_the_listener_of_that_port_within_the_timeout() -> None:
    lsof = Lsof(0, "p4242\ncpython3\n")

    assert asyncio.run(port_holder(8351, lsof)) == "python3 (pid 4242)"
    ((argv, timeout),) = lsof.asked
    assert argv == ["/usr/sbin/lsof", "-nP", "-iTCP:8351", "-sTCP:LISTEN", "-Fpc"]
    assert timeout == LOOKUP_TIMEOUT_SECONDS


@pytest.mark.usefixtures("installed")
@pytest.mark.parametrize("code", [1, TIMED_OUT], ids=["nobody-listens", "timed-out"])
def test_an_lsof_that_fails_or_does_not_answer_names_nobody(code: int) -> None:
    assert asyncio.run(port_holder(8351, Lsof(code, "p4242\ncpython3\n"))) is None


def test_a_machine_without_lsof_names_nobody_and_starts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ports.shutil, "which", lambda name: None)
    lsof = Lsof(0, "p4242\ncpython3\n")

    assert asyncio.run(port_holder(8351, lsof)) is None
    assert lsof.asked == []
