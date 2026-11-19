"""``ela diagnostics`` shows what the scope of the files opens, the scope every capability
declares, and the standing waits of the guard of the disk (M13.17, ADR 0074; decision 7, answers 37
and 40 of the review of its SPEC)."""

from __future__ import annotations

from httpx import AsyncClient

from ela.composition import Ela
from ela.permissions import TERMINAL_RUN


async def test_the_diagnostics_show_the_files_the_scopes_and_the_waits(
    ela: Ela, client: AsyncClient
) -> None:
    """Answer 37: the scope a denial no longer prints is read here, for every capability that
    declares one; answer 40: the standing waits of the guard."""
    shown = (await client.get("/diagnostics")).json()

    root = ela.settings.filesystem.root.resolve()
    assert shown["files"]["root"] == str(root)
    assert shown["files"]["folders"] == [{"entry": "ELA", "folder": str(root / "ELA")}]
    assert shown["files"]["commands_from"] == str(root / "ELA")
    assert shown["files"]["waiting"] == 0
    assert shown["scopes"]["fs.write"] == ["ELA"]
    declaring = {
        str(spec.id): list(spec.scope)
        for spec in ela.capabilities.specs()
        if spec.scoped_arguments or spec.scope
    }
    assert shown["scopes"] == declaring


async def test_an_empty_scope_is_shown_where_the_denial_says_it_is_read(
    ela: Ela, client: AsyncClient
) -> None:
    """The consistency reading of M13.17, R5: with ``ELA_TERMINAL_PROGRAMS=[]`` — the example of
    ``ela init`` — the Guardian denies every command and says the scope is read in ``ela
    diagnostics``; the row must be there, empty, and not missing."""
    shown = (await client.get("/diagnostics")).json()

    assert ela.capabilities.get(TERMINAL_RUN).scope == ()
    assert shown["scopes"]["terminal.run"] == []
