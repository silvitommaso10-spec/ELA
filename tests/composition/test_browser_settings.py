"""``ELA_BROWSER_SITES``: the sites ELA's browser may open, declared by the user (M13.4 form E).

Required and without a default, with ``[]`` an admitted answer — the form of
``ELA_TERMINAL_PROGRAMS``. An entry is a host name alone, in the grammar the schema and the tool
read (``SITE_PATTERN``), and an entry outside it stops the start-up with its reason. And the node
does not read it (decision 1): its ``.env`` stays as it is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ela.composition import ConfigurationError, NodeConfig, Settings
from tests.composition.support import declare

SITES = "ELA_BROWSER_SITES"


def test_without_the_sites_ela_does_not_start_and_says_what_to_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    monkeypatch.delenv(SITES)

    with pytest.raises(ConfigurationError) as caught:
        Settings.load()

    message = str(caught.value)
    assert f'{SITES}=["example.com"]' in message, "the line to write, not only the name"
    assert f"{SITES}=[]" in message and "an answer, not an error" in message
    assert "without https://" in message


def test_the_fixtures_declare_no_site_unless_a_test_asks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)

    assert Settings.load().browser.sites == ()


def test_the_declared_sites_are_read_as_they_are(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, **{SITES: json.dumps(["example.com", "httpbin.org"])})

    assert Settings.load().browser.sites == ("example.com", "httpbin.org")


@pytest.mark.parametrize(
    "entry",
    [
        "https://example.com",
        "Example.com",
        "example.com:8080",
        "localhost",
        "192.168.1.1",
        "example.com/path",
        "example.com.",
    ],
)
def test_an_entry_that_is_not_a_host_name_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entry: str
) -> None:
    declare(monkeypatch, tmp_path, **{SITES: json.dumps([entry])})

    with pytest.raises(ConfigurationError) as caught:
        Settings.load()

    message = str(caught.value)
    assert repr(entry) in message
    assert "is not a host name" in message and "'example.com'" in message


def test_the_node_neither_reads_nor_asks_for_the_sites(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 1: the ``.env`` of the PC stays as it is. The node's settings have no such field,
    and load without the line."""
    declare(monkeypatch, tmp_path)
    monkeypatch.delenv(SITES)
    monkeypatch.setenv("ELA_NODE_STATE_DIR", str(tmp_path / "node"))

    config = NodeConfig.load()

    fields = {
        name
        for section in type(config).model_fields
        for name in type(getattr(config, section)).model_fields
    }
    assert not any("browser" in name for name in fields)
