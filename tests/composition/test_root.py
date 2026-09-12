"""``build`` (ADR 0023 §5): ELA put together once, and the configurations it refuses.

The test builds the real thing — the SQL adapters, the catalogue, the Guardian, the router, the
tools, the runner — on a database in a temporary directory. What is under test is the wiring
itself: that ELA starts, that what the ADR promises about the order actually happened, and that
a configuration ELA cannot honour stops it with a message instead of a stack trace.
"""

from __future__ import annotations

import json
import platform
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from ela.composition import ELA_ACTOR, ConfigurationError, Ela, Settings, build
from ela.devices.local import LOCAL_DEVICE_ID, LOCAL_DEVICE_NAME
from ela.domain import ActorKind, PermissionOutcome, ProviderStatus
from ela.infrastructure.machine import UnsupportedScreenCapture
from ela.permissions import (
    CORE_ECHO,
    DEFAULT_DECISION_TTL,
    DEFAULT_NOTES_SCOPE,
    MODEL_COMPLETE,
    PERCEPTION_CAPTURE_SCREEN,
    WORKSPACE_WRITE_NOTE,
    catalogue_v01,
    production_catalogue,
)
from ela.ports import ROUTING_EMPTY_ROUTES, ROUTING_UNKNOWN_PROVIDER
from ela.providers.anthropic import PROVIDER_NAME
from tests.composition.support import TOKEN, create_schema, database_url, declare

ROUTER = "_router"
"""Where the tool and the verifier keep the router they were given.

Read here on purpose: ADR 0022 §10 asks for the **same object**, and no behavioural check can
tell one router from a second one with an equal table — until the day one of the two tables
changes, which is exactly the accident the rule exists to prevent.
"""


async def built(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> Ela:
    declare(monkeypatch, tmp_path, **extra)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    return await build(settings)


# ----------------------------------------------------------------------------------------
# What was built
# ----------------------------------------------------------------------------------------


async def test_every_piece_of_the_pipeline_is_there(ela: Ela) -> None:
    """The root builds the **production** catalogue, not v0.1's (ADR 0029 §13).

    ``catalogue_v01()`` says what it contains and keeps containing it; ``production_catalogue()``
    says when it is used. The root uses the second, and this is the test that would catch the two
    drifting apart — a fourth capability with no tool, or a tool with no verifier.
    """
    assert [spec.id for spec in ela.capabilities.specs()] == [
        spec.id for spec in production_catalogue().specs()
    ]
    assert [spec.id for spec in catalogue_v01().specs()] == [
        spec.id for spec in production_catalogue().specs()
    ][:3]
    # Derived from the catalogue rather than written down: a capability added with a tool but no
    # verifier is the drift this catches, and a hard-coded count would only catch it by accident.
    assert (
        len(ela.tools.tools())
        == len(ela.verifiers.verifiers())
        == len(production_catalogue().specs())
    )
    assert ela.providers.names() == (PROVIDER_NAME,)
    assert ela.runner is not None and ela.executor is not None


async def test_the_tools_and_the_verifiers_share_one_router(ela: Ela) -> None:
    """ADR 0022 §10: the verifier of ``model.routed_as_asked`` recomputes the route, and two
    routers with two tables would fail every verification."""
    tool = ela.tools.get(MODEL_COMPLETE)
    verifier = ela.verifiers.get(MODEL_COMPLETE)

    assert getattr(tool, ROUTER) is ela.router
    assert getattr(verifier, ROUTER) is ela.router


async def test_the_local_node_knows_which_tools_it_has(ela: Ela) -> None:
    """ADR 0016 §4: without the names no node is ever eligible and every task waits."""
    local = await ela.devices.get(LOCAL_DEVICE_ID)

    assert local.available_tools == tuple(tool.name for tool in ela.tools.tools())


async def test_the_local_node_is_alive_because_it_is_this_process(ela: Ela) -> None:
    """ADR 0023 §5-bis: a node registered and never heard from is UNAVAILABLE, and nothing
    would ever be placed on it."""
    assert [device.name for device in await ela.devices.available()] == [LOCAL_DEVICE_NAME]


async def test_the_workspace_is_created_and_is_the_user_s_alone(ela: Ela) -> None:
    workspace = ela.settings.workspace.workspace_dir

    assert workspace.is_dir()
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700  # §57


async def test_the_durations_of_the_settings_reach_the_engine_and_the_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The proof that they are *used* is in the API tests, where an approval expires when the
    setting says; here it is that they are read at all."""
    # The TTL of an assignment below the orphan threshold, as ADR 0038 §9 requires since M12.2.
    ela = await built(
        monkeypatch,
        tmp_path,
        ELA_TASK_ORPHAN_AFTER_SECONDS="60",
        ELA_ASSIGNMENT_TTL_SECONDS="30",
    )
    try:
        assert ela.settings.core.orphan_after.total_seconds() == 60
        assert await ela.engine.recover() == ((), (), ())  # an engine that works
    finally:
        await ela.aclose()


async def test_the_notes_scope_of_the_settings_reaches_the_catalogue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR 0025 §5: ``catalogue_v01`` always took the parameter — this line is what M8.1 left.

    And it is a **behavioural** check, not a field read: the Guardian denies a note outside the
    configured scope and allows one inside it, which is what the variable is for.
    """
    ela = await built(monkeypatch, tmp_path, ELA_NOTES_SCOPE="appunti")
    try:
        spec = ela.capabilities.get(WORKSPACE_WRITE_NOTE)
        assert spec.scope == ("appunti",)

        inside = ela.guardian.decide(spec, {"path": "appunti/x.md", "body": "b"})
        outside = ela.guardian.decide(spec, {"path": "workspace/notes/x.md", "body": "b"})

        assert inside.outcome is PermissionOutcome.ALLOWED
        assert outside.outcome is PermissionOutcome.DENIED
    finally:
        await ela.aclose()


async def test_the_default_scope_is_still_the_one_the_catalogue_declares(ela: Ela) -> None:
    """Negative case for the one above: with nothing set, nothing moved."""
    assert ela.capabilities.get(WORKSPACE_WRITE_NOTE).scope == (DEFAULT_NOTES_SCOPE,)


async def test_the_decision_ttl_of_the_settings_reaches_the_guardian(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR 0025 §6, checked on a decision and not on a field: an ``ALLOWED`` expires when the
    variable says it does."""
    # An offer never outlives its decision, so its TTL comes down with it (ADR 0038 §5).
    ela = await built(
        monkeypatch, tmp_path, ELA_DECISION_TTL_SECONDS="60", ELA_ASSIGNMENT_TTL_SECONDS="60"
    )
    try:
        spec = ela.capabilities.get(CORE_ECHO)
        decision = ela.guardian.decide(spec, {"message": "ciao"})

        assert decision.expires_at is not None
        assert decision.expires_at - decision.created_at == timedelta(seconds=60)
    finally:
        await ela.aclose()


async def test_without_the_variable_a_decision_lives_as_long_as_it_always_did(ela: Ela) -> None:
    decision = ela.guardian.decide(ela.capabilities.get(CORE_ECHO), {"message": "ciao"})

    assert decision.expires_at is not None
    assert decision.expires_at - decision.created_at == DEFAULT_DECISION_TTL


async def test_ela_acts_as_itself(ela: Ela) -> None:
    assert ELA_ACTOR.kind is ActorKind.ELA


async def test_closing_twice_is_allowed(ela: Ela) -> None:
    await ela.aclose()
    await ela.aclose()


# ----------------------------------------------------------------------------------------
# A machine with no key still runs ELA (ADR 0020 §2)
# ----------------------------------------------------------------------------------------


async def test_without_a_key_the_provider_is_unavailable_and_ela_starts(ela: Ela) -> None:
    assert ela.providers.get(PROVIDER_NAME).status is ProviderStatus.UNAVAILABLE


async def test_with_a_key_the_provider_is_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ela = await built(monkeypatch, tmp_path, ELA_ANTHROPIC_API_KEY=TOKEN)
    try:
        assert ela.providers.get(PROVIDER_NAME).status is ProviderStatus.AVAILABLE
    finally:
        await ela.aclose()


# ----------------------------------------------------------------------------------------
# What stops the start-up (ADR 0023 §5)
# ----------------------------------------------------------------------------------------


async def test_a_database_nobody_migrated_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR 0006 refused automatic migration; ADR 0023 §5 refuses silence about it."""
    declare(monkeypatch, tmp_path)

    with pytest.raises(ConfigurationError) as raised:
        await build(Settings.load())

    message = str(raised.value)
    assert "alembic upgrade head" in message
    assert "tasks" in message and "audit_events" in message


async def test_a_route_naming_an_unknown_provider_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR 0022 §7: a typo in ``ELA_MODEL_ROUTES`` stops ELA before it works, not a step later."""
    table = json.dumps({"coding": {"providers": ["openai"], "profile": "quality"}})
    declare(monkeypatch, tmp_path, ELA_MODEL_ROUTES=table)
    await create_schema(database_url(tmp_path))

    with pytest.raises(ConfigurationError) as raised:
        await build(Settings.load())

    assert ROUTING_UNKNOWN_PROVIDER in str(raised.value)
    assert "ELA_MODEL_ROUTES" in str(raised.value)


async def test_an_empty_routing_table_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, ELA_MODEL_ROUTES="{}")
    await create_schema(database_url(tmp_path))

    with pytest.raises(ConfigurationError) as raised:
        await build(Settings.load())

    assert ROUTING_EMPTY_ROUTES in str(raised.value)


async def test_a_refused_configuration_leaves_no_connection_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``build`` opens the engine before it can know the rest is wrong; it releases it either way,
    and the proof is that the very next ``build`` succeeds on the same file."""
    declare(monkeypatch, tmp_path, ELA_MODEL_ROUTES="{}")
    await create_schema(database_url(tmp_path))
    with pytest.raises(ConfigurationError):
        await build(Settings.load())

    monkeypatch.delenv("ELA_MODEL_ROUTES")
    ela = await build(Settings.load())
    try:
        assert await ela.repository.tasks() == ()
    finally:
        await ela.aclose()


# --------------------------------------------------------------------------------------
# The capture store (M10.2, ADR 0029 §1)
# --------------------------------------------------------------------------------------


async def test_the_capture_store_is_built_beside_the_database_and_never_in_the_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A permanent constraint, not this milestone's convenience: the workspace is what §23 calls
    synchronised, and content in a folder something may one day sync leaves the machine without
    anybody having decided it."""
    ela = await built(monkeypatch, tmp_path)
    try:
        assert ela.captures.directory == (tmp_path / "captures").resolve()
        assert not ela.captures.directory.is_relative_to(
            ela.settings.workspace.workspace_dir.resolve()
        )
    finally:
        await ela.aclose()


async def test_the_capture_store_is_created_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ela = await built(monkeypatch, tmp_path)
    try:
        assert stat.S_IMODE(ela.captures.directory.stat().st_mode) == 0o700
    finally:
        await ela.aclose()


async def test_the_capture_tool_and_its_verifier_share_the_one_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One directory and one retention: two would mean a verifier looking for a capture
    somewhere else, or thinking one still there had expired."""
    ela = await built(monkeypatch, tmp_path)
    try:
        tool = ela.tools.get(PERCEPTION_CAPTURE_SCREEN)
        verifier = ela.verifiers.get(PERCEPTION_CAPTURE_SCREEN)

        assert getattr(tool, "_store") is ela.captures  # noqa: B009
        assert getattr(verifier, "_directory") == ela.captures.directory  # noqa: B009
    finally:
        await ela.aclose()


async def test_the_capture_tool_preflights_with_the_probe_the_perception_core_uses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One reader of this machine, so "what ELA believes" and "what ELA checks before acting"
    cannot come from two places that disagree. They stay two *reads*: a periodic belief never
    decides an action (ADR 0029 §7)."""
    ela = await built(monkeypatch, tmp_path)
    try:
        tool = ela.tools.get(PERCEPTION_CAPTURE_SCREEN)

        assert getattr(tool, "_probe") is getattr(ela.perception, "_probe")  # noqa: B009
    finally:
        await ela.aclose()


async def test_on_a_machine_without_a_capture_helper_ela_still_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Linux in CI, Windows nodes later (§4): the capability exists, and the tool says why it
    cannot be used, rather than the composition failing or the capability vanishing."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    ela = await built(monkeypatch, tmp_path)
    try:
        assert PERCEPTION_CAPTURE_SCREEN in {spec.id for spec in ela.capabilities.specs()}
        assert isinstance(
            getattr(ela.tools.get(PERCEPTION_CAPTURE_SCREEN), "_capture"),  # noqa: B009
            UnsupportedScreenCapture,
        )
    finally:
        await ela.aclose()
