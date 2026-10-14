"""``browser.guided_as_you``: the guided session of M14.3, with the profile (M13.9, ADR 0063 §6).

The session is the same — the room, the gateway, the budget, a child task for every gesture —,
and what is under test here is **what makes it another kind**: its capability, the capabilities
its two tools ask for, the one site it names, what it tells the user leaves the machine, and the
line more its model is given. The capability and the gestures of a session are a datum now, and
the room refuses a gesture that is not its session's own.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import ErrorMetadata, ExecutionStatus, TaskId, TaskState
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_ACT_AS_YOU,
    BROWSER_GUIDED,
    BROWSER_GUIDED_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_READ,
    BROWSER_READ_AS_YOU,
)
from ela.ports import Gesture, SessionEnd, SessionGestures, SessionHost, SessionPlan
from ela.testing.fakes import (
    FakeAgentSession,
    FakeStop,
    finished,
    session_tool_names,
)
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.guided import (
    EMPTY_SESSION,
    INSTRUCTIONS,
    LOGIN_DESCRIPTION,
    LOOKS_OF_A_LOGIN,
    SENDS,
    SENDS_AS_YOU,
    SESSION_AS_YOU,
    BrowserGuidedVerifier,
)
from tests.domain.examples import STEP_ID, TASK_ID
from tests.tools.guided import ARGUMENTS, GuidedWorld, guided_world

READ = {"site": "www.youtube.com", "path": "/", "purpose": "guardare"}


class Recorded:
    """What the room was asked, in order. The session opens in the room itself; a gesture stops
    here, with an answer of the test's — walking one wants a task, and that is the room's test
    (``tests/api/test_guided_room.py``)."""

    def __init__(self, world: GuidedWorld) -> None:
        self.opened: list[dict[str, Any]] = []
        self.gestures: list[str] = []
        room = world.room
        open_ = room.open

        async def opening(task_id: Any, step_id: Any, **named: Any) -> Any:
            self.opened.append(named)
            return await open_(task_id, step_id, **named)

        async def asked(session: Any, capability: Any, arguments: Any) -> Gesture:
            self.gestures.append(str(capability))
            return Gesture("read", TaskState.COMPLETED, acted=False)

        room.open, room.gesture = opening, asked  # type: ignore[method-assign]


def test_the_two_kinds_of_session_and_the_tool_and_the_verifier_of_each() -> None:
    world, as_you = guided_world(), guided_world(kind=SESSION_AS_YOU)

    assert world.tool.capability_id == BROWSER_GUIDED and world.tool.name == "browser-guided"
    assert as_you.tool.capability_id == BROWSER_GUIDED_AS_YOU
    assert as_you.tool.name == "browser-guided-as-you"
    assert type(as_you.tool) is type(world.tool), "one tool, and the kind of session is a datum"
    verifier = BrowserGuidedVerifier(as_you.room, as_you.session, None, kind=SESSION_AS_YOU)  # type: ignore[arg-type]
    assert verifier.capability_id == BROWSER_GUIDED_AS_YOU
    assert verifier.name == "browser-guided-as-you-verifier"
    assert SESSION_AS_YOU.gestures == SessionGestures(
        read=BROWSER_READ_AS_YOU, act=BROWSER_ACT_AS_YOU, login=BROWSER_LOGIN
    )
    assert EMPTY_SESSION.gestures == SessionGestures(read=BROWSER_READ, act=BROWSER_ACT)
    assert EMPTY_SESSION.gestures.login is None


def test_the_tools_of_a_session_are_called_read_and_act_whatever_they_ask_for() -> None:
    """The model sees ``read`` and ``act`` in both: what changes is the capability behind them —
    and, with the profile only, ``login`` since M13.10 (ADR 0065 §4)."""
    gestures = SESSION_AS_YOU.gestures

    assert gestures.named("read") == BROWSER_READ_AS_YOU
    assert gestures.named("act") == BROWSER_ACT_AS_YOU
    assert gestures.named("login") == BROWSER_LOGIN
    assert EMPTY_SESSION.gestures.named("login") is None
    assert gestures.named("browser.read") is None


async def test_a_session_with_the_profile_that_names_two_sites_is_refused_before_the_question() -> (
    None
):
    """Decision 30, and criterion 22: one site — «it would start» says so before any yes, and a
    call that reached the tool all the same launches nothing."""
    world = guided_world(kind=SESSION_AS_YOU)
    two = {**ARGUMENTS, "sites": ["www.youtube.com", "example.com"]}

    prospect = await world.tool.prospect(two)
    result = await world.tool.execute(world.decision, two, FakeStop())

    assert prospect.guided is None and prospect.refusal is not None
    assert prospect.refusal.code == ARGUMENTS_INVALID
    assert "names one site, and this one names 2" in prospect.refusal.message
    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert world.session.launched == []


async def test_a_session_on_the_empty_browser_still_names_as_many_sites_as_it_likes() -> None:
    world = guided_world()

    prospect = await world.tool.prospect({**ARGUMENTS, "sites": ["www.youtube.com", "example.com"]})

    assert prospect.refusal is None and prospect.guided is not None
    assert prospect.guided.sites == ("www.youtube.com", "example.com")


async def test_the_question_says_that_what_goes_to_the_model_is_the_user_s_own_content() -> None:
    """§57, rewritten for this session (ADR 0063 §6): the same things leave, and among them the
    text of pages the user is signed in to."""
    as_you = (await guided_world(kind=SESSION_AS_YOU).tool.prospect(ARGUMENTS)).guided
    empty = (await guided_world().tool.prospect(ARGUMENTS)).guided

    assert as_you is not None and empty is not None
    assert empty.sends == SENDS.format("fake")
    assert as_you.sends == SENDS_AS_YOU.format("fake")
    assert "your own content — your mail, your messages" in as_you.sends
    assert "your own content" not in empty.sends
    # Decision 32 of the review of M13.10's SPEC: what a login gives back, and what it never does.
    assert (
        "the text of the pages read as you, and of a login where its page ended, its status and "
        "whether its form was still there — never the entry, the username or the password"
    ) in as_you.sends


async def test_the_model_of_a_session_with_the_profile_is_told_one_line_more() -> None:
    """Inside its site a model may open any address as the user: it is told not to open one that
    confirms, cancels, unsubscribes or signs out unless the goal asks for exactly that."""
    world = guided_world(kind=SESSION_AS_YOU)

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    ((_, plan),) = world.session.launched
    assert plan.instructions.startswith(
        INSTRUCTIONS.format(sites="www.youtube.com", looks=world.arguments["looks"])
    )
    assert "opening an address may act as the user" in plan.instructions
    assert "confirms, cancels, unsubscribes or signs out unless the goal asks" in plan.instructions
    assert "empty" not in plan.instructions


async def test_the_gestures_of_a_session_with_the_profile_are_the_profile_s() -> None:
    """The session opens as its own capability, with its own pair; and what its model calls
    ``read`` reaches the room as ``browser.read_as_you`` — never as the empty browser's."""

    async def reads_and_acts(plan: SessionPlan, host: SessionHost) -> SessionEnd:
        await host.started(tuple(sorted(session_tool_names(plan.tools))))
        await host.gesture("read", dict(READ))
        await host.gesture("act", {**READ, "fill": [], "click": "button", "expect_text": "ok"})
        await host.gesture("login", dict(READ))
        return finished()

    world = guided_world(session=FakeAgentSession(reads_and_acts), kind=SESSION_AS_YOU)
    seen = Recorded(world)

    await world.tool.execute(world.decision, world.arguments, FakeStop())

    (opened,) = seen.opened
    assert opened["capability"] == BROWSER_GUIDED_AS_YOU
    assert opened["gestures"] == SESSION_AS_YOU.gestures
    assert opened["sites"] == ("www.youtube.com",)
    assert seen.gestures == [BROWSER_READ_AS_YOU, BROWSER_ACT_AS_YOU, BROWSER_LOGIN]


async def test_the_room_refuses_a_gesture_that_is_not_its_session_s_own() -> None:
    """Both ways: a session with the profile does not make a gesture on the empty browser, nor a
    session on the empty browser one with the profile — and the empty one makes no login (the
    one with the profile does, since M13.10). Refused by the room, before a task is planned for
    it, and counted among the refused."""
    for kind, foreign in (
        (SESSION_AS_YOU, (BROWSER_READ, BROWSER_ACT, BROWSER_GUIDED_AS_YOU)),
        (EMPTY_SESSION, (BROWSER_READ_AS_YOU, BROWSER_ACT_AS_YOU, "browser.login")),
    ):
        world = guided_world(kind=kind)
        opened = await world.room.open(
            TaskId(TASK_ID),
            STEP_ID,
            capability=kind.capability,
            sites=("www.youtube.com",),
            tools=await world.session.tools(kind.tools),
            gestures=kind.gestures,
        )
        assert not isinstance(opened, ErrorMetadata)

        for capability in foreign:
            made = await world.room.gesture(STEP_ID, capability, dict(READ))  # type: ignore[arg-type]

            assert made.state is TaskState.DENIED and made.acted is False, (kind, capability)
            assert "no such gesture" in made.text

        tally = await world.room.close(STEP_ID, reason="the test is over")
        assert tally.refused == len(foreign)


# ----------------------------------------------------------------------------------------
# The tool login (M13.10, ADR 0065 §4)
# ----------------------------------------------------------------------------------------


def test_the_session_with_the_profile_offers_login_and_the_empty_one_does_not() -> None:
    assert [one.name for one in SESSION_AS_YOU.tools] == ["read", "act", "login"]
    assert [one.name for one in EMPTY_SESSION.tools] == ["read", "act"]
    (login,) = [one for one in SESSION_AS_YOU.tools if one.name == "login"]
    assert login.description == LOGIN_DESCRIPTION
    assert dict(login.schema)["required"] == ["site"]
    assert set(dict(login.schema)["properties"]) == {"site", "path", "expect_text"}


def test_the_model_is_told_a_login_costs_two_gestures_and_never_shows_a_password() -> None:
    """Decision 45: a login asked by the model counts two looks, and the description says so."""
    assert LOOKS_OF_A_LOGIN == 2
    assert "It costs two gestures" in LOGIN_DESCRIPTION
    assert "never give or see the password, the entry of the vault or the username" in (
        LOGIN_DESCRIPTION
    )
    assert "use the tool login" in SESSION_AS_YOU.instructions


@pytest.mark.parametrize(("looks", "stopped"), [(3, False), (2, True)], ids=["fits", "past"])
async def test_a_login_counts_two_of_the_session_s_gestures(looks: int, stopped: bool) -> None:
    async def reads_then_logs_in(plan: SessionPlan, host: SessionHost) -> SessionEnd:
        await host.started(tuple(sorted(session_tool_names(plan.tools))))
        await host.gesture("read", dict(READ))
        said.append(await host.gesture("login", {"site": "www.youtube.com"}))
        return finished()

    said: list[str] = []
    world = guided_world(session=FakeAgentSession(reads_then_logs_in), kind=SESSION_AS_YOU)
    seen = Recorded(world)

    await world.tool.execute(world.decision, {**world.arguments, "looks": looks}, FakeStop())

    if stopped:
        assert seen.gestures == [BROWSER_READ_AS_YOU]
        assert said == [f"ELA stops the session: the {looks} gestures of this session are used"]
    else:
        assert seen.gestures == [BROWSER_READ_AS_YOU, BROWSER_LOGIN]


async def test_the_room_refuses_a_login_whose_arguments_are_not_the_model_s_three() -> None:
    """The model gives the site, the path and a text — never a selector, an entry or a value: the
    room refuses anything more by itself, before a child is born."""
    world = guided_world(kind=SESSION_AS_YOU)
    opened = await world.room.open(
        TaskId(TASK_ID),
        STEP_ID,
        capability=SESSION_AS_YOU.capability,
        sites=("www.youtube.com",),
        tools=await world.session.tools(SESSION_AS_YOU.tools),
        gestures=SESSION_AS_YOU.gestures,
    )
    assert not isinstance(opened, ErrorMetadata)

    for arguments in (
        {"site": "www.youtube.com", "password_field": "#word"},
        {"site": "www.youtube.com", "entry": "an-id"},
        {"path": "/login"},
        {"site": "www.youtube.com", "expect_text": ""},
    ):
        made = await world.room.gesture(STEP_ID, BROWSER_LOGIN, arguments)  # type: ignore[arg-type]

        assert made.state is TaskState.DENIED and made.acted is False, arguments
        assert "not a call ELA can plan" in made.text

    tally = await world.room.close(STEP_ID, reason="the test is over")
    assert tally.refused == 4 and tally.looks == 4, "each refused, and no child was born"
