"""A policy is never changed: revoking it and creating another is the only way (M13.14, proposal 12
of the SPEC; criterion 3 (c), the first missing piece).

Until M13.14 only closed **counts** said it — the routes of the API, the commands of the CLI, the
table of the ports —, which a new route, command or member would break without saying why. Here it
is said **by name**: the members of the store that write, what each of them leaves of a policy, the
routes and pages under the policies, and the commands of ``ela policy``.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Final, cast

import pytest

import ela.api
from ela.cli.app import app as cli_app
from ela.domain import Authorization
from ela.ports import (
    AlreadyExistsError,
    AuthorizationAlreadyRevokedError,
    AuthorizationRevokedError,
    AuthorizationStore,
)
from tests.contracts.implementations import Implementation, implementations_of
from tests.contracts.protocols import members
from tests.domain.examples import LATER, NOW
from tests.permissions.policy_support import TERMED, policy_for

WRITING: Final = frozenset({"grant", "revoke", "consume"})
"""The members of :class:`AuthorizationStore` that write, named: a birth, the one instant of a
revocation, and a use. None of them changes what a policy covers."""
READING: Final = frozenset({"get", "for_capability", "uses"})

POLICY: Final = policy_for(TERMED, tail=1314, max_uses=3)
"""A policy with everything a policy can carry: a scope, the limits, an end and a number of uses."""

KEPT: Final = (
    "id",
    "capability_id",
    "scope",
    "bounds",
    "expires_at",
    "max_uses",
    "granted_by",
)
"""What a policy is: none of these moves after its birth, whatever the store is asked."""


@pytest.fixture(params=implementations_of(AuthorizationStore), ids=str)
async def store(request: pytest.FixtureRequest) -> AsyncIterator[AuthorizationStore]:
    implementation = cast(Implementation, request.param)
    instance = implementation.make()
    if implementation.setup is not None:
        await implementation.setup(instance)
    try:
        yield cast(AuthorizationStore, instance)
    finally:
        if implementation.teardown is not None:
            await implementation.teardown(instance)


def _same_policy(read: Authorization) -> None:
    for name in KEPT:
        assert getattr(read, name) == getattr(POLICY, name), name
    assert read.model_dump(exclude={"revoked_at"}) == POLICY.model_dump(exclude={"revoked_at"})


def test_the_store_writes_with_three_members_named_and_reads_with_the_others() -> None:
    """A member added tomorrow is neither of the two: it fails here, by its name."""
    assert members(AuthorizationStore) == WRITING | READING
    assert not WRITING & READING


async def test_after_every_member_that_writes_the_policy_reads_the_same(
    store: AuthorizationStore,
) -> None:
    """``grant``, ``consume`` and ``revoke``: after each, the policy read again is the one that was
    born — only the uses move, and ``revoked_at`` once, at the first instant."""
    await store.grant(POLICY)
    _same_policy(await store.get(POLICY.id))

    assert await store.consume(POLICY.id, now=NOW) == 1
    assert await store.consume(POLICY.id, now=NOW) == 2
    _same_policy(await store.get(POLICY.id))
    assert await store.uses(POLICY.id) == 2

    gone = await store.revoke(POLICY.id, at=NOW)
    _same_policy(gone)
    assert gone.revoked_at == NOW
    with pytest.raises(AuthorizationAlreadyRevokedError):
        await store.revoke(POLICY.id, at=LATER)
    with pytest.raises(AuthorizationRevokedError):
        await store.consume(POLICY.id, now=NOW)

    after = await store.get(POLICY.id)
    _same_policy(after)
    assert after.revoked_at == NOW
    assert await store.uses(POLICY.id) == 2
    assert await store.for_capability(POLICY.capability_id) == (after,)


async def test_a_grant_on_an_id_that_is_held_is_refused_and_the_policy_stays(
    store: AuthorizationStore,
) -> None:
    """The one way a store could be asked to «change» a policy — a second birth with its id, wider
    — is refused, and the row is the first one."""
    await store.grant(POLICY)
    wider = POLICY.model_copy(
        update={
            "scope": (*POLICY.scope, "gamma.example"),
            "expires_at": POLICY.created_at + timedelta(days=90),
            "max_uses": None,
        }
    )

    with pytest.raises(AlreadyExistsError):
        await store.grant(wider)

    _same_policy(await store.get(POLICY.id))
    assert await store.uses(POLICY.id) == 0


def _routes() -> set[tuple[str, str]]:
    """Every (method, path) the routers of ``ela.api`` carry — what ``generate_stato`` counts."""
    found: set[tuple[str, str]] = set()
    for info in pkgutil.iter_modules(ela.api.__path__):
        if info.name.startswith("_"):
            continue
        router = getattr(importlib.import_module(f"ela.api.{info.name}"), "router", None)
        if router is None:
            continue
        found |= {
            (method, route.path)
            for route in router.routes
            for method in getattr(route, "methods", set())
            if method not in {"HEAD", "OPTIONS"}
        }
    return found


def _under(prefix: str) -> set[tuple[str, str]]:
    return {
        (method, path)
        for method, path in _routes()
        if path == prefix or path.startswith(prefix + "/")
    }


def test_the_routes_of_the_policies_are_the_list_the_preview_the_birth_and_the_revocation() -> None:
    """No route under ``/policies`` serves ``PUT``, ``PATCH`` or ``DELETE``, and the one ``POST``
    on a policy that exists is its revocation."""
    routes = _under("/policies")

    assert routes == {
        ("GET", "/policies"),
        ("POST", "/policies/preview"),
        ("POST", "/policies"),
        ("POST", "/policies/{policy_id}/revoke"),
    }
    assert not {method for method, _ in routes} & {"PUT", "PATCH", "DELETE"}
    assert {path for _, path in routes if "{" in path} == {"/policies/{policy_id}/revoke"}


def test_the_pages_of_the_policies_are_the_list_the_preview_the_birth_and_the_revocation() -> None:
    """The console's pages call the routes' functions (rule 55): the same four, and no other."""
    assert _under("/console/policies") == {
        ("GET", "/console/policies"),
        ("POST", "/console/policies/preview"),
        ("POST", "/console/policies"),
        ("POST", "/console/policies/revoke"),
    }


def test_ela_policy_creates_lists_and_revokes_and_nothing_else() -> None:
    (group,) = [group for group in cli_app.registered_groups if group.name == "policy"]
    commands = {
        command.name or command.callback.__name__
        for command in group.typer_instance.registered_commands
        if command.callback is not None
    }

    assert commands == {"create", "list", "revoke"}
    assert group.typer_instance.registered_groups == []
