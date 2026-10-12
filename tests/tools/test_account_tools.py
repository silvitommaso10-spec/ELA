"""The three tools of the browser with the user's accounts (M13.9, ADR 0063).

``browser.read_as_you`` and ``browser.act_as_you`` are the empty browser's two on another
browser: what is under test here is **what changes** — the sentence, the boundary of a read, and
the refusals only a profile has, before the question and after the yes. ``browser.login`` is
under test whole: every refusal born before the question, with its code and without a word of an
entry; the question, which names the entry and never a value; and, after the yes, a page looked
at before anything is asked of the vault, one reading of the entry, and two secrets that go to the
browser and nowhere else.
"""

from __future__ import annotations

import asyncio
import stat
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from ela.domain import (
    DecisionId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.permissions import BROWSER_ACT_AS_YOU, BROWSER_LOGIN, BROWSER_READ_AS_YOU
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    VAULT_LOCKED,
    VAULT_UNAUTHENTICATED,
    BrowserFailed,
    BrowserStopped,
    BrowserUnsupported,
    Field,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
    Secret,
    ToolStopped,
    VaultTimeout,
)
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeVault,
    FakeVaultEntry,
)
from ela.tools.account import (
    ACCOUNT_CODES,
    ACTS_AS_YOU,
    BROWSER_SECOND_FACTOR,
    ENTRY_FORGOTTEN,
    LOGIN_FORM_GET,
    LOGS_IN,
    NOT_A_PASSWORD_FIELD,
    PROFILE_BUSY,
    PROFILE_UNDECLARED,
    PROFILE_UNSAFE,
    READS_AS_YOU,
    AccountActTool,
    AccountActVerifier,
    AccountReadTool,
    AccountReadVerifier,
    LoginTool,
    LoginVerifier,
)
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.browser import (
    ACTS,
    ELEMENT_AMBIGUOUS,
    ELEMENT_MISSING,
    FAILED,
    FIRST_GESTURE,
    LEFT_SITE,
    NOT_INSTALLED,
    OPENS,
    SECRET_FIELD,
    STOPPED,
    UNSUPPORTED_SYSTEM,
    BrowserReadTool,
    Browsing,
)
from ela.tools.vault import KEY_REFUSED, VAULT_CODES, VaultDoor
from ela.tools.verifiers import (
    BROWSER_EXPECT_MISSING,
    BROWSER_EXPECT_VISIBLE,
    BROWSER_PAGE_GONE,
    BROWSER_TEXT_MATCHES,
)
from ela.tools.verify import VERIFICATION_ARGUMENTS_INVALID

CLOCK = FakeClock()
SITES = Browsing(sites=("posta.example", "altro.example"))
READ = {"site": "posta.example", "path": "/inbox", "purpose": "la prova"}
ACT = {
    "site": "posta.example",
    "path": "/scrivi",
    "fill": [["#testo", "ciao"]],
    "click": "#manda",
    "expect_text": "Mandato",
    "purpose": "la prova",
}
LOGIN = {
    "site": "posta.example",
    "path": "/login",
    "username_field": "#user",
    "password_field": "#word",
    "click": "#go",
    "expect_text": "Benvenuto",
    "purpose": "la prova",
}
KEY = "the-key-of-the-fake-vault"
WORD_FIELD = "_".join(("password", "field"))
"""The name of the argument that names the field — composed, so that a line giving it a selector
does not read as a line giving something a password."""
TYPED = "-".join(("SENTINEL", "of", "the", "word", "typed"))
USERNAME = "mario.rossi@example.com"
MARIO = FakeVaultEntry(
    "11111111-2222-4333-8444-555555555555",
    "La posta",
    ("https://posta.example/login",),
    USERNAME,
    TYPED,
    "m…@example.com",
)
ANNA = FakeVaultEntry(
    "99999999-2222-4333-8444-555555555555",
    "La posta di Anna",
    ("https://posta.example/",),
    "anna@example.com",
    "another word",
    "a…@example.com",
)
A_LOGIN_FORM = {
    "#user": Field("text", "username", "post"),
    "#word": Field("password", "current-password", "post"),
    "#go": Field("submit", "", "post"),
}


def decision(capability: str) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
    )


def program(folder: Path) -> Path:
    made = folder / "bw"
    made.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    made.chmod(made.stat().st_mode | stat.S_IXUSR)
    return made


def page(**changed: Any) -> FakePage:
    return FakePage(fields=dict(A_LOGIN_FORM), **changed)


async def door(vault: FakeVault | None, folder: Path | None, *, opened: bool = True) -> VaultDoor:
    made = await VaultDoor.fixed(
        vault, None if folder is None else str(program(folder)), clock=FakeClock()
    )
    if opened and vault is not None:
        assert await made.open(Secret(KEY)) is None
        vault.calls.clear()
    return made


async def login(
    browser: FakeAccountBrowser, vault: FakeVault | None, folder: Path | None, **options: Any
) -> LoginTool:
    return LoginTool(SITES, browser, await door(vault, folder, **options), CLOCK, FakeIdGenerator())


def tools(browser: FakeAccountBrowser, vault_door: VaultDoor) -> dict[str, Any]:
    return {
        BROWSER_READ_AS_YOU: AccountReadTool(SITES, browser, CLOCK, FakeIdGenerator()),
        BROWSER_ACT_AS_YOU: AccountActTool(SITES, browser, CLOCK, FakeIdGenerator()),
        BROWSER_LOGIN: LoginTool(SITES, browser, vault_door, CLOCK, FakeIdGenerator()),
    }


CALLS = {BROWSER_READ_AS_YOU: READ, BROWSER_ACT_AS_YOU: ACT, BROWSER_LOGIN: LOGIN}
EVERY = pytest.mark.parametrize("capability", sorted(CALLS))


# ----------------------------------------------------------------------------------------
# What they declare, and what the question says
# ----------------------------------------------------------------------------------------


def test_what_the_three_tools_declare() -> None:
    assert AccountReadTool.idempotent is True
    assert AccountActTool.idempotent is False and LoginTool.idempotent is False
    for tool in (AccountReadTool, AccountActTool, LoginTool):
        assert tool.relocatable is False, "the browser does not travel, and neither does a login"
        assert tool.error_codes >= ACCOUNT_CODES
    assert AccountReadTool.audit_numbers == {"status", "shown", "total"}
    assert AccountActTool.audit_numbers == LoginTool.audit_numbers == {"status", "gestures"}
    assert SECRET_FIELD not in AccountReadTool.error_codes
    assert SECRET_FIELD in AccountActTool.error_codes and SECRET_FIELD in LoginTool.error_codes
    assert VAULT_CODES - {KEY_REFUSED} <= LoginTool.error_codes
    assert KEY_REFUSED not in LoginTool.error_codes, "a key is handed by a route, never by a step"
    assert not VAULT_CODES & (AccountReadTool.error_codes | AccountActTool.error_codes)
    assert LoginTool.stop_point.here == FIRST_GESTURE


def test_the_sentences_say_as_you_where_it_is_true_and_a_visitor_where_it_is() -> None:
    """Criterion 3: «the site sees a visitor» stays true only where it is — the empty browser."""
    for sentence in (READS_AS_YOU, ACTS_AS_YOU):
        assert "where you are signed in" in sentence and "as you" in sentence
        assert "visitor" not in sentence and "empty" not in sentence
    assert "as you" in LOGS_IN and "ELA keeps the password nowhere" in LOGS_IN
    assert "nowhere else" not in LOGS_IN, "the form is sent again through ELA's process"
    for sentence in (OPENS, ACTS):
        assert "visitor" in sentence and "as you" not in sentence
    assert AccountReadTool.does == READS_AS_YOU
    assert AccountActTool.does == ACTS_AS_YOU
    assert LoginTool.does == LOGS_IN


async def test_the_question_of_a_read_and_of_an_action_is_the_empty_browser_s_with_its_sentence(
    tmp_path: Path,
) -> None:
    browser = FakeAccountBrowser()
    made = tools(browser, await door(None, None))

    read = (await made[BROWSER_READ_AS_YOU].prospect(READ)).visit
    act = (await made[BROWSER_ACT_AS_YOU].prospect(ACT)).visit

    assert read is not None and act is not None
    assert (read.site, read.address, read.does) == (
        "posta.example",
        "https://posta.example/inbox",
        READS_AS_YOU,
    )
    assert act.does == ACTS_AS_YOU and act.expect == "Mandato"
    assert act.gestures == ("fills #testo with “ciao”", "clicks #manda")
    assert browser.opened == [], "asking opens nothing"


# ----------------------------------------------------------------------------------------
# Before the question: what only a profile refuses
# ----------------------------------------------------------------------------------------


@EVERY
@pytest.mark.parametrize(
    ("failure", "code", "said"),
    [
        (
            ProfileUndeclared("ELA_BROWSER_PROFILE_DIR is not set: write it"),
            PROFILE_UNDECLARED,
            "ELA_BROWSER_PROFILE_DIR",
        ),
        (ProfileUnsafe("the folder is open to others than you"), PROFILE_UNSAFE, "open to others"),
        (BrowserUnsupported("Linux"), UNSUPPORTED_SYSTEM, "runs on a Mac, and this is Linux"),
        (BrowserStopped("ELA is stopping"), STOPPED, "no browser was started"),
        (BrowserFailed("OSError"), FAILED, "could not be read"),
    ],
    ids=["undeclared", "unsafe", "unsupported", "stopping", "failed"],
)
async def test_a_profile_that_cannot_be_used_is_refused_before_the_question(
    tmp_path: Path, capability: str, failure: Exception, code: str, said: str
) -> None:
    """«It would start» (criterion 10): with its code, the adapter's own sentence, and no browser
    opened — and for a login, before the vault is asked anything."""
    browser = FakeAccountBrowser()
    browser.raising["occupied"] = failure
    vault = FakeVault([MARIO])
    tool = tools(browser, await door(vault, tmp_path))[capability]

    prospect = await tool.prospect(CALLS[capability])

    assert prospect.refusal is not None and prospect.visit is None
    assert prospect.refusal.code == code and said in prospect.refusal.message
    assert browser.opened == [] and vault.calls == []


@EVERY
async def test_a_browser_that_is_not_installed_is_said_with_the_command_that_installs_it(
    tmp_path: Path, capability: str
) -> None:
    browser = FakeAccountBrowser(installed=False)
    tool = tools(browser, await door(FakeVault([MARIO]), tmp_path))[capability]

    refusal = (await tool.prospect(CALLS[capability])).refusal

    assert refusal is not None and refusal.code == NOT_INSTALLED
    assert "`uv run playwright install chromium`" in refusal.message
    assert "--only-shell" not in refusal.message, "the shell is the empty browser's"


@EVERY
@pytest.mark.parametrize(
    ("holder", "said"),
    [
        (PROFILE_STEP, "another step of ELA's"),
        (PROFILE_WINDOW, "its window is open: quit that browser (Cmd-Q"),
        (PROFILE_PROCESS, "another process holds it"),
    ],
)
async def test_a_folder_that_is_held_is_busy_before_the_question_and_can_be_asked_again(
    tmp_path: Path, capability: str, holder: str, said: str
) -> None:
    """Criterion 14: for the user's own window too. Retryable — what holds it ends. **And what
    ends the window is a quit**: on the Mac a browser whose window is closed goes on running,
    and holding the folder — a sentence that said «close it» would leave the user with a profile
    that stays busy and nothing on the screen to close."""
    browser = FakeAccountBrowser(holder=holder)
    vault = FakeVault([MARIO])
    tool = tools(browser, await door(vault, tmp_path))[capability]

    refusal = (await tool.prospect(CALLS[capability])).refusal

    assert refusal is not None and refusal.code == PROFILE_BUSY
    assert said in refusal.message and refusal.retryable is True
    assert browser.opened == [] and vault.calls == []


@EVERY
async def test_a_browser_that_does_not_answer_in_time_is_a_refusal_and_not_a_wait(
    tmp_path: Path, capability: str
) -> None:
    browser = FakeAccountBrowser()

    async def never() -> str | None:
        await asyncio.Event().wait()
        return None

    browser.occupied = never  # type: ignore[method-assign]
    quick = Browsing(sites=SITES.sites, timeout_seconds=0)
    made = {
        BROWSER_READ_AS_YOU: AccountReadTool(quick, browser, CLOCK, FakeIdGenerator()),
        BROWSER_ACT_AS_YOU: AccountActTool(quick, browser, CLOCK, FakeIdGenerator()),
        BROWSER_LOGIN: LoginTool(quick, browser, await door(None, None), CLOCK, FakeIdGenerator()),
    }

    refusal = (await made[capability].prospect(CALLS[capability])).refusal

    assert refusal is not None and refusal.code == FAILED
    assert "within 0 s" in refusal.message


# ----------------------------------------------------------------------------------------
# After the yes: the folder that became held, or unfit
# ----------------------------------------------------------------------------------------


@EVERY
@pytest.mark.parametrize(
    ("failure", "code", "retryable"),
    [
        (ProfileBusy(PROFILE_WINDOW), PROFILE_BUSY, True),
        (ProfileUnsafe("the folder is open to others than you"), PROFILE_UNSAFE, False),
        (ProfileUndeclared("ELA_BROWSER_PROFILE_DIR is not set"), PROFILE_UNDECLARED, False),
        (BrowserUnsupported("Linux"), UNSUPPORTED_SYSTEM, False),
    ],
    ids=["busy", "unsafe", "undeclared", "unsupported"],
)
async def test_what_the_opening_itself_refuses_is_named_and_nothing_was_started(
    tmp_path: Path, capability: str, failure: Exception, code: str, retryable: bool
) -> None:
    """Between the question and the yes the window was opened, or the folder was widened: the
    yes is spent, and no gesture was made (ADR 0052 §7)."""
    browser = FakeAccountBrowser(page())
    vault = FakeVault([MARIO])
    tool = tools(browser, await door(vault, tmp_path))[capability]
    await tool.prospect(CALLS[capability])
    browser.raising["open"] = failure

    result = await tool.execute(decision(capability), CALLS[capability], FakeStop())

    assert result.status is ExecutionStatus.FAILED and result.error is not None
    assert result.error.code == code and result.error.retryable is retryable
    assert result.output == ({} if capability == BROWSER_READ_AS_YOU else {"gestures": 0})
    assert browser.secrets == [] and browser.fills == [] and browser.clicks == []
    assert not [call for call in vault.calls if call.startswith("take")]


# ----------------------------------------------------------------------------------------
# A read: the site it names, and no other
# ----------------------------------------------------------------------------------------


async def test_a_read_with_the_profile_does_not_leave_the_site_it_names() -> None:
    """Criterion 8, and the contrast: the empty browser follows a redirect between two declared
    sites; with the profile that would carry the credentials of the second into a read that
    named the first."""
    accounts, empty = FakeAccountBrowser(), FakeBrowser()

    await AccountReadTool(SITES, accounts, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_READ_AS_YOU), READ, FakeStop()
    )
    await BrowserReadTool(SITES, empty, CLOCK, FakeIdGenerator()).execute(
        decision("browser.read"), READ, FakeStop()
    )

    (with_the_profile,), (without,) = accounts.allowed, empty.allowed
    assert with_the_profile("https://posta.example/an/other/page")
    assert not with_the_profile("https://altro.example/"), "declared, and still another site"
    assert not with_the_profile("http://posta.example/"), "another origin"
    assert without("https://altro.example/")


async def test_a_redirect_to_another_declared_site_is_left_site_and_reads_nothing() -> None:
    browser = FakeAccountBrowser(FakePage(left="https://altro.example/accedi?next=x"))

    result = await AccountReadTool(SITES, browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_READ_AS_YOU), READ, FakeStop()
    )

    assert result.error is not None and result.error.code == LEFT_SITE
    assert "https://altro.example," in result.error.message
    assert "not the site the question named" in result.error.message
    assert "accedi" not in result.error.message, "an origin, never a path"
    assert browser.closed == ["page-1"]


async def test_a_read_and_an_action_go_through_the_browser_with_the_profile() -> None:
    browser = FakeAccountBrowser(FakePage(texts={None: "la posta di Mario"}))
    made = tools(browser, await door(None, None))

    read = await made[BROWSER_READ_AS_YOU].execute(decision(BROWSER_READ_AS_YOU), READ, FakeStop())
    await browser.close(str(read.output["page"]))
    acted = await made[BROWSER_ACT_AS_YOU].execute(decision(BROWSER_ACT_AS_YOU), ACT, FakeStop())

    assert read.output["text"] == "la posta di Mario"
    assert acted.output == {"status": 200, "gestures": 2, "page": "page-2"}
    assert browser.fills == [("#testo", "ciao")] and browser.clicks == ["#manda"]
    assert browser.opened == ["https://posta.example/inbox", "https://posta.example/scrivi"]


async def test_an_action_with_the_profile_refuses_a_secret_field_like_the_empty_browser_s() -> None:
    """ADR 0052 §8 is revised for ``browser.login`` alone: every other tool still refuses."""
    browser = FakeAccountBrowser(
        FakePage(fields={"#testo": Field("password", "current-password", "post")})
    )

    result = await AccountActTool(SITES, browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT_AS_YOU), ACT, FakeStop()
    )

    assert result.error is not None and result.error.code == SECRET_FIELD
    assert browser.fills == [] and browser.secrets == []


# ----------------------------------------------------------------------------------------
# The login, before the question
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changed", "said"),
    [
        ({"username_field": ""}, "username_field"),
        ({WORD_FIELD: "xpath=//input"}, WORD_FIELD),
        ({"click": ">> x"}, "click"),
        ({"expect_text": ""}, "expect_text"),
        ({"entry": ""}, "entry"),
        ({"entry": "x" * 65}, "entry"),
        ({"entry": 7}, "entry"),
        ({"site": "https://posta.example"}, "site"),
    ],
)
async def test_arguments_that_are_not_a_login_are_refused_before_anything_is_looked_at(
    tmp_path: Path, changed: dict[str, object], said: str
) -> None:
    browser, vault = FakeAccountBrowser(), FakeVault([MARIO])
    browser.raising["occupied"] = AssertionError("the profile was looked at")
    tool = await login(browser, vault, tmp_path)

    refusal = (await tool.prospect({**LOGIN, **changed})).refusal

    assert refusal is not None and refusal.code == ARGUMENTS_INVALID
    assert said in refusal.message and vault.calls == []


async def vault_that(
    kind: str, folder: Path
) -> tuple[FakeVault | None, Path | None, dict[str, Any]]:
    """The vault of each refusal before the question, built — and the arguments of the call."""
    if kind == "vault.undeclared":
        return None, None, {}
    vault = FakeVault([MARIO])
    arguments: dict[str, Any] = {}
    if kind == "vault.unauthenticated":
        vault.state = VAULT_UNAUTHENTICATED
    elif kind == "vault.locked":
        vault.state = VAULT_LOCKED
    elif kind == "vault.timeout":
        vault.raising["find"] = VaultTimeout("bw list items did not answer within 15 s")
    elif kind == "vault.no_entry":
        vault.entries = [FakeVaultEntry("x", "Altro", ("https://altro.example/",), "u", "w", "u")]
    elif kind == "vault.entry_ambiguous":
        vault.entries = [MARIO, ANNA]
    elif kind == "vault.entry_not_for_site":
        other = FakeVaultEntry("other-id", "Altro", ("https://altro.example/",), "u", "w", "u")
        vault.entries = [MARIO, other]
        arguments = {"entry": "other-id"}
    elif kind == "vault.no_password":
        vault.entries = [FakeVaultEntry(MARIO.id, MARIO.name, MARIO.addresses, USERNAME, "", "m…")]
    return vault, folder, arguments


@pytest.mark.parametrize(
    "code",
    [
        "vault.undeclared",
        "vault.unauthenticated",
        "vault.locked",
        "vault.timeout",
        "vault.no_entry",
        "vault.entry_ambiguous",
        "vault.entry_not_for_site",
        "vault.no_password",
    ],
)
async def test_every_refusal_of_the_vault_is_born_before_the_question_and_names_no_entry(
    tmp_path: Path, code: str
) -> None:
    """Criterion 10, and decision 28: with its code, without an approval — the tool answers a
    refusal and no visit —, and neither the name nor the id of an entry is in what it says."""
    vault, folder, arguments = await vault_that(code, tmp_path)
    browser = FakeAccountBrowser(page())
    was_open = vault is not None and vault.state == "unlocked"
    tool = await login(browser, vault, folder, opened=was_open)
    if vault is not None and code in {"vault.locked", "vault.unauthenticated"}:
        vault.calls.clear()

    prospect = await tool.prospect({**LOGIN, **arguments})

    assert prospect.visit is None and prospect.refusal is not None
    assert prospect.refusal.code == code
    for entry in (MARIO, ANNA):
        assert entry.name not in prospect.refusal.message
        assert entry.id not in prospect.refusal.message
        assert entry.username not in prospect.refusal.message
    assert browser.opened == [], "no page is opened to ask"
    if vault is not None:
        assert not [call for call in vault.calls if call.startswith("take")], (
            "without the yes no password leaves the vault's adapter"
        )
    assert prospect.refusal.retryable is (code in {"vault.locked", "vault.timeout"})


async def test_the_program_of_the_vault_is_looked_at_before_the_vault_is_asked(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    tool = await login(FakeAccountBrowser(page()), vault, tmp_path)
    program(tmp_path).write_bytes(b"\xcf\xfa\xed\xfe an update ELA did not see start")

    refusal = (await tool.prospect(LOGIN)).refusal

    assert refusal is not None and refusal.code == "vault.program_changed"
    assert vault.calls == []


async def test_the_profile_is_refused_before_the_vault_is_asked(tmp_path: Path) -> None:
    """The order of «it would start»: the arguments, the profile, the vault. A folder nobody
    declared is said before a vault that is locked — and the vault is not launched to learn it."""
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    browser = FakeAccountBrowser()
    browser.raising["occupied"] = ProfileUndeclared("ELA_BROWSER_PROFILE_DIR is not set")
    tool = await login(browser, vault, tmp_path, opened=False)

    refusal = (await tool.prospect(LOGIN)).refusal

    assert refusal is not None and refusal.code == PROFILE_UNDECLARED
    assert vault.calls == []


# ----------------------------------------------------------------------------------------
# The login: the question
# ----------------------------------------------------------------------------------------


async def test_the_question_of_a_login_names_the_entry_and_never_a_value(tmp_path: Path) -> None:
    """Decisions 15d and 31: the site, the address, **the entry by its name and its username
    masked**, the fields, the click, the text awaited, the time and the tool's sentence — never
    the password, never the whole username, never the id."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)

    prospect = await tool.prospect(LOGIN)

    visit = prospect.visit
    assert prospect.refusal is None and visit is not None
    assert (visit.site, visit.address) == ("posta.example", "https://posta.example/login")
    assert visit.does == LOGS_IN and visit.expect == "Benvenuto"
    assert visit.timeout_seconds == 30
    assert (visit.entry, visit.username) == ("La posta", "m…@example.com")
    assert visit.gestures == (
        "types the username of that entry into #user",
        "types its password into #word",
        "clicks #go",
    ), "which entry is a fact of its own, and the gestures name the fields"
    shown = repr(prospect)
    assert TYPED not in shown and USERNAME not in shown and MARIO.id not in shown
    assert browser.opened == []
    assert [call.split(":")[0] for call in vault.calls] == ["find"], (
        "before the yes: the listing for the site, and nothing that takes a value"
    )


async def test_an_entry_the_plan_names_is_the_one_the_question_names(tmp_path: Path) -> None:
    vault = FakeVault([MARIO, ANNA])
    tool = await login(FakeAccountBrowser(page()), vault, tmp_path)

    visit = (await tool.prospect({**LOGIN, "entry": ANNA.id})).visit

    assert visit is not None
    assert (visit.entry, visit.username) == ("La posta di Anna", "a…@example.com")


# ----------------------------------------------------------------------------------------
# The login: after the yes
# ----------------------------------------------------------------------------------------


async def asked(tool: LoginTool, arguments: dict[str, object] = LOGIN) -> None:
    prospect = await tool.prospect(arguments)
    assert prospect.refusal is None, prospect.refusal


async def test_after_the_yes_the_entry_is_read_once_and_typed_through_the_browser_alone(
    tmp_path: Path,
) -> None:
    """Criterion 2 and decision 64: one reading of the entry after the yes — no second listing —,
    two secrets handed to the browser, one click; and the value is in nothing the tool returns."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    vault.calls.clear()
    stop = FakeStop()

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, stop)

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output == {
        "status": 200,
        "gestures": 3,
        "page": "page-1",
        "ended_at": "posta.example/login",
        "ended_status": 200,
        "password_field_still_there": True,
    }
    assert browser.secrets == [("#user", USERNAME), ("#word", TYPED)]
    assert browser.clicks == ["#go"]
    assert browser.fills == [], "never through the fill that takes a plain value"
    assert vault.calls == [f"take:{MARIO.id}"], "one reading, and nothing else is asked"
    assert stop.listened[-1] == FIRST_GESTURE
    assert browser.kept == ["page-1"], "the page is handed to the verifier"
    said = result.model_dump_json()
    assert TYPED not in said and USERNAME not in said and MARIO.id not in said
    assert browser.allowed[0]("https://posta.example/after")
    assert not browser.allowed[0]("https://altro.example/")


LOOKED_AT_FIRST = [
    (
        {"fields": {**A_LOGIN_FORM, "#word": Field("text", "current-password", "post")}},
        NOT_A_PASSWORD_FIELD,
    ),
    (
        {"fields": {**A_LOGIN_FORM, "#word": Field("password", "new-password", "post")}},
        SECRET_FIELD,
    ),
    (
        {"fields": {**A_LOGIN_FORM, "#word": Field("password", "one-time-code", "post")}},
        SECRET_FIELD,
    ),
    ({"fields": {**A_LOGIN_FORM, "#word": Field("password", "cc-number", "post")}}, SECRET_FIELD),
    (
        {"fields": {**A_LOGIN_FORM, "#word": Field("password", "cc-exp-month", "post")}},
        SECRET_FIELD,
    ),
    ({"fields": {**A_LOGIN_FORM, "#user": Field("password", "", "post")}}, SECRET_FIELD),
    ({"fields": {**A_LOGIN_FORM, "#user": Field("text", "one-time-code", "post")}}, SECRET_FIELD),
    (
        {"fields": {**A_LOGIN_FORM, "#word": Field("password", "current-password", "get")}},
        LOGIN_FORM_GET,
    ),
    (
        {"fields": {**A_LOGIN_FORM, "#word": Field("password", "current-password", "")}},
        LOGIN_FORM_GET,
    ),
    ({"fields": {**A_LOGIN_FORM, "#go": Field("submit", "", "get")}}, LOGIN_FORM_GET),
    ({"counts": {"#user": 0}}, ELEMENT_MISSING),
    ({"counts": {"#word": 2}}, ELEMENT_AMBIGUOUS),
    ({"counts": {"#go": 0}}, ELEMENT_MISSING),
    ({"address": "https://altro.example/login"}, LEFT_SITE),
]


@pytest.mark.parametrize(
    ("shows", "code"),
    LOOKED_AT_FIRST,
    ids=[
        "not-a-password-field",
        "a-new-password",
        "a-one-time-code",
        "a-card",
        "a-card-s-month",
        "the-username-is-a-password",
        "the-username-is-a-code",
        "the-form-sends-with-get",
        "the-field-is-in-no-form",
        "the-button-sends-with-get",
        "no-username-field",
        "two-password-fields",
        "no-button",
        "another-site",
    ],
)
async def test_the_page_is_looked_at_before_anything_is_asked_of_the_vault(
    tmp_path: Path, shows: dict[str, Any], code: str
) -> None:
    """Criterion 9. A password is not typed where the page would show it, nor into a form that
    would put it in an address; a field of a card or of a one-time code is filled by no tool.
    Whatever the page fails on, **the vault is not asked**: the yes is spent, nothing was typed."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(FakePage(**{"fields": dict(A_LOGIN_FORM), **shows}))
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    vault.calls.clear()

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.error is not None and result.error.code == code
    assert result.error.message.endswith("the yes was spent, and nothing was typed")
    assert result.output == {"gestures": 0}
    assert vault.calls == [], "no password was taken"
    assert browser.secrets == [] and browser.clicks == []
    assert browser.closed == ["page-1"]


@pytest.mark.parametrize(
    ("happens", "code", "retryable"),
    [
        ("locked", "vault.locked", True),
        ("changed", "vault.program_changed", False),
        ("moved", "vault.entry_not_for_site", False),
        ("timeout", "vault.timeout", True),
        ("gone", "vault.failed", False),
    ],
)
async def test_a_vault_that_closes_or_changes_between_the_question_and_the_yes_gives_nothing(
    tmp_path: Path, happens: str, code: str, retryable: bool
) -> None:
    """The comparison runs again on fresh data, on the very reading the password would come
    from: an entry that moved to another site is not typed, whatever the question said."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    if happens == "locked":
        vault.state = VAULT_LOCKED
    elif happens == "changed":
        program(tmp_path).write_bytes(b"\xcf\xfa\xed\xfe an update ELA did not see start")
    elif happens == "moved":
        vault.entries = [
            FakeVaultEntry(MARIO.id, MARIO.name, ("https://altro.example/",), USERNAME, TYPED, "m…")
        ]
    elif happens == "timeout":
        vault.raising["take"] = VaultTimeout("bw get item did not answer within 15 s")
    else:
        vault.entries = []

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.error is not None and result.error.code == code
    assert result.error.retryable is retryable
    assert result.error.message.endswith("the yes was spent, and nothing was typed")
    assert result.output == {"gestures": 0}
    assert browser.secrets == [] and browser.clicks == []
    assert TYPED not in result.model_dump_json()


async def test_the_entry_typed_is_the_one_the_question_named_and_not_the_one_there_now(
    tmp_path: Path,
) -> None:
    """A yes covers the entry the question named. Between the question and the yes the vault
    changed, and another entry is now the only one for the site: it is not typed."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    vault.entries = [ANNA]
    vault.calls.clear()

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert vault.calls == [f"take:{MARIO.id}"]
    assert result.error is not None and result.error.code == "vault.failed"
    assert browser.secrets == []


async def test_a_login_ela_no_longer_remembers_the_question_of_types_nothing(
    tmp_path: Path,
) -> None:
    """ELA was started again between the question and the yes: the tool that receives the yes
    never asked, and does not look the entry up again — what it would find is what the vault
    holds now, not what the question named. The plan that names its entry is not concerned."""
    vault = FakeVault([MARIO, ANNA])
    browser = FakeAccountBrowser(page())
    restarted = await login(browser, vault, tmp_path)

    result = await restarted.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.error is not None and result.error.code == ENTRY_FORGOTTEN
    assert "ask again" in result.error.message
    assert vault.calls == [] and browser.secrets == []

    named = await restarted.execute(
        decision(BROWSER_LOGIN), {**LOGIN, "entry": ANNA.id}, FakeStop()
    )

    assert named.status is ExecutionStatus.SUCCEEDED, named.error
    assert browser.secrets == [("#user", "anna@example.com"), ("#word", "another word")]


async def test_the_tool_remembers_a_bounded_number_of_questions(tmp_path: Path) -> None:
    """The oldest question goes first — and a question asked again is the newest again."""
    from ela.tools import account

    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)

    def call(number: int) -> dict[str, object]:
        return {**LOGIN, "purpose": f"la prova {number}"}

    for number in range(account.REMEMBERED):
        await asked(tool, call(number))
    await asked(tool, call(0))
    for number in range(account.REMEMBERED, account.REMEMBERED + 3):
        await asked(tool, call(number))

    assert len(tool._found) == account.REMEMBERED
    forgotten = await tool.execute(decision(BROWSER_LOGIN), call(1), FakeStop())
    assert forgotten.error is not None and forgotten.error.code == ENTRY_FORGOTTEN
    await browser.close("page-1")
    again = await tool.execute(decision(BROWSER_LOGIN), call(0), FakeStop())
    assert again.status is ExecutionStatus.SUCCEEDED, again.error


async def test_a_task_stopped_by_the_time_the_page_is_checked_takes_no_password(
    tmp_path: Path,
) -> None:
    """A task that is stopped when the page has been looked at is heard **before the vault is
    asked**: no password is taken for a step that will type nothing."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    vault.calls.clear()
    stop, field = FakeStop(), browser.field

    async def looked_at_while_the_user_says_stop(page_: str, selector: str) -> Any:
        found = await field(page_, selector)
        stop.event.set()
        return found

    browser.field = looked_at_while_the_user_says_stop  # type: ignore[method-assign]

    with pytest.raises(ToolStopped):
        await tool.execute(decision(BROWSER_LOGIN), LOGIN, stop)

    assert stop.listened.count(FIRST_GESTURE) == 1
    assert vault.calls == [] and browser.secrets == []
    assert browser.closed == ["page-1"]


async def test_a_stop_that_arrives_while_the_vault_is_asked_types_nothing(
    tmp_path: Path,
) -> None:
    """The reading of the entry takes seconds — the door, the program, ``bw get item`` —, and a
    «ferma» given meanwhile found nobody listening: the username was typed after it (re-read of
    2026-10-11, defect 4). **The point of the tool is the last instant before its first gesture,
    and that is after the vault has answered**: the task is heard there, as one stopped before
    its point — whatever the vault gave is dropped, nothing is typed, and the page is closed."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    stop, take = FakeStop(), vault.take

    async def take_while_the_user_says_stop(entry: str) -> Any:
        taken = await take(entry)
        stop.event.set()
        return taken

    vault.take = take_while_the_user_says_stop  # type: ignore[method-assign]

    with pytest.raises(ToolStopped) as stopped:
        await tool.execute(decision(BROWSER_LOGIN), LOGIN, stop)

    assert stop.listened.count(FIRST_GESTURE) == 1, "heard once, at its point"
    assert browser.secrets == [] and browser.clicks == []
    assert browser.closed == ["page-1"]
    assert TYPED not in repr(stopped.value) and USERNAME not in repr(stopped.value)


async def test_the_point_of_a_login_is_after_the_vault_has_answered(tmp_path: Path) -> None:
    """A task that goes on listens once, when the vault has answered and the field has been
    looked at again — the last instant before anything is typed."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    vault.calls.clear()
    seen: list[tuple[list[str], int]] = []

    class Listening(FakeStop):
        def listen(self, where: str) -> None:
            if where == FIRST_GESTURE:
                seen.append((list(vault.calls), len(browser.secrets)))
            super().listen(where)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, Listening())

    assert result.error is None
    ((asked_of_the_vault, typed),) = seen
    assert any(call.startswith("take") for call in asked_of_the_vault), "the vault has answered"
    assert typed == 0, "and nothing is typed yet"


async def test_two_questions_for_the_same_call_that_named_different_entries_type_neither(
    tmp_path: Path,
) -> None:
    """One tool serves every task, and what it remembers of a question is keyed by the call. The
    same plan asked twice, with the vault changed in between: the second question named another
    entry and took the place of the first — and a yes to the first typed the second's password
    (re-read of 2026-10-11, defect 3). A yes covers the entry its question named: when ELA cannot
    tell which that was, it types none, and the next question starts clean."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)  # the first question names Mario's entry
    vault.entries = [ANNA]
    second = await tool.prospect(LOGIN)  # the same call, asked again: it names Anna's
    vault.calls.clear()

    first_yes = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())
    second_yes = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())
    await asked(tool)
    after_asking_again = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert second.visit is not None and second.visit.entry == ANNA.name
    for refused in (first_yes, second_yes):
        assert refused.error is not None and refused.error.code == ENTRY_FORGOTTEN
    assert "different entries" in str(first_yes.error and first_yes.error.message)
    assert not any(call.startswith("take") for call in vault.calls[:-1]), "nothing was read"
    assert after_asking_again.status is ExecutionStatus.SUCCEEDED, after_asking_again.error
    assert [typed for _, typed in browser.secrets] == [ANNA.username, ANNA.password]


async def test_the_same_question_asked_again_with_the_same_entry_keeps_its_memory(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error


async def test_an_entry_with_no_name_is_still_named_in_the_question(tmp_path: Path) -> None:
    """ADR 0063 §9: every surface that offers a yes shows the entry and its owner, or does not
    answer. An entry the user never named reached the question with **neither** — the facts are
    written only for a visit that names an entry (defect 6). It is named for what it is."""
    nameless = FakeVaultEntry(MARIO.id, "", MARIO.addresses, USERNAME, TYPED, MARIO.shown)
    tool = await login(FakeAccountBrowser(page()), FakeVault([nameless]), tmp_path)

    visit = (await tool.prospect(LOGIN)).visit

    assert visit is not None
    assert visit.entry == "(an entry of your vault that has no name)"
    assert visit.username == MARIO.shown


async def test_a_field_that_changed_while_the_vault_was_asked_gets_no_password(
    tmp_path: Path,
) -> None:
    """The page was looked at, then the vault was awaited for seconds, then the fields were
    typed: a page that turns its password field into a text field meanwhile — or its form into
    one that sends with GET — would have shown the password, or put it in an address. The field
    is looked at again when the password is in hand, and before any of it is typed."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    take = vault.take

    async def take_while_the_page_changes(entry: str) -> Any:
        browser.page.fields["#word"] = Field("text", "current-password", "post")
        return await take(entry)

    vault.take = take_while_the_page_changes  # type: ignore[method-assign]

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.error is not None and result.error.code == NOT_A_PASSWORD_FIELD
    assert browser.secrets == [] and browser.clicks == []
    assert result.output["gestures"] == 0


async def test_a_task_stopped_after_the_first_gesture_types_no_password(tmp_path: Path) -> None:
    """No gesture follows a stop (M6.3c): the username was typed, and the password is not. The
    stop arrives **while the username is being typed**, past the point of the tool — one that is
    there when the vault has answered is heard at the point and types nothing at all: the test
    above."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    stop, fill = FakeStop(), browser.fill_secret

    async def typed_while_the_user_says_stop(page_: str, selector: str, value: Secret) -> None:
        await fill(page_, selector, value)
        stop.event.set()

    browser.fill_secret = typed_while_the_user_says_stop  # type: ignore[method-assign]

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, stop)

    assert result.error is not None and result.error.code == STOPPED
    assert result.output == {"status": 200, "gestures": 1}
    assert browser.secrets == [("#user", USERNAME)] and browser.clicks == []


async def test_a_click_that_leaves_the_site_after_a_login_is_said(tmp_path: Path) -> None:
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page(left_after_click="https://altro.example/sso"))
    tool = await login(browser, vault, tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.error is not None and result.error.code == LEFT_SITE
    assert result.output == {"status": 200, "gestures": 3}
    assert "3 gestures were made" in result.error.message


async def test_a_browser_that_fails_while_it_types_names_the_failure_and_not_the_value(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    browser.raising["fill_secret"] = BrowserFailed("Error")
    tool = await login(browser, vault, tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.error is not None and result.error.code == FAILED
    assert TYPED not in result.model_dump_json() and USERNAME not in result.model_dump_json()
    assert browser.closed == ["page-1"]


async def test_a_read_with_a_selector_that_is_not_one_is_refused_like_the_empty_browser_s() -> None:
    tool = AccountReadTool(SITES, FakeAccountBrowser(), CLOCK, FakeIdGenerator())

    refusal = (await tool.prospect({**READ, "selector": "xpath=//h1"})).refusal

    assert refusal is not None and refusal.code == ARGUMENTS_INVALID


async def test_a_task_stopped_while_the_password_is_typed_does_not_click(tmp_path: Path) -> None:
    """The last look at the stop, right before the click that sends the form."""
    vault = FakeVault([MARIO])
    stop = FakeStop()

    class StopsAtThePassword(FakeAccountBrowser):
        async def fill_secret(self, page: str, selector: str, value: Secret) -> None:
            await super().fill_secret(page, selector, value)
            if selector == "#word":
                stop.event.set()

    browser = StopsAtThePassword(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, stop)

    assert result.error is not None and result.error.code == STOPPED
    assert result.output == {"status": 200, "gestures": 2}
    assert browser.clicks == [], "the form was not sent"


# ----------------------------------------------------------------------------------------
# The verifiers: the page says, in the browser that opened it
# ----------------------------------------------------------------------------------------


async def kept(browser: FakeAccountBrowser) -> str:
    """A page a tool handed to its verifier, as the tool does."""
    opened = await browser.open("https://posta.example/login", lambda url: True, FakeStop())
    await browser.keep(opened.page)
    return opened.page


def succeeded(capability: str, output: dict[str, object]) -> ExecutionResult:
    from tests.tools.test_verifiers import succeeded as made

    return made(capability, output=output)


def test_what_the_three_verifiers_declare() -> None:
    from ela.tools.verifiers import BrowserActVerifier, BrowserReadVerifier

    assert AccountReadVerifier.conditions == BrowserReadVerifier.conditions
    assert AccountActVerifier.conditions == BrowserActVerifier.conditions
    assert LoginVerifier.conditions == {BROWSER_EXPECT_VISIBLE}
    assert BROWSER_SECOND_FACTOR in LoginVerifier.failure_codes
    assert BROWSER_SECOND_FACTOR not in AccountActVerifier.failure_codes
    assert {BROWSER_EXPECT_MISSING, BROWSER_PAGE_GONE} <= LoginVerifier.failure_codes


async def test_a_read_and_an_action_with_the_profile_are_verified_as_the_empty_browser_s() -> None:
    reading = FakeAccountBrowser(FakePage(texts={None: "la posta di Mario"}))
    read = AccountReadVerifier(reading, 30.0)
    acting = FakeAccountBrowser(FakePage(shown=False))
    act = AccountActVerifier(acting, 30.0)

    assert read.capability_id == BROWSER_READ_AS_YOU and act.capability_id == BROWSER_ACT_AS_YOU
    assert (
        await read.verify(
            [BROWSER_TEXT_MATCHES],
            {},
            succeeded(
                BROWSER_READ_AS_YOU, {"text": "la posta di Mario", "page": await kept(reading)}
            ),
        )
        == ()
    )
    (failure,) = await act.verify(
        [BROWSER_EXPECT_VISIBLE],
        {"expect_text": "Mandato"},
        succeeded(BROWSER_ACT_AS_YOU, {"page": await kept(acting)}),
    )
    assert failure.code == BROWSER_EXPECT_MISSING
    assert reading.glances and acting.glances, "each looked at its page in its own browser"


async def test_a_login_is_verified_by_the_text_the_plan_awaits() -> None:
    browser = FakeAccountBrowser(FakePage(shown=True))
    verifier = LoginVerifier(browser, 30.0)

    failures = await verifier.verify(
        [BROWSER_EXPECT_VISIBLE],
        {"expect_text": "Benvenuto"},
        succeeded(BROWSER_LOGIN, {"page": await kept(browser)}),
    )

    assert failures == () and verifier.capability_id == BROWSER_LOGIN
    assert browser.glances == [("page-1", None, "Benvenuto", 30.0)]


async def test_a_page_that_asks_for_a_second_factor_is_said_with_a_code_of_its_own() -> None:
    """Decision 17: «do it by hand in ELA's window» — instead of «the text is missing», which a
    person reads as a login that failed."""
    browser = FakeAccountBrowser(FakePage(shown=False, second_factor=True))

    (failure,) = await LoginVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE],
        {"expect_text": "Benvenuto"},
        succeeded(BROWSER_LOGIN, {"page": await kept(browser)}),
    )

    assert failure.code == BROWSER_SECOND_FACTOR
    assert "do it by hand in ELA's window" in failure.message
    assert "Benvenuto" not in failure.message, "the text of the plan enters no failure"


async def test_a_text_that_does_not_appear_without_a_second_factor_is_a_text_that_is_missing() -> (
    None
):
    browser = FakeAccountBrowser(FakePage(shown=False))

    (failure,) = await LoginVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE],
        {"expect_text": "Benvenuto"},
        succeeded(BROWSER_LOGIN, {"page": await kept(browser)}),
    )

    assert failure.code == BROWSER_EXPECT_MISSING
    assert "within 30 s after the login was sent" in failure.message


async def test_a_text_that_appears_is_a_login_that_worked_whatever_else_the_page_shows() -> None:
    browser = FakeAccountBrowser(FakePage(shown=True, second_factor=True))

    failures = await LoginVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE],
        {"expect_text": "Benvenuto"},
        succeeded(BROWSER_LOGIN, {"page": await kept(browser)}),
    )

    assert failures == ()


async def test_a_login_s_verifier_without_a_text_or_a_page_says_which(tmp_path: Path) -> None:
    browser = FakeAccountBrowser()
    verifier = LoginVerifier(browser, 30.0)

    (no_text,) = await verifier.verify(
        [BROWSER_EXPECT_VISIBLE], {}, succeeded(BROWSER_LOGIN, {"page": "page-1"})
    )
    (no_page,) = await verifier.verify(
        [BROWSER_EXPECT_VISIBLE], {"expect_text": "Benvenuto"}, succeeded(BROWSER_LOGIN, {})
    )

    assert no_text.code == VERIFICATION_ARGUMENTS_INVALID
    assert no_page.code == BROWSER_PAGE_GONE


# ----------------------------------------------------------------------------------------
# What the page was when a login left it (decision 106)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("landed", "still", "said"),
    [
        ("https://posta.example/inbox", 0, ("posta.example/inbox", False)),
        (
            "https://posta.example/login?failed=1&next=%2Finbox#top",
            1,
            ("posta.example/login", True),
        ),
    ],
    ids=["a page of who is in", "the form again"],
)
async def test_the_result_of_a_login_says_where_the_page_ended_its_status_and_the_password_field(
    tmp_path: Path, landed: str, still: int, said: tuple[str, bool]
) -> None:
    """Decision 106. The proof of 2026-10-12 ended with «the text did not appear», and nobody
    could say whether the site had refused the login or had signed in and the cookie was lost.
    The result of the step says the three things that tell the two apart — **and it is the
    result that says them**: a failure's sentence goes to the audit, where a path never goes
    (ADR 0052 §12). The query and the fragment of the address are in neither."""
    browser = FakeAccountBrowser(
        page(landed=landed, landed_status=200, counts_after_click={"#word": still})
    )
    tool = await login(browser, FakeVault([MARIO]), tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output == {
        "status": 200,
        "gestures": 3,
        "page": "page-1",
        "ended_at": said[0],
        "ended_status": 200,
        "password_field_still_there": said[1],
    }
    assert browser.landings == ["page-1"], "asked once, of the page the click was made on"


async def test_a_document_that_never_came_back_has_no_status_to_tell(tmp_path: Path) -> None:
    browser = FakeAccountBrowser(page(landed_status=None))
    tool = await login(browser, FakeVault([MARIO]), tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.output["ended_status"] is None
    assert result.output["ended_at"] == "posta.example/login", "where the page was opened"


async def test_a_login_that_left_the_site_or_typed_nothing_is_not_asked_where_it_ended(
    tmp_path: Path,
) -> None:
    """What the page was is the diagnosis of a login **that was sent and stayed**: one that
    left the site says so with its own code, and one that typed nothing has nothing to tell."""
    left = FakeAccountBrowser(page(left_after_click="https://altro.example/sso"))
    tool = await login(left, FakeVault([MARIO]), tmp_path)
    await asked(tool)
    away = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    untyped = FakeAccountBrowser(page(counts={"#word": 0}))
    tool = await login(untyped, FakeVault([MARIO]), tmp_path)
    await asked(tool)
    nothing = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert away.error is not None and away.error.code == LEFT_SITE
    assert away.output == {"status": 200, "gestures": 3} and left.landings == []
    assert nothing.error is not None and nothing.output == {"gestures": 0}
    assert untyped.landings == []


def test_where_a_login_ended_is_in_no_number_the_audit_takes_from_the_result() -> None:
    """``ended_status`` is an integer, and the audit copies the integers a tool names: it names
    the two it named before, and not this one — what the page was stays in the result."""
    assert LoginTool.audit_numbers == {"status", "gestures"}


@pytest.mark.parametrize(
    ("address", "place"),
    [
        ("https://posta.example/login?failed=1&next=%2Finbox#top", "posta.example/login"),
        ("https://posta.example", "posta.example/"),
        ("https://posta.example:8443/a/b", "posta.example:8443/a/b"),
        ("https://" + ":".join(("mario", "x")) + "@posta.example/a", "posta.example/a"),
        ("https://POSTA.example/A", "posta.example/A"),
        ("about:blank", "about:blank"),
    ],
    ids=["query and fragment", "no path", "a port", "a user before the host", "case", "no host"],
)
def test_the_place_of_an_address_is_its_host_and_its_path_and_nothing_else(
    address: str, place: str
) -> None:
    from ela.tools.browser import place_of

    assert place_of(address) == place


async def test_a_text_that_is_missing_after_a_login_says_where_what_the_page_was_is_written() -> (
    None
):
    """The failure points at the result and carries nothing of it: its sentence goes to the
    audit. So the proof that fails says by itself where to read what happened."""
    browser = FakeAccountBrowser(
        FakePage(shown=False, landed="https://posta.example/accedi-rifiutato")
    )

    (failure,) = await LoginVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE],
        {"expect_text": "Benvenuto"},
        succeeded(BROWSER_LOGIN, {"page": await kept(browser)}),
    )

    assert failure.code == BROWSER_EXPECT_MISSING
    assert "in the result of this step" in failure.message
    assert "`ela task results`" in failure.message
    assert "accedi-rifiutato" not in failure.message and "posta.example" not in failure.message
    assert set(failure.details) == {"condition"}, "and no detail carries it either"
