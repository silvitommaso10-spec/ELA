"""The lines «why I ask» name a policy that ended only if, alive, it would have covered the call
(M13.17, decision 17; the first point M13.15's proof put in its account).

The fact, from the proof of 2026-11-18 (``docs/milestones/M13.15.md``, «I punti in conto dalla
prova», point 1): at step 4 a download from a site the live policy did not name asked, and the
lines said «policy 84e23528 was revoked» of a policy that, alive, named another site — while the one
sentence of the question said «none was given». ``why_lines`` wrote the first reason of
``shortfall`` for every recent policy, and the first check is the revocation.

**The rule**: a live policy that does not cover says its gap; a live one that covers says so; an
ended one — revoked, expired, spent — is named, with how it ended, only if it would have covered
the call alive; one that would not have covered is not named. **The choice comes before the cut to
``WHY_MAX``**: three ended policies that do not matter take no room from the line that does.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ela.domain import Authorization, CapabilityId
from ela.permissions import WHY_MAX, short_id, why_lines, would_cover
from tests.domain.examples import NOW
from tests.permissions.catalogue_calls import CALLS, CATALOGUE
from tests.permissions.policy_support import policy_for, revoked

DOWNLOAD = CATALOGUE.get(CapabilityId("browser.download"))
HERE = "httpbin.org"
"""The site of the live policy: the one the proof's step 4 had, 48d695e7's."""
THERE = "testpages.eviltester.com"
"""A site no policy of the call names: what the step downloaded from."""
OTHER = "news.ycombinator.com"
"""The site of the policies that ended, which named neither."""
CALL = {**CALLS["browser.download"], "site": THERE}


def lines(*policies: tuple[Authorization, int]) -> tuple[str, ...]:
    return why_lines(list(policies), DOWNLOAD, CALL, now=NOW, on_the_core=True)


def live_on(site: str, *, hours: int, tail: int) -> Authorization:
    return policy_for(
        DOWNLOAD,
        values=(site,),
        created_at=NOW - timedelta(hours=hours),
        expires_at=NOW + timedelta(days=5),
        tail=tail,
    )


def ended(how: str, site: str, *, hours: int, tail: int) -> tuple[Authorization, int]:
    """A policy on ``site``, born ``hours`` before the call, that ended ``how``: with its uses."""
    born = live_on(site, hours=hours, tail=tail)
    if how == "revoked":
        return revoked(born, NOW - timedelta(minutes=30)), 0
    if how == "expired":
        return born.model_copy(update={"expires_at": NOW - timedelta(minutes=30)}), 0
    return born.model_copy(update={"max_uses": 1}), 1


GAP = "a value of site is not among those of policy {}"
ENDINGS = pytest.mark.parametrize("how", ["revoked", "expired", "spent"])


@ENDINGS
def test_an_ended_policy_that_would_not_have_covered_the_call_is_not_named(how: str) -> None:
    """Step 4 of the proof of 2026-11-18: the live policy says its gap, and the one that ended on
    another site is not a reason of this question."""
    live = live_on(HERE, hours=1, tail=901)

    found = lines((live, 0), ended(how, OTHER, hours=2, tail=902))

    assert found == (GAP.format(short_id(live.id)),)


@ENDINGS
def test_an_ended_policy_that_would_have_covered_the_call_says_how_it_ended(how: str) -> None:
    gone, uses = ended(how, THERE, hours=2, tail=903)

    (line,) = lines((gone, uses))

    assert line.startswith(f"policy {short_id(gone.id)} ")
    assert {"revoked": "was revoked on", "expired": "expired on", "spent": "was used 1 of"}[
        how
    ] in (line)


def test_three_recent_policies_that_would_not_have_covered_leave_room_for_the_one_that_does() -> (
    None
):
    """The cut to ``WHY_MAX`` comes after the choice: three revocations on another site, more recent
    than the live policy, used to take all three places."""
    live = policy_for(
        DOWNLOAD,
        values=(HERE,),
        created_at=NOW - timedelta(days=2),
        expires_at=NOW + timedelta(days=5),
        tail=904,
    )
    gone = [ended("revoked", OTHER, hours=n, tail=910 + n) for n in (1, 2, 3)]

    found = lines((live, 0), *gone)

    assert WHY_MAX == 3
    assert found == (GAP.format(short_id(live.id)),)


def test_a_live_policy_that_does_not_cover_says_its_gap_and_one_that_covers_says_so() -> None:
    """What does not change: a live policy is always a reason, the way it was."""
    gap = live_on(HERE, hours=1, tail=905)
    covers = live_on(THERE, hours=2, tail=906)

    assert lines((gap, 0), (covers, 0)) == (
        GAP.format(short_id(gap.id)),
        f"policy {short_id(covers.id)} covers this call: this step asks again for the yes it was "
        "given",
    )


# ----------------------------------------------------------------------------------------
# The line of when nothing is left to name, true to the letter (answer 43), and the policy
# the sentence names first (answer 42)
# ----------------------------------------------------------------------------------------


def test_a_capability_that_never_had_a_policy_says_so() -> None:
    assert lines() == ("no policy of yours for browser.download",)


@pytest.mark.parametrize("age", [timedelta(hours=2), timedelta(days=60)], ids=["recent", "old"])
def test_one_that_had_policies_none_of_which_matters_says_that_and_not_none(
    age: timedelta,
) -> None:
    """A policy on another site, ended — recently or past the window —: «no policy of yours» would
    be false, because there was one; the line says what is true of every policy it had."""
    gone = revoked(
        policy_for(
            DOWNLOAD,
            values=(OTHER,),
            created_at=NOW - age,
            expires_at=NOW + timedelta(days=5),
            tail=930,
        ),
        NOW - age + timedelta(minutes=1),
    )

    found = lines((gone, 0))

    assert found == (
        "no live policy of yours for browser.download, and none that ended would have covered "
        "this call",
    )
    assert not would_cover(gone, DOWNLOAD, CALL, now=NOW, on_the_core=True), "true to the letter"


def test_the_policy_the_executor_hands_comes_first_whatever_its_age() -> None:
    """Answer 42: the policy the sentence names is among the lines — first —, even ended past the
    window, and the cut keeps the total at ``WHY_MAX``."""
    old = revoked(
        policy_for(
            DOWNLOAD,
            values=(THERE,),
            created_at=NOW - timedelta(days=60),
            expires_at=NOW + timedelta(days=5),
            tail=931,
        ),
        NOW - timedelta(days=40),
    )
    newer = [live_on(HERE, hours=n, tail=932 + n) for n in (1, 2, 3)]

    found = why_lines(
        [(old, 0), *((one, 0) for one in newer)],
        DOWNLOAD,
        CALL,
        now=NOW,
        on_the_core=True,
        handed=old.id,
    )

    assert len(found) == WHY_MAX
    assert found[0].startswith(f"policy {short_id(old.id)} was revoked on")
