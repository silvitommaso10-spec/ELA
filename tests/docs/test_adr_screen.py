"""ADR 0029 and the code say the same thing about the screen capture (M10.2).

Same shape as ``test_adr_perception.py``: the tables of the document are read and compared with
what the code has, and the decisions that are **properties** rather than prose are asserted.
The port table and the capability table are checked by ``test_adr_ports.py`` and
``test_adr_catalogue.py``, which now read this ADR as a continuation; what is here is the rest —
the rule, the totals, and the four things this milestone promised *not* to do.

A declared constraint nobody reads is the failure mode M9.2 exists to fix, and it is why the
promises in the second half of this file are tests and not sentences in a document.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from ela.api import approvals, audit, devices, perception, results, system, tasks
from ela.domain import FAMILY_FIELDS, AuditEventType, ProbeFamily, RawObservation, RiskLevel
from ela.permissions import PERCEPTION_CAPTURE_SCREEN, catalogue_v01, production_catalogue
from ela.tools import CaptureScreenTool
from tests.architecture.rules import RULES
from tests.architecture.violations import PACKAGE_ROOT
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_cli import coded_commands

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0029-screen-capture.md"
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")

ROUTERS = (
    system.router,
    tasks.router,
    approvals.router,
    audit.router,
    devices.router,
    results.router,
    perception.router,
)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# §12: the rule, and the totals this ADR now owns
# ----------------------------------------------------------------------------------------


def test_the_rule_is_registered_under_the_name_the_adr_gives_it() -> None:
    documented = [
        match.groups() for line in adr_text().splitlines() if (match := RULE_ROW.match(line))
    ]

    assert [number for number, *_ in documented] == ["35"]
    assert documented[0][1] in RULES


def test_the_new_rule_holds_on_the_real_tree() -> None:
    assert RULES["capture-stays-on-the-machine"](PACKAGE_ROOT) == []


def test_the_conseguenze_count_the_rules_the_ports_and_the_capabilities() -> None:
    """The current totals, pinned by the ADR that changed them.

    ADR 0028 counted thirty-four and still can, as a number about the tree it left behind; this
    is the document that owns today's total, and the next one to add a rule takes the pin over.
    """
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**trentacinque**" in conseguenze
    assert len(RULES) == 35
    assert "**venti**" in conseguenze
    assert len(tuple(port_protocols())) == 20
    assert "**tredici**" in conseguenze
    assert "**quattro**" in conseguenze
    assert len(production_catalogue().specs()) == 4
    assert "**tre**" in conseguenze
    assert len(catalogue_v01().specs()) == 3


# ----------------------------------------------------------------------------------------
# The vow ADR 0028 §9 registered, kept
# ----------------------------------------------------------------------------------------


def test_the_deferred_capability_was_delivered_as_medium_and_asks_for_authorization() -> None:
    """ADR 0028 §9 registered a constraint instead of shipping a capability nobody consumed:
    *la prima lettura di contenuto nasce con la propria capability MEDIUM*. This is the test that
    it was kept rather than quietly dropped — the deferral's other failure mode."""
    spec = production_catalogue().get(PERCEPTION_CAPTURE_SCREEN)

    assert spec.risk is RiskLevel.MEDIUM
    assert spec.requires_authorization
    assert PERCEPTION_CAPTURE_SCREEN not in {one.id for one in catalogue_v01().specs()}


def test_the_capability_has_no_scope_and_the_adr_says_why() -> None:
    """§6: the Guardian's scope is path-shaped and a display is not a path. An absent scope with
    no argument is a decision, and a decision has to be written down or it reads as an omission."""
    spec = production_catalogue().get(PERCEPTION_CAPTURE_SCREEN)

    assert spec.scope == () and spec.scoped_arguments == ()
    assert "non è un percorso" in adr_text()


def test_the_question_the_user_reads_carries_the_purpose() -> None:
    """§6 and §30: a yes is only worth something if the question was complete."""
    spec = production_catalogue().get(PERCEPTION_CAPTURE_SCREEN)

    assert spec.prompt_arguments == ("purpose",)
    assert "purpose" in spec.input_schema["required"]


def test_no_capability_of_v01_shows_an_argument_in_the_question() -> None:
    """The default is the defence: ``model.complete`` takes ``input``, which is the user's
    content, and a prompt that showed it would write it into a stored ``Approval`` (§57)."""
    assert all(spec.prompt_arguments == () for spec in catalogue_v01().specs())


# ----------------------------------------------------------------------------------------
# The four things this milestone promised not to do
# ----------------------------------------------------------------------------------------


def test_no_route_was_added() -> None:
    """§15: the capture is reached through ``POST /tasks``, ``/approvals`` and the results."""
    coded = {
        (method, route.path)
        for router in ROUTERS
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert len(coded) == 16
    assert "Nessuna rotta nuova e nessun comando nuovo" in adr_text()


def test_no_command_was_added() -> None:
    """Nineteen, the same nineteen ``ela perception`` made it in M10.1."""
    assert len(coded_commands()) == 19


def test_no_audit_event_type_was_added() -> None:
    """§10: the audit records what ELA decides, and the execution is audited already. Reading is
    not causing, so the exception ADR 0028 §10 registered has not fired yet."""
    assert "PERCEPTION" not in {kind.value for kind in AuditEventType}
    assert "CAPTURE" not in {kind.value for kind in AuditEventType}


def test_the_capture_tool_writes_no_audit_of_its_own() -> None:
    """Structural, not asserted about behaviour: the module does not name the audit log at all.

    The same shape as ``PerceptionCore.__slots__`` in ``test_adr_perception.py`` — a module that
    cannot reach the audit log cannot start keeping a second trail beside the executor's.
    """
    source = (PACKAGE_ROOT / "tools" / "screen.py").read_text(encoding="utf-8")
    imported = {
        alias.name if isinstance(node, ast.Import) else alias.asname or alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    assert "AuditLog" not in imported
    assert "AuditEvent" not in imported


def test_the_perception_core_did_not_learn_about_the_capture() -> None:
    """§5: the capture is an **action**. The first ring observes, the second acts, and the
    observation model is untouched — no fourth family, no widened ``RawObservation``."""
    assert [family.value for family in ProbeFamily] == ["SENSORS", "SESSION", "PERMISSIONS"]
    partition = [field for family in ProbeFamily for field in FAMILY_FIELDS[family]]
    assert sorted(partition) == sorted(RawObservation.model_fields)

    source = (PACKAGE_ROOT / "perception" / "core.py").read_text(encoding="utf-8")
    assert "ela.tools" not in source


# ----------------------------------------------------------------------------------------
# The criteria that must survive this document, written down and not only applied
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "una credenza periodica non decide mai un'azione",
        "il contenuto catturato non vive mai in una directory",
        "v0.1 non si ripiega, si affianca",
    ],
)
def test_the_criteria_are_written_down_and_not_only_applied(sentence: str) -> None:
    """A criterion lives only where somebody writes it: the fact has a test, the reason that
    produced it has none unless it is in the document, and without it the next person decides
    again from scratch."""
    assert sentence in adr_text().lower()


def test_the_measured_timeout_and_the_adr_say_the_same_number() -> None:
    """§14: the placeholder was replaced, and the document carries the measurement.

    The condition that watched it is still armed (``test_screencapture_smoke.py``, negative case
    in ``tests/tools/test_settings.py``); what this checks is that the number in the code and the
    number in the ADR did not drift the moment one of them was edited.
    """
    from ela.tools.settings import CAPTURE_TIMEOUT_IS_MEASURED, DEFAULT_CAPTURE_TIMEOUT_SECONDS

    assert DEFAULT_CAPTURE_TIMEOUT_SECONDS == 5.0
    assert CAPTURE_TIMEOUT_IS_MEASURED is True
    text = " ".join(adr_text().split())
    assert f"{DEFAULT_CAPTURE_TIMEOUT_SECONDS:g} s" in text or "cinque secondi" in text
    assert "88 ms" in text
    assert "la condizione è un fatto osservabile, non una data" in text.lower()


def test_the_reason_the_question_may_carry_an_argument_is_written_down() -> None:
    """§6: ``prompt_arguments`` is not an exception made for the screen.

    Every informed consent ELA will ask for needs it — a call (§7) is *to whom* and *to say what*,
    an email (§39) is *to whom* and *about what*, an order (§30) is *what* and *for how much* —
    and the criterion that produced the field has to be in the document, or the next capability
    invents its own way of saying the same thing.
    """
    assert "non soltanto quale" in adr_text().lower()
    assert "consenso informato" in adr_text().lower()


def test_the_limit_of_the_verifier_is_written_down() -> None:
    """§9: it cannot say the image depicts the screen, only that it exists and is the one
    declared. Admitting that is worth more than a verifier that seems to say more."""
    text = " ".join(adr_text().split())

    assert "non può dire che l'immagine ritrae lo schermo" in text
    assert "byte, digest, larghezza, altezza" in text


def test_the_tool_declares_every_code_the_adr_relies_on() -> None:
    """A refusal the document promises and the tool cannot produce would be prose."""
    assert {
        "screen.unsupported",
        "screen.permission_denied",
        "screen.not_observable",
        "screen.timeout",
        "screen.capture_failed",
        "screen.store_full",
    } <= CaptureScreenTool.error_codes
    assert "io.error" not in CaptureScreenTool.error_codes
