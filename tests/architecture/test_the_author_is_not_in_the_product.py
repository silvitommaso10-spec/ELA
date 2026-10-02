"""Nothing of whoever wrote ELA in what ELA installs and serves: ``src/`` and ``apps/`` (M9.6).

The rule is ``CLAUDE.md``'s, «Qualità», and most of it is for a review to judge: a name, a machine
described in a docstring, a preference. **This module proves the part a machine can recognise, and
its name says which**: no host of a Tailscale network and no absolute path inside a user's home, in
the files git tracks under ``src/`` and ``apps/``. Text, not Python: the rule crosses both trees and
lives in one place, so it is not one of the AST rules of :mod:`tests.architecture.rules` and does
not change their count. The exception to «the rules of ``apps/`` live in the tests of their folder»
is ADR 0056's, with the README of ``apps/command-center/`` as its precedent.

**A network is not an address.** The networks are :data:`~ela.composition.settings.TAILNET_RANGES`,
IPv4 and IPv6, read from there and not written here; one written with its prefix — shorter than the
address, with no host bits, what ``ipaddress.ip_network(strict=True)`` accepts — is admitted. A host
written as ``/32`` or ``/128``, or followed by a numeric path in a URL, is still a host.

**A home is ``/Users/<name>``, ``/home/<name>`` or ``<drive>:\\Users\\<name>``**, in any case and
with either slash, where a path begins — at the start of a line, after a space, a quote, a backtick,
``=``, a parenthesis or ``file://`` —, never after a host: ``https://example.com/home/`` is a page.
The one name admitted is the documented placeholder, ``you`` (``/Users/you/Documents``, the example
of ``ELA_FS_ROOT``).

In the same pass, the voices the author chose for their own ELA: the six ids of the table in
``docs/milestones/M9.6.md``, read from there, are in no file of ``src/`` or ``apps/`` — they are
written in the ``.env`` of whoever chose them (decision K).

And every ``README.md`` under ``apps/``, the placeholders of ``apps/desktop/`` included, names this
rule with its test (decision M, decision 11 of the review): it is the only defence the folders
without a test of their own will have, and a new README that does not name it stops the suite.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

from ela.composition.settings import TAILNET_RANGES

ROOT = Path(__file__).resolve().parents[2]
TREES = ("src", "apps")
BINARY = "i/-text"
THIS = "tests/architecture/test_the_author_is_not_in_the_product.py"
RULE = "test_no_tailnet_host_and_no_path_inside_a_home_in_src_and_apps"
PLACEHOLDER = "you"
VOICES_DOCUMENT = ROOT / "docs" / "milestones" / "M9.6.md"
VOICES_SECTION = "## Il censimento del 2026-09-30"
VOICE_ROW = re.compile(r"^\| `([A-Za-z0-9]{20})` \| [^|]+ \|$", re.MULTILINE)

IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,3}))?(?!\.?\d)")
"""A dotted quad not inside a longer number or name; a full stop after it ends a sentence."""
IPV6 = re.compile(
    r"(?<![\w:.])([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})(?:/(\d{1,3}))?(?![\w:])"
)
"""Hex groups with at least two colons: ``ipaddress`` decides which of them are addresses."""
HOME = re.compile(
    r"(?:^|(?<=[\s\"'`=(])|(?<=file://))"
    r"(?:/Users/|/home/|[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/))"
    r"([^\s/\\\"'`)<>]+)",
    re.IGNORECASE | re.MULTILINE,
)
"""Where a path begins, a home, and the name after it — up to the next separator or quote."""


def tailnet_hosts(text: str) -> Iterator[tuple[int, str]]:
    """Each host of a network of ``TAILNET_RANGES`` written in ``text``, with its line."""
    for pattern in (IPV4, IPV6):
        for found in pattern.finditer(text):
            try:
                address = ipaddress.ip_address(found.group(1))
            except ValueError:
                continue
            if not any(address in network for network in TAILNET_RANGES):
                continue
            if _a_network(address, found.group(2)):
                continue
            yield _line(text, found.start()), found.group(0)


def _a_network(address: ipaddress.IPv4Address | ipaddress.IPv6Address, prefix: str | None) -> bool:
    """A prefix shorter than the address and no host bits: a range, not a machine."""
    if prefix is None or int(prefix) >= address.max_prefixlen:
        return False
    try:
        ipaddress.ip_network(f"{address}/{prefix}", strict=True)
    except ValueError:
        return False
    return True


def homes(text: str) -> Iterator[tuple[int, str]]:
    """Each absolute path inside a user's home written in ``text``, but the placeholder's."""
    for found in HOME.finditer(text):
        if found.group(1) != PLACEHOLDER:
            yield _line(text, found.start()), found.group(0)


def voices_in(text: str, voices: Iterable[str]) -> Iterator[tuple[int, str]]:
    for voice in voices:
        for found in re.finditer(re.escape(voice), text):
            yield _line(text, found.start()), voice


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _listing() -> tuple[list[str], str | None]:
    """The text files git tracks under the two trees: binaries and deleted files are not read."""
    listed = subprocess.run(
        ["git", "ls-files", "--eol", "-z", *TREES], cwd=ROOT, capture_output=True
    )
    if listed.returncode != 0:
        return [], "not a git repository: nobody to ask which files ELA installs and serves"
    paths = []
    for entry in filter(None, listed.stdout.decode("utf-8").split("\0")):
        described, path = entry.split("\t", 1)
        if described.split()[0] != BINARY and (ROOT / path).is_file():
            paths.append(path)
    return paths, None


TRACKED, NO_REPOSITORY = _listing()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def the_six_voices() -> list[str]:
    text = VOICES_DOCUMENT.read_text(encoding="utf-8")
    start = text.index(VOICES_SECTION)
    return VOICE_ROW.findall(text[start : text.index("\n## ", start + 1)])


@pytest.mark.skipif(NO_REPOSITORY is not None, reason=NO_REPOSITORY or "")
def test_no_tailnet_host_and_no_path_inside_a_home_in_src_and_apps() -> None:
    """The tree git tracks, every text file of it. Seeing nothing is not a pass."""
    assert TRACKED, "git listed no file under src/ and apps/"
    found = [
        f"{path}:{line}: {written}"
        for path in TRACKED
        for finder in (tailnet_hosts, homes)
        for line, written in finder(read(path))
    ]

    assert not found, "\n".join(found)


@pytest.mark.skipif(NO_REPOSITORY is not None, reason=NO_REPOSITORY or "")
def test_none_of_the_six_voices_the_author_chose_is_written_in_src_or_apps() -> None:
    voices = the_six_voices()
    assert len(voices) == 6, f"the table of M9.6 gave {voices}"

    found = [
        f"{path}:{line}: {voice}"
        for path in TRACKED
        for line, voice in voices_in(read(path), voices)
    ]

    assert not found, "\n".join(found)


@pytest.mark.skipif(NO_REPOSITORY is not None, reason=NO_REPOSITORY or "")
def test_every_readme_of_apps_names_the_rule_with_its_test() -> None:
    readmes = [path for path in TRACKED if path.startswith("apps/") and path.endswith("README.md")]
    assert readmes, "git listed no README under apps/"

    silent = [path for path in readmes if not names_the_rule(read(path))]

    assert not silent, f"these READMEs do not name {THIS} and {RULE}: {silent}"


def names_the_rule(readme: str) -> bool:
    return f"`{THIS}`" in readme and f"`{RULE}`" in readme


# --------------------------------------------------------------------------------------
# The negative cases, on constructed strings: a finder that only ever finds nothing proves nothing
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "written",
    [
        "the Core answers on 100.76.92.39 too",
        "this Mac is 100.76.92.39.",
        "100.76.92.39/32",
        "http://100.76.92.39/8",
        "http://100.76.92.39:8351/health",
        "fd7a:115c:a1e0::1",
        "fd7a:115c:a1e0:ab12:4843:cd96:625c:5c27",
        "[fd7a:115c:a1e0::1]:8351",
        "fd7a:115c:a1e0::1/128",
    ],
)
def test_a_host_of_a_tailscale_network_is_found(written: str) -> None:
    assert [line for line, _ in tailnet_hosts(written)] == [1], written


@pytest.mark.parametrize(
    "written",
    [
        "100.64.0.0/10",
        "fd7a:115c:a1e0::/48",
        "ipaddress.ip_network('100.64.0.0/10')",
        "127.0.0.1",
        "192.168.1.10",
        "100.128.0.1",
        "fd7a:115c:a1e1::1",
        "version 1.100.64.1.2",
        "a[::2] and 12:30:45",
    ],
)
def test_a_network_and_an_address_of_no_tailnet_are_not(written: str) -> None:
    assert list(tailnet_hosts(written)) == [], written


@pytest.mark.parametrize(
    "written",
    [
        "/Users/tommaso/Documents",
        'Path("/Users/someone/ELA")',
        "ELA_FS_ROOT=/Users/anna/Documents",
        "`/home/marco/.ela`",
        "(see /home/marco)",
        r"C:\Users\tommaso\ELA",
        "c:\\\\users\\\\tommaso\\\\ELA",
        "C:/Users/tommaso/ELA",
        "/users/tommaso",
        "file:///Users/tommaso/ELA/apps/design-system/index.html",
        "/Users/youngster/ELA",
    ],
)
def test_a_path_inside_somebody_s_home_is_found(written: str) -> None:
    assert [line for line, _ in homes(written)] == [1], written


@pytest.mark.parametrize(
    "written",
    [
        "/Users/you/Documents",
        "ELA_FS_ROOT=/Users/you/Documents",
        r"C:\Users\you\Documents",
        "C:\\\\Users\\\\you",
        "https://example.com/home/index.html",
        "https://example.com/Users/tommaso",
        "~/Documents and Path.home()",
        "the /Users/ folder",
    ],
)
def test_the_placeholder_and_what_is_not_a_home_are_not(written: str) -> None:
    assert list(homes(written)) == [], written


def test_the_line_of_what_is_found_is_the_line_it_is_on() -> None:
    """The message names ``path:line``: the line has to be the right one."""
    text = "one\ntwo\nthe Mac is 100.76.92.39\n/Users/tommaso\n"

    assert [line for line, _ in tailnet_hosts(text)] == [3]
    assert [line for line, _ in homes(text)] == [4]


def test_a_voice_of_the_table_inside_a_text_is_found() -> None:
    voices = the_six_voices()
    text = f'CANDIDATES = (\n    ("{voices[2]}", "a name"),\n)'

    assert list(voices_in(text, voices)) == [(2, voices[2])]


def test_the_voices_are_read_from_the_table_and_not_from_elsewhere_in_the_document() -> None:
    """Six rows in one section: an id written in another section would not be one of them."""
    voices = the_six_voices()

    assert len(set(voices)) == len(voices) == 6
    assert all(VOICE_ROW.fullmatch(f"| `{voice}` | a name |") for voice in voices)


def test_a_readme_that_does_not_name_the_rule_is_reported() -> None:
    assert names_the_rule(f"| a rule | `{THIS}`, `{RULE}` |")
    assert not names_the_rule(f"| a rule | `{THIS}` |")
    assert not names_the_rule("Fase: post-0.1 — applicazioni desktop (spec §48).")
