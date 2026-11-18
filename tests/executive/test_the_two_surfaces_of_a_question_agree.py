"""The one sentence of a question and its lines «why I ask» say the same thing about a policy that
ended (M13.17, decision 17).

The sentence is the Guardian's reason, composed from the grant the executor hands over — among the
policies that would cover the call, none usable, the one that ended last (ADR 0071 §10, point 1) —
or «none was given» when it hands none. The lines are ``why_lines``. **For every case**: if the
sentence says «none was given», no line says a policy ended; if it names a policy that ended, that
policy is among the lines.

The first case is step 4 of the proof of M13.15 on 2026-11-18: «policy 84e23528 was revoked» among
the lines, «none was given» in the sentence.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from ela.domain import Authorization, CapabilityId
from ela.executive import ASKED
from ela.permissions import short_id
from tests.executive.test_policy_files_and_login import five_world
from tests.permissions.catalogue_calls import CALLS, CATALOGUE
from tests.permissions.policy_support import policy_for

DOWNLOAD = CapabilityId("browser.download")
THERE = "testpages.eviltester.com"
"""The site of the call: one the live policies do not name."""
CALL = {**CALLS[str(DOWNLOAD)], "site": THERE}
ENDED = re.compile(r"policy ([0-9a-f]{8}) (was revoked on|expired on|was used \d+ of)")
NONE_GIVEN = "none was given"


def disagreements(prompt: str, lines: list[str]) -> list[str]:
    """What the two surfaces say differently about the policies that ended: empty when they
    agree."""
    named = {found.group(1) for line in lines if (found := ENDED.search(line))}
    said = ENDED.search(prompt.rsplit(": ", 1)[-1])
    problems = []
    if NONE_GIVEN in prompt and named:
        problems.append(f"the sentence says {NONE_GIVEN!r} and the lines name {sorted(named)}")
    if said is not None and said.group(1) not in named:
        problems.append(f"the sentence names {said.group(1)} and the lines do not")
    return problems


async def granted(
    w: Any, site: str, *, tail: int, born: timedelta, **changes: Any
) -> Authorization:
    policy = policy_for(
        CATALOGUE.get(DOWNLOAD),
        values=(site,),
        created_at=w.now - born,
        expires_at=w.now + timedelta(days=30),
        tail=tail,
        **changes,
    )
    await w.store.grant(policy)
    return policy


async def asked(w: Any) -> tuple[str, list[str]]:
    task, step = await w.running(DOWNLOAD, arguments=CALL)
    execution = await w.execute(task.id, step.id)
    assert execution.approval is not None
    return execution.approval.prompt, list(execution.approval.metadata[ASKED]["why"])


async def test_step_4_of_the_proof_none_given_and_no_line_says_a_policy_ended() -> None:
    w = five_world()
    live = await granted(w, "httpbin.org", tail=901, born=timedelta(hours=1))
    gone = await granted(w, "news.ycombinator.com", tail=902, born=timedelta(hours=2))
    await w.store.revoke(gone.id, at=w.now - timedelta(minutes=10))

    prompt, lines = await asked(w)

    assert NONE_GIVEN in prompt
    assert disagreements(prompt, lines) == [], lines
    assert lines == [f"a value of site is not among those of policy {short_id(live.id)}"]


async def test_three_live_policies_newer_than_the_one_named_leave_it_among_the_lines() -> None:
    """The cut to ``WHY_MAX`` keeps the most recent; the executor hands the covering policy that
    ended last, whenever it was born. Three live policies on another site, born after it."""
    w = five_world()
    covering = await granted(w, THERE, tail=903, born=timedelta(hours=5))
    await w.store.revoke(covering.id, at=w.now - timedelta(minutes=10))
    for n in (1, 2, 3):
        await granted(w, "httpbin.org", tail=903 + n, born=timedelta(hours=5 - n))

    prompt, lines = await asked(w)

    assert f"policy {short_id(covering.id)} was revoked on" in prompt
    assert disagreements(prompt, lines) == [], lines


async def test_a_covering_policy_that_ended_long_ago_is_named_by_both_or_by_neither() -> None:
    """The executor's choice reads no window; the lines read the thirty days of ``WHY_DAYS``."""
    w = five_world()
    old = await granted(w, THERE, tail=910, born=timedelta(days=60))
    await w.store.revoke(old.id, at=w.now - timedelta(days=40))

    prompt, lines = await asked(w)

    named = ENDED.search(prompt.rsplit(": ", 1)[-1])
    assert NONE_GIVEN in prompt or (named is not None and named.group(1) == short_id(old.id)), (
        prompt
    )
    assert disagreements(prompt, lines) == [], (prompt, lines)
