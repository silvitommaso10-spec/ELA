"""No ``NODE_`` variable reaches the browser's driver (decision 4 of the review of 2026-09-30).

The document of the main frame is fetched by Playwright's Node driver, which inherits ELA's
environment (ADR 0052 §6, §14). Measured (M4-ter): ``NODE_TLS_REJECT_UNAUTHORIZED=0`` or
``NODE_EXTRA_CA_CERTS`` in the shell that starts ELA make a page with an invalid certificate open —
a variable forgotten in a shell turns off, in silence, the check of a HIGH action that sends data
out. So **the Core removes from its own environment every variable whose name begins with**
``NODE_`` — by the prefix, never by a list of names — while it is assembled and before the adapter
exists, and keeps the names, never the values, for the start-up to write.

The last test reads the driver's own process, as the measure of decision 14 read it: the real
browser, and it fails if the shell is not installed, with the command to give.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from ela.composition import Settings, build
from ela.permissions import BROWSER_READ
from ela.testing.fakes import FakeBrowser, FakePower, FakeStop
from tests.composition.support import create_schema, database_url, declare

PREFIX = "NODE_"


async def test_the_core_removes_every_node_variable_and_keeps_only_the_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    monkeypatch.setenv("NODE_TLS_REJECT_UNAUTHORIZED", "0")
    monkeypatch.setenv("NODE_UNA_QUALSIASI", "valore-7431")
    monkeypatch.setenv("NOT_NODE_OPTIONS", "resta")
    before = sorted(name for name in os.environ if name.startswith(PREFIX))

    ela = await build(Settings.load(), power=FakePower(), browser=FakeBrowser())
    try:
        removed = ela.removed_from_environment
    finally:
        await ela.aclose()

    assert removed == tuple(before), "every NODE_ variable, by the prefix, in order"
    assert {"NODE_TLS_REJECT_UNAUTHORIZED", "NODE_UNA_QUALSIASI"} <= set(removed)
    assert not any(name.startswith(PREFIX) for name in os.environ)
    assert os.environ["NOT_NODE_OPTIONS"] == "resta", "only the prefix, not a word inside"
    assert all("7431" not in name for name in removed), "names, never values"


def driver_of_this_process() -> int:
    """The pid of the Node driver this worker started: the descendant running ``run-driver``."""
    out = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True, check=True
    ).stdout
    children: dict[int, list[tuple[int, str]]] = {}
    for pid, ppid, command in (line.split(None, 2) for line in out.splitlines()):
        children.setdefault(int(ppid), []).append((int(pid), command))
    todo, found = [os.getpid()], []
    while todo:
        for pid, command in children.get(todo.pop(), []):
            todo.append(pid)
            if "run-driver" in command:
                found.append(pid)
    (driver,) = found
    return driver


def environment_names(pid: int) -> set[str]:
    """The names in a process's environment, never the values: ``/proc`` where the kernel keeps
    one, ``ps eww`` where it does not (the reading of the measure of decision 14, on this Mac)."""
    proc = Path(f"/proc/{pid}/environ")
    if proc.exists():
        return {entry.split("=", 1)[0] for entry in proc.read_text().split("\0") if "=" in entry}
    line = subprocess.run(
        ["/bin/ps", "eww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True
    ).stdout
    return set(re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=", line))


async def test_the_driver_of_the_core_does_not_receive_a_node_variable_of_the_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    monkeypatch.setenv("NODE_TLS_REJECT_UNAUTHORIZED", "0")
    ela = await build(Settings.load(), power=FakePower())
    browser = ela.tools.get(BROWSER_READ)._browser  # type: ignore[attr-defined]  # noqa: SLF001
    try:
        opened = await browser.open("about:blank", lambda url: True, FakeStop())
        try:
            names = environment_names(driver_of_this_process())
        finally:
            await browser.close(opened.page)
    finally:
        await ela.aclose()

    assert "PW_LANG_NAME" in names, "the reading reads the driver: Playwright gives it this name"
    assert "NODE_TLS_REJECT_UNAUTHORIZED" not in names
