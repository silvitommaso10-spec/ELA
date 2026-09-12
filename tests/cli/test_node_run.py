"""``ela node run``: the four ways a resident command ends (M12.3 dec. C, dec. M; ADR 0039 §4).

It is neither of the two kinds ADR 0024 §2 knew. It opens a client, so it can be refused and can
find nobody there; but its life is not a request, so no answer makes it return. That is why its
exit codes are proved here and not by the three parametrised failures of ``test_exit_codes.py``,
whose closed world drives every command **to its end** — a resident has none to drive it to.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from ela.cli import node as command
from ela.cli.app import app
from ela.cli.errors import CONFIGURATION, OK, REFUSED, UNREACHABLE
from ela.composition import ConfigurationError
from ela.node import CoreUnreachable, NodeRevoked, NotEnrolled

runner = CliRunner()


def answering(monkeypatch: pytest.MonkeyPatch, raises: BaseException | None = None) -> list[Any]:
    """Replace the cycle, keep the command. What is under test is the ending, not the node."""
    seen: list[Any] = []

    async def instead(config: Any, *, join: str | None = None, **_: Any) -> None:
        seen.append(join)
        if raises is not None:
            raise raises

    monkeypatch.setattr(command, "run", instead)
    return seen


def test_ctrl_c_is_how_a_resident_command_is_meant_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit ``0``. Stopping it is not a failure: it is the price dec. C declares, and for the Core
    a window that closed is a node that has gone quiet — a case the protocol already handles."""
    answering(monkeypatch, KeyboardInterrupt())

    result = runner.invoke(app, ["node", "run"])

    assert result.exit_code == OK


def test_a_revoked_node_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit ``1``: ELA answered, and the answer was no (M12.1 D13)."""
    answering(monkeypatch, NodeRevoked("this node has been revoked"))

    result = runner.invoke(app, ["node", "run"])

    assert result.exit_code == REFUSED
    assert "revoked" in result.output


def test_a_core_that_never_answers_is_unreachable_and_not_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit ``3``, and the distinction is the point: a script told "refused" would go looking at
    the wrong end of the wire (ADR 0024 §6, the table of exits as a contract)."""
    answering(monkeypatch, CoreUnreachable("nobody answered after 60 tries"))

    result = runner.invoke(app, ["node", "run"])

    assert result.exit_code == UNREACHABLE


def test_a_machine_that_never_enrolled_is_a_refusal_that_says_what_to_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, NotEnrolled("this machine is not enrolled as a node."))

    result = runner.invoke(app, ["node", "run"])

    assert result.exit_code == REFUSED
    assert "not enrolled" in result.output


def test_a_configuration_it_cannot_use_stops_before_anything_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit ``2``: nothing was sent to ELA. The message names the variable, because whoever reads
    it wrote the ``.env`` — never a traceback."""

    def broken() -> None:
        raise ConfigurationError("ELA_MODEL_ROUTES cannot be used")

    monkeypatch.setattr(command.NodeConfig, "load", staticmethod(broken))
    answering(monkeypatch)

    result = runner.invoke(app, ["node", "run"])

    assert result.exit_code == CONFIGURATION
    assert "ELA_MODEL_ROUTES" in result.output


def test_the_enrollment_code_is_asked_for_and_never_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0037 §5, verbatim: "on the node's side the code is read from stdin without echo, never
    as an argument" — because a secret on the command line lands in ``ps`` and in the shell's
    history (ADR 0024 §2). The check is that it is not in the output the terminal kept.
    """
    seen = answering(monkeypatch, KeyboardInterrupt())

    result = runner.invoke(app, ["node", "run", "--join"], input="un-codice-segreto\n")

    assert result.exit_code == OK
    assert seen == ["un-codice-segreto"]
    assert "un-codice-segreto" not in result.output


def test_without_join_no_code_is_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node that already knows who it is just runs: the second start is not an enrollment."""
    seen = answering(monkeypatch, KeyboardInterrupt())

    result = runner.invoke(app, ["node", "run"])

    assert result.exit_code == OK
    assert seen == [None]


def test_join_takes_no_value_on_the_command_line() -> None:
    """The flag prompts; it is not ``--join <codice>``. A value here is a usage error, which is
    the mechanical half of the rule ADR 0037 §5 states in words."""
    result = runner.invoke(app, ["node", "run", "--join", "un-codice"])

    assert result.exit_code != OK
