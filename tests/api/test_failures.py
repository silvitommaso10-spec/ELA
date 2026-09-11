"""Every row of ``FAILURES`` raised through the real application (ADR 0023 §10).

``tests/docs/test_adr_composition.py`` proves the **table**: that the exceptions the app installs
are the ones the ADR documents, that every code is a code, that a base never sits above its own
subclass. It cannot prove the **response**, because a table is not an answer to a request. Until
M9.4 nothing did: a probe over every request ``tests/api`` and ``tests/cli`` make saw seven of the
eight codes come back and never ``already_exists``, and — worse — two of the codes are shared, so
seeing ``conflict`` said nothing about *which* of the three exceptions had produced it.

So each row gets a scenario **only that exception can reach**, driven through a real HTTP request
against a real ELA, and the assertion covers the status, the code and a fragment of the message
that no other exception writes. Where a scenario needs a state a caller cannot ask for, it is
prepared through ELA's own ports — the precedent is ``tamper_with_the_trail`` — never by mounting
a route that exists only here: a route invented for a test would prove that the test works.

The rows that cannot be reached are declared instead of faked — :data:`ALREADY_EXISTS` since M9.4,
and since M12.2 :data:`AT_CAP` and :data:`REFUSED_ASSIGNMENT`, both about a state a request cannot
produce without waiting out real seconds. Every declaration says why today and what would open it,
and :data:`DECLARED` is what keeps the census closed.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient, Response

from ela.api import create_app
from ela.api.app import FAILURES, NOT_YOUR_WORK
from ela.api.errors import (
    DatabaseUnavailableError,
    RevisionRequiredError,
    TaskAlreadyRunningError,
)
from ela.audit.chain import AuditChainError
from ela.composition import Ela
from ela.devices import (
    LOCAL_DEVICE_ID,
    LocalDeviceNotRevocableError,
)
from ela.domain import (
    CapabilityId,
    DeviceId,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    StepId,
    TaskId,
)
from ela.executive import (
    AssignmentAtCapError,
    AssignmentRefusedError,
    AssignmentVoidError,
    DeliveryConflictError,
    ExecutorError,
    RunnerError,
    WorkNotYoursError,
)
from ela.ports import (
    AlreadyExistsError,
    ApprovalNotAnswerableError,
    AssignmentExpiredError,
    AssignmentNotUsableError,
    IdentityConflictError,
    NotFoundError,
)
from ela.tasks.errors import GraphError, TaskError
from tests.api.support import (
    AUTHORIZED,
    BASE,
    BrokenRepository,
    echo_plan,
    note_plan,
    queued,
    served_paths,
    tamper_with_the_trail,
)
from tests.api.test_nodes_work import ENVELOPE, taken, work_for


@dataclass(frozen=True, slots=True)
class Live:
    """A running ELA and a client that talks to it: what a scenario is handed."""

    client: AsyncClient
    ela: Ela
    app: FastAPI


Scenario = Callable[[Live], Awaitable[Response]]


@dataclass(frozen=True, slots=True)
class Raised:
    """One row of ``FAILURES``, and the scenario that makes the application raise it."""

    exception: type[Exception]
    method: str
    route: str
    status: int
    code: str
    message: str
    """A fragment of the message **only this exception** writes: the discriminator for the two
    codes three exceptions share."""
    scenario: Scenario


@dataclass(frozen=True, slots=True)
class Missing:
    """One ``(method, route, status)`` the probe of M9.4 found no test produced."""

    method: str
    route: str
    status: int
    scenario: Scenario


ALREADY_EXISTS = """
``AlreadyExistsError`` (409 ``already_exists``) cannot be reached through v0.1, and this says why
and what would change it — the row is declared, not faked (decision 3 of M9.4).

**Why not today.** Every id that can collide is minted by the server's ``IdGenerator``: task,
plan, task event, approval, authorization, execution result, audit event, device. The one id a
caller does choose is ``StepIn.id``, and a step is not a row with a key of its own — it lives
inside the plan it belongs to — so two steps with the same id are a plan that is not a graph
(422 ``invalid``), never a duplicate insert. There is therefore no request a client can make
twice and be told the second time that the thing already exists.

**What would open it.** A route that accepts an id **proposed by the caller**. The classic shape
is idempotency over an unreliable network: whoever calls generates the id of the request so that
repeating it cannot duplicate the effect, and the second call is answered ``409 already_exists``
instead of acting again. The day such a route exists, this row becomes observable and this
deferral expires.
"""


AT_CAP = """
``AssignmentAtCapError`` (409 ``assignment.at_cap``) is not reachable through a request of this
suite, and the reason is time (M12.2, ADR 0038 §13).

**Why not today.** The cap is reached when ``min(now + ttl, claimed_at + max)`` can no longer move
the deadline, which with the defaults — a TTL of two minutes, a cap of an hour — takes an hour of
real seconds. A suite that waited them would be the slowest in the repository; one that faked the
clock would not be going through HTTP at all, because the clock ELA serves with is the real one. So
the behaviour is tested where the cap is decided, with an injected clock:
``tests/executive/test_assignments.py``.

**What would open it.** A way to serve a request against an ELA whose settings a test chose — a
second ``live`` fixture over a ``build`` with ``ELA_ASSIGNMENT_MAX_SECONDS`` equal to the TTL, where
the first renewal is already at the cap. It is a fixture and not a product change, and the day it
exists this row becomes observable.
"""

REFUSED_ASSIGNMENT = """
``AssignmentRefusedError`` (409 ``conflict``) is not reachable through a request of this suite, and
the reason is where it happens (M12.2, ADR 0038 §6).

**Why not today.** It is raised by ``Assignments.assign`` — inside the walk, after the Guardian and
the ``consume`` — when the decision the walk just obtained is not ``ALLOWED``, has expired at that
very instant, or names ``local``. The walk reaches ``assign`` only with a fresh ``ALLOWED`` decision
for a remote node, so a caller has nothing to send that produces it. It is in ``FAILURES`` for the
fail-safe direction: if it ever escaped, a node would read ``409`` and not a traceback. The
refusals themselves are tested where they are decided: ``tests/executive/test_assignments.py``.

**What would open it.** A decision TTL short enough to expire between ``authorize`` and ``assign``
— a setting a test could choose, like the cap above — or a second producer of assignments that a
route could reach directly. Neither exists, and the second one is exactly what rule 48 forbids.
"""


# ----------------------------------------------------------------------------------------
# The scenarios: one per row, named for the reason it can only be that exception
# ----------------------------------------------------------------------------------------


async def a_task_that_was_never_created(live: Live) -> Response:
    return await live.client.get(f"/tasks/{uuid.uuid4()}")


async def an_answer_that_contradicts_the_one_already_recorded(live: Live) -> Response:
    task_id, approval_id = await waiting(live)
    await live.client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})
    return await live.client.post(f"/tasks/{task_id}/deny", json={"approval_id": approval_id})


async def a_trail_somebody_rewrote_under_the_triggers(live: Live) -> Response:
    await queued(live.client, echo_plan())
    await tamper_with_the_trail(live.ela)
    return await live.client.get("/audit/verify")


async def a_plan_whose_step_depends_on_itself(live: Live) -> Response:
    """Not a DAG, so not a plan: the caller has to change *what* it sent, not *when* (§10)."""
    plan = echo_plan()
    plan["steps"][0]["dependencies"] = [plan["steps"][0]["id"]]
    created = await live.client.post("/tasks", json={"text": "un piano circolare"})
    return await live.client.post(f"/tasks/{created.json()['id']}/plan", json=plan)


async def a_second_plan_for_a_task_that_already_has_one(live: Live) -> Response:
    """A state the task is not in: ``IllegalTransitionError``, which is a ``TaskError``."""
    task_id = await queued(live.client, echo_plan())
    return await live.client.post(f"/tasks/{task_id}/plan", json=echo_plan())


async def a_step_that_already_carries_two_results(live: Live) -> Response:
    """Only the executor counts the results of a step, and only it refuses a step that ran twice.

    The state is prepared through ``ela.results`` because no caller can ask for it: two settled
    results for one step is what a crash in the wrong place would leave, and the refusal is the
    executor's alone — the runner never looks, and the engine has no opinion about it.
    """
    task_id, _ = await waiting(live)
    step_id = (await live.client.get(f"/tasks/{task_id}")).json()["steps"][0]["id"]
    for _ in range(2):
        await live.ela.results.add(
            ExecutionResult(
                id=ExecutionId(live.ela.ids.new_uuid()),
                created_at=live.ela.clock.now(),
                capability_id=CapabilityId("workspace.write_note"),
                status=ExecutionStatus.SUCCEEDED,
                task_id=TaskId(uuid.UUID(task_id)),
                step_id=StepId(uuid.UUID(step_id)),
                tool_name="workspace-notes",
            )
        )
    approvals = (await live.client.get("/approvals")).json()
    await live.client.post(f"/tasks/{task_id}/approve", json={"approval_id": approvals[0]["id"]})
    return await live.client.post(f"/tasks/{task_id}/run")


async def a_run_of_a_task_that_has_no_plan_to_walk(live: Live) -> Response:
    """The runner refuses before the executor is ever called: the state, not the step."""
    created = await live.client.post("/tasks", json={"text": "senza piano"})
    return await live.client.post(f"/tasks/{created.json()['id']}/run")


async def a_second_run_while_the_first_is_still_walking(live: Live) -> Response:
    task_id = await queued(live.client, echo_plan())
    live.app.state.running.add(TaskId(uuid.UUID(task_id)))
    return await live.client.post(f"/tasks/{task_id}/run")


async def a_database_that_does_not_answer_health(live: Live) -> Response:
    """The only row that is not about a task at all, and the only 503."""
    broken = dataclasses.replace(live.ela, repository=BrokenRepository())  # type: ignore[arg-type]
    app = create_app(broken)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
    ) as client:
        return await client.get("/health")


async def a_query_parameter_the_route_itself_refuses(live: Live) -> Response:
    """``limit=0`` never reaches the port: ``Query(ge=1)`` stops it at the edge of the route."""
    return await live.client.get("/audit", params={"limit": 0})


async def a_deadline_with_no_timezone_at_all(live: Live) -> Response:
    """``TaskCreate`` takes a naive datetime; the domain does not (ADR 0003 §4).

    The refusal is a pydantic ``ValidationError`` — a ``ValueError`` — raised while building the
    ``Task``, which is past the route's own validation: nothing else in v0.1 reaches that handler.
    """
    return await live.client.post(
        "/tasks", json={"text": "domani", "deadline": "2030-01-01T00:00:00"}
    )


DECLARATION = {"name": "pc", "os": "WINDOWS", "available_tools": ["core-echo"]}


async def a_node_credential(live: Live) -> dict[str, str]:
    """A node enrolled through the routes, as the header it speaks with (ADR 0037 §3)."""
    code = (await live.client.post("/nodes/enrollments", json={"privacy": "TRUSTED"})).json()
    born = (
        await live.client.post(
            "/nodes/enroll", json=DECLARATION, headers={"Authorization": f"Bearer {code['code']}"}
        )
    ).json()
    return {"Authorization": f"Bearer {born['device_id']}.{born['secret']}"}


async def an_announcement_at_a_revision_the_row_left(live: Live) -> Response:
    node = await a_node_credential(live)
    return await live.client.put("/nodes/me", json=DECLARATION, headers={**node, "If-Match": "0"})


async def an_announcement_that_names_no_revision(live: Live) -> Response:
    node = await a_node_credential(live)
    return await live.client.put("/nodes/me", json=DECLARATION, headers=node)


async def a_revocation_of_this_machine(live: Live) -> Response:
    return await live.client.post(f"/nodes/{LOCAL_DEVICE_ID}/revoke")


async def _delivery(
    live: Live, assignment_id: str, headers: dict[str, str], **envelope: object
) -> Response:
    return await live.client.post(
        "/nodes/work/result",
        json={"assignment_id": assignment_id, **ENVELOPE, **envelope},
        headers=headers,
    )


async def a_delivery_after_the_work_was_cut_short(live: Live) -> Response:
    """The revocation brings the expiry to ``now`` (D17), so a late delivery needs no waiting."""
    _, order, headers, device_id = await taken(live.client, live.ela)
    await live.ela.assignments.cut_short(device_id)
    return await _delivery(live, order["assignment_id"], headers)


async def a_delivery_for_a_task_the_user_stopped(live: Live) -> Response:
    """The node was working while the task closed: what it brings has nowhere to go (§12)."""
    task_id, order, headers, _ = await taken(live.client, live.ela)
    await live.client.post(f"/tasks/{task_id}/cancel", json={"reason": "non mi serve più"})
    return await _delivery(live, order["assignment_id"], headers)


async def a_delivery_of_work_the_core_never_minted(live: Live) -> Response:
    """An id nobody handed out — answered exactly as another node's work is (``NOT_YOUR_WORK``)."""
    _, _, headers, _ = await taken(live.client, live.ela)
    return await _delivery(live, str(uuid.uuid4()), headers)


async def a_renewal_of_work_that_was_only_offered(live: Live) -> Response:
    """Renewing an offer is renewing something nobody took: the same answer as work of another's.

    This is the row of the ports' family — ``AssignmentStateError`` under
    ``AssignmentNotUsableError`` — and it reaches the same sentence as the executor's own refusal,
    which is the point of both.
    """
    _, device_id, headers = await work_for(live.client, live.ela)
    offer = await live.ela.assignments.next_for(DeviceId(uuid.UUID(device_id)))
    assert offer is not None
    return await live.client.post(
        "/nodes/work/renew", json={"assignment_id": str(offer.id)}, headers=headers
    )


async def a_second_envelope_for_work_already_delivered(live: Live) -> Response:
    """Two different claims about what happened: the first one stands (§12)."""
    _, order, headers, _ = await taken(live.client, live.ela)
    await _delivery(live, order["assignment_id"], headers)
    return await _delivery(live, order["assignment_id"], headers, output={"message": "altro"})


RAISED: tuple[Raised, ...] = (
    Raised(
        NotFoundError,
        "GET",
        "/tasks/{task_id}",
        404,
        "not_found",
        "task",
        a_task_that_was_never_created,
    ),
    Raised(
        ApprovalNotAnswerableError,
        "POST",
        "/tasks/{task_id}/deny",
        409,
        "not_answerable",
        "already GRANTED",
        an_answer_that_contradicts_the_one_already_recorded,
    ),
    Raised(
        AuditChainError,
        "GET",
        "/audit/verify",
        409,
        "tampered",
        "ALTERED_ROW",
        a_trail_somebody_rewrote_under_the_triggers,
    ),
    Raised(
        GraphError,
        "POST",
        "/tasks/{task_id}/plan",
        422,
        "invalid",
        "cyclic dependency between steps",
        a_plan_whose_step_depends_on_itself,
    ),
    Raised(
        TaskError,
        "POST",
        "/tasks/{task_id}/plan",
        409,
        "conflict",
        "the task already has plan",
        a_second_plan_for_a_task_that_already_has_one,
    ),
    Raised(
        ExecutorError,
        "POST",
        "/tasks/{task_id}/run",
        409,
        "conflict",
        "a step runs once",
        a_step_that_already_carries_two_results,
    ),
    Raised(
        RunnerError,
        "POST",
        "/tasks/{task_id}/run",
        409,
        "conflict",
        "a plan is walked from QUEUED or EXECUTING",
        a_run_of_a_task_that_has_no_plan_to_walk,
    ),
    Raised(
        TaskAlreadyRunningError,
        "POST",
        "/tasks/{task_id}/run",
        409,
        "already_running",
        "already running",
        a_second_run_while_the_first_is_still_walking,
    ),
    Raised(
        DatabaseUnavailableError,
        "GET",
        "/health",
        503,
        "database_unavailable",
        "database",
        a_database_that_does_not_answer_health,
    ),
    Raised(
        RequestValidationError,
        "GET",
        "/audit",
        422,
        "invalid",
        "query.limit: Input should be greater than or equal to 1",
        a_query_parameter_the_route_itself_refuses,
    ),
    Raised(
        ValueError,
        "POST",
        "/tasks",
        422,
        "invalid",
        "timezone-aware",
        a_deadline_with_no_timezone_at_all,
    ),
    Raised(
        IdentityConflictError,
        "PUT",
        "/nodes/me",
        412,
        "identity_conflict",
        "two processes claim to be it",
        an_announcement_at_a_revision_the_row_left,
    ),
    Raised(
        LocalDeviceNotRevocableError,
        "POST",
        "/nodes/{device_id}/revoke",
        409,
        "not_revocable",
        "cannot be revoked",
        a_revocation_of_this_machine,
    ),
    Raised(
        RevisionRequiredError,
        "PUT",
        "/nodes/me",
        428,
        "revision_required",
        "If-Match",
        an_announcement_that_names_no_revision,
    ),
    Raised(
        AssignmentExpiredError,
        "POST",
        "/nodes/work/result",
        410,
        "assignment.expired",
        "it expired at",
        a_delivery_after_the_work_was_cut_short,
    ),
    Raised(
        AssignmentVoidError,
        "POST",
        "/nodes/work/result",
        410,
        "assignment.void",
        "nothing left to deliver into",
        a_delivery_for_a_task_the_user_stopped,
    ),
    Raised(
        WorkNotYoursError,
        "POST",
        "/nodes/work/result",
        404,
        "not_assigned",
        NOT_YOUR_WORK,
        a_delivery_of_work_the_core_never_minted,
    ),
    Raised(
        AssignmentNotUsableError,
        "POST",
        "/nodes/work/renew",
        404,
        "not_assigned",
        NOT_YOUR_WORK,
        a_renewal_of_work_that_was_only_offered,
    ),
    Raised(
        DeliveryConflictError,
        "POST",
        "/nodes/work/result",
        409,
        "delivery.conflict",
        "already delivered with another envelope",
        a_second_envelope_for_work_already_delivered,
    ),
)


async def waiting(live: Live) -> tuple[str, str]:
    """A task stopped on a request for consent, and the id of the request."""
    task_id = await queued(live.client, note_plan())
    await live.client.post(f"/tasks/{task_id}/run")
    pending = (await live.client.get("/approvals")).json()
    assert len(pending) == 1
    return task_id, pending[0]["id"]


@pytest.fixture
def live(client: AsyncClient, ela: Ela, app: FastAPI) -> Live:
    return Live(client, ela, app)


@pytest.mark.parametrize("row", RAISED, ids=lambda row: row.exception.__name__)
async def test_every_failure_of_the_table_is_answered_that_way_by_the_application(
    row: Raised, live: Live
) -> None:
    response = await row.scenario(live)

    assert response.status_code == row.status, response.text
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == row.code
    assert row.message in body["error"]["message"], body["error"]["message"]


DECLARED: dict[type[Exception], str] = {
    AlreadyExistsError: ALREADY_EXISTS,
    AssignmentAtCapError: AT_CAP,
    AssignmentRefusedError: REFUSED_ASSIGNMENT,
}
"""The rows no request of this suite can reach, each with its own reason and its own expiry.

One was here before M12.2; the two the work protocol adds are both about **time and place**: a cap
that a request cannot reach without waiting out real seconds, and a refusal that happens inside the
walk rather than at the edge of a route. Neither is faked with a mounted route or a patched clock —
a scenario invented to satisfy a census proves that the census works.
"""


def test_every_row_of_failures_is_observed_or_declared() -> None:
    """The closed world: a row added to ``FAILURES`` without a scenario or a reason fails here."""
    observed = {row.exception for row in RAISED}
    assert observed | set(DECLARED) == {failure.exception for failure in FAILURES}
    assert not observed & set(DECLARED)
    assert len(RAISED) == len(FAILURES) - len(DECLARED)


@pytest.mark.parametrize("declared", list(DECLARED), ids=lambda one: one.__name__)
def test_every_unreachable_row_says_why_today_and_what_would_open_it_tomorrow(
    declared: type[Exception],
) -> None:
    """Declared, not faked (decision 3): every deferral carries its own expiry condition, and
    names where the behaviour *is* tested so the row is not an excuse for a hole."""
    reason = DECLARED[declared]

    assert "**Why not today.**" in reason and "**What would open it.**" in reason
    assert "tests/" in reason or "IdGenerator" in reason


def test_the_row_that_was_unreachable_before_the_work_protocol_still_says_its_own_why() -> None:
    assert "IdGenerator" in ALREADY_EXISTS
    assert "StepIn.id" in ALREADY_EXISTS  # the one id a caller chooses, and why it does not count
    assert "idempotency" in ALREADY_EXISTS


# ----------------------------------------------------------------------------------------
# The seven statuses no test produced (the probe of M9.4)
# ----------------------------------------------------------------------------------------


async def a_plan_sent_to_a_task_that_does_not_exist(live: Live) -> Response:
    return await live.client.post(f"/tasks/{uuid.uuid4()}/plan", json=echo_plan())


async def a_run_asked_of_a_task_that_does_not_exist(live: Live) -> Response:
    return await live.client.post(f"/tasks/{uuid.uuid4()}/run")


async def a_no_to_a_request_that_does_not_exist(live: Live) -> Response:
    return await live.client.post(
        f"/tasks/{uuid.uuid4()}/deny", json={"approval_id": str(uuid.uuid4())}
    )


async def a_stop_asked_of_a_task_that_does_not_exist(live: Live) -> Response:
    return await live.client.post(f"/tasks/{uuid.uuid4()}/cancel", json={})


async def a_stop_asked_of_a_task_that_has_already_finished(live: Live) -> Response:
    """Stopping is the user's (§65), and a task that is done cannot be stopped.

    Not a *second* cancel: that one is idempotent and answers 200 with the task as it stands —
    asking twice for something that already happened is not a conflict. What has no answer is
    stopping something that finished on its own.
    """
    task_id = await queued(live.client, echo_plan())
    walked = await live.client.post(f"/tasks/{task_id}/run")
    assert walked.json()["task"]["state"] == "COMPLETED", walked.text
    return await live.client.post(f"/tasks/{task_id}/cancel", json={"reason": "troppo tardi"})


async def a_task_id_that_is_not_a_uuid(live: Live) -> Response:
    return await live.client.get("/tasks/non-e-un-uuid")


async def results_asked_for_an_id_that_is_not_a_uuid(live: Live) -> Response:
    return await live.client.get("/tasks/non-e-un-uuid/results")


MISSING: tuple[Missing, ...] = (
    Missing("POST", "/tasks/{task_id}/plan", 404, a_plan_sent_to_a_task_that_does_not_exist),
    Missing("POST", "/tasks/{task_id}/run", 404, a_run_asked_of_a_task_that_does_not_exist),
    Missing("POST", "/tasks/{task_id}/deny", 404, a_no_to_a_request_that_does_not_exist),
    Missing("POST", "/tasks/{task_id}/cancel", 404, a_stop_asked_of_a_task_that_does_not_exist),
    Missing(
        "POST", "/tasks/{task_id}/cancel", 409, a_stop_asked_of_a_task_that_has_already_finished
    ),
    Missing("GET", "/tasks/{task_id}", 422, a_task_id_that_is_not_a_uuid),
    Missing("GET", "/tasks/{task_id}/results", 422, results_asked_for_an_id_that_is_not_a_uuid),
)
"""The seven ``(method, route, status)`` a probe over every request ``tests/api`` and
``tests/cli`` make found nobody producing (M9.4). Four routes answered no 404 at all, ``cancel``
answered nothing but 200, and the two routes that take an id in the path had never been given a
malformed one — the shape of hole a suite grown by feature leaves: the happy path of each route
and the refusals somebody happened to think of."""


@pytest.mark.parametrize(
    "hole", MISSING, ids=lambda hole: f"{hole.method} {hole.route} -> {hole.status}"
)
async def test_the_statuses_no_test_used_to_produce(hole: Missing, live: Live) -> None:
    response = await hole.scenario(live)

    assert response.status_code == hole.status, response.text
    assert set(response.json()["error"]) == {"code", "message"}


def test_every_route_the_two_tables_name_is_a_route_the_application_serves(app: FastAPI) -> None:
    """A renamed route leaves the tables naming something nobody serves: caught here.

    Both tables carry the ``(method, route)`` they exercise, and neither can go stale quietly —
    which is the difference between a list of expectations and a list of intentions.
    """
    served = set(served_paths(app))
    named = {(row.method, row.route) for row in RAISED} | {
        (hole.method, hole.route) for hole in MISSING
    }
    assert named <= served, named - served


TOLD_APART = ("conflict", "invalid")
"""The shared codes whose rows must be distinguishable by their message."""
SAID_THE_SAME_WAY = ("not_assigned",)
"""And the one whose rows must **not** be (M12.2, ADR 0038 §12).

Work the Core never minted, work of another node and work no longer taken share the status *and the
sentence*, because a node that could tell them apart could map the assignments of the others — the
reason ADR 0023 §7 answers ``401`` and not ``404`` to a path that does not exist. The audit keeps
the difference, where the user reads and nodes do not.
"""


def test_the_shared_codes_are_told_apart_by_something_other_than_the_code() -> None:
    """``conflict`` is three exceptions and ``invalid`` is three others (ADR 0023 §10).

    A caller branches on the code, and that is the point of the code — but a *test* that only
    checked status and code would pass with the wrong exception raised, and would go on passing
    if two of the three stopped happening entirely. So every row of a shared code carries a
    fragment of the message that only it writes, and this is what keeps those fragments from
    quietly becoming the same string.
    """
    shared = [code for code in {row.code for row in RAISED} if _rows_with(code) > 1]
    assert sorted(shared) == sorted(TOLD_APART + SAID_THE_SAME_WAY)
    for code in TOLD_APART:
        fragments = [row.message for row in RAISED if row.code == code]
        assert len(set(fragments)) == len(fragments), code
        for one in fragments:
            assert sum(one in other for other in fragments) == 1, one


def test_the_refusals_of_the_work_are_said_the_same_way_on_purpose() -> None:
    """The exception to the rule above, and the only one: a node learns nothing from *which* way
    the work is not its own. Both rows carry the overriding sentence of ``FAILURES`` itself, so the
    day somebody gives one of them a message of its own, this fails."""
    for code in SAID_THE_SAME_WAY:
        rows = [row for row in RAISED if row.code == code]
        assert len(rows) > 1
        assert {row.message for row in rows} == {NOT_YOUR_WORK}
        overriding = {failure.message for failure in FAILURES if failure.code == code}
        assert overriding == {NOT_YOUR_WORK}


def _rows_with(code: str) -> int:
    return sum(row.code == code for row in RAISED)
