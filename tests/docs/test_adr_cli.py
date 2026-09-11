"""The tables of ADR 0024 and the CLI say the same thing.

Four tables, four shapes: §3 (the commands and the route each one calls, seventeen here and an
eighteenth in ADR 0025 §10), §4 (the
protocol that ``audit verify`` needs and why it is not a port), §6 (the four exit codes) and §7
(the rule that lets the CLI import typer, extended from ADR 0002). The routes ADR 0024 adds and
the failure it adds are checked in ``test_adr_composition.py``, with the tables they extend.

The list of variables ``ela init`` writes is here too: it is documentation of another kind —
``.env.example`` — and the two must not drift, because a variable added to one and not the other
is a variable nobody discovers.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.audit.verifier import AuditVerifier
from ela.cli.app import app
from ela.cli.errors import CONFIGURATION, OK, REFUSED, UNREACHABLE
from ela.cli.setup import TOKEN_VARIABLE, VARIABLES
from ela.infrastructure.persistence import SqlAuditLog
from ela.tombstones import (
    RETIRED_SETTINGS,
)
from tests.architecture.rules import INFRA_PACKAGES, RULES
from tests.contracts.protocols import method_names, port_protocols

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = REPO_ROOT / "docs" / "adr" / "0024-cli.md"
DEBTS_ADR_PATH = REPO_ROOT / "docs" / "adr" / "0025-phase-8-debts.md"
PERCEPTION_ADR_PATH = REPO_ROOT / "docs" / "adr" / "0028-perception-core.md"
CONTEXT_ADR_PATH = REPO_ROOT / "docs" / "adr" / "0032-context-core.md"
VOICE_ADR_PATH = REPO_ROOT / "docs" / "adr" / "0034-voice-online.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

COMMAND_ROW = re.compile(
    r"^\| `ela ([\w ]+)` \| (?:`(GET|POST) (/[\w{}/]*)`|\*\(([^)]*)\)\*) \| ((?:`\d` ?)+) \|$"
)
EXIT_ROW = re.compile(r"^\| `(\d)` \| ([^|]+) \|$")
PROTOCOL_ROW = re.compile(r"^\| `(\w+)` \| `(\w+)\(\)` \| `([\w.]+)` \| ([^|]+) \|$")
RULE_ROW = re.compile(r"^\| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$")
ENV_VARIABLE = re.compile(r"^#?\s*(ELA_\w+)\s*=", re.MULTILINE)
RULE_NAME = "cli-talks-over-the-api"
RETIRED = frozenset(RETIRED_SETTINGS)
"""Every retired variable (ADR 0022 §8, ADR 0037 §15): declared as a tombstone, never offered."""
"""Declared to be refused, never to be set (ADR 0022 §8): a field ELA reads only to say no."""


def adr_text() -> str:
    """ADR 0024, ADR 0025, ADR 0028 and ADR 0032, read together.

    An ADR is immutable, so a command a later milestone adds is documented in *its* ADR, in the
    row shape of this table (ADR 0025 §10, ADR 0028 §12). The table of commands is therefore the
    union of the documents, exactly as the table of ports is (``test_adr_ports.py``).
    """
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ADR_PATH,
            DEBTS_ADR_PATH,
            PERCEPTION_ADR_PATH,
            CONTEXT_ADR_PATH,
            VOICE_ADR_PATH,
        )
    )


def cli_adr_text() -> str:
    """ADR 0024 alone, for the tables that are only its own: the exit codes and rule 28."""
    return ADR_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# §3 — the commands, and the route each one calls
# ----------------------------------------------------------------------------------------


def documented_commands() -> dict[str, tuple[str, str] | None]:
    """command → the (method, path) it calls, or ``None`` for the two that are local."""
    return documented_commands_of(adr_text())


def documented_commands_of(text: str) -> dict[str, tuple[str, str] | None]:
    rows: dict[str, tuple[str, str] | None] = {}
    for line in text.splitlines():
        if (match := COMMAND_ROW.match(line)) is not None:
            method, path = match.group(2), match.group(3)
            rows[match.group(1)] = None if method is None else (method, path)
    assert rows, "ADR 0024 §3 must contain the table of the commands"
    return rows


def documented_command_exits() -> dict[str, frozenset[int]]:
    """command → the exit codes its row promises. Read by ``tests/cli/test_exit_codes.py``,
    which drives every command in the three ways that fail and checks it comes back with one."""
    rows = {
        match.group(1): frozenset(int(code) for code in re.findall(r"\d", match.group(5)))
        for line in adr_text().splitlines()
        if (match := COMMAND_ROW.match(line)) is not None
    }
    assert rows, "ADR 0024 §3 must give each command its exit codes"
    return rows


def coded_commands() -> set[str]:
    """Every command the app serves, a sub-command written as its group and its name.

    A **group that answers on its own** counts as one of them (M11.3): ``ela voice`` is a group
    with a callback and ``invoke_without_command``, so it is something a person types and gets an
    answer from, not a help screen — and the table of ADR 0024 §3 is about what can be typed.
    """
    found = {command.name for command in app.registered_commands if command.name}
    for group in app.registered_groups:
        assert group.typer_instance is not None and group.name is not None
        found |= {
            f"{group.name} {command.name}"
            for command in group.typer_instance.registered_commands
            if command.name
        }
        if group.typer_instance.info.invoke_without_command is True:
            found.add(group.name)
    return found


def test_the_commands_of_the_adr_are_the_commands_of_the_code() -> None:
    assert set(documented_commands()) == coded_commands()


def test_there_are_twenty_three_of_them() -> None:
    assert len(coded_commands()) == 23


def test_the_commands_after_adr_0024_are_the_ones_the_later_adrs_add() -> None:
    """``task results`` (ADR 0025 §4), ``perception`` (ADR 0028 §12), ``context`` (ADR 0032 §13).

    Each is the client of the one route its milestone introduced, and each is documented in the
    ADR that introduced it rather than back-written into ADR 0024.
    """
    added = set(documented_commands()) - set(documented_commands_of(cli_adr_text()))

    assert added == {
        "task results",
        "perception",
        "context",
        "voice",
        "voice preview",
        "voice audition",
    }


def test_only_two_commands_are_local_and_they_are_the_two_that_cannot_be_calls() -> None:
    """``serve`` starts the process, ``init`` runs before there is one (ADR 0024 §2)."""
    local = {name for name, route in documented_commands().items() if route is None}

    assert local == {"init", "serve"}


def test_every_other_command_names_a_route_the_application_serves() -> None:
    from tests.docs.test_adr_composition import coded_routes

    called = {route for route in documented_commands().values() if route is not None}

    assert called <= coded_routes()


def test_every_route_is_reachable_from_the_command_line() -> None:
    """The point of the perimeter (decision 2a): a whole turn of ELA without ``curl``.

    Fourteen routes, fourteen commands that call them — ``diagnostics`` and ``provider list``
    share one — so a route added tomorrow without a command fails here.
    """
    from tests.docs.test_adr_composition import coded_routes

    called = {route for route in documented_commands().values() if route is not None}

    assert called == coded_routes()


def test_a_command_that_talks_to_ela_can_end_in_any_of_the_four_ways() -> None:
    """It can work, be refused, be misconfigured, or find nobody there."""
    exits = documented_command_exits()
    calling = [name for name, route in documented_commands().items() if route is not None]

    assert calling
    assert all(exits[name] == {OK, REFUSED, CONFIGURATION, UNREACHABLE} for name in calling)


def test_a_local_command_can_only_work_or_be_misconfigured() -> None:
    """``init`` and ``serve`` open no client, so nothing can refuse them and no port can be
    closed to them: the two codes that belong to a client are not theirs to produce."""
    exits = documented_command_exits()
    local = [name for name, route in documented_commands().items() if route is None]

    assert all(exits[name] == {OK, CONFIGURATION} for name in local)


# ----------------------------------------------------------------------------------------
# §4 — the protocol that is deliberately not a port
# ----------------------------------------------------------------------------------------


def documented_protocol() -> tuple[str, str, str]:
    rows = [
        (match.group(1), match.group(2), match.group(3))
        for line in cli_adr_text().splitlines()
        if (match := PROTOCOL_ROW.match(line)) is not None
    ]
    assert len(rows) == 1, "ADR 0024 §4 must document exactly one protocol"
    return rows[0]


def test_the_protocol_is_the_one_the_code_declares() -> None:
    name, member, module = documented_protocol()

    assert name == AuditVerifier.__name__
    assert module == AuditVerifier.__module__
    assert method_names(AuditVerifier) == frozenset({member})


def test_it_is_not_a_port_and_the_audit_log_still_has_two_members() -> None:
    """A port that returned ``ChainSummary`` would drag the chain into ``ela.ports``; and whoever
    receives ``AuditLog`` must not gain a third way to write."""
    ports = {protocol.__name__: protocol for protocol in port_protocols()}

    assert AuditVerifier.__name__ not in ports
    assert method_names(ports["AuditLog"]) == frozenset({"append", "read"})
    assert issubclass(SqlAuditLog, AuditVerifier)  # the adapter is the implementation


# ----------------------------------------------------------------------------------------
# §6 — the four exit codes, which are a contract for whoever writes a script
# ----------------------------------------------------------------------------------------


def documented_exits() -> dict[int, str]:
    rows = {
        int(match.group(1)): match.group(2).strip()
        for line in cli_adr_text().splitlines()
        if (match := EXIT_ROW.match(line)) is not None
    }
    assert rows, "ADR 0024 §6 must contain the table of the exit codes"
    return rows


def test_the_exit_codes_of_the_adr_are_the_ones_the_cli_uses() -> None:
    assert set(documented_exits()) == {OK, REFUSED, CONFIGURATION, UNREACHABLE}


def test_each_code_says_which_of_the_four_situations_it_is() -> None:
    documented = documented_exits()

    assert "ELA ha risposto" in documented[REFUSED]
    assert "configurazione" in documented[CONFIGURATION]
    assert "nessuno risponde" in documented[UNREACHABLE]


# ----------------------------------------------------------------------------------------
# §7 — the rule this ADR introduces, and the one it extends
# ----------------------------------------------------------------------------------------


def test_rule_28_is_registered_under_the_name_the_adr_gives_it() -> None:
    assert RULE_NAME in cli_adr_text()
    assert "cli-over-the-api" in RULES


def test_the_extended_rule_3_names_the_fourth_edge() -> None:
    """ADR 0002's row is repeated whole under "Regole estese:", with ``cli/`` in it."""
    rows = [line for line in cli_adr_text().splitlines() if RULE_ROW.match(line)]

    assert len(rows) == 1
    assert rows[0].startswith("| 3 |")
    assert "`cli/`" in rows[0]
    assert set(INFRA_PACKAGES) == {"providers", "infrastructure", "api", "cli"}


# ----------------------------------------------------------------------------------------
# §8 — what ``ela init`` writes, and ``.env.example``
# ----------------------------------------------------------------------------------------


def documented_variables() -> list[str]:
    """The ``ELA_`` variables ``.env.example`` names in an assignment, commented or not.

    ``ELA_ANTHROPIC_MODEL`` is named there in a sentence and not in an assignment, because it was
    retired (ADR 0022 §8): it is not one to suggest, and this is why the pattern reads ``=``.
    """
    return ENV_VARIABLE.findall(ENV_EXAMPLE.read_text(encoding="utf-8"))


def test_init_writes_the_variables_the_example_documents() -> None:
    assert sorted(documented_variables()) == sorted([TOKEN_VARIABLE, *(n for n, _ in VARIABLES)])


def test_the_list_of_variables_is_every_variable_ela_actually_reads() -> None:
    """Derived, so "a variable nobody discovers" stops being a promise (M10.1).

    ``VARIABLES`` and ``.env.example`` have always been kept in step with each other; what nobody
    checked is that either of them is in step with the **settings**. A knob added to a
    ``BaseSettings`` and to neither list works perfectly and is invisible, which is the quietest
    way a configurable system stops being configurable.
    """
    from ela.composition.settings import Settings

    declared = {
        f"ELA_{field.upper()}"
        for group in Settings.model_fields.values()
        for field in group.annotation.model_fields  # type: ignore[union-attr]
    }

    assert declared - RETIRED == {TOKEN_VARIABLE, *(name for name, _ in VARIABLES)}


def test_the_retired_variable_is_not_among_them() -> None:
    """Suggesting it would stop ELA at start-up (ADR 0022 §8).

    It is the one field the settings declare and the lists must not offer, which is why the
    derivation above subtracts it by name instead of quietly allowing a difference.
    """
    assert not RETIRED & set(documented_variables())
    assert not RETIRED & {name for name, _ in VARIABLES}
