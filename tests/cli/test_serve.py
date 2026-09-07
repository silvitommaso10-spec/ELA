"""``ela serve``: the one command that is not a client (ADR 0024 §2).

What is tested here is that it starts *the same* ELA ``python -m ela.api`` starts, from the same
settings, and that a configuration ELA cannot use stops it with the message and the exit code the
table promises. The server itself is never actually run: the loop belongs to ``ela.api``, which
has its own tests, and a test that bound a port would open a socket.
"""

from __future__ import annotations

import pytest

from ela.api import server
from ela.cli.errors import CONFIGURATION
from ela.composition import Settings
from tests.cli.support import Cli, plain


async def test_serve_builds_ela_from_the_settings_and_serves_it(
    cli: Cli, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: list[Settings] = []
    monkeypatch.setattr(server, "serve", served.append)

    result = await cli("serve")

    assert result.exit_code == 0
    assert [one.api.api_port for one in served] == [settings.api.api_port]
    assert served[0].persistence.db_url == settings.persistence.db_url


async def test_a_configuration_ela_cannot_use_stops_before_anything_is_built(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message names the variable; the exit code says nothing reached ELA."""
    called: list[Settings] = []
    monkeypatch.setattr(server, "serve", called.append)
    monkeypatch.setenv("ELA_API_HOST", "0.0.0.0")

    result = await cli("serve")

    assert result.exit_code == CONFIGURATION
    assert "ELA_API_HOST" in plain(result.stderr)
    assert called == []
