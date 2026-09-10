"""``perception.listen`` verified, and the limit it has to say out loud.

What this verifier proves is that ELA wrote what it says it wrote. What it **cannot** prove is
that those are the words somebody said — and nothing ELA has can, because the only thing that
could is the recording, and the milestone decided not to keep it (M11.2 dec. E).

That limit is bigger than the capture's, so it gets a test of its own rather than a sentence in a
docstring: :func:`test_the_verifier_passes_a_transcript_of_words_nobody_said`. A verifier that
sounded stronger than it is would be worse than none (M11.1 dec. C), and the way to keep it honest
is to write down the case it happily accepts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from ela.domain import ErrorMetadata, ExecutionResult, ExecutionStatus, JsonMapping
from ela.tools.captures import CAPTURE_MISSING, TEXT_MALFORMED, transcript_name_for
from ela.tools.verifiers import (
    TRANSCRIPT_DECLARED_MISMATCH,
    TRANSCRIPT_EXISTS,
    TRANSCRIPT_MATCHES,
    ListenVerifier,
)
from tests.domain.examples import EXECUTION_RESULT

TRANSCRIPT_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
TTL = timedelta(minutes=5)
SAID = " Ela, sposta la call di domani."


def payload(text: str = SAID) -> bytes:
    return (
        json.dumps(
            {
                "text": text,
                "start_ms": 0,
                "end_ms": 1840,
                "tokens": [{"text": " Ela", "p": 0.543607}],
            }
        ).encode("utf-8")
        + b"\n"
    )


def written(tmp_path: Path, data: bytes = b"") -> Path:
    target = tmp_path / transcript_name_for(TRANSCRIPT_ID)
    target.write_bytes(data or payload())
    return target


def declared(target: Path, **overrides: object) -> JsonMapping:
    raw = target.read_bytes()
    output: dict[str, object] = {
        "transcript_id": TRANSCRIPT_ID,
        "path": target.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "segments": 1,
        "characters": len(SAID),
    }
    output.update(overrides)
    return output


def succeeded(capability_id: object, output: JsonMapping) -> ExecutionResult:
    return EXECUTION_RESULT.model_copy(
        update={
            "capability_id": capability_id,
            "status": ExecutionStatus.SUCCEEDED,
            "error": None,
            "output": output,
        }
    )


async def check(
    tmp_path: Path, output: JsonMapping, condition: str = TRANSCRIPT_MATCHES
) -> ErrorMetadata | None:
    verifier = ListenVerifier(tmp_path, TTL)
    failures = await verifier.verify((condition,), {}, succeeded(verifier.capability_id, output))
    return failures[0] if failures else None


async def test_a_transcript_that_is_there_and_matches_passes_both_conditions(
    tmp_path: Path,
) -> None:
    target = written(tmp_path)
    output = declared(target)

    assert await check(tmp_path, output, TRANSCRIPT_EXISTS) is None
    assert await check(tmp_path, output, TRANSCRIPT_MATCHES) is None


async def test_a_transcript_that_is_not_there_fails(tmp_path: Path) -> None:
    failure = await check(tmp_path, {"path": transcript_name_for(TRANSCRIPT_ID)})

    assert failure is not None
    assert failure.code == CAPTURE_MISSING


async def test_a_transcript_that_no_longer_parses_fails(tmp_path: Path) -> None:
    target = written(tmp_path, b"}{\n")

    failure = await check(tmp_path, declared(target), TRANSCRIPT_EXISTS)

    assert failure is not None
    assert failure.code == TEXT_MALFORMED


async def test_a_path_that_is_not_a_string_is_refused_before_the_disk(tmp_path: Path) -> None:
    failure = await check(tmp_path, {"path": 7})

    assert failure is not None
    assert failure.retryable is False


@pytest.mark.parametrize(
    ("field", "value"),
    [("bytes", 1), ("sha256", "0" * 64), ("segments", 9), ("characters", 3)],
)
async def test_a_declaration_the_disk_contradicts_fails_and_names_only_the_field(
    tmp_path: Path, field: str, value: object
) -> None:
    """The names of what differs, never the values: a digest beside another is two fingerprints
    of the user's room in the trail, and a character count is harmless while the words are not."""
    target = written(tmp_path)

    failure = await check(tmp_path, declared(target, **{field: value}))

    assert failure is not None
    assert failure.code == TRANSCRIPT_DECLARED_MISMATCH
    assert field in failure.message
    assert hashlib.sha256(target.read_bytes()).hexdigest() not in failure.message


async def test_the_verifier_passes_a_transcript_of_words_nobody_said(tmp_path: Path) -> None:
    """The declared limit, made a test so that nobody mistakes this for a proof of hearing.

    This is «Grazie a tutti.» — what a transcriber writes when handed thirty seconds of digital
    silence. The verifier accepts it, because it is exactly what the tool says it wrote. What
    stops it from ever being written is the preflight and the signal gate, upstream of here; this
    verifier's job is a different one, and pretending otherwise would be the failure.
    """
    invented = " Grazie a tutti."
    target = written(tmp_path, payload(invented))
    output = declared(target, characters=len(invented))

    assert await check(tmp_path, output, TRANSCRIPT_MATCHES) is None


async def test_the_conditions_are_the_two_this_verifier_answers() -> None:
    assert ListenVerifier.conditions == frozenset({TRANSCRIPT_EXISTS, TRANSCRIPT_MATCHES})
