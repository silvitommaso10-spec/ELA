"""The second test that touches a framework, and it asserts nothing about the framework.

``vision.py`` is the other module no runner can cover — a Linux runner has no Vision — so what CI
on macOS can still prove is the part that does not depend on what the machine reads: that the
helper **runs**, that its ``ctypes`` signatures are right, that it does not die of an Objective-C
exception, and that what it prints is the shape the adapter expects.

That is not a formality here. The first attempt at reaching Vision through ``ctypes`` died of
``SIGSEGV`` before printing a line, which is precisely the class of failure this asserts the
absence of — and the reason the recognition runs in a child at all (ADR 0028 §2, met again).

The line between this and the rest is the same one ``test_probe_smoke`` draws: a test that asserted
"this image contains the word X" would pass on the machine that wrote it and prove nothing about
the contract. So: exit 0, valid JSON, known keys, and the values are whatever this Mac reads.
"""

from __future__ import annotations

import json
import platform
import struct
import subprocess  # noqa: S404 — this test *is* the one that starts the helper for real
import sys
import zlib
from pathlib import Path

import pytest

from ela.infrastructure.perception import VISION_MODULE

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin", reason="the helper reads the macOS Vision framework"
)

KEYS = {"lines", "unsupported_languages"}


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def blank_png(path: Path, width: int = 64, height: int = 64) -> Path:
    """A real, decodable PNG with nothing written on it.

    Blank on purpose: the contract is what is asserted, and a blank image makes the answer
    predictable in *shape* without making it predictable in *content*, which is the line this
    test must not cross.
    """
    row = b"\x00" + b"\xff" * (width * 3)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )
    return path


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", VISION_MODULE, *arguments],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_helper_runs_and_prints_the_object_the_adapter_expects(tmp_path: Path) -> None:
    finished = run(str(blank_png(tmp_path / "blank.png")), "it-IT,en-US")

    assert finished.returncode == 0, finished.stderr
    answer = json.loads(finished.stdout)
    assert set(answer) == KEYS
    assert isinstance(answer["lines"], list)
    assert answer["unsupported_languages"] == []


def test_a_language_this_mac_does_not_have_is_named_and_nothing_is_read(tmp_path: Path) -> None:
    """The measured trap, against the real framework: an unsupported language does **not** fail.

    Vision answers successfully with zero observations, so "no text on this screen" and "ELA was
    configured with a language that does not exist" would be the same value. The helper checks the
    supported list first, and this is that check working against the thing it protects from.
    """
    finished = run(str(blank_png(tmp_path / "blank.png")), "xx-YY,it-IT")

    assert finished.returncode == 0, finished.stderr
    answer = json.loads(finished.stdout)
    assert answer["unsupported_languages"] == ["xx-YY"]
    assert answer["lines"] == []


def test_a_region_is_accepted_and_the_answer_keeps_its_shape(tmp_path: Path) -> None:
    """Four normalised numbers, in Vision's bottom-left coordinates: the flip is the caller's."""
    finished = run(str(blank_png(tmp_path / "blank.png")), "it-IT", "0", "0", "1", "0.5")

    assert finished.returncode == 0, finished.stderr
    assert set(json.loads(finished.stdout)) == KEYS


def test_an_image_that_is_not_one_fails_loudly_instead_of_answering_empty(tmp_path: Path) -> None:
    """The distinction this whole helper is built around, at its own level.

    A file Vision cannot read raises inside the child and the child exits non-zero — which the
    adapter turns into ``text.recognition_failed``. What must **never** happen is a clean exit
    with an empty answer, because that is indistinguishable from a screen with no text on it.
    """
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")

    finished = run(str(broken), "it-IT")

    assert finished.returncode != 0
