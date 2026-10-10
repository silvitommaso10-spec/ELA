"""The executor and the cover of a session (M13.9, decision 29).

A step a guided session's model wrote is ``MEDIUM`` when it reads with the profile, and what lets
it run without a question is **the room's word, read when the step is decided**: «this session is
open». The executor asks the room — nobody else builds that word, and no tool does —, and hands
it to the Guardian only for the capability the session's own capability declares it covers.

So: an open session's read runs with no question, no grant born and none spent; a session that is
over covers nothing, and the same read asks; an ``act`` of the session asks as it always did,
because no session covers a row that asks at every use; and a plan no session wrote never reaches
the room at all.
"""

from __future__ import annotations

from typing import Any

from ela.domain import (
    CapabilityId,
    CapabilitySpec,
    PermissionOutcome,
    PlanAuthor,
    PlanAuthorKind,
    PlanId,
    RiskLevel,
    StepId,
    Task,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.permissions import Rule, browser_act, browser_read
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool
from tests.executive.support import OK, World, fake_verifier, world
from tests.permissions.policy_support import GUIDED, GUIDED_ARGS, MODEL

SITES = ("posta.example", "video.example")
READ: CapabilitySpec = browser_read(SITES).model_copy(
    update={
        "id": CapabilityId("test.read_as_you"),
        "risk": RiskLevel.MEDIUM,
        "requires_authorization": True,
    }
)
ACT: CapabilitySpec = browser_act(SITES)
LOW_READ: CapabilitySpec = browser_read(SITES)
READ_ARGS: dict[str, Any] = {"site": "posta.example", "path": "/inbox", "purpose": "leggere"}
ACT_ARGS: dict[str, Any] = {
    "site": "posta.example",
    "path": "/send",
    "fill": [["#to", "x"]],
    "click": "#send",
    "expect_text": "sent",
    "purpose": "mandare",
}
SESSION_ID = CapabilityId("test.session")


def session_capability() -> CapabilitySpec:
    """Built in a test and not at import: until M13.9 a capability could not say what it covers."""
    from ela.domain import Covered

    declared = Covered(capability_id=READ.id, input_schema=READ.input_schema)
    return GUIDED.model_copy(update={"id": SESSION_ID, "covers": declared})


class Room:
    """The room, as far as the executor knows it: asked for its word about one session."""

    def __init__(self) -> None:
        self.open: dict[StepId, Any] = {}
        self.asked: list[StepId] = []

    async def attest(self, session: StepId) -> Any:
        self.asked.append(session)
        return self.open.get(session)


def a_world(room: Room | None) -> World:
    clock, ids = FakeClock(), FakeIdGenerator()
    specs = (session_capability(), READ, ACT, LOW_READ)
    tools = [
        FakeTool(spec.id, clock, ids, name=f"fake-{spec.id}", output={"ok": True}) for spec in specs
    ]
    verifiers = [fake_verifier(spec.id) for spec in specs]
    options: dict[str, Any] = {} if room is None else {"sessions": room}
    w = world(tools=tools, verifiers=verifiers, catalogue=specs, **options)
    w.fake_tools = {tool.capability_id: tool for tool in tools}
    w.fake_verifiers = {verifier.capability_id: verifier for verifier in verifiers}
    return w


async def a_session(w: World, room: Room | None) -> tuple[Task, TaskStep]:
    """A task whose step is the session, running — and, in the room, open."""
    from ela.domain import SessionCover

    task, step = await w.running(SESSION_ID, arguments=GUIDED_ARGS)
    if room is not None:
        room.open[step.id] = SessionCover(
            session=step.id, task_id=task.id, capability_id=SESSION_ID, sites=SITES
        )
    return task, step


async def a_gesture(
    w: World,
    session: tuple[Task, TaskStep],
    capability: CapabilitySpec,
    arguments: dict[str, Any],
    *,
    number: int = 1,
    author: PlanAuthor | None = None,
) -> tuple[Task, TaskStep]:
    """The child a session's gesture is: its plan written by the session, its step running."""
    parent, at = session
    child = await w.engine.create_child(
        parent.id, key=f"gesture-{number}/{at.id}", goal="a gesture"
    )
    await w.engine.start_planning(child.id)
    step = TaskStep(
        id=StepId(w.ids.new_uuid()),
        created_at=w.now,
        goal="what the model of the session asked for",
        required_capabilities=(capability.id,),
        arguments=arguments,
        risk=capability.risk,
        expected_result="done",
        success_conditions=(OK,),
        requires_authorization=capability.requires_authorization,
        within=SITES,
    )
    written = PlanAuthor(by=PlanAuthorKind.SESSION, session=at.id, model=MODEL)
    plan = TaskPlan(
        id=PlanId(w.ids.new_uuid()),
        created_at=w.now,
        task_id=child.id,
        goal="a gesture",
        steps=(step,),
        author=written if author is None else author,
    )
    await w.engine.plan(child.id, plan)
    await w.engine.queue(child.id)
    child = await w.engine.start(child.id, device_id=w.node.id)
    await w.engine.start_step(child.id, step.id, device_id=w.node.id)
    return child, step


async def test_a_read_an_open_session_wrote_runs_with_no_question_and_no_grant() -> None:
    room = Room()
    w = a_world(room)
    session = await a_session(w, room)
    child, step = await a_gesture(w, session, READ, READ_ARGS)

    execution = await w.execute(child.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.decision.metadata["rule"] == Rule.SESSION.value
    assert execution.decision.metadata["session"] == str(session[1].id)
    assert execution.approval is None, "nobody was asked"
    assert execution.authorization is None, "no grant was born, and none was spent"
    assert execution.result is not None and execution.result.authorization_id is None
    assert w.tool(READ.id).calls != ()
    assert room.asked == [session[1].id]


async def test_the_room_is_asked_when_the_step_is_decided_and_a_closed_session_covers_nothing() -> (
    None
):
    """Never from a copy: the session was open when the gesture was written, and is over when
    its step is decided. The read asks, as a ``MEDIUM`` always did."""
    room = Room()
    w = a_world(room)
    session = await a_session(w, room)
    child, step = await a_gesture(w, session, READ, READ_ARGS)
    room.open.clear()

    execution = await w.execute(child.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.decision.metadata["rule"] == Rule.APPROVAL_UNLESS_AUTHORIZED.value
    assert execution.approval is not None
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert w.tool(READ.id).calls == ()
    assert room.asked == [session[1].id], "asked now, and the answer was no"


async def test_an_act_of_the_session_asks_as_it_always_did() -> None:
    """``HIGH`` asks at every use. The executor does not hand the room's word to the Guardian for
    a capability the session does not declare it covers: the act **asks**, and is not denied."""
    room = Room()
    w = a_world(room)
    session = await a_session(w, room)
    child, step = await a_gesture(w, session, ACT, ACT_ARGS)

    execution = await w.execute(child.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.decision.metadata["rule"] == Rule.APPROVAL_EVERY_USE.value
    assert execution.approval is not None
    assert w.tool(ACT.id).calls == ()


async def test_a_plan_no_session_wrote_never_reaches_the_room() -> None:
    room = Room()
    w = a_world(room)
    session = await a_session(w, room)
    by_hand = PlanAuthor(by=PlanAuthorKind.HAND)
    child, step = await a_gesture(w, session, READ, READ_ARGS, author=by_hand)

    execution = await w.execute(child.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert room.asked == [], "a hand wrote it: there is no session to ask about"


async def test_what_does_not_ask_is_not_shown_to_the_room_s_word_either() -> None:
    """A gesture on a row that asks nobody is allowed by its row: the room's word would be a fact
    too many, and the Guardian denies a fact that does not fit."""
    room = Room()
    w = a_world(room)
    session = await a_session(w, room)
    child, step = await a_gesture(w, session, LOW_READ, READ_ARGS)

    execution = await w.execute(child.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.decision.metadata["rule"] == Rule.ALLOW_WITHIN_SCOPE.value
    assert "session" not in execution.decision.metadata


async def test_an_executor_with_no_room_asks() -> None:
    w = a_world(None)
    session = await a_session(w, None)
    child, step = await a_gesture(w, session, READ, READ_ARGS)

    execution = await w.execute(child.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL


async def test_a_session_of_a_capability_the_catalogue_does_not_know_covers_nothing() -> None:
    """The room's word names the capability of the session; one the catalogue does not hold
    declares nothing. The executor hands nothing over, and the read asks."""
    room = Room()
    w = a_world(room)
    session = await a_session(w, room)
    room.open[session[1].id] = room.open[session[1].id].model_copy(
        update={"capability_id": CapabilityId("test.unknown")}
    )
    child, step = await a_gesture(w, session, READ, READ_ARGS)

    execution = await w.execute(child.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.approval is not None
