"""``ela diagnostics`` shows what the scope of the files opens, the scope every capability
declares, and the standing waits of the guard of the disk (M13.17, ADR 0074; decision 7, answers 37
and 40 of the review of its SPEC)."""

from __future__ import annotations

from httpx import AsyncClient

from ela.composition import Ela


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
    assert shown["scopes"] == {
        str(spec.id): list(spec.scope) for spec in ela.capabilities.specs() if spec.scope
    }
