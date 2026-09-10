"""The transcript in the store: strict on the way in, re-derived on the way out.

JSON Lines is **self-delimiting**, and that is why it was chosen for the recognition and why it is
right here too: a helper killed halfway leaves bytes that fail to parse rather than a shorter
answer that looks like an answer (ADR 0030 §7). Every "not one of ours" below is that property
being exercised, one malformation at a time.

And one property that belongs to this milestone alone: a transcript is an **origin**, not a
derived artefact. A recognition inherits the clock of the image it was read from; the audio a
transcript came from was never an artefact — it had no name and the kernel freed it — so this
carries its own ``mtime``, and the test at the bottom is what says so.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ela.tools.captures import (
    CAPTURE_MISSING,
    CAPTURE_NAME_INVALID,
    TEXT_MALFORMED,
    CaptureProblem,
    TranscriptArtefact,
    inspect_transcript,
    is_transcript_name,
    jsonl_segments,
    transcript_name_for,
)

TRANSCRIPT_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
TTL = timedelta(minutes=5)


def line(**overrides: object) -> bytes:
    record: dict[str, object] = {
        "text": " Ela, sposta la call di domani.",
        "start_ms": 0,
        "end_ms": 1840,
        "tokens": [{"text": " Ela", "p": 0.543607}],
    }
    record.update(overrides)
    return json.dumps(record).encode("utf-8") + b"\n"


def test_a_name_this_store_issues_is_a_uuid_and_the_heard_suffix() -> None:
    assert is_transcript_name(transcript_name_for(TRANSCRIPT_ID))
    assert not is_transcript_name(f"{TRANSCRIPT_ID}.jsonl")
    assert not is_transcript_name(f"{TRANSCRIPT_ID}.png")
    assert not is_transcript_name("../elsewhere.heard.jsonl")


def test_the_segments_and_their_probabilities_come_back() -> None:
    segments = jsonl_segments(line() + line(text=" e basta.", start_ms=1840, end_ms=2000))

    assert segments is not None
    assert [one.text for one in segments] == [" Ela, sposta la call di domani.", " e basta."]
    assert segments[0].probabilities == (0.543607,)


def test_an_empty_file_is_a_transcript_with_no_segments() -> None:
    """Nobody spoke is a reading, and it has to survive the parser to be one."""
    assert jsonl_segments(b"") == ()


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"\xff\xfe not utf-8", id="not-utf-8"),
        pytest.param(b"}{\n", id="not-json"),
        pytest.param(b'"a string"\n', id="not-an-object"),
        pytest.param(line(text=7), id="text-not-a-string"),
        pytest.param(line(start_ms="0"), id="start-not-an-integer"),
        pytest.param(line(end_ms=None), id="end-not-an-integer"),
        pytest.param(line(tokens="none"), id="tokens-not-a-list"),
        pytest.param(line(tokens=[{"text": " Ela"}]), id="token-without-a-probability"),
        pytest.param(line(tokens=[{"text": " Ela", "p": "high"}]), id="probability-not-a-number"),
        pytest.param(line(tokens=[{"text": " Ela", "p": True}]), id="probability-a-boolean"),
        pytest.param(line(tokens=["  Ela"]), id="token-not-an-object"),
    ],
)
def test_what_this_store_did_not_write_does_not_parse(payload: bytes) -> None:
    assert jsonl_segments(payload) is None


def test_a_transcript_is_measured_back_from_the_disk(tmp_path: Path) -> None:
    """What the tool declares must be what the file says (§20): read, not remembered."""
    target = tmp_path / transcript_name_for(TRANSCRIPT_ID)
    target.write_bytes(line())

    found = inspect_transcript(tmp_path, target.name, TTL)

    assert isinstance(found, TranscriptArtefact)
    assert found.segments == 1
    assert found.characters == len(" Ela, sposta la call di domani.")
    assert found.bytes == len(line())


def test_a_name_this_store_did_not_issue_is_refused_before_anything_is_read(
    tmp_path: Path,
) -> None:
    found = inspect_transcript(tmp_path, "somebody-elses.heard.jsonl", TTL)

    assert isinstance(found, CaptureProblem)
    assert found.code == CAPTURE_NAME_INVALID


def test_a_transcript_that_is_not_there_says_so(tmp_path: Path) -> None:
    found = inspect_transcript(tmp_path, transcript_name_for(TRANSCRIPT_ID), TTL)

    assert isinstance(found, CaptureProblem)
    assert found.code == CAPTURE_MISSING


def test_a_transcript_that_is_not_json_lines_says_so_with_a_size_and_no_bytes(
    tmp_path: Path,
) -> None:
    """A failure carries a size, never a byte: the words are the user's (§57)."""
    target = tmp_path / transcript_name_for(TRANSCRIPT_ID)
    target.write_bytes(b"}{\n")

    found = inspect_transcript(tmp_path, target.name, TTL)

    assert isinstance(found, CaptureProblem)
    assert found.code == TEXT_MALFORMED
    assert "3 bytes" in found.message(target.name)


def test_a_transcript_is_an_origin_and_carries_its_own_clock(tmp_path: Path) -> None:
    """The property this milestone adds to the store, and the reason it does not weaken the other.

    A recognition has no clock of its own because the image it was read from is still there to
    consult. A transcript has one because **nothing is above it**: the audio was never an
    artefact, so there is no origin to inherit from and no orphan to be.
    """
    target = tmp_path / transcript_name_for(TRANSCRIPT_ID)
    target.write_bytes(line())
    written = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    os.utime(target, (written.timestamp(), written.timestamp()))

    found = inspect_transcript(tmp_path, target.name, TTL)

    assert isinstance(found, TranscriptArtefact)
    assert found.expires_at == written + TTL
