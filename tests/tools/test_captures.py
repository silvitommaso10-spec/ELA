"""The read-only classification of a screen capture (M10.2, ADR 0029 §1, §5).

What the tool writes and what the verifier reads back go through this module, so these tests are
the ones that stop the two from disagreeing. Nothing here needs a permission, a screen or a Mac:
a PNG is twenty-four bytes of header, and every failure mode is a file a test can lay down.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ela.tools.captures import (
    ALREADY_EXPIRED,
    CAPTURE_MALFORMED,
    CAPTURE_MISSING,
    CAPTURE_NAME_INVALID,
    CAPTURE_NOT_REGULAR,
    CAPTURE_UNREADABLE,
    HEADER_BYTES,
    PNG_SIGNATURE,
    TEXT_MALFORMED,
    CaptureProblem,
    Size,
    TextArtefact,
    _read,
    capture_id_of,
    inspect,
    inspect_text,
    is_capture_name,
    measure,
    name_for,
    path_for,
    png_size,
    retained,
    room,
    text_name_for,
)

TTL = timedelta(seconds=300)
NAME = "3f2504e0-4f89-41d3-9a0c-0305e82c3301.png"
OTHER = "9c858901-8a57-4791-81fe-4c455b099bc9.png"


def png(width: int = 2560, height: int = 1664, *, tail: bytes = b"\x00" * 64) -> bytes:
    """A PNG as far as anything ELA reads is concerned: signature, IHDR, then bytes."""
    return (
        PNG_SIGNATURE
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + tail
    )


def write(directory: Path, name: str, data: bytes, *, age: timedelta | None = None) -> Path:
    """A capture in the store, optionally aged by setting its ``mtime`` back."""
    target = directory / name
    target.write_bytes(data)
    if age is not None:
        stamp = (datetime.now(tz=UTC) - age).timestamp()
        os.utime(target, (stamp, stamp))
    return target


# ----------------------------------------------------------------------------------------
# png_size: four ways to be None, and each is a file a helper can really leave behind
# ----------------------------------------------------------------------------------------


def test_a_png_header_gives_the_size_the_ihdr_declares() -> None:
    assert png_size(png()[:HEADER_BYTES]) == Size(2560, 1664)


def test_too_few_bytes_is_not_a_png() -> None:
    """A child killed mid-write leaves exactly this."""
    assert png_size(png()[: HEADER_BYTES - 1]) is None


def test_a_wrong_signature_is_not_a_png() -> None:
    """An error page, a JPEG, a file the helper truncated to nothing."""
    assert png_size(b"<!doctype html>" + b"\x00" * 32) is None


def test_a_first_chunk_that_is_not_ihdr_is_not_a_png() -> None:
    header = bytearray(png())
    header[12:16] = b"pHYs"
    assert png_size(bytes(header)) is None


@pytest.mark.parametrize(("width", "height"), [(0, 1664), (2560, 0)])
def test_a_zero_dimension_is_a_capture_of_nothing(width: int, height: int) -> None:
    assert png_size(png(width, height)) is None


# ----------------------------------------------------------------------------------------
# Names: the store issues them, so anything else is not one it issued
# ----------------------------------------------------------------------------------------


def test_a_name_the_store_issues_is_a_uuid_and_png() -> None:
    assert is_capture_name(name_for("3f2504e0-4f89-41d3-9a0c-0305e82c3301"))


@pytest.mark.parametrize(
    "name",
    [
        "../ela.db",
        "notes/briefing.md",
        "3f2504e0-4f89-41d3-9a0c-0305e82c3301.jpg",
        "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
        "3F2504E0-4F89-41D3-9A0C-0305E82C3301.png",
        "",
    ],
)
def test_anything_else_is_not(name: str) -> None:
    """A separator stops being expressible rather than being filtered — the name arrives from a
    persisted result when the verifier reads it back (ADR 0029 §4)."""
    assert not is_capture_name(name)


def test_a_name_the_store_did_not_issue_leads_nowhere(tmp_path: Path) -> None:
    problem = path_for(tmp_path, "../ela.db")

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NAME_INVALID
    assert "../ela.db" in problem.message("../ela.db")


def test_a_name_the_store_issued_leads_into_the_store(tmp_path: Path) -> None:
    assert path_for(tmp_path, NAME) == tmp_path / NAME


# ----------------------------------------------------------------------------------------
# measure: what is there, in the order the first problem names itself
# ----------------------------------------------------------------------------------------


def test_a_capture_is_measured_from_the_disk(tmp_path: Path) -> None:
    import hashlib

    data = png()
    target = write(tmp_path, NAME, data)

    found = measure(target, TTL)

    assert not isinstance(found, CaptureProblem)
    assert found.name == NAME
    assert found.bytes == len(data)
    assert found.sha256 == hashlib.sha256(data).hexdigest()
    assert found.size == Size(2560, 1664)


def test_the_expiry_comes_from_the_file_and_not_from_a_clock(tmp_path: Path) -> None:
    """ADR 0029 §1: what ELA reports is what the purge will apply, and there is no second
    record of the user's screen to keep in step."""
    target = write(tmp_path, NAME, png(), age=timedelta(seconds=100))

    found = measure(target, TTL)

    assert not isinstance(found, CaptureProblem)
    assert (found.expires_at - datetime.now(tz=UTC)).total_seconds() == pytest.approx(200, abs=5)


def test_a_capture_that_was_never_written_is_missing(tmp_path: Path) -> None:
    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_MISSING


def test_a_directory_at_the_name_is_not_a_regular_file(tmp_path: Path) -> None:
    (tmp_path / NAME).mkdir()

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NOT_REGULAR


def test_a_link_is_not_a_regular_file_even_when_it_points_at_a_png(tmp_path: Path) -> None:
    """Going *through* a link is a doubt (§33), and the target is never opened."""
    real = write(tmp_path, OTHER, png())
    (tmp_path / NAME).symlink_to(real)

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NOT_REGULAR


def test_a_name_inside_an_unreachable_directory_is_unreadable(tmp_path: Path) -> None:
    closed = tmp_path / "closed"
    closed.mkdir()
    write(closed, NAME, png())
    closed.chmod(0o000)
    try:
        problem = measure(closed / NAME, TTL)
    finally:
        closed.chmod(0o700)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_UNREADABLE
    assert "PermissionError" in problem.reason


def test_a_file_that_cannot_be_opened_is_unreadable(tmp_path: Path) -> None:
    """``lstat`` said regular file and the read still failed: the second net, and it reports."""
    target = write(tmp_path, NAME, png())
    target.chmod(0o000)
    try:
        problem = measure(target, TTL)
    finally:
        target.chmod(0o600)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_UNREADABLE


def test_bytes_that_are_not_a_png_are_malformed_and_report_only_a_size(tmp_path: Path) -> None:
    """A helper that exits 0 and leaves this behind has not captured anything. The reason carries
    a length and never a byte (§57)."""
    write(tmp_path, NAME, b"not an image at all")

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_MALFORMED
    assert "19 bytes" in problem.reason
    assert "not an image" not in problem.reason


def test_an_empty_file_is_malformed(tmp_path: Path) -> None:
    write(tmp_path, NAME, b"")

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_MALFORMED


def test_a_capture_replaced_by_a_directory_between_the_checks_and_the_read_is_refused(
    tmp_path: Path,
) -> None:
    """The ``fstat`` after ``open`` is the net behind ``lstat``, probed on the read itself."""
    (tmp_path / "adir").mkdir()

    with pytest.raises(OSError, match="not a regular file"):
        _read(tmp_path / "adir")


# ----------------------------------------------------------------------------------------
# inspect: the verifier's entry point
# ----------------------------------------------------------------------------------------


def test_inspect_refuses_a_name_before_touching_the_disk(tmp_path: Path) -> None:
    problem = inspect(tmp_path, "../ela.db", TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NAME_INVALID


def test_inspect_finds_what_the_tool_wrote(tmp_path: Path) -> None:
    write(tmp_path, NAME, png())

    found = inspect(tmp_path, NAME, TTL)

    assert not isinstance(found, CaptureProblem)
    assert found.size == Size(2560, 1664)


# ----------------------------------------------------------------------------------------
# retained: only what the store issued, only regular files
# ----------------------------------------------------------------------------------------


def test_an_empty_store_holds_nothing(tmp_path: Path) -> None:
    assert retained(tmp_path, TTL) == ()


def test_a_store_that_is_not_there_holds_nothing(tmp_path: Path) -> None:
    """A read must not raise because the directory went away: ``/diagnostics`` calls this."""
    assert retained(tmp_path / "gone", TTL) == ()


def test_a_store_that_cannot_be_listed_holds_nothing(tmp_path: Path) -> None:
    tmp_path.chmod(0o000)
    try:
        assert retained(tmp_path, TTL) == ()
    finally:
        tmp_path.chmod(0o700)


def test_a_stranger_in_the_store_is_not_counted(tmp_path: Path) -> None:
    """Not ELA's to count — and, as the purge reads this same list, not ELA's to delete."""
    write(tmp_path, NAME, png())
    (tmp_path / "somebody-elses-file.txt").write_text("mine", encoding="utf-8")

    assert [one.name for one in retained(tmp_path, TTL)] == [NAME]


def test_a_directory_named_like_a_capture_is_not_counted(tmp_path: Path) -> None:
    (tmp_path / NAME).mkdir()

    assert retained(tmp_path, TTL) == ()


def test_a_dangling_link_named_like_a_capture_is_not_counted(tmp_path: Path) -> None:
    (tmp_path / NAME).symlink_to(tmp_path / "nowhere.png")

    assert retained(tmp_path, TTL) == ()


def test_a_capture_that_vanishes_between_the_listing_and_the_stat_is_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A race no test can stage for real: the file is listed and gone a microsecond later.

    Injected rather than staged, and injected at the syscall the race is *in* — not asserted by a
    mock that only proves ``lstat`` was called. Without this branch ``/diagnostics`` would answer
    500 because a capture expired while it was being counted.
    """
    write(tmp_path, NAME, png())
    real = Path.lstat

    def vanishing(self: Path) -> os.stat_result:
        if self.name == NAME:
            raise FileNotFoundError(self)
        return real(self)

    monkeypatch.setattr(Path, "lstat", vanishing)

    assert retained(tmp_path, TTL) == ()


def test_captures_come_back_soonest_expiry_first(tmp_path: Path) -> None:
    write(tmp_path, NAME, png(), age=timedelta(seconds=10))
    write(tmp_path, OTHER, png(), age=timedelta(seconds=200))

    assert [one.name for one in retained(tmp_path, TTL)] == [OTHER, NAME]


def test_what_is_held_carries_the_size_on_disk(tmp_path: Path) -> None:
    data = png()
    write(tmp_path, NAME, data)

    assert retained(tmp_path, TTL)[0].bytes == len(data)


# ----------------------------------------------------------------------------------------
# room: the ceilings refuse, they never evict (ADR 0029 §15)
# ----------------------------------------------------------------------------------------


def test_an_empty_store_has_room(tmp_path: Path) -> None:
    assert room(tmp_path, TTL, max_count=20, max_bytes=1 << 30) is None


def test_the_count_ceiling_refuses(tmp_path: Path) -> None:
    write(tmp_path, NAME, png())

    refusal = room(tmp_path, TTL, max_count=1, max_bytes=1 << 30)

    assert refusal is not None
    assert "1 captures" in refusal


def test_the_byte_ceiling_refuses(tmp_path: Path) -> None:
    data = png()
    write(tmp_path, NAME, data)

    refusal = room(tmp_path, TTL, max_count=20, max_bytes=len(data))

    assert refusal is not None
    assert f"{len(data)} bytes" in refusal


def test_a_full_store_still_holds_what_it_held(tmp_path: Path) -> None:
    """The whole point of §15: refusing is not evicting, and the first capture stays."""
    write(tmp_path, NAME, png())

    assert room(tmp_path, TTL, max_count=1, max_bytes=1 << 30) is not None
    assert (tmp_path / NAME).is_file()


def test_the_mode_of_a_capture_is_not_the_classifications_business(tmp_path: Path) -> None:
    """This module reads; tightening the mode is the store's, in :mod:`ela.tools.screen`."""
    target = write(tmp_path, NAME, png())
    target.chmod(0o644)

    assert not isinstance(measure(target, TTL), CaptureProblem)
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


# ----------------------------------------------------------------------------------------
# The derived artefact: it inherits, it never has a clock of its own (M10.3 dec. 10)
# ----------------------------------------------------------------------------------------

TEXT = "3f2504e0-4f89-41d3-9a0c-0305e82c3301.jsonl"
OTHER_TEXT = "9c858901-8a57-4791-81fe-4c455b099bc9.jsonl"


def jsonl(*lines: tuple[str, float]) -> bytes:
    return "".join(
        json.dumps({"text": text, "confidence": confidence}) + "\n" for text, confidence in lines
    ).encode("utf-8")


def test_the_two_artefacts_of_one_capture_share_a_stem() -> None:
    """The name *is* the link: no index says which text belongs to which image, so there is no
    index to fall out of step with the disk."""
    capture_id = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"

    assert name_for(capture_id) == NAME
    assert text_name_for(capture_id) == TEXT
    assert capture_id_of(NAME) == capture_id_of(TEXT) == capture_id


def test_a_name_the_store_did_not_issue_belongs_to_no_capture() -> None:
    assert capture_id_of("notes.jsonl") is None
    assert capture_id_of("../../etc/passwd") is None


def test_a_recognition_inherits_the_expiry_of_its_image_and_not_its_own(tmp_path: Path) -> None:
    """The image is five minutes old and the text was written now; they expire together.

    Read on its own ``mtime`` the text would get five extra minutes of life — which is the one
    way this milestone could leave the text of somebody's screen on the disk after the picture of
    it had gone.
    """
    write(tmp_path, NAME, png(), age=timedelta(seconds=240))
    write(tmp_path, TEXT, jsonl(("ciao", 1.0)))

    held = {one.name: one.expires_at for one in retained(tmp_path, TTL)}

    assert held[TEXT] == held[NAME]
    assert held[TEXT] < datetime.now(tz=UTC) + timedelta(seconds=61)


def test_a_recognition_whose_image_is_gone_is_already_expired(tmp_path: Path) -> None:
    """**The worst case, and it is asserted on the classification with no purge in sight.**

    Proving this by running the purge and watching both files go would prove that *this* purge, in
    *this* order, behaves. A reordering would break it silently. What is proven instead is that
    ``retained`` answers ``ALREADY_EXPIRED`` — a pure function of the directory — after which the
    purge cannot fail to take it, because its only comparison is ``expires_at <= now`` and this
    value is in the past for every ``now`` there is.
    """
    write(tmp_path, TEXT, jsonl(("orfano", 1.0)))  # no ``.png`` beside it, ever

    (orphan,) = retained(tmp_path, TTL)

    assert orphan.name == TEXT
    assert orphan.expires_at == ALREADY_EXPIRED
    assert orphan.expires_at <= datetime.min.replace(tzinfo=UTC)


@pytest.mark.parametrize("ttl", [timedelta(seconds=1), timedelta(hours=1), timedelta(days=3650)])
def test_an_orphan_is_already_expired_whatever_the_ttl(tmp_path: Path, ttl: timedelta) -> None:
    """No lifetime to inherit means no lifetime, and a longer TTL cannot give it one."""
    write(tmp_path, TEXT, jsonl(("orfano", 1.0)))

    assert retained(tmp_path, ttl)[0].expires_at == ALREADY_EXPIRED


def test_a_directory_where_the_image_should_be_leaves_the_text_an_orphan(tmp_path: Path) -> None:
    """Not a regular file is not an origin: the fail-safe direction of §33 on content."""
    (tmp_path / NAME).mkdir()
    write(tmp_path, TEXT, jsonl(("orfano", 1.0)))

    held = {one.name: one.expires_at for one in retained(tmp_path, TTL)}

    assert held[TEXT] == ALREADY_EXPIRED


def test_the_byte_ceiling_counts_the_text_and_the_count_ceiling_does_not(tmp_path: Path) -> None:
    """The two ceilings ask different questions, so they count different things.

    ``max_count`` asks how many screens ELA is holding, and reading one does not make it two.
    ``max_bytes`` asks about the disk, where every byte is a byte.
    """
    write(tmp_path, NAME, png())
    write(tmp_path, TEXT, jsonl(("ciao", 1.0)))

    assert room(tmp_path, TTL, max_count=1, max_bytes=10**9) is not None
    assert room(tmp_path, TTL, max_count=2, max_bytes=10**9) is None
    total = sum(one.bytes for one in retained(tmp_path, TTL))
    assert room(tmp_path, TTL, max_count=9, max_bytes=total) is not None


def test_a_recognition_is_measured_from_the_disk(tmp_path: Path) -> None:
    data = jsonl(("prima riga", 1.0), ("seconda", 0.5))
    write(tmp_path, NAME, png())
    write(tmp_path, TEXT, data)

    found = inspect_text(tmp_path, TEXT, TTL)

    assert isinstance(found, TextArtefact)
    assert (found.name, found.bytes, found.lines) == (TEXT, len(data), 2)
    assert found.characters == len("prima riga") + len("seconda")
    assert found.sha256 == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "data",
    [
        b"not json at all\n",
        b'{"text": "x"}\n',  # a missing confidence
        b'{"text": "x", "confidence": 1.0, "extra": 1}\n',
        b'{"text": 1, "confidence": 1.0}\n',
        b'{"text": "x", "confidence": true}\n',  # a bool is an int, and is not a confidence
        b'["x", 1.0]\n',
        b'{"text": "x", "confidence": 1.0}\n{"truncat',  # a helper killed mid-write
        b"\xff\xfe not utf-8\n",
    ],
    ids=[
        "not-json",
        "missing-confidence",
        "an-extra-field",
        "text-is-not-a-string",
        "confidence-is-a-bool",
        "a-list-not-an-object",
        "truncated-halfway",
        "not-utf-8",
    ],
)
def test_bytes_that_are_not_the_json_lines_ela_writes_are_malformed(
    tmp_path: Path, data: bytes
) -> None:
    """The self-delimiting property, exercised: a truncated file **fails to parse**.

    That is what base64 could not do (ADR 0029 §4) — a truncated image decodes into a partial
    image, a shorter answer shaped like an answer — and it is why the text may cross a pipe where
    the pixels could not (M10.3 dec. 7).
    """
    write(tmp_path, NAME, png())
    write(tmp_path, TEXT, data)

    problem = inspect_text(tmp_path, TEXT, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == TEXT_MALFORMED
    assert "byte" in problem.reason
    assert data.decode("utf-8", "replace")[:8] not in problem.reason  # a size, never a byte


def test_an_empty_recognition_is_a_recognition_of_nothing_not_a_malformed_one(
    tmp_path: Path,
) -> None:
    """A screen with no text on it is an answer. It is *only* an answer because the language was
    validated first (dec. 8): otherwise this and "ELA was misconfigured" would be the same file.
    """
    write(tmp_path, NAME, png())
    write(tmp_path, TEXT, b"")

    found = inspect_text(tmp_path, TEXT, TTL)

    assert isinstance(found, TextArtefact)
    assert (found.lines, found.characters) == (0, 0)


def test_inspect_text_refuses_a_png_name_and_inspect_refuses_a_jsonl_one(tmp_path: Path) -> None:
    """Each artefact has one reader, and neither will read the other's file as if it were its
    own — the way a PNG would otherwise arrive at the text verifier as "malformed JSON"."""
    assert inspect_text(tmp_path, NAME, TTL) == CaptureProblem(
        CAPTURE_NAME_INVALID, "is not a name this store issues"
    )
    assert inspect(tmp_path, TEXT, TTL) == CaptureProblem(
        CAPTURE_NAME_INVALID, "is not a name this store issues"
    )


def test_a_recognition_that_was_never_written_is_missing(tmp_path: Path) -> None:
    write(tmp_path, NAME, png())

    problem = inspect_text(tmp_path, TEXT, TTL)

    assert problem == CaptureProblem(CAPTURE_MISSING, "was not written")


def test_a_directory_at_the_recognition_name_is_not_a_regular_file(tmp_path: Path) -> None:
    write(tmp_path, NAME, png())
    (tmp_path / TEXT).mkdir()

    problem = inspect_text(tmp_path, TEXT, TTL)

    assert problem == CaptureProblem(CAPTURE_NOT_REGULAR, "is not a regular file")


def test_a_capture_whose_mtime_vanishes_between_the_read_and_the_stat_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one line between reading the bytes and reading the clock they expire on.

    Produced rather than skipped: the file really can go in that window, and a capture ELA cannot
    date is a capture ELA cannot say when it will purge.
    """
    write(tmp_path, NAME, png())
    original = Path.lstat
    calls = {"n": 0}

    def flaky(self: Path) -> object:
        calls["n"] += 1
        if calls["n"] > 1:  # the first is the regular-file check, the second the expiry
            raise OSError("vanished")
        return original(self)

    monkeypatch.setattr(Path, "lstat", flaky)

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_UNREADABLE
