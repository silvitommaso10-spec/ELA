"""The files from the browser and the login under a policy, in the tools (M13.15, ADR 0071).

What a yes guaranteed and a policy does not have, and what takes its place — decisions 3, 4, 7 and
13, answers 36–39 and 51 of the review of the SPEC:

- **an upload reads its file once** under a policy: the bytes given to the page are exactly the
  ones read, and the result says their size and sha256 — never compared with a question that was
  never asked. The road is taken **only** for a decision with an authorization and no approval;
  any other decision takes the road of a yes, which refuses without what its question named;
- **the prospect of a covered call reads no byte** and refuses with the same code as the question's
  prospect — the same function for the same refusal;
- **what ELA uses to exist and a file with more than one name are refused at every read** — the
  defect C of the census (a file with two names composed a question), and the same in ``fs.read``
  (answer 36) —, on the path and on the descriptor that reads;
- **the «partirebbe» of a policy's birth** for the four files — the folder, the sites, the browser —
  and for the login — the profile, the window, and each entry of the vault for the site, shown by
  its name and its masked username, never its id.
"""

from __future__ import annotations

import hashlib
import os
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    ApprovalId,
    AuthorizationId,
    DecisionId,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.permissions import (
    BROWSER_DOWNLOAD,
    BROWSER_DOWNLOAD_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_UPLOAD,
    BROWSER_UPLOAD_AS_YOU,
)
from ela.ports import VAULT_LOCKED, GivenFile, ShownEntry
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeVault,
    FakeVaultEntry,
)
from ela.tools import browser_files
from ela.tools.base import ARGUMENTS_INVALID, under_a_policy
from ela.tools.browser import NOT_INSTALLED
from ela.tools.browser_files import (
    FILE_CHANGED,
    FILE_TOO_LARGE,
    SITE_NOT_DECLARED,
    UPLOAD_MAX_BYTES,
)
from ela.tools.fs import (
    CHUNK,
    ELA_S_OWN,
    HARD_LINK,
    NO_ROOT,
    NOT_A_FOLDER,
    FsReadTool,
    MoreThanOneName,
    read_bytes,
)
from ela.tools.paths import PATH_IS_DIRECTORY, PATH_MISSING, PATH_OUTSIDE_ROOT, PATH_SYMLINK
from tests.tools.test_account_tools import ANNA, LOGIN, MARIO, login
from tests.tools.test_browser_files import (
    BYTES,
    CLOCK,
    UPLOAD,
    _file_field,
    download,
    root,
    upload,
)

AUTHORIZATION = AuthorizationId(UUID("00000000-0000-4000-8000-0000000a0715"))
APPROVAL = ApprovalId(UUID("00000000-0000-4000-8000-0000000a9970"))
ENTRY = MARIO.id


def deciding(
    capability: str, *, authorization: bool = True, approval: bool = False
) -> PermissionDecision:
    """An allowed decision as the Guardian writes it since M13.15: the grant it rests on, and —
    for a grant born from a yes — the approval behind it."""
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        authorization_id=AUTHORIZATION if authorization else None,
        approval_id=APPROVAL if approval else None,
        expires_at=CLOCK.now() + timedelta(minutes=5),
    )


def with_two_names(folder: Path, outside: Path) -> Path:
    """``ELA/prova/da-caricare.txt`` under ``folder``, a second name of ``outside/segreto.txt``."""
    outside.mkdir(exist_ok=True)
    (outside / "segreto.txt").write_bytes(BYTES)
    target = folder / "ELA" / "prova" / "da-caricare.txt"
    os.link(outside / "segreto.txt", target)
    assert os.lstat(target).st_nlink == 2
    return target


PROFILES = pytest.mark.parametrize(
    ("profile", "capability"), [(False, BROWSER_UPLOAD), (True, BROWSER_UPLOAD_AS_YOU)]
)


def counting_reads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every read of an upload's bytes, remembered — the real read, then counted."""
    read: list[Path] = []

    def counted(target: Path, **named: Any) -> bytes:
        read.append(target)
        return read_bytes(target, **named)

    monkeypatch.setattr(browser_files, "read_bytes", counted)
    return read


# ----------------------------------------------------------------------------------------
# Which road: a policy only with an authorization and no approval (answer 38)
# ----------------------------------------------------------------------------------------


def test_the_road_of_a_policy_is_taken_only_with_an_authorization_and_no_approval() -> None:
    assert under_a_policy(deciding(BROWSER_UPLOAD)) is True
    assert under_a_policy(deciding(BROWSER_UPLOAD, approval=True)) is False
    assert under_a_policy(deciding(BROWSER_UPLOAD, authorization=False)) is False
    assert under_a_policy(deciding(BROWSER_UPLOAD, authorization=False, approval=True)) is False


# ----------------------------------------------------------------------------------------
# An upload under a policy: one read, and the result says what left (decision 3, answer 37)
# ----------------------------------------------------------------------------------------


@PROFILES
async def test_under_a_policy_an_upload_reads_once_and_gives_exactly_those_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: bool, capability: str
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = (FakeAccountBrowser if profile else FakeBrowser)(
        FakePage(fields={"#fileinput": _file_field()})
    )
    tool = upload(browser, folder, profile=profile)
    read = counting_reads(monkeypatch)

    covered = await tool.prospect_covered(UPLOAD)
    reads_before = len(read)
    result = await tool.execute(deciding(capability), UPLOAD, FakeStop(), {})

    assert covered.refusal is None and reads_before == 0, "the covered prospect read a byte"
    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert len(read) == 1, "the file was read more than once"
    assert browser.given == [("#fileinput", GivenFile("da-caricare.txt", "text/plain", BYTES))]
    assert result.output["size"] == len(BYTES)
    assert result.output["digest"] == hashlib.sha256(BYTES).hexdigest()
    assert "size" not in tool.audit_numbers and "digest" not in tool.audit_numbers


async def test_a_yes_compares_with_its_question_and_any_other_decision_takes_the_road_of_a_yes(
    tmp_path: Path,
) -> None:
    """The mistake falls on the safe side (answer 38): a yes without what its question named, and
    a decision with neither a grant nor an approval, both refuse — only a policy reads and gives."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    for chosen in (
        deciding(BROWSER_UPLOAD, approval=True),
        deciding(BROWSER_UPLOAD, authorization=False),
    ):
        browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))

        result = await upload(browser, folder).execute(chosen, UPLOAD, FakeStop(), {})

        assert result.error is not None and result.error.code == FILE_CHANGED, chosen
        assert browser.given == [] and browser.opened == []


async def test_a_yes_gives_its_file_and_says_its_size_and_sha256_too(tmp_path: Path) -> None:
    """Answer 37: one form of the result — under a yes too the result says what left."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    tool = upload(browser, folder)
    asked = await tool.prospect(UPLOAD)

    result = await tool.execute(
        deciding(BROWSER_UPLOAD, approval=True), UPLOAD, FakeStop(), asked.named or {}
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert (result.output["size"], result.output["digest"]) == (
        len(BYTES),
        hashlib.sha256(BYTES).hexdigest(),
    )


async def test_nothing_given_says_no_size_and_no_sha256(tmp_path: Path) -> None:
    """The two keys say the bytes that left: a field that is not a file field receives nothing."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={}))

    result = await upload(browser, folder).execute(deciding(BROWSER_UPLOAD), UPLOAD, FakeStop(), {})

    assert result.error is not None
    assert "size" not in result.output and "digest" not in result.output


async def test_a_file_that_grows_past_the_limit_under_a_policy_is_refused_and_nothing_leaves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 51: the read stops one byte past the limit, and that byte refuses the file."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(b"12345")
    monkeypatch.setattr(browser_files, "UPLOAD_MAX_BYTES", 10)
    asked: list[int | None] = []

    def grown(target: Path, *, at_most: int | None = None) -> bytes:
        asked.append(at_most)
        return b"x" * 11

    monkeypatch.setattr(browser_files, "read_bytes", grown)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))

    result = await upload(browser, folder).execute(deciding(BROWSER_UPLOAD), UPLOAD, FakeStop(), {})

    assert result.error is not None and result.error.code == FILE_TOO_LARGE
    assert asked == [10] and browser.given == []


@pytest.mark.parametrize("at_most", [10, CHUNK - 1, CHUNK, CHUNK + 1, 2 * CHUNK])
def test_the_read_stops_one_byte_past_the_limit(tmp_path: Path, at_most: int) -> None:
    """Decision 51, to the byte: a file larger than the limit gives **the limit and one byte**,
    never the rest of a piece of the read — whatever the limit is against the size of a piece
    (found by the consistency reading of the branch, finding 1)."""
    target = tmp_path / "grande.bin"
    target.write_bytes(b"x" * (3 * CHUNK + 7))

    assert len(read_bytes(target, at_most=at_most)) == at_most + 1
    assert UPLOAD_MAX_BYTES == 50 * 1024 * 1024


def test_a_file_within_the_limit_is_read_whole(tmp_path: Path) -> None:
    target = tmp_path / "piccolo.bin"
    target.write_bytes(b"x" * (CHUNK + 3))

    assert len(read_bytes(target, at_most=CHUNK + 3)) == CHUNK + 3
    assert len(read_bytes(target)) == CHUNK + 3


def test_a_second_name_is_refused_on_the_descriptor_that_reads(tmp_path: Path) -> None:
    """Answer 36 and decision 51: regular and with one name, asked of the descriptor with
    ``fstat`` — a name added after the path was looked at is still a second name."""
    (tmp_path / "uno.txt").write_bytes(BYTES)
    os.link(tmp_path / "uno.txt", tmp_path / "due.txt")

    with pytest.raises(MoreThanOneName):
        read_bytes(tmp_path / "uno.txt")


# ----------------------------------------------------------------------------------------
# What ELA uses to exist, and a file with more than one name, at every read (defect C)
# ----------------------------------------------------------------------------------------


@PROFILES
async def test_a_file_with_two_names_one_outside_the_root_is_not_uploaded(
    tmp_path: Path, profile: bool, capability: str
) -> None:
    """Point C of the census of M13.15, red before its fix: the question was composed with the
    bytes of a file whose other name is outside the root — and under a yes too (answer 36)."""
    folder = root(tmp_path)
    with_two_names(folder, tmp_path / "fuori")
    browser = (FakeAccountBrowser if profile else FakeBrowser)(
        FakePage(fields={"#fileinput": _file_field()})
    )
    tool = upload(browser, folder, profile=profile)

    asked = await tool.prospect(UPLOAD)
    covered = await tool.prospect_covered(UPLOAD)
    under_a_yes = await tool.execute(deciding(capability, approval=True), UPLOAD, FakeStop(), {})
    under_a_policy_ = await tool.execute(deciding(capability), UPLOAD, FakeStop(), {})

    for refusal in (asked.refusal, covered.refusal, under_a_yes.error, under_a_policy_.error):
        assert refusal is not None and refusal.code == HARD_LINK, refusal
    assert browser.given == [] and browser.opened == []


@PROFILES
async def test_an_upload_refuses_what_ela_uses_to_exist_on_both_roads(
    tmp_path: Path, profile: bool, capability: str
) -> None:
    """Decision 7: the list of the places no write reaches is the list no read reaches — given to
    the uploads, and compared both ways, before the question and before a covered spend."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = (FakeAccountBrowser if profile else FakeBrowser)(
        FakePage(fields={"#fileinput": _file_field()})
    )
    tool = upload(
        browser, folder, profile=profile, protected={"the database": folder / "ELA" / "prova"}
    )

    asked = await tool.prospect(UPLOAD)
    covered = await tool.prospect_covered(UPLOAD)
    ran = await tool.execute(deciding(capability), UPLOAD, FakeStop(), {})

    for refusal in (asked.refusal, covered.refusal, ran.error):
        assert refusal is not None and refusal.code == ELA_S_OWN, refusal
    assert ELA_S_OWN in tool.error_codes and HARD_LINK in tool.error_codes
    assert browser.given == []


async def test_fs_read_refuses_a_file_with_two_names_and_what_ela_uses_to_exist(
    tmp_path: Path,
) -> None:
    """Answer 36, red before its fix: ``fs.read`` had defect C — the same function now judges it."""
    folder = root(tmp_path)
    with_two_names(folder, tmp_path / "fuori")
    tool = FsReadTool(folder, CLOCK, FakeIdGenerator(), protected={})
    guarded = FsReadTool(
        folder, CLOCK, FakeIdGenerator(), protected={"the database": folder / "ELA"}
    )
    (folder / "ELA" / "uno.txt").write_text("ciao")

    two_names = await tool.prospect({"path": "ELA/prova/da-caricare.txt"})
    ran = await tool.execute(
        deciding("fs.read", approval=True), {"path": "ELA/prova/da-caricare.txt"}, FakeStop()
    )
    protected = await guarded.prospect({"path": "ELA/uno.txt"})

    assert two_names.refusal is not None and two_names.refusal.code == HARD_LINK
    assert ran.error is not None and ran.error.code == HARD_LINK
    assert "content" not in ran.output
    assert protected.refusal is not None and protected.refusal.code == ELA_S_OWN
    assert {HARD_LINK, ELA_S_OWN} <= FsReadTool.error_codes


# ----------------------------------------------------------------------------------------
# The prospect of a covered call: the question's refusals, and not a byte read (answer 39)
# ----------------------------------------------------------------------------------------


def _made(kind: str, folder: Path, outside: Path) -> dict[str, Any]:
    """The world of one refusal, built under ``folder``, and the arguments of the call."""
    target = folder / "ELA" / "prova" / "da-caricare.txt"
    if kind == SITE_NOT_DECLARED:
        target.write_bytes(BYTES)
        return {**UPLOAD, "site": "altro.example"}
    if kind == PATH_IS_DIRECTORY:
        target.mkdir()
    elif kind == PATH_SYMLINK:
        (folder / "ELA" / "vero.txt").write_bytes(BYTES)
        target.symlink_to(folder / "ELA" / "vero.txt")
    elif kind == PATH_OUTSIDE_ROOT:
        outside.mkdir(exist_ok=True)
        (outside / "vero.txt").write_bytes(BYTES)
        target.symlink_to(outside / "vero.txt")
    elif kind == HARD_LINK:
        with_two_names(folder, outside)
    elif kind == FILE_TOO_LARGE:
        with target.open("wb") as big:
            big.truncate(UPLOAD_MAX_BYTES + 1)
    elif kind == NO_ROOT:
        target.write_bytes(BYTES)
    return dict(UPLOAD)


@pytest.mark.parametrize(
    "kind",
    [
        SITE_NOT_DECLARED,
        PATH_MISSING,
        PATH_IS_DIRECTORY,
        PATH_SYMLINK,
        PATH_OUTSIDE_ROOT,
        HARD_LINK,
        FILE_TOO_LARGE,
        NO_ROOT,
    ],
)
async def test_the_covered_prospect_refuses_what_the_question_refuses_and_reads_no_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    folder = root(tmp_path)
    arguments = _made(kind, folder, tmp_path / "fuori")
    tool = upload(FakeBrowser(), tmp_path / "missing" if kind == NO_ROOT else folder)
    read = counting_reads(monkeypatch)

    covered = await tool.prospect_covered(arguments)
    unread = len(read)
    asked = await tool.prospect(arguments)

    assert covered.refusal is not None and covered.refusal.code == kind
    assert asked.refusal is not None and asked.refusal.code == kind
    assert unread == 0, "the prospect of a covered call read the file"


async def test_a_browser_that_is_not_there_refuses_both_prospects(tmp_path: Path) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    tool = upload(FakeBrowser(installed=False), folder)

    for prospect in (await tool.prospect_covered(UPLOAD), await tool.prospect(UPLOAD)):
        assert prospect.refusal is not None and prospect.refusal.code == NOT_INSTALLED


# ----------------------------------------------------------------------------------------
# The «partirebbe» of a birth: the four files (decisions 6 and 7)
# ----------------------------------------------------------------------------------------

FOUR = pytest.mark.parametrize(
    ("capability", "profile"),
    [
        (BROWSER_DOWNLOAD, False),
        (BROWSER_DOWNLOAD_AS_YOU, True),
        (BROWSER_UPLOAD, False),
        (BROWSER_UPLOAD_AS_YOU, True),
    ],
)


def _tool(capability: str, profile: bool, folder: Path, **options: Any) -> Any:
    browser = (FakeAccountBrowser if profile else FakeBrowser)()
    if capability in (BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU):
        return download(browser, folder, profile=profile, **options)
    return upload(browser, folder, profile=profile, **options)


@FOUR
async def test_a_folder_of_the_scope_with_declared_sites_would_start_and_is_named_whole(
    tmp_path: Path, capability: str, profile: bool
) -> None:
    folder = root(tmp_path)

    looked = await _tool(capability, profile, folder).prospect_place(
        "ELA/prova", ("httpbin.org", "testpages.eviltester.com")
    )

    assert looked.refusal is None
    assert looked.target is not None and looked.target.resolved == str(folder / "ELA" / "prova")


@FOUR
@pytest.mark.parametrize(
    ("place", "sites", "code"),
    [
        ("ELA/prova", ("altro.example",), SITE_NOT_DECLARED),
        ("ELA/nessuna", ("httpbin.org",), PATH_MISSING),
        ("ELA/prova/un-file.txt", ("httpbin.org",), NOT_A_FOLDER),
        ("ELA/prova", ("httpbin.org",), ELA_S_OWN),
    ],
    ids=["a site not declared", "no folder", "a file", "a place of ELA's"],
)
async def test_a_place_no_call_could_start_in_is_refused_with_its_code(
    tmp_path: Path, capability: str, profile: bool, place: str, sites: tuple[str, ...], code: str
) -> None:
    """For the two uploads too — a reader — the protected places and the folder: not the look at
    a site a gesture inherits, which would say «it would start» of any folder."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "un-file.txt").write_bytes(BYTES)
    protected = {"the database": folder / "ELA"} if code == ELA_S_OWN else {}

    looked = await _tool(capability, profile, folder, protected=protected).prospect_place(
        place, sites
    )

    assert looked.refusal is not None and looked.refusal.code == code


@pytest.mark.parametrize("capability", ["fs.write", "browser.act"])
async def test_a_tool_that_names_nothing_by_value_refuses_a_value(
    tmp_path: Path, capability: str
) -> None:
    from ela.testing.fakes import FakeTaskPages
    from ela.tools.browser import BrowserActTool, Browsing
    from ela.tools.fs import FsWriteTool

    folder = root(tmp_path)
    tool: Any = (
        FsWriteTool(folder, CLOCK, FakeIdGenerator(), protected={})
        if capability == "fs.write"
        else BrowserActTool(
            Browsing(sites=("httpbin.org",)),
            FakeBrowser(),
            CLOCK,
            FakeIdGenerator(),
            pages=FakeTaskPages(),
        )  # fmt: skip
    )
    place = "ELA/prova" if capability == "fs.write" else "httpbin.org"

    named = await tool.prospect_place(place, ("httpbin.org",))
    plain = await tool.prospect_place(place)

    assert named.refusal is not None and named.refusal.code == ARGUMENTS_INVALID
    assert plain.refusal is None


# ----------------------------------------------------------------------------------------
# The «partirebbe» of a birth: the login (decision 10)
# ----------------------------------------------------------------------------------------


async def test_a_login_s_birth_shows_each_entry_by_its_name_and_its_masked_username(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO, ANNA])
    tool = await login(FakeAccountBrowser(), vault, tmp_path)

    looked = await tool.prospect_place("posta.example", (MARIO.id, ANNA.id))

    assert looked.refusal is None
    assert looked.entries == (
        ShownEntry("La posta", "m…@example.com"),
        ShownEntry("La posta di Anna", "a…@example.com"),
    )
    assert MARIO.id not in repr(looked) and ANNA.id not in repr(looked), "an id came back"


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("locked", "vault.locked"),
        ("no entry for the site", "vault.no_entry"),
        ("an entry of another site", "vault.entry_not_for_site"),
        ("no values", ARGUMENTS_INVALID),
    ],
)
async def test_a_login_s_birth_is_refused_with_the_code_of_today(
    tmp_path: Path, kind: str, code: str
) -> None:
    """Decision 10: the vault opened by you, and every id found for the site — or no policy is
    born, with the codes that are already there, and a message that names no entry."""
    other = FakeVaultEntry("other-id", "Altro", ("https://altro.example/",), "u", "w", "u")
    vault = FakeVault([MARIO, other])
    values: tuple[str, ...] = (MARIO.id,)
    if kind == "locked":
        vault.state = VAULT_LOCKED  # opened by nobody: the door below holds no key
    elif kind == "no entry for the site":
        values = ("an-id-the-vault-does-not-hold",)
    elif kind == "an entry of another site":
        values = ("other-id",)
    elif kind == "no values":
        values = ()
    tool = await login(FakeAccountBrowser(), vault, tmp_path, opened=kind != "locked")

    looked = await tool.prospect_place("posta.example", values)

    assert looked.refusal is not None and looked.refusal.code == code
    for value in values:
        assert value not in looked.refusal.message


async def test_a_login_s_birth_with_the_profile_held_is_refused_before_the_vault(
    tmp_path: Path,
) -> None:
    from ela.ports import PROFILE_WINDOW

    browser = FakeAccountBrowser(holder=PROFILE_WINDOW)
    vault = FakeVault([MARIO])
    tool = await login(browser, vault, tmp_path)

    looked = await tool.prospect_place("posta.example", (MARIO.id,))

    assert looked.refusal is not None and looked.refusal.code == "browser.profile_busy"
    assert vault.calls == [], "the vault was asked with the profile held"


async def test_a_covered_login_reads_the_entry_the_plan_names(tmp_path: Path) -> None:
    """Decision 4 (iii): under a policy the call carries ``entry``, and the tool reads that one —
    no question named it, and nothing is remembered between two moments."""
    from tests.tools.test_account_tools import page

    vault = FakeVault([MARIO, ANNA])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)

    covered = await tool.prospect_covered({**LOGIN, "entry": ANNA.id})
    result = await tool.execute(
        deciding(BROWSER_LOGIN), {**LOGIN, "entry": ANNA.id}, FakeStop(), {}
    )

    assert covered.refusal is None
    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert [call for call in vault.calls if call.startswith("take")] == [f"take:{ANNA.id}"]


# ----------------------------------------------------------------------------------------
# The races: what changes between the look at the path and the read
# ----------------------------------------------------------------------------------------


class _Os:
    """``os`` as a module sees it, with ``lstat`` raising: a file gone between two looks."""

    def __init__(self, error: OSError) -> None:
        self._error = error

    def lstat(self, *_: object, **__: object) -> os.stat_result:
        raise self._error

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


async def test_a_file_gone_before_its_size_is_asked_is_an_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    monkeypatch.setattr(browser_files, "os", _Os(FileNotFoundError(2, "gone")))

    covered = await upload(FakeBrowser(), folder).prospect_covered(UPLOAD)

    assert covered.refusal is not None and covered.refusal.code == "io.error"


def test_a_file_gone_before_its_names_are_counted_is_an_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ela.tools import fs

    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "letto.txt").write_bytes(BYTES)
    monkeypatch.setattr(fs, "os", _Os(FileNotFoundError(2, "gone")))

    refused, _ = fs.looked_for_a_read(folder, "ELA/prova/letto.txt", protected={})

    assert refused is not None and refused.code == "io.error"


async def test_a_second_name_given_after_the_look_is_refused_by_the_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The descriptor that reads has the last word (answer 36, decision 51): a name added after
    the path was looked at is refused there — for an upload, and for ``fs.read``."""
    from ela.tools import fs

    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)

    def two_names(*_: object, **__: object) -> bytes:
        raise MoreThanOneName(HARD_LINK)

    monkeypatch.setattr(browser_files, "read_bytes", two_names)
    monkeypatch.setattr(fs, "read_bytes", two_names)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    reader = FsReadTool(folder, CLOCK, FakeIdGenerator(), protected={"a place": tmp_path / "x"})

    uploaded = await upload(browser, folder).execute(
        deciding(BROWSER_UPLOAD), UPLOAD, FakeStop(), {}
    )
    read = await reader.execute(
        deciding("fs.read", approval=True), {"path": "ELA/prova/da-caricare.txt"}, FakeStop()
    )

    assert uploaded.error is not None and uploaded.error.code == HARD_LINK
    assert read.error is not None and read.error.code == HARD_LINK
    assert browser.given == []
    assert dict(reader.protected) == {"a place": tmp_path / "x"}


@FOUR
async def test_a_place_with_no_browser_to_start_is_refused(
    tmp_path: Path, capability: str, profile: bool
) -> None:
    folder = root(tmp_path)
    browser = (FakeAccountBrowser if profile else FakeBrowser)(installed=False)
    tool = (
        download(browser, folder, profile=profile)
        if capability in (BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU)
        else upload(browser, folder, profile=profile)
    )

    looked = await tool.prospect_place("ELA/prova", ("httpbin.org",))

    assert looked.refusal is not None and looked.refusal.code == NOT_INSTALLED
