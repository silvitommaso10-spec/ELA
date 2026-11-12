"""A policy saved before M13.14 still covers what it covered (M13.14, ADR 0068 §3; criterion 21).

The terms of a policy grew a field, ``on_the_core``, with a default: a row written by M13.9 or
M13.12 carries no such key, and it must read as the declaration of today — or every policy of the
user would stop covering by itself the day the code moved. On the SQL store, with a row written in
the form of that day.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import AuthorizationId, CapabilityId
from ela.infrastructure.persistence import SqlAuthorizationStore
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import authorization_to_row
from ela.permissions import (
    GAPS,
    PolicyRequest,
    authorization_from_policy,
    production_catalogue,
    shortfall,
)

NOW: Final = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
SITES: Final = ("www.youtube.com", "httpbin.org")
MODEL: Final = "claude-haiku-5-5"
AS_YOU: Final = CapabilityId("browser.guided_as_you")
POLICY_ID: Final = AuthorizationId(UUID("3f2a1b2c-0000-4000-8000-000000000913"))


async def test_a_policy_saved_without_on_the_core_covers_the_same_session(
    engine: AsyncEngine,
) -> None:
    catalogue = production_catalogue(sites=SITES, guided_model=MODEL)
    spec = catalogue.get(AS_YOU)
    grant = authorization_from_policy(
        PolicyRequest(
            capability_id=AS_YOU,
            scope=SITES,
            limits={"max_cost_usd": "1.10", "looks": "10", "seconds": "600"},
            days=30,
        ),
        catalogue=catalogue,
        granted_by="core",
        now=NOW,
        authorization_id=POLICY_ID,
    )
    row = authorization_to_row(grant)
    assert row.bounds is not None
    terms = dict(row.bounds["terms"])
    del terms["on_the_core"]  # the form of M13.9 and M13.12: the key did not exist
    row.bounds = {**row.bounds, "terms": terms}
    async with make_session_factory(engine)() as session, session.begin():
        session.add(row)
    async with engine.connect() as connection:
        stored = (
            await connection.execute(
                text("SELECT bounds FROM authorizations WHERE id = :id"), {"id": POLICY_ID.hex}
            )
        ).scalar_one()

    read = await SqlAuthorizationStore(engine).get(POLICY_ID)
    call = {
        "goal": "Apri YouTube e cerca il canale di MrBeast.",
        "sites": ["www.youtube.com"],
        "max_cost_usd": "0.60",
        "looks": 8,
        "seconds": 600,
    }

    assert "on_the_core" not in str(stored), "the row is in the form of that day"
    assert read.bounds is not None and read.bounds.terms == spec.policy_terms
    assert shortfall(read, spec, call, now=NOW, gaps=GAPS) is None
    assert shortfall(read, spec, call, now=NOW, on_the_core=False, gaps=GAPS) is None
