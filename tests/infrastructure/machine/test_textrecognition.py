"""The Vision adapter: every way the helper can disappoint, produced without a framework.

The port's hardest promise is that it **does not fail, it reports**, and this is where that is
proved: a timeout, a child killed by a signal, output that is not JSON, a key the two sides no
longer agree on. All of them with a fake spawn, on any runner, at 100%.

The one that is worth reading twice is the truncated answer. ADR 0029 §4 kept the *image* out of
the pipe because a base64 string cut in half decodes into a partial image — a shorter answer shaped
like an answer. A JSON object cut in half is a parse error, so the same accident here is a clean
failure, and that difference is the whole argument for the direction M10.3 reversed (dec. 7).
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from ela.infrastructure.perception import (
    TIMED_OUT,
    VISION_MODULE,
    UnsupportedTextRecognition,
    VisionTextRecognition,
)

ANSWER = {"lines": [{"text": "Riunione", "confidence": 1.0}], "unsupported_languages": []}


def recogniser(code: int, output: str) -> tuple[VisionTextRecognition, list[list[str]]]:
    """An adapter whose helper answers ``(code, output)`` and never starts anything."""
    seen: list[list[str]] = []

    async def spawn(argv: list[str], timeout: float) -> tuple[int, str]:
        del timeout
        seen.append(argv)
        return code, output

    return VisionTextRecognition(timeout=timedelta(seconds=1), runner=spawn), seen


async def test_a_clean_answer_becomes_lines_and_confidences() -> None:
    adapter, _ = recogniser(0, json.dumps(ANSWER))

    report = await adapter.recognise("/x.png", languages=("it-IT",), region=None)

    assert report.exit_code == 0
    assert not report.killed
    assert [(line.text, line.confidence) for line in report.lines] == [("Riunione", 1.0)]


async def test_the_helper_is_asked_for_the_module_the_path_and_the_languages() -> None:
    adapter, seen = recogniser(0, json.dumps(ANSWER))

    await adapter.recognise("/x.png", languages=("it-IT", "en-US"), region=None)

    assert seen[0][1:] == ["-m", VISION_MODULE, "/x.png", "it-IT,en-US"]


async def test_a_region_is_passed_as_four_numbers_and_absence_passes_none() -> None:
    """Four arguments or none: a half-given rectangle is not something to complete by guessing."""
    adapter, seen = recogniser(0, json.dumps(ANSWER))

    await adapter.recognise("/x.png", languages=("it-IT",), region=(0.0, 0.5, 1.0, 0.5))
    await adapter.recognise("/x.png", languages=("it-IT",), region=None)

    assert seen[0][5:] == ["0.0", "0.5", "1.0", "0.5"]
    assert seen[1][5:] == []


async def test_a_helper_that_ran_out_of_time_is_reported_as_killed() -> None:
    adapter, _ = recogniser(TIMED_OUT, "")

    report = await adapter.recognise("/x.png", languages=("it-IT",), region=None)

    assert (report.exit_code, report.killed) == (TIMED_OUT, True)
    assert report.lines == ()


async def test_a_non_zero_exit_carries_its_code_and_no_lines() -> None:
    adapter, _ = recogniser(3, "")

    report = await adapter.recognise("/x.png", languages=("it-IT",), region=None)

    assert (report.exit_code, report.killed, report.lines) == (3, False, ())


@pytest.mark.parametrize(
    "output",
    [
        "",
        "not json",
        '{"lines": [{"text": "Riun',  # cut in half: a parse error, not a shorter answer
        '{"lines": [{"text": "x"}]}',  # a line with no confidence
        '{"lines": [], "unknown_key": 1}',
        '{"lines": [{"text": "x", "confidence": 4.0}]}',  # a confidence outside 0..1
        "[]",
    ],
    ids=[
        "nothing",
        "not-json",
        "truncated-halfway",
        "a-line-without-a-confidence",
        "a-key-the-two-sides-do-not-share",
        "a-confidence-outside-the-range",
        "a-list-not-an-object",
    ],
)
async def test_a_child_that_did_not_make_sense_is_a_report_and_never_an_exception(
    output: str,
) -> None:
    """Nothing here raises: a reading must never be able to take ELA down with it (§33)."""
    adapter, _ = recogniser(0, output)

    report = await adapter.recognise("/x.png", languages=("it-IT",), region=None)

    assert report.lines == ()
    assert report.exit_code == 0


async def test_a_helper_that_could_not_be_started_at_all_reports_nothing() -> None:
    """Between ``available()`` and here the interpreter can go: an ``OSError`` is not an answer."""

    async def spawn(argv: list[str], timeout: float) -> tuple[int, str]:
        del argv, timeout
        raise OSError("no such interpreter")

    adapter = VisionTextRecognition(timeout=timedelta(seconds=1), runner=spawn)

    report = await adapter.recognise("/x.png", languages=("it-IT",), region=None)

    assert (report.exit_code, report.killed, report.lines) == (None, False, ())


async def test_unsupported_languages_come_back_named() -> None:
    """The value that lets the tool tell "no text" from "misconfigured" (ADR 0030 §8)."""
    adapter, _ = recogniser(0, json.dumps({"lines": [], "unsupported_languages": ["xx-YY"]}))

    report = await adapter.recognise("/x.png", languages=("xx-YY",), region=None)

    assert report.unsupported_languages == ("xx-YY",)


async def test_the_darwin_adapter_says_it_is_there_and_the_other_says_it_is_not() -> None:
    """ "ELA on Linux reads nothing" is an answer with a name, not a gap somebody discovers."""
    adapter, _ = recogniser(0, json.dumps(ANSWER))

    assert await adapter.available() is True
    assert await UnsupportedTextRecognition().available() is False


async def test_the_unsupported_adapter_reads_nothing_whatever_it_is_asked() -> None:
    report = await UnsupportedTextRecognition().recognise(
        "/x.png", languages=("it-IT",), region=(0.0, 0.0, 1.0, 1.0)
    )

    assert (report.exit_code, report.killed, report.lines) == (None, False, ())
