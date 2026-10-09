"""The session of Claude Code launched by ELA (M14.3, ADR 0060): its launcher, its closed
environment, its folder — and, with the binary of the SDK's wheel, a dry run on a fake model on
loopback that spends nothing.

The dry run proves what only the real binary can: the tools of the start are the two of ELA, a
gesture reaches the host in-process, a stop ends the session, no process is left, the folder is
gone — and **a variable of ELA's environment is not in the process's**, read from the process
itself (criterion 8): the SDK builds the environment of ``claude`` from the one of the process that
uses it, and the launcher is what closes it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from ela.domain import ErrorMetadata, JsonMapping, Reservation, StepId
from ela.infrastructure.machine.agent import (
    LAUNCHER,
    PID,
    SDK_NAMES,
    TOOLS,
    ClaudeAgentSession,
    _changed,
    bundled_binary,
    closed_environment,
    launcher_text,
)
from ela.ports import (
    GUIDED_FOLDER_CHANGED,
    GUIDED_NOT_INSTALLED,
    SessionHandle,
    SessionHost,
    SessionPlan,
)
from tests.tools.test_terminal_limits import fired, skip_problems

SENTINEL = "ELA_SENTINEL_OF_M14_3"
TOKEN = "t" * 43


def plan(gateway: str = "http://127.0.0.1:1", seconds: int = 120) -> SessionPlan:
    return SessionPlan(
        session=StepId(uuid.uuid4()),
        goal="Leggi example.com e dimmi il titolo.",
        instructions="You guide a web browser. Use the tools read and act.",
        model="claude-haiku-5-5",
        max_tokens=8192,
        gateway=gateway,
        token=TOKEN,
        seconds=seconds,
    )


RESERVATION = Reservation(
    task_id=uuid.uuid4(),  # type: ignore[arg-type]
    step_id=uuid.uuid4(),  # type: ignore[arg-type]
    started_id=uuid.uuid4(),  # type: ignore[arg-type]
    amount=Decimal("0.60"),
    currency="USD",
    model="claude-haiku-5-5",
    input_tokens=991_808,
    output_tokens=8_192,
)


def test_the_environment_is_closed_and_holds_no_key_and_nothing_of_ela_s(tmp_path: Path) -> None:
    environment = closed_environment(plan(), tmp_path)

    assert not any(name.startswith("ELA_") for name in environment)
    assert environment["ANTHROPIC_API_KEY"] == TOKEN, "the token, not a key"
    assert environment["HOME"] == environment["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert environment["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "8192"
    assert environment["MCP_TOOL_TIMEOUT"] == "120000"
    assert environment["DISABLE_PROMPT_CACHING"] == "1"
    assert environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"


def test_the_launcher_passes_the_names_and_holds_no_value(tmp_path: Path) -> None:
    environment = closed_environment(plan(), tmp_path)
    text = launcher_text(Path("/opt/the binary/claude"), (*environment, *SDK_NAMES))

    assert text.startswith("#!/bin/sh\n")
    assert "exec /usr/bin/env -i " in text
    assert 'ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"' in text
    assert 'CLAUDE_AGENT_SDK_VERSION="${CLAUDE_AGENT_SDK_VERSION}"' in text
    assert "'/opt/the binary/claude' \"$@\"" in text
    assert TOKEN not in text


def test_a_folder_that_is_not_what_ela_wrote_is_said(tmp_path: Path) -> None:
    (tmp_path / LAUNCHER).write_text("#!/bin/sh\n", encoding="utf-8")
    fingerprint = hashlib.sha256(b"#!/bin/sh\n").hexdigest()

    assert _changed(tmp_path, fingerprint) is None
    assert _changed(tmp_path, "0" * 64) == "the launcher of the session is not the one ELA wrote"
    (tmp_path / "extra").write_text("x", encoding="utf-8")
    assert "2 entries" in str(_changed(tmp_path, fingerprint))


async def test_no_binary_no_session(tmp_path: Path) -> None:
    session = ClaudeAgentSession(tmp_path / "sessions", binary=tmp_path / "nowhere")

    unready = await session.ready()
    launched = await session.launch(RESERVATION, plan(), _host())

    assert unready is not None and unready.code == GUIDED_NOT_INSTALLED
    assert isinstance(launched, ErrorMetadata) and launched.code == GUIDED_NOT_INSTALLED


async def test_a_folder_of_the_sessions_that_cannot_be_made_is_said(tmp_path: Path) -> None:
    (tmp_path / "sessions").write_text("a file where the folder goes", encoding="utf-8")
    session = ClaudeAgentSession(tmp_path / "sessions", binary=Path(sys.executable))

    unready = await session.ready()

    assert unready is not None and unready.code == GUIDED_FOLDER_CHANGED


async def test_a_folder_already_there_launches_nothing(tmp_path: Path) -> None:
    session = ClaudeAgentSession(tmp_path / "sessions", binary=Path(sys.executable))
    planned = plan()
    (tmp_path / "sessions" / str(planned.session)).mkdir(parents=True)

    launched = await session.launch(RESERVATION, planned, _host())

    assert isinstance(launched, ErrorMetadata) and launched.code == GUIDED_FOLDER_CHANGED
    assert not await session.running(planned.session)


def test_the_check_of_the_folder_knows_the_pid_ela_writes(tmp_path: Path) -> None:
    """Decision 34 (a): at the launch ELA writes the process's pid beside the launcher; the check
    of the folder knows that file — a number, and nothing else — as ELA's own."""
    text = launcher_text(Path("/bin/claude"), ("PATH",))
    (tmp_path / LAUNCHER).write_text(text, encoding="utf-8")
    fingerprint = hashlib.sha256(text.encode()).hexdigest()
    (tmp_path / PID).write_text("4242\n", encoding="utf-8")

    assert _changed(tmp_path, fingerprint) is None
    (tmp_path / PID).write_text("not a pid", encoding="utf-8")
    assert _changed(tmp_path, fingerprint) is not None


def a_leftover(root: Path, pid: int | None, content: str | None = None) -> Path:
    """A session's folder as a crash leaves it: the launcher, the pid when the launch got that far,
    and whatever the session wrote."""
    folder = root / str(uuid.uuid4())
    folder.mkdir(parents=True)
    (folder / LAUNCHER).write_text("#!/bin/sh\n", encoding="utf-8")
    if pid is not None:
        (folder / PID).write_text(f"{pid}\n", encoding="utf-8")
    if content is not None:
        (folder / "registro.txt").write_text(content, encoding="utf-8")
    return folder


async def test_the_sweep_kills_a_session_s_process_and_deletes_its_folder(tmp_path: Path) -> None:
    """Decision 34 (b), with a real process, as for the terminal: a session's process alive at
    start-up — measured on the Mac, 2026-10-09: ``claude`` outlives an ``ela serve`` killed with
    ``SIGKILL``, reparented to ``launchd``, for at least 120 s — is killed, and its folder deleted.
    Here the session's binary is the interpreter of the tests, so the process is the binary's."""
    session = ClaudeAgentSession(tmp_path / "sessions", binary=Path(sys.executable))
    living = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    try:
        folder = a_leftover(tmp_path / "sessions", living.pid, "il testo di una pagina")

        swept = await session.sweep()

        assert living.wait(timeout=10) == -9
        assert swept == 1 and not folder.exists()
    finally:
        if living.poll() is None:
            living.kill()
            living.wait()


async def test_the_sweep_never_kills_a_process_that_is_not_the_session_s_binary(
    tmp_path: Path,
) -> None:
    """A pid is a number the kernel gives again: after a crash and a restart it can name another
    program. The sweep kills only a process whose command is the session's binary; the folder goes
    anyway."""
    session = ClaudeAgentSession(tmp_path / "sessions", binary=tmp_path / "claude")
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    try:
        folder = a_leftover(tmp_path / "sessions", other.pid)

        swept = await session.sweep()

        assert other.poll() is None, "another program's process is left alone"
        assert swept == 1 and not folder.exists()
    finally:
        other.kill()
        other.wait()


async def test_the_sweep_deletes_what_has_no_pid_or_a_pid_that_is_not_a_number(
    tmp_path: Path,
) -> None:
    session = ClaudeAgentSession(tmp_path / "sessions", binary=Path(sys.executable))
    root = tmp_path / "sessions"
    bare = a_leftover(root, None, "il testo di una pagina")
    garbled = a_leftover(root, None)
    (garbled / PID).write_text("x", encoding="utf-8")
    gone = a_leftover(root, 2**22 + 7)
    (root / "a-file").write_text("not a session", encoding="utf-8")

    swept = await session.sweep()

    assert swept == 3
    assert not bare.exists() and not garbled.exists() and not gone.exists()
    assert (root / "a-file").exists(), "only the folders of sessions are ELA's to sweep"


async def test_a_sweep_with_no_folder_of_the_sessions_sweeps_nothing(tmp_path: Path) -> None:
    session = ClaudeAgentSession(tmp_path / "never", binary=Path(sys.executable))

    assert await session.sweep() == 0


def test_the_two_tools_are_ela_s() -> None:
    assert frozenset({"mcp__ela__read", "mcp__ela__act"}) == TOOLS


def _host(
    seen: list[tuple[str, ...]] | None = None,
    gestures: list[tuple[str, JsonMapping]] | None = None,
    reading: Any = None,
) -> SessionHost:
    async def started(tools: tuple[str, ...]) -> ErrorMetadata | None:
        if seen is not None:
            seen.append(tools)
        return None

    async def gesture(name: str, arguments: JsonMapping) -> str:
        if gestures is not None:
            gestures.append((name, arguments))
        if reading is not None:
            await reading()
        return "address: https://example.com/\ntitle: Example Domain\ntext: Example Domain"

    async def asked() -> None:
        return None

    return SessionHost(started=started, gesture=gesture, asked=asked)


# ----------------------------------------------------------------------------------------
# The dry run: the binary of the SDK on a fake model on loopback
# ----------------------------------------------------------------------------------------

RUNNABLE = os.access(bundled_binary(), os.X_OK) and sys.platform != "win32"
NO_BINARY = "the binary of Claude Code that the SDK's wheel carries is not on this machine"
NO_PROC = (
    "only Linux hands a process the environment of another, in /proc: macOS keeps it out of "
    "KERN_PROCARGS2 and of ps -E (measured on the Mac, 2026-10-09)"
)


async def _fake_model(request: Request) -> Response:
    body = json.loads(await request.body())
    tools = [str(one.get("name")) for one in body.get("tools") or []]
    request.app.state.calls.append({"tools": tools, "model": body.get("model")})
    read = next((one for one in tools if one.endswith("read")), None)
    looked = "Example Domain" in json.dumps(body.get("messages") or [])
    if read is not None and not looked:
        content: dict[str, Any] = {
            "type": "tool_use",
            "id": f"toolu_{uuid.uuid4().hex[:20]}",
            "name": read,
            "input": {"site": "example.com", "path": "/"},
        }
        stop = "tool_use"
    else:
        content = {"type": "text", "text": "Il titolo è Example Domain (https://example.com/)."}
        stop = "end_turn"
    return StreamingResponse(
        _events(body.get("model"), content, stop), media_type="text/event-stream"
    )


async def _events(model: str, content: dict[str, Any], stop: str) -> AsyncIterator[bytes]:
    def event(kind: str, data: Mapping[str, Any]) -> bytes:
        return f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode()

    start = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 1},
    }
    yield event("message_start", {"type": "message_start", "message": start})
    if content["type"] == "tool_use":
        block = dict(content, input={})
        delta = {"type": "input_json_delta", "partial_json": json.dumps(content["input"])}
    else:
        block = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": content["text"]}
    yield event(
        "content_block_start", {"type": "content_block_start", "index": 0, "content_block": block}
    )
    yield event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": delta})
    yield event("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield event(
        "message_delta",
        {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 20}},
    )
    yield event("message_stop", {"type": "message_stop"})


@asynccontextmanager
async def a_fake_model() -> AsyncIterator[tuple[str, list[dict[str, Any]]]]:
    app = Starlette(routes=[Route("/v1/messages", _fake_model, methods=["POST"])])
    app.state.calls = []
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    serving = asyncio.ensure_future(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app.state.calls
    finally:
        server.should_exit = True
        await serving


async def a_dry_session(
    tmp_path: Path, reading: Any = None
) -> tuple[Any, list[tuple[str, ...]], list[tuple[str, JsonMapping]], list[dict[str, Any]], Path]:
    """One session of the real binary on the fake model, to its end."""
    session = ClaudeAgentSession(tmp_path / "sessions")
    seen: list[tuple[str, ...]] = []
    gestures: list[tuple[str, JsonMapping]] = []
    async with a_fake_model() as (url, calls):
        planned = plan(url)

        async def read_the_process() -> None:
            if reading is not None:
                found = session._running[planned.session].pid  # noqa: SLF001
                assert found is not None
                await reading(found)

        launched = await session.launch(
            RESERVATION, planned, _host(seen, gestures, read_the_process)
        )
        assert isinstance(launched, SessionHandle)
        end = await asyncio.wait_for(launched.ended, 120)
        assert not await session.running(planned.session)
    return end, seen, gestures, calls, tmp_path / "sessions" / str(planned.session)


@pytest.mark.skipif(not RUNNABLE, reason=NO_BINARY)
async def test_the_real_binary_starts_with_the_two_tools_makes_a_gesture_and_ends_closed(
    tmp_path: Path,
) -> None:
    end, seen, gestures, calls, folder = await a_dry_session(tmp_path)

    assert end.subtype == "success", end
    assert "Example Domain" in end.text
    assert end.closed and end.version
    assert seen and set(seen[0]) == set(TOOLS)
    assert [name for name, _ in gestures] == ["read"]
    assert calls and all(set(call["tools"]) == set(TOOLS) for call in calls)
    assert not folder.exists()


@pytest.mark.skipif(sys.platform != "linux", reason=NO_PROC)
@pytest.mark.skipif(not RUNNABLE, reason=NO_BINARY)
async def test_the_process_of_a_session_sees_nothing_of_ela_s_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 8: a variable of ELA's process, absent from the process of the session — read
    from the kernel while the session's gesture runs. The variables the launcher passes on are
    there, so the reading is not empty."""
    monkeypatch.setenv(SENTINEL, "a variable of ELA's process")
    environments: list[str] = []

    async def reading(pid: int) -> None:
        environments.append(Path(f"/proc/{pid}/environ").read_bytes().decode(errors="replace"))

    await a_dry_session(tmp_path, reading)

    (seen,) = environments
    assert "ANTHROPIC_BASE_URL=" in seen and "MCP_TOOL_TIMEOUT=" in seen
    assert SENTINEL not in seen


@pytest.mark.parametrize(
    ("test", "kernel", "absent"),
    [
        (test_the_process_of_a_session_sees_nothing_of_ela_s_environment, "linux", NO_PROC),
    ],
    ids=["environment-on-linux"],
)
def test_the_reading_of_the_environment_is_never_skipped_on_linux_and_elsewhere_says_why(
    test: Any, kernel: str, absent: str
) -> None:
    assert skip_problems(test, kernel, absent) == []


@pytest.mark.parametrize(
    "test",
    [test_the_real_binary_starts_with_the_two_tools_makes_a_gesture_and_ends_closed],
)
def test_the_real_binary_is_never_skipped_where_the_suite_runs(test: Any) -> None:
    """The SDK's wheel carries the binary on macOS and on Linux, the two systems of ``make check``:
    a binary missing there is a skip that would hide the dry run."""
    assert sys.platform == "win32" or fired(test) == []


@pytest.mark.skipif(not RUNNABLE, reason=NO_BINARY)
async def test_the_real_binary_stopped_during_a_gesture_ends_and_leaves_nothing(
    tmp_path: Path,
) -> None:
    """Criterion 7: the interrupt first, the end of the input, then — never needed here — the
    kill. The gesture in progress is waiting when the stop arrives."""
    session = ClaudeAgentSession(tmp_path / "sessions", grace=5.0)
    waiting = asyncio.Event()
    async with a_fake_model() as (url, calls):
        planned = plan(url)

        async def reading() -> None:
            waiting.set()
            await asyncio.Event().wait()

        launched = await session.launch(RESERVATION, planned, _host(reading=reading))
        assert isinstance(launched, SessionHandle)
        await asyncio.wait_for(waiting.wait(), 120)
        await launched.interrupt()
        end = await asyncio.wait_for(launched.ended, 60)

    assert end.subtype != "success"
    assert end.closed
    assert not (tmp_path / "sessions" / str(planned.session)).exists()


@pytest.mark.skipif(not RUNNABLE, reason=NO_BINARY)
async def test_a_launched_session_writes_its_pid_beside_the_launcher(tmp_path: Path) -> None:
    """Decision 34 (a): the pid of the process the SDK started, in the session's folder, so that a
    start-up after a crash finds it."""
    session = ClaudeAgentSession(tmp_path / "sessions", grace=5.0)
    waiting = asyncio.Event()
    async with a_fake_model() as (url, calls):
        planned = plan(url)

        async def reading() -> None:
            waiting.set()
            await asyncio.Event().wait()

        launched = await session.launch(RESERVATION, planned, _host(reading=reading))
        assert isinstance(launched, SessionHandle)
        await asyncio.wait_for(waiting.wait(), 120)
        folder = tmp_path / "sessions" / str(planned.session)
        written = (folder / PID).read_text(encoding="utf-8").strip()
        process = session._running[planned.session].pid  # noqa: SLF001
        await launched.interrupt()
        await asyncio.wait_for(launched.ended, 60)

    assert written == str(process)


@pytest.mark.skipif(not RUNNABLE, reason=NO_BINARY)
async def test_after_the_sweep_the_session_of_a_step_left_by_a_crash_starts(
    tmp_path: Path,
) -> None:
    """Decision 34: a folder a crash left makes the next session of the same step fail with
    ``guided.folder_changed`` (``test_a_folder_already_there_launches_nothing``); after the sweep
    of the start-up the old content is gone, and the session starts and ends."""
    session = ClaudeAgentSession(tmp_path / "sessions")
    async with a_fake_model() as (url, calls):
        planned = plan(url)
        folder = tmp_path / "sessions" / str(planned.session)
        folder.mkdir(parents=True)
        (folder / "registro.txt").write_text("il testo di una pagina", encoding="utf-8")
        refused = await session.launch(RESERVATION, planned, _host())
        assert isinstance(refused, ErrorMetadata) and refused.code == GUIDED_FOLDER_CHANGED

        await session.sweep()
        assert not folder.exists()
        launched = await session.launch(RESERVATION, planned, _host())
        assert isinstance(launched, SessionHandle)
        end = await asyncio.wait_for(launched.ended, 120)

    assert end.subtype == "success", end
