"""``GET /context``: the answer to §44, and what this ELA cannot answer (M10.4, ADR 0032).

Two things are asserted here that are asserted nowhere else.

The first is the **key set of every section**. ``ContextOut`` reuses the domain's models instead
of transcribing them, which is a declared exception to the rule ``schemas.py`` gives itself (ADR
0032 §13); the guarantee that rule protects — *a field added to the domain must not leave the
machine because nobody noticed* — is kept here instead, derived rather than copied. A field added
to a context model fails this file until somebody decides it may go out.

The second is that all seven questions of §44 come back, with the absences named. A route that
answered five of seven and said nothing about the other two would be the failure this milestone
exists to prevent.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from ela.domain import ContextQuestion, ContextSource
from tests.api.support import AUTHORIZED, BASE  # noqa: F401 — imported for parity with siblings

ACTIVITY_KEYS = {
    "observed_at",
    "microphone",
    "camera",
    "permissions",
    "display_count",
    "display_asleep",
    "screen_locked",
    "on_console",
    "idle_seconds",
    "running_bundle_ids",
    "frontmost_bundle_id",
    "window_count",
}
WORK_KEYS = {"tasks", "shown", "total", "states", "pending_approvals"}
DEADLINES_KEYS = {"deadlines", "shown", "total"}
RECENT_KEYS = {"since", "changes", "events"}
SNAPSHOT_KEYS = {"at", "activity", "device", "work", "deadlines", "recent", "questions"}


async def context(client: AsyncClient) -> dict[str, Any]:
    answer = await client.get("/context")
    assert answer.status_code == 200
    return dict(answer.json())


async def test_the_route_needs_the_token_like_every_other(anonymous: AsyncClient) -> None:
    assert (await anonymous.get("/context")).status_code == 401


# ----------------------------------------------------------------------------------------
# What leaves the machine, key by key
# ----------------------------------------------------------------------------------------


async def test_the_snapshot_carries_exactly_these_sections(client: AsyncClient) -> None:
    assert set(await context(client)) == SNAPSHOT_KEYS


@pytest.mark.parametrize(
    "section, keys",
    [
        ("activity", ACTIVITY_KEYS),
        ("work", WORK_KEYS),
        ("deadlines", DEADLINES_KEYS),
        ("recent", RECENT_KEYS),
    ],
)
async def test_every_section_carries_exactly_these_keys(
    client: AsyncClient, section: str, keys: set[str]
) -> None:
    """The derived half of ``schemas.py``'s promise (ADR 0032 §13)."""
    assert set((await context(client))[section]) == keys


def every_key(value: Any) -> set[str]:
    """Every key of a JSON body, at every depth — read, not guessed at from a repr."""
    if isinstance(value, dict):
        return set(value) | {key for one in value.values() for key in every_key(one)}
    if isinstance(value, list):
        return {key for one in value for key in every_key(one)}
    return set()


async def test_the_snapshot_never_carries_screen_text_or_a_capture(client: AsyncClient) -> None:
    """Answering "what is the user doing" by reading the screen costs a capability, and what
    costs a capability is not context (architecture rule 38).

    Read as keys and not as a substring of the body: ``lines`` is a substring of ``deadlines``,
    and a check that cannot tell the two apart is a check that fails for the wrong reason.
    """
    keys = every_key(await context(client))

    for forbidden in ("capture_id", "lines", "confidence", "arguments", "output", "prompt"):
        assert forbidden not in keys, forbidden


async def test_a_sensor_still_arrives_with_its_cause(client: AsyncClient) -> None:
    """Composing does not get to drop the discipline the observation was carrying (ADR 0028 §3)."""
    activity = (await context(client))["activity"]

    for sensor in ("microphone", "camera"):
        assert set(activity[sensor]) == {"state", "cause"}


# ----------------------------------------------------------------------------------------
# The seven questions
# ----------------------------------------------------------------------------------------


async def test_all_seven_questions_come_back_in_order(client: AsyncClient) -> None:
    questions = (await context(client))["questions"]

    assert [one["question"] for one in questions] == [q.value for q in ContextQuestion]


async def test_the_questions_with_no_source_name_what_is_missing(client: AsyncClient) -> None:
    """§44's own worked example rests on the sources this ELA does not have."""
    questions = {one["question"]: one for one in (await context(client))["questions"]}

    relevance = questions[ContextQuestion.RELEVANT_INFORMATION.value]
    assert relevance["answered_by"] == []
    assert set(relevance["missing"]) == {
        ContextSource.RELEVANCE.value,
        ContextSource.MAIL.value,
        ContextSource.DOCUMENTS.value,
    }
    projects = questions[ContextQuestion.PROJECT_ACTIVITY.value]
    assert projects["answered_by"] == []
    assert ContextSource.PROJECTS.value in projects["missing"]


async def test_the_deadlines_question_is_answered_and_still_names_the_calendar(
    client: AsyncClient,
) -> None:
    """Answered and incomplete at once — the row that decided the shape (ADR 0032 §3)."""
    questions = {one["question"]: one for one in (await context(client))["questions"]}
    deadlines = questions[ContextQuestion.DEADLINES.value]

    assert deadlines["answered_by"] == [ContextSource.TASK_DEADLINES.value]
    assert deadlines["missing"] == [ContextSource.CALENDAR.value]


# ----------------------------------------------------------------------------------------
# It looks, and it records nothing
# ----------------------------------------------------------------------------------------


async def test_reading_the_context_writes_no_audit_event(client: AsyncClient) -> None:
    """Composing is not deciding: the audit records what ELA decides (ADR 0028 §10)."""
    before = (await client.get("/audit")).json()

    await context(client)

    assert (await client.get("/audit")).json() == before


async def test_the_route_looks_before_it_answers(client: AsyncClient) -> None:
    """Whoever asks what is happening wants the answer of now, as for ``/perception``."""
    first = (await context(client))["activity"]["observed_at"]
    second = (await context(client))["activity"]["observed_at"]

    assert first is not None and second is not None


async def test_a_live_task_appears_with_its_goal_and_the_totals_agree(
    client: AsyncClient,
) -> None:
    created = await client.post("/tasks", json={"text": "preparare la riunione"})
    assert created.status_code == 201

    work = (await context(client))["work"]

    assert work["shown"] == work["total"] == 1
    assert [one["goal"] for one in work["tasks"]] == ["preparare la riunione"]


async def test_diagnostics_still_says_what_ela_is_wired_to_and_not_what_it_is_doing(
    client: AsyncClient,
) -> None:
    """The line between the two routes, asserted rather than described (ADR 0032 §13)."""
    diagnostics = (await client.get("/diagnostics")).json()

    assert "context" not in diagnostics
    assert "questions" not in diagnostics
