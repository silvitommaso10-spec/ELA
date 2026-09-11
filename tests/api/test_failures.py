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

The one row that cannot be reached is declared instead of faked, in :data:`ALREADY_EXISTS`.
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
from ela.api.app import FAILURES
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
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    StepId,
    TaskId,
)
from ela.executive import ExecutorError, RunnerError
from ela.ports import (
    AlreadyExistsError,
    ApprovalNotAnswerableError,
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
        409,
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


def test_every_row_of_failures_is_observed_or_declared() -> None:
    """The closed world: a row added to ``FAILURES`` without a scenario fails here."""
    observed = {row.exception for row in RAISED}
    assert observed | {AlreadyExistsError} == {failure.exception for failure in FAILURES}
    assert len(RAISED) == len(FAILURES) - 1


def test_the_unreachable_row_says_why_today_and_what_would_open_it_tomorrow() -> None:
    """Declared, not faked (decision 3): the deferral carries its own expiry condition."""
    assert "**Why not today.**" in ALREADY_EXISTS and "**What would open it.**" in ALREADY_EXISTS
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


def test_the_two_shared_codes_are_told_apart_by_something_other_than_the_code() -> None:
    """``conflict`` is three exceptions and ``invalid`` is three others (ADR 0023 §10).

    A caller branches on the code, and that is the point of the code — but a *test* that only
    checked status and code would pass with the wrong exception raised, and would go on passing
    if two of the three stopped happening entirely. So every row of a shared code carries a
    fragment of the message that only it writes, and this is what keeps those fragments from
    quietly becoming the same string.
    """
    shared = [code for code in {row.code for row in RAISED} if _rows_with(code) > 1]
    assert sorted(shared) == ["conflict", "invalid"]
    for code in shared:
        fragments = [row.message for row in RAISED if row.code == code]
        assert len(set(fragments)) == len(fragments), code
        for one in fragments:
            assert sum(one in other for other in fragments) == 1, one


def _rows_with(code: str) -> int:
    return sum(row.code == code for row in RAISED)
