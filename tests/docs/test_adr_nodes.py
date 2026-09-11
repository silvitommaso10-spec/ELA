"""ADR 0037 and the code say the same thing about the identity of the nodes (M12.1).

Written with the code it checks, a table at a time: the rules and the debt of ADR 0036 §12 arrive
with the commit that pays it; the three halves, the events, the routes and the new port arrive
with the commits that make them true. The pin on today's totals moves here from ADR 0036 as each
total moves — the rules first, because M12.1 wrote its rules before its code (ADR 0030 §15).
"""

from __future__ import annotations

import inspect
import re
from contextlib import (
    suppress,
)
from datetime import (
    timedelta,
)
from pathlib import Path
from typing import (
    Any,
)

from ela.devices import (
    LOCAL_USER,
    DeviceRegistry,
    NodeEnrollment,
    Rejection,
)
from ela.domain import (
    AuditEventType,
    OperatingSystem,
    PerformanceClass,
    PrivacyLevel,
)
from ela.permissions import (
    production_catalogue,
)
from ela.ports import (
    ANNOUNCED_FIELDS,
    EnrollmentConsumedError,
    IdentityConflictError,
)
from ela.testing.fakes import (
    FakeAuditLog,
    FakeClock,
    FakeDeviceRegistry,
    FakeEnrollmentStore,
    FakeIdGenerator,
)
from tests.architecture.rules import RULES
from tests.contracts.protocols import (
    port_protocols,
)
from tests.docs.test_adr_listening import writers_of
from tests.docs.test_adr_placement import _rules_up_to
from tests.docs.test_adr_ports import (
    EXTENDING,
    INTRODUCING,
    documented_ports,
)
from tests.domain.examples import (
    MUCH_LATER,
)

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0037-node-identity.md"
ADR_0036 = ADR_DIR / "0036-listening.md"
RULE_ROW = re.compile(r"^\| (\d+) `([a-z0-9-]+)` \|")
PAID_TITLE = "Il debito di ADR 0036 §12, saldato"
RETIRED_TYPES = ("PROVIDER_CALLED", "ERROR_RECORDED")
ADDED_RULES = {
    46: "a-nodes-secret-crosses-no-readable-boundary",
    47: "identity-resolved-in-one-place",
}
EXTENDED_RULES = {
    31: "constant-time-token",
    44: "a-refresh-touches-only-what-is-declared",
}


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def documented_rules(text: str) -> dict[int, str]:
    """Every rule the ADR names in a table row, by the number it gives it."""
    return {
        int(match.group(1)): match.group(2)
        for line in text.splitlines()
        if (match := RULE_ROW.match(line)) is not None
    }


def unwritten(types: list[AuditEventType]) -> list[str]:
    """The members nothing in ``src/ela`` writes: a pure function of the tree and of the enum."""
    return [event.name for event in types if not writers_of(event)]


# ----------------------------------------------------------------------------------------
# The rules, and the pin on today's number of them
# ----------------------------------------------------------------------------------------


def test_the_rules_this_adr_adds_are_registered_under_the_names_it_gives_them() -> None:
    documented = documented_rules(adr_text())

    assert {number: documented.get(number) for number in ADDED_RULES} == ADDED_RULES
    for number, name in ADDED_RULES.items():
        assert name in RULES
        assert f"Rule {number}:" in (inspect.getdoc(RULES[name]) or ""), name


def test_the_rules_this_adr_extends_exist_under_the_names_it_gives_them() -> None:
    """`Regole estese:` names rules that exist, each declaring its number and its extension."""
    documented = documented_rules(adr_text())

    assert {number: documented.get(number) for number in EXTENDED_RULES} == EXTENDED_RULES
    for number, name in EXTENDED_RULES.items():
        doc = inspect.getdoc(RULES[name]) or ""
        assert f"Rule {number}:" in doc, name
        assert "M12.1" in doc, name


def test_the_conseguenze_count_the_rules_the_ports_and_the_capabilities_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0036 by the ADR that changed them.

    The rules moved first, with the commit that wrote rules 46 and 47 before their code (ADR 0030
    §15); the ports with the commit that wrote the twenty-fourth. The capabilities did not move —
    in M12.1 no capability travels — and ADR 0037 says so, so their pin is here with the others.

    The rules have moved on: M12.2 writes rules 48 to 50 before ADR 0038 exists (ADR 0030 §15,
    the defence before the room), so ADR 0037's «quarantasette» is read the way ADR 0036 read its
    «quarantacinque» — as the rules numbered up to 47 — and the pin on today's total passes to the
    test of ADR 0038 when it exists.
    """
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**quarantasette**" in conseguenze
    assert len(_rules_up_to(47)) == 47
    assert "**ventiquattro**" in conseguenze
    assert len(tuple(port_protocols())) == 24
    assert "restano otto" in conseguenze
    assert len(production_catalogue().specs()) == 8


# ----------------------------------------------------------------------------------------
# The twenty-fourth port, and the half an announcement writes
# ----------------------------------------------------------------------------------------


def test_the_adr_introduces_the_enrollment_store_and_extends_the_registry() -> None:
    """ADR 0037 §8: the tables ``test_adr_ports.py`` composes, pinned to what M12.1 wrote."""
    text = adr_text()

    assert documented_ports(text, INTRODUCING) == {
        "EnrollmentStore": ("async", frozenset({"offer", "consume"}))
    }
    assert documented_ports(text, EXTENDING) == {
        "DeviceRegistryPort": (
            "async",
            frozenset({"enroll", "secret_hash", "announce", "observe", "revoke"}),
        )
    }


def test_the_declared_half_of_the_table_is_what_an_announcement_writes() -> None:
    """ADR 0037 §10's «Dichiarata» row and :data:`~ela.ports.ANNOUNCED_FIELDS`: the same five."""
    row = re.search(r"^\| Dichiarata \| [^|]+ \| (.+) \|$", adr_text(), re.MULTILINE)

    assert row is not None
    assert tuple(re.findall(r"`(\w+)`", row.group(1))) == ANNOUNCED_FIELDS


# ----------------------------------------------------------------------------------------
# D11: every type of event has a writer, and the debt of ADR 0036 §12 is paid
# ----------------------------------------------------------------------------------------


def test_every_audit_event_type_has_a_writer() -> None:
    """A type nothing can produce is worse than an absent one (ADR 0026 §7; M12.1, D11).

    Read from the AST by :func:`writers_of`, for every member: it failed on ``PROVIDER_CALLED`` and
    ``ERROR_RECORDED`` until M12.1 took them out, and it fails tomorrow on a type added without
    the code that writes it — including the five M12.1 adds, if one of them stayed without a
    writer. It replaces the guardian ADR 0036 §12 kept on one member with a law on all of them.
    """
    assert unwritten(list(AuditEventType)) == []


def test_a_type_without_a_writer_is_detected() -> None:
    """The negative case, on today's tree: a member that exists nowhere but in the enum."""
    phantom = AuditEventType("TASK_CREATED")
    renamed = type("Phantom", (), {"name": "NOBODY_WRITES_THIS"})()

    assert unwritten([phantom]) == []
    assert unwritten([renamed]) == ["NOBODY_WRITES_THIS"]  # type: ignore[list-item]


def test_the_debt_of_adr_0036_is_paid_and_this_adr_says_by_whom() -> None:
    """The form ADR 0036 §10 used for ADR 0035 §7: the payment is a section of the ADR that paid.

    ``scripts/generate_stato.py`` reads that title — and only in an ADR (``9653ecd``) — so the
    restart point says the debt is closed the moment this section exists, and not before.
    """
    text = adr_text()
    heading = re.search(rf"^## (\d+)\. {re.escape(PAID_TITLE)}$", text, re.MULTILINE)

    assert heading is not None, "ADR 0037 must carry the section that says the debt is paid"
    section = text[heading.end() :].split("\n## ", 1)[0]
    assert "M12.1" in section
    assert all(name not in AuditEventType.__members__ for name in RETIRED_TYPES)
    assert "## 12. Un debito datato: `PROVIDER_CALLED` non lo scrive nessuno" in ADR_0036.read_text(
        encoding="utf-8"
    )


# ----------------------------------------------------------------------------------------
# §13: the five events, and who signs each — read from the table, checked by running the flows
# ----------------------------------------------------------------------------------------

EVENT_ROW = re.compile(r"^\| `(DEVICE_\w+)` \| ([^|]+?) \| `(\w+)` \|$")
DECLARED: dict[str, Any] = {
    "name": "pc",
    "os": OperatingSystem.WINDOWS,
    "capabilities": (),
    "available_tools": (),
    "performance": PerformanceClass.HIGH,
}


def documented_events(text: str) -> dict[str, str]:
    rows = {
        match.group(1): match.group(3)
        for line in text.splitlines()
        if (match := EVENT_ROW.match(line)) is not None
    }
    assert rows, "ADR 0037 §13 must contain the table of the five events"
    return rows


async def signed_by() -> dict[str, str]:
    """Every flow of an identity run once, on fakes, and who signed each event it wrote."""
    ids, clock, audit = FakeIdGenerator(), FakeClock(MUCH_LATER), FakeAuditLog()
    registry = DeviceRegistry(
        FakeDeviceRegistry(), clock, audit, ids, heartbeat_ttl=timedelta(seconds=60)
    )
    enrollment = NodeEnrollment(FakeEnrollmentStore(), registry, clock, ids)
    issued = await enrollment.issue(PrivacyLevel.TRUSTED)
    node = (await enrollment.enroll(issued.code, **DECLARED)).device
    with suppress(EnrollmentConsumedError):
        await enrollment.enroll(issued.code, **DECLARED)
    await registry.announce(node.id, **{**DECLARED, "name": "renamed"}, expected_revision=1)
    with suppress(IdentityConflictError):
        await registry.announce(node.id, **DECLARED, expected_revision=1)
    await registry.revoke(node.id, by=LOCAL_USER)
    return {event.event_type.value: event.actor.kind.value for event in await audit.read()}


async def test_the_events_of_an_identity_are_signed_as_the_adr_says() -> None:
    """The table of §13 against the code, by running it: five types, five actors, no other."""
    documented = documented_events(adr_text())

    assert set(documented) <= set(AuditEventType.__members__)
    assert documented == await signed_by()


def test_a_drifted_event_row_is_detected() -> None:
    """Negative case: the table claiming a rejection is signed by the node that failed to prove
    itself — the attribution ADR 0037 §13 refuses."""
    drifted = adr_text().replace(
        "| `DEVICE_REJECTED` | una richiesta che nomina un nodo esistente, rifiutata | `SYSTEM` |",
        "| `DEVICE_REJECTED` | una richiesta che nomina un nodo esistente, rifiutata | `DEVICE` |",
    )
    assert documented_events(drifted)["DEVICE_REJECTED"] == "DEVICE"


def test_the_reasons_of_a_rejection_are_the_four_the_adr_names() -> None:
    """ADR 0037 §13 names four reasons, in backticks; ``Rejection`` derives its values from its
    member names, so this is where the two are held to the same four words."""
    text = adr_text()

    assert len(Rejection) == 4
    for reason in Rejection:
        assert f"`{reason.value}`" in text, reason
