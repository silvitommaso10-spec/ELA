"""``ELA_ELEVENLABS_CANDIDATES``: the voices an audition offers, chosen by whoever listens (M9.6).

Until M9.6 the catalogue was a tuple in ``src/``, six voices of the author's account (decision K):
whoever chooses writes, so the list is in the ``.env`` of whoever chose it. One line of JSON, an
object ``{"<voice_id>": "<name>"}`` in the order the voices are heard; **empty by default**, and
the empty value is an empty catalogue, not a stopped start-up — the form of
``ELA_ELEVENLABS_VOICE_ID=``. A section only the Core reads: the node's ``.env`` stays as it is,
and a malformed line of the catalogue does not stop ``ela node run``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ela.composition import ConfigurationError, NodeConfig, Settings
from tests.composition.support import declare

CANDIDATES = "ELA_ELEVENLABS_CANDIDATES"
CATALOGUE = {"voice-b": "Second — written first", "voice-a": "First — written second"}


def test_without_the_line_the_catalogue_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)

    assert Settings.load().audition.catalogue == ()


@pytest.mark.parametrize("written", ["", "   ", "{}"])
def test_an_empty_value_is_an_empty_catalogue_and_not_a_stopped_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str
) -> None:
    """From the ``.env``, where ``ela init`` and a person write it: the line without a value."""
    declare(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text(f"{CANDIDATES}={written}\n", encoding="utf-8")

    assert Settings.load().audition.catalogue == ()


def test_an_empty_value_in_the_environment_is_an_empty_catalogue_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, **{CANDIDATES: ""})

    assert Settings.load().audition.catalogue == ()


def test_the_catalogue_is_read_in_the_order_it_is_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text(
        f"{CANDIDATES}={json.dumps(CATALOGUE, ensure_ascii=False)}\n", encoding="utf-8"
    )

    assert Settings.load().audition.catalogue == (
        ("voice-b", "Second — written first"),
        ("voice-a", "First — written second"),
    )


def test_malformed_json_stops_the_start_up_with_the_variable_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, **{CANDIDATES: '{"voice-a": "First"'})

    with pytest.raises(ConfigurationError) as caught:
        Settings.load()

    assert CANDIDATES in str(caught.value)
    assert "(is it valid JSON?)" in str(caught.value)


@pytest.mark.parametrize("written", ['["voice-a"]', '{"voice-a": 1}', '"voice-a"'])
def test_a_value_that_is_not_an_object_of_names_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str
) -> None:
    declare(monkeypatch, tmp_path, **{CANDIDATES: written})

    with pytest.raises(ConfigurationError) as caught:
        Settings.load()

    assert CANDIDATES in str(caught.value)


def test_the_node_does_not_read_the_catalogue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A malformed line of the Core's catalogue does not stop ``NodeConfig.load``."""
    declare(monkeypatch, tmp_path, **{CANDIDATES: '{"voice-a": "First"'})
    monkeypatch.setenv("ELA_NODE_STATE_DIR", str(tmp_path / "node"))

    config = NodeConfig.load()

    fields = {
        name
        for section in type(config).model_fields
        for name in type(getattr(config, section)).model_fields
    }
    assert not any("candidates" in name for name in fields)
