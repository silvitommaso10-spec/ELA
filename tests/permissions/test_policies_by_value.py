"""The second dimension of a policy, named by value (M13.15, ADR 0071; decision 6).

- **The catalogue** holds a fifth class in the closed world — the argument named by value —, and
  refuses one that is not a string, one on a capability whose scope is a list, and the words of
  the product without the argument, or the argument without them.
- **``VALUES``**, after ``SCOPE``: the values of that argument and only them, at least one, valid,
  none twice — and no sentence repeats one.
- **``VALUE``**, after ``SITE``: a call is covered only if each of its dimensions is the policy's —
  the scope and the value —, built both ways for each; a call without the argument is not
  covered, and the sentence names the argument and never a value.
- **What the birth showed** is kept beside the grant, and a policy of before reads «nothing kept».
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import CapabilityId, PolicyTerms, PolicyWords
from ela.permissions import (
    Gap,
    PolicyCheck,
    PolicyRefusedError,
    PolicyRequest,
    authorization_from_policy,
    short_id,
    shortfall,
    shown_at_birth,
    shown_of,
)
from ela.permissions.capabilities import (
    CapabilityRegistry,
    InvalidCapabilityError,
    browser_download,
    browser_guided,
    browser_login,
)
from ela.testing.fakes import FakeIdGenerator
from tests.domain.examples import NOW
from tests.permissions.catalogue_calls import CALLS, CATALOGUE
from tests.permissions.policy_support import BY_VALUE, policy_for

DOWNLOAD = CATALOGUE.get(CapabilityId("browser.download"))
LOGIN = CATALOGUE.get(CapabilityId("browser.login"))
ENTRY = BY_VALUE["entry"][0]


def born(request: PolicyRequest) -> Any:
    return authorization_from_policy(
        request,
        catalogue=CATALOGUE,
        granted_by="local",
        now=NOW,
        authorization_id=FakeIdGenerator().new_uuid(),  # type: ignore[arg-type]
    )


def refused(request: PolicyRequest) -> PolicyRefusedError:
    with pytest.raises(PolicyRefusedError) as caught:
        born(request)
    return caught.value


# ----------------------------------------------------------------------------------------
# The catalogue
# ----------------------------------------------------------------------------------------


def _with(spec: Any, **terms: Any) -> Any:
    assert spec.policy_terms is not None
    return spec.model_copy(update={"policy_terms": spec.policy_terms.model_copy(update=terms)})


@pytest.mark.parametrize(
    ("spec", "fragment"),
    [
        (
            _with(
                browser_download(("ELA",)),
                by_value="overwrite",
                free=("path", "site", "click", "purpose"),
            ),
            "is not a string",
        ),
        (_with(browser_download(("ELA",)), by_value=None), "in one class"),
        (
            browser_download(("ELA",)).model_copy(
                update={"policy_words": PolicyWords(does="d", goes="g")}
            ),
            "policy_words.together",
        ),
        (
            browser_guided(("httpbin.org",), "m").model_copy(
                update={"policy_words": PolicyWords(does="d", goes="g", together="t")}
            ),
            "policy_words.together",
        ),
    ],
    ids=["not a string", "an argument in no class", "no product", "a product without a value"],
)
def test_the_catalogue_refuses_a_second_dimension_that_could_not_be_true(
    spec: Any, fragment: str
) -> None:
    with pytest.raises(InvalidCapabilityError) as caught:
        CapabilityRegistry((spec,))
    assert fragment in str(caught.value)


def test_a_capability_whose_scope_is_a_list_names_nothing_by_value() -> None:
    guided = browser_guided(("httpbin.org",), "m")
    assert guided.policy_terms is not None
    named = guided.model_copy(
        update={
            "policy_terms": PolicyTerms(
                limits=("max_cost_usd", "looks", "seconds"),
                uncovered=("task_type",),
                by_value="goal",
                route=guided.policy_terms.route,
                model="m",
            ),
            "policy_words": PolicyWords(does="d", goes="g", together="t"),
        }
    )

    with pytest.raises(InvalidCapabilityError) as caught:
        CapabilityRegistry((named,))
    assert "names nothing by value" in str(caught.value)


def test_the_login_is_admitted_with_its_entry_named_by_value() -> None:
    CapabilityRegistry((browser_login(("posta.example",)),))
    assert LOGIN.policy_terms is not None and LOGIN.policy_terms.by_value == "entry"


# ----------------------------------------------------------------------------------------
# VALUES
# ----------------------------------------------------------------------------------------


def test_a_policy_is_born_with_its_values() -> None:
    grant = born(
        PolicyRequest(
            DOWNLOAD.id, ("ELA/giu",), {}, 1, values={"site": ("httpbin.org", "example.com")}
        )
    )

    assert grant.bounds is not None and grant.bounds.values == ("httpbin.org", "example.com")
    assert grant.bounds.terms.by_value == "site"


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"entry": ("httpbin.org",)},
        {"site": ()},
        {"site": ("httpbin.org", "httpbin.org")},
        {"site": ("not a site",)},
        {"site": ("httpbin.org",), "entry": (ENTRY,)},
    ],
    ids=["none", "another argument", "empty", "twice", "invalid", "two arguments"],
)
def test_values_that_are_not_the_argument_s_are_refused_at_values(values: Any) -> None:
    found = refused(PolicyRequest(DOWNLOAD.id, ("ELA/giu",), {}, 1, values=values))

    assert found.check is PolicyCheck.VALUES
    for written in values.values():
        for one in written:
            assert one not in found.reason or one in ("site", "entry")


def test_an_id_too_long_is_refused_and_never_repeated() -> None:
    long = "4" * 65

    found = refused(PolicyRequest(LOGIN.id, ("httpbin.org",), {}, 1, values={"entry": (long,)}))

    assert found.check is PolicyCheck.VALUES and long not in found.reason


def test_a_capability_that_names_nothing_by_value_refuses_values() -> None:
    write = CATALOGUE.get(CapabilityId("fs.write"))

    found = refused(PolicyRequest(write.id, ("ELA",), {}, 1, values={"site": ("httpbin.org",)}))

    assert found.check is PolicyCheck.VALUES


def test_values_are_checked_after_the_scope_and_before_the_limits() -> None:
    found = refused(PolicyRequest(DOWNLOAD.id, ("Altrove",), {}, 1))

    assert found.check is PolicyCheck.SCOPE


# ----------------------------------------------------------------------------------------
# VALUE, both ways, for each dimension
# ----------------------------------------------------------------------------------------

FILE_CALL = dict(CALLS["browser.download"])
LOGIN_CALL = dict(CALLS["browser.login"])


@pytest.mark.parametrize(
    ("spec", "call", "gap"),
    [
        (DOWNLOAD, FILE_CALL, None),
        (DOWNLOAD, {**FILE_CALL, "site": "example.com"}, Gap.VALUE),
        (DOWNLOAD, {**FILE_CALL, "file": "Altrove/x.bin"}, Gap.SITE),
        (LOGIN, LOGIN_CALL, None),
        (LOGIN, {**LOGIN_CALL, "entry": "another-entry"}, Gap.VALUE),
        (LOGIN, {k: v for k, v in LOGIN_CALL.items() if k != "entry"}, Gap.VALUE),
        (LOGIN, {**LOGIN_CALL, "site": "example.com"}, Gap.SITE),
    ],
    ids=[
        "the file's: covered",
        "another site",
        "another folder",
        "the login's: covered",
        "another entry",
        "no entry",
        "another site of a login",
    ],
)
def test_a_call_is_covered_only_if_every_dimension_is_the_policy_s(
    spec: Any, call: dict[str, Any], gap: Gap | None
) -> None:
    policy = policy_for(spec, scope=("ELA",) if spec is DOWNLOAD else ("httpbin.org",))

    found = shortfall(policy, spec, call, now=NOW, on_the_core=True)

    assert (None if found is None else found.gap) is gap, found
    if gap is Gap.VALUE:
        assert found is not None
        name = spec.policy_terms.by_value
        short = short_id(policy.id)
        assert found.reason == f"a value of {name} is not among those of policy {short}"
        assert str(call.get(name)) not in found.reason


def test_a_policy_of_before_names_no_value_and_its_terms_are_its_own() -> None:
    """No migration: a row saved before M13.15 reads ``values`` empty, and its terms name nothing
    by value — ``fs.write``'s policy of M13.14 covers what it covered."""
    write = CATALOGUE.get(CapabilityId("fs.write"))
    policy = policy_for(write, scope=("ELA",))

    assert policy.bounds is not None and policy.bounds.values == ()
    assert shortfall(policy, write, CALLS["fs.write"], now=NOW, on_the_core=True) is None


# ----------------------------------------------------------------------------------------
# What the birth showed
# ----------------------------------------------------------------------------------------


def test_what_the_birth_showed_is_kept_and_read_back() -> None:
    policy = policy_for(LOGIN, scope=("httpbin.org",))

    kept = shown_at_birth(policy, resolved=(None,), values=("La posta (m…@example.com)",))

    assert shown_of(kept) == ((None,), ("La posta (m…@example.com)",))
    assert shown_of(policy) is None, "a policy of before kept nothing: its views say «—»"
    assert kept.bounds == policy.bounds, "words, not terms: what it covers did not change"
