"""``perception.read_screen_text``: the reading that costs no permission and sends nothing.

Two of these tests assert on the adapter's ``calls`` rather than on a file, and that is the point
rather than a style: **not recognising** is the behaviour under test in both, and a behaviour is
only proven by watching for it. Asserting "no artefact appeared" would pass equally well for a
tool that called the framework and threw the answer away — which is not the same thing at all when
the framework is reading somebody's screen.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from ela.domain import ExecutionStatus, PermissionDecision, RawRecognition, RawTextLine
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTextRecognition
from ela.tools import (
    ARGUMENTS_INVALID,
    PERCEPTION_READ_SCREEN_TEXT,
    TEXT_LANGUAGE_UNSUPPORTED,
    TEXT_RECOGNITION_FAILED,
    TEXT_TIMEOUT,
    TEXT_UNSUPPORTED,
    CaptureSettings,
    CaptureStore,
    ReadScreenTextTool,
)
from ela.tools.captures import (
    CAPTURE_MALFORMED,
    CAPTURE_MISSING,
    CAPTURE_UNREADABLE,
    PNG_SIGNATURE,
    name_for,
    text_name_for,
)
from tests.tools.support import allowed

DECISION = allowed(PERCEPTION_READ_SCREEN_TEXT)
CAPTURE_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
LANGUAGES = ("it-IT", "en-US")


def png(width: int = 2940, height: int = 1912) -> bytes:
    return (
        PNG_SIGNATURE
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x00" * 64
    )


def tool_for(
    tmp_path: Path,
    *,
    report: RawRecognition | None = None,
    there: bool = True,
    languages: tuple[str, ...] = LANGUAGES,
) -> tuple[ReadScreenTextTool, FakeTextRecognition, CaptureStore]:
    store = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    recognition = FakeTextRecognition(report=report, there=there)
    tool = ReadScreenTextTool(
        store, recognition, FakeClock(), FakeIdGenerator(), languages=languages
    )
    return tool, recognition, store


def capture(store: CaptureStore, *, age: timedelta | None = None) -> Path:
    """A capture in the store, aged against **the fake clock the tool purges with**.

    Ageing it against the wall clock would age it against a different clock from the one the purge
    reads, and the test would prove nothing about expiry.
    """
    target = store.directory / name_for(CAPTURE_ID)
    target.write_bytes(png())
    if age is not None:
        stamp = (FakeClock().now() - age).timestamp()
        os.utime(target, (stamp, stamp))
    return target


async def run(
    tool: ReadScreenTextTool, decision: PermissionDecision, **arguments: object
) -> object:
    return await tool.execute(decision, {"capture_id": CAPTURE_ID, "purpose": "x", **arguments})


# ----------------------------------------------------------------------------------------
# The happy path, and what it does and does not leave behind
# ----------------------------------------------------------------------------------------


async def test_the_text_lands_beside_its_image_under_the_same_stem(tmp_path: Path) -> None:
    """The name is the link between the two artefacts, and there is no index to drift from it."""
    lines = (RawTextLine(text="Riunione trimestrale", confidence=1.0),)
    tool, _, store = tool_for(tmp_path, report=RawRecognition(exit_code=0, lines=lines))
    capture(store)

    result = await run(tool, DECISION)

    assert result.output["path"] == text_name_for(CAPTURE_ID)
    written = store.directory / text_name_for(CAPTURE_ID)
    assert written.exists()
    assert json.loads(written.read_text().splitlines()[0]) == {
        "text": "Riunione trimestrale",
        "confidence": 1.0,
    }


async def test_the_file_is_private_from_its_first_byte(tmp_path: Path) -> None:
    """The parent writes, so there is no window in which the file carries the process umask.

    That window was a **declared limit** of the capture (ADR 0029 §4), where the helper creates
    the file and ELA can only ``chmod`` it afterwards. Writing the text here closes it — one of
    the two things gained by turning the direction round (ADR 0030 §7).
    """
    tool, _, store = tool_for(
        tmp_path,
        report=RawRecognition(exit_code=0, lines=(RawTextLine(text="x", confidence=1.0),)),
    )
    capture(store)

    await run(tool, DECISION)

    mode = (store.directory / text_name_for(CAPTURE_ID)).stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


async def test_the_output_carries_the_measurements_and_not_one_character(tmp_path: Path) -> None:
    """``ExecutionResult.output`` is insert-only and has no expiry: the text must never be in it.

    ``characters`` says how much of the screen became text, which is a fact about the reading and
    is exactly what somebody auditing this later needs; the text itself lives in a file with five
    minutes of life (§57, ADR 0029 §2).
    """
    lines = (
        RawTextLine(text="prima riga", confidence=1.0),
        RawTextLine(text="seconda", confidence=0.5),
    )
    tool, _, store = tool_for(tmp_path, report=RawRecognition(exit_code=0, lines=lines))
    capture(store)

    output = (await run(tool, DECISION)).output

    assert output["lines"] == 2
    assert output["characters"] == len("prima riga") + len("seconda")
    assert output["confidence_min"] == 0.5
    assert output["languages"] == LANGUAGES
    # Every value of the output, flattened: the text must not be hiding in any of them.
    flattened = " ".join(str(value) for value in output.values())
    assert "prima riga" not in flattened
    assert "seconda" not in flattened


async def test_a_screen_with_no_text_is_an_answer(tmp_path: Path) -> None:
    """Zero lines is a real observation — and it is *only* one because the languages were checked
    first. Without that check it would also be the answer to a typo in the configuration."""
    tool, _, store = tool_for(tmp_path, report=RawRecognition(exit_code=0, lines=()))
    capture(store)

    result = await run(tool, DECISION)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert (result.output["lines"], result.output["characters"]) == (0, 0)
    assert result.output["confidence_min"] is None


# ----------------------------------------------------------------------------------------
# The two behaviours proved by watching the adapter, not the disk
# ----------------------------------------------------------------------------------------


async def test_a_malformed_capture_is_never_handed_to_the_framework(tmp_path: Path) -> None:
    """A truncated PNG makes the real Vision answer **successfully with zero lines**, measured.

    So "no text on this screen" is only true if the image was whole, and the check has to come
    first. Asserted on ``calls`` because the behaviour is *not recognising*: an assertion that no
    artefact appeared would also pass for a tool that read the screen and discarded the answer.
    """
    tool, recognition, store = tool_for(tmp_path)
    (store.directory / name_for(CAPTURE_ID)).write_bytes(b"not a png at all")

    result = await run(tool, DECISION)

    assert result.error is not None
    assert result.error.code == CAPTURE_MALFORMED
    assert recognition.calls == ()


async def test_an_unsupported_language_stops_the_reading_and_says_which(tmp_path: Path) -> None:
    """The measured trap: ``xx-YY`` makes Vision answer ``ok=True`` with zero observations.

    Handed on unsplit, a typo in ``ELA_OCR_LANGUAGES`` would report "this screen contains no
    text" forever and silently. The code names the language, so the fix is legible.
    """
    tool, _, store = tool_for(
        tmp_path, report=RawRecognition(exit_code=0, unsupported_languages=("xx-YY",))
    )
    capture(store)

    result = await run(tool, DECISION)

    assert result.error is not None
    assert result.error.code == TEXT_LANGUAGE_UNSUPPORTED
    assert "xx-YY" in result.error.message
    assert not (store.directory / text_name_for(CAPTURE_ID)).exists()


# ----------------------------------------------------------------------------------------
# The TTL, applied by the purge and by nothing else
# ----------------------------------------------------------------------------------------


async def test_an_expired_capture_reads_as_missing_with_no_expired_branch(tmp_path: Path) -> None:
    """The purge runs before the reading, so the TTL is applied by the mechanism that owns it.

    A second "has it expired?" check here would be a second place to keep in step with the purge,
    and the two could disagree. There is one, and this is what it looks like from outside.
    """
    tool, recognition, store = tool_for(tmp_path)
    capture(store, age=timedelta(seconds=600))  # the TTL is 300

    result = await run(tool, DECISION)

    assert result.error is not None
    assert result.error.code == CAPTURE_MISSING
    assert recognition.calls == ()
    assert not (store.directory / name_for(CAPTURE_ID)).exists()


async def test_reading_purges_an_orphaned_recognition_left_by_an_earlier_capture(
    tmp_path: Path,
) -> None:
    """**The worst case, in sequence.** A recognition whose image is gone must not survive.

    The classification is what makes this certain (``ALREADY_EXPIRED``, proved in
    ``test_captures``); this is the same fact seen from the tool, where every write purges first.
    """
    tool, _, store = tool_for(tmp_path, report=RawRecognition(exit_code=0, lines=()))
    orphan = store.directory / "9c858901-8a57-4791-81fe-4c455b099bc9.jsonl"
    orphan.write_text('{"text": "vecchio", "confidence": 1.0}\n')
    capture(store)

    await run(tool, DECISION)

    assert not orphan.exists()


# ----------------------------------------------------------------------------------------
# The region: top-left in, bottom-left out
# ----------------------------------------------------------------------------------------


async def test_the_region_reaches_the_framework_flipped(tmp_path: Path) -> None:
    """The schema is top-left because that is how a person asks for "the top half of the screen".

    Vision's is bottom-left. The conversion is one subtraction and it is asserted because getting
    it wrong is **silent**: the recognition succeeds and returns the text of the other half.
    """
    tool, recognition, store = tool_for(tmp_path, report=RawRecognition(exit_code=0, lines=()))
    capture(store)

    result = await run(tool, DECISION, region={"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.5})

    (_, _, region) = recognition.calls[0]
    assert region == (0.0, 0.5, 1.0, 0.5)  # the top half, in Vision's coordinates
    assert result.output["region"] == (0.0, 0.0, 1.0, 0.5)  # reported as it was asked for


async def test_no_region_asks_for_the_whole_image(tmp_path: Path) -> None:
    tool, recognition, store = tool_for(tmp_path, report=RawRecognition(exit_code=0, lines=()))
    capture(store)

    result = await run(tool, DECISION)

    assert recognition.calls[0][2] is None
    assert result.output["region"] is None


@pytest.mark.parametrize(
    "region,reason",
    [
        ({"x": 0.0, "y": 0.0}, "exactly x, y, width and height"),
        ({"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.5, "z": 1}, "exactly"),
        ({"x": -0.1, "y": 0.0, "width": 1.0, "height": 0.5}, "between 0 and 1"),
        ({"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.5}, "above zero"),
        ({"x": 0.6, "y": 0.0, "width": 0.6, "height": 0.5}, "fit inside the image"),
        ({"x": True, "y": 0.0, "width": 1.0, "height": 0.5}, "must be a number"),
        ("half", "must be an object"),
    ],
    ids=[
        "missing-a-side",
        "an-extra-key",
        "outside-the-image",
        "zero-width",
        "runs-off-the-edge",
        "a-bool-is-not-a-number",
        "not-an-object",
    ],
)
async def test_a_region_that_is_not_one_is_refused_before_anything_is_read(
    tmp_path: Path, region: object, reason: str
) -> None:
    """Refused before the framework is asked: a rectangle nobody can mean is not a rectangle to
    guess at, and guessing would read some part of the user's screen."""
    tool, recognition, store = tool_for(tmp_path)
    capture(store)

    result = await run(tool, DECISION, region=region)

    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID
    assert reason in result.error.message
    assert recognition.calls == ()


# ----------------------------------------------------------------------------------------
# Everything else that can go wrong, each with its own name
# ----------------------------------------------------------------------------------------


async def test_a_machine_without_the_framework_says_so(tmp_path: Path) -> None:
    tool, _, store = tool_for(tmp_path, there=False)
    capture(store)

    result = await run(tool, DECISION)

    assert result.error is not None
    assert result.error.code == TEXT_UNSUPPORTED


async def test_a_helper_that_did_not_answer_in_time_is_retryable(tmp_path: Path) -> None:
    tool, _, store = tool_for(tmp_path, report=RawRecognition(exit_code=-1, killed=True))
    capture(store)

    result = await run(tool, DECISION)

    assert result.error is not None
    assert (result.error.code, result.error.retryable) == (TEXT_TIMEOUT, True)


async def test_a_helper_that_exited_non_zero_is_reported_with_its_code(tmp_path: Path) -> None:
    tool, _, store = tool_for(tmp_path, report=RawRecognition(exit_code=3))
    capture(store)

    result = await run(tool, DECISION)

    assert result.error is not None
    assert result.error.code == TEXT_RECOGNITION_FAILED
    assert "3" in result.error.message


@pytest.mark.parametrize(
    "arguments,reason",
    [
        ({"purpose": ""}, "purpose must be a non-empty string"),
        ({"purpose": 1}, "purpose must be a non-empty string"),
        ({"capture_id": "../../etc/passwd"}, "an id this store issued"),
        ({"capture_id": "not-a-uuid"}, "an id this store issued"),
        ({"capture_id": 7}, "an id this store issued"),
    ],
    ids=["empty-purpose", "purpose-not-a-string", "a-path", "not-a-uuid", "not-a-string"],
)
async def test_arguments_that_are_not_arguments_are_refused(
    tmp_path: Path, arguments: dict[str, object], reason: str
) -> None:
    """A capture id that could carry a path separator would be a way to point the reading out of
    the store; it stops being expressible rather than being filtered."""
    tool, recognition, store = tool_for(tmp_path)
    capture(store)

    result = await tool.execute(DECISION, {"capture_id": CAPTURE_ID, "purpose": "x", **arguments})

    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID
    assert reason in result.error.message
    assert recognition.calls == ()


async def test_the_tool_is_not_idempotent(tmp_path: Path) -> None:
    """Two readings write the file twice, so it runs under the STARTED protocol like the capture
    and is never run twice for one step."""
    assert ReadScreenTextTool.idempotent is False


async def test_a_store_that_cannot_be_written_to_is_reported_and_not_raised(
    tmp_path: Path,
) -> None:
    """The last thing that can go wrong, and it must arrive as a code like every other.

    A read-only store is the ordinary way this happens — a disk that filled, a directory somebody
    changed. It is not ELA's to fix and not ELA's to crash on.
    """
    tool, _, store = tool_for(
        tmp_path,
        report=RawRecognition(exit_code=0, lines=(RawTextLine(text="x", confidence=1.0),)),
    )
    capture(store)
    store.directory.chmod(0o500)
    try:
        result = await run(tool, DECISION)
    finally:
        store.directory.chmod(0o700)

    assert result.error is not None
    assert result.error.code == CAPTURE_UNREADABLE
    assert text_name_for(CAPTURE_ID) in result.error.message


async def test_the_worst_case_in_sequence_leaves_nothing_behind(tmp_path: Path) -> None:
    """**Criterion 6-bis.** Image and text written, then the image aged past the TTL: one purge
    takes both, and there is never a moment where ELA holds the text of a screen whose picture it
    has already thrown away.

    The classification is what makes this certain (``ALREADY_EXPIRED``, in ``test_captures``);
    this is the same property observed end to end, through the tool that writes.
    """
    tool, _, store = tool_for(
        tmp_path,
        report=RawRecognition(exit_code=0, lines=(RawTextLine(text="segreto", confidence=1.0),)),
    )
    capture(store)
    await run(tool, DECISION)
    image = store.directory / name_for(CAPTURE_ID)
    text = store.directory / text_name_for(CAPTURE_ID)
    assert image.exists() and text.exists()

    stamp = (FakeClock().now() - timedelta(seconds=600)).timestamp()
    os.utime(image, (stamp, stamp))  # only the image is aged; the text was written "now"
    store.purge(FakeClock().now())

    assert not image.exists()
    assert not text.exists()
