"""A session of Claude Code launched by ELA as a program (M14.3, ADR 0060; STATO 5.7, 5.8).

The **only** module of ELA that imports ``claude_agent_sdk`` (architecture rule 32 names it among
the libraries that start processes by themselves): the Agent SDK pinned in the lock, with the binary
of Claude Code inside its wheel, so the version that runs is the one the lock names (proposal 13).

What a session is allowed, all of it written here and nothing chosen by the session:

* **no tools of its own** — ``--tools ""`` and ``--bare`` — and only the two gestures of ELA,
  **in-process** (``create_sdk_mcp_server``): no MCP route, no second listener, and no idle timeout
  on a gesture that waits for a yes (the documentation: «The idle timeout applies to every server
  type except IDE servers and SDK in-process servers»);
* **nothing to ask**: the two tools allowed by name, ``dontAsk``, ``--permission-prompts none``,
  and no ``can_use_tool`` — a request for a permission is an anomaly, and the host stops the
  session;
* **a folder of ELA's**, ``<sessions>/<step>/``, empty at birth but for the launcher, checked —
  exactly the launcher, with the fingerprint ELA wrote — right before the launch, and deleted after;
  once launched it holds the **pid** of the process too, so that the start-up after a crash finds
  it: ``ela serve`` killed with ``SIGKILL`` leaves ``claude`` running, reparented to ``launchd``,
  for at least 120 s (measured on the Mac, 2026-10-09), and :meth:`ClaudeAgentSession.sweep`
  kills it and deletes every folder;
* **a closed environment**: the four names of a program of the terminal (ADR 0047 §6) and the ones
  of the session, the gateway and its token among them — never a key, never a variable of ELA's.
  The SDK builds the environment of ``claude`` from the one of the process that uses it, so
  ``cli_path`` is a **launcher** that starts the binary with ``env -i`` and the names it is given;
* **the stop**: the interrupt first (decision 11), then the end of the input, then — after a grace —
  ``SIGKILL`` to the process. Never ``SIGTERM`` first: it leaves the turn half done.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shlex
import shutil
import signal
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    ToolAnnotations,
    create_sdk_mcp_server,
    tool,
)

from ela.domain import ErrorMetadata, JsonMapping, Reservation, StepId
from ela.ports import (
    GUIDED_FOLDER_CHANGED,
    GUIDED_NOT_INSTALLED,
    SessionEnd,
    SessionHandle,
    SessionHost,
    SessionPlan,
)

__all__ = [
    "ACT_SCHEMA",
    "CLOSED_PATH",
    "GRACE_SECONDS",
    "LANGUAGE",
    "LAUNCHER",
    "PID",
    "READ_SCHEMA",
    "RESULT_CHARS",
    "SDK_NAMES",
    "SERVER",
    "TOOLS",
    "ClaudeAgentSession",
    "bundled_binary",
    "closed_environment",
    "launcher_text",
]

SERVER: Final = "ela"
TOOLS: Final = frozenset({f"mcp__{SERVER}__read", f"mcp__{SERVER}__act"})
"""The two tools every session offers its model, by the names Claude Code gives them."""

LAUNCHER: Final = "launch"
"""The file ELA writes in a session's folder before the launch: the only one the folder holds then.
"""

PID: Final = "pid"
"""The file ELA writes in a session's folder once the process has started: its pid, which the
start-up reads after a crash (decision 34 of the review of the summary of M14.3)."""

PS: Final = "/bin/ps"
"""Where the command of a process is read: the same path on macOS and Linux."""

GRACE_SECONDS: Final = 5.0
"""How long ELA waits for a session to end after the interrupt and the end of its input, before
``SIGKILL``: the measure saw the end in 0,77 s."""

RESULT_CHARS: Final = 100_000
"""``anthropic/maxResultSizeChars`` of the two tools: without it Claude Code saves a text over
50 000 characters to a file and gives the model the path, and the model has no tool to read it
(Claude Code's documentation, «MCP output limits», read on 2026-10-08). ``browser.read`` returns at
most 64 KiB of text."""

CLOSED_PATH: Final = "/usr/bin:/bin:/usr/sbin:/sbin"
LANGUAGE: Final = "C.UTF-8"
"""Two of the four names of a program of the terminal (ADR 0047 §6), with the same values."""

SDK_NAMES: Final = (
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_AGENT_SDK_VERSION",
    "CLAUDE_CODE_SDK_READS_SESSION_STATE",
)
"""The variables the SDK sets for ``claude`` itself (``subprocess_cli.py`` at 0.2.165), which the
launcher passes on by name."""

SITE_SAID: Final = "one of the sites, a host name"
PATH_SAID: Final = 'what follows the site, starting with "/"'

READ_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "site": {"type": "string", "description": SITE_SAID},
        "path": {"type": "string", "description": PATH_SAID},
        "selector": {
            "type": "string",
            "description": "optional: the one element to read, a selector as the tool says",
        },
    },
    "required": ["site", "path"],
    "additionalProperties": False,
}
ACT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "site": {"type": "string", "description": SITE_SAID},
        "path": {"type": "string", "description": PATH_SAID},
        "fill": {
            "type": "array",
            "description": "pairs [selector, value], filled in order",
            "items": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        },
        "click": {"type": "string", "description": "the selector of the one element to click"},
        "expect_text": {
            "type": "string",
            "description": "the text the page must show after the click",
        },
    },
    "required": ["site", "path", "fill", "click", "expect_text"],
    "additionalProperties": False,
}


def bundled_binary() -> Path:
    """The binary of Claude Code the SDK's wheel carries: the version of the lock."""
    import claude_agent_sdk

    name = "claude"
    if os.name == "nt":
        name = "claude.exe"
    return Path(claude_agent_sdk.__file__).parent / "_bundled" / name


def closed_environment(plan: SessionPlan, folder: Path) -> dict[str, str]:
    """The environment of a session, all of it: no key, no variable of ELA's (proposal 6)."""
    return {
        "PATH": CLOSED_PATH,
        "HOME": str(folder),
        "TMPDIR": str(folder),
        "LANG": LANGUAGE,
        "ANTHROPIC_BASE_URL": plan.gateway,
        "ANTHROPIC_API_KEY": plan.token,
        "CLAUDE_CONFIG_DIR": str(folder),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
        "DISABLE_PROMPT_CACHING": "1",
        "DISABLE_COMPACT": "1",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": plan.model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": plan.model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": plan.model,
        "CLAUDE_CODE_SUBAGENT_MODEL": plan.model,
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(plan.max_tokens),
        "MAX_THINKING_TOKENS": "0",
        "MCP_TOOL_TIMEOUT": str(plan.seconds * 1000),
    }


def launcher_text(binary: Path, names: tuple[str, ...]) -> str:
    """The launcher: ``env -i``, the names it passes on, the binary. The values are never in the
    file — the token is passed by name, so the folder holds no secret."""
    passed = " ".join(f'{name}="${{{name}}}"' for name in names)
    return (
        "#!/bin/sh\n"
        "# The launcher of a guided session of ELA (M14.3, ADR 0060): written and checked by ELA.\n"
        f'exec /usr/bin/env -i {passed} {shlex.quote(str(binary))} "$@"\n'
    )


@dataclass(slots=True)
class _Session:
    """One running session: its client, its process, and what it has said so far."""

    client: ClaudeSDKClient
    folder: Path
    pid: int | None = None
    version: str | None = None
    denials: int = 0
    stopping: bool = False
    result: ResultMessage | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


class ClaudeAgentSession:
    """Implements :class:`~ela.ports.AgentSession` with the Agent SDK and its binary."""

    def __init__(
        self,
        root: Path,
        *,
        binary: Path | None = None,
        grace: float = GRACE_SECONDS,
    ) -> None:
        self._root = root
        self._binary = bundled_binary() if binary is None else binary
        self._grace = grace
        self._running: dict[StepId, _Session] = {}

    @property
    def tools(self) -> frozenset[str]:
        return TOOLS

    async def ready(self) -> ErrorMetadata | None:
        if not os.access(self._binary, os.X_OK):
            return ErrorMetadata(
                code=GUIDED_NOT_INSTALLED,
                message=f"the binary of the session is not at {self._binary}",
            )
        try:
            self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            return ErrorMetadata(
                code=GUIDED_FOLDER_CHANGED,
                message=f"the folder of the sessions cannot be prepared: {type(error).__name__}",
            )
        return None

    async def running(self, session: StepId) -> bool:
        found = self._running.get(session)
        if found is None or found.pid is None:
            return False
        return _alive(found.pid)

    async def launch(
        self, reservation: Reservation, plan: SessionPlan, host: SessionHost
    ) -> SessionHandle | ErrorMetadata:
        unready = await self.ready()
        if unready is not None:
            return unready
        folder = self._root / str(plan.session)
        environment = closed_environment(plan, folder)
        text = launcher_text(self._binary, (*environment, *SDK_NAMES))
        try:
            folder.mkdir(mode=0o700)
            launcher = folder / LAUNCHER
            launcher.write_text(text, encoding="utf-8")
            launcher.chmod(0o700)
        except OSError as error:
            return ErrorMetadata(
                code=GUIDED_FOLDER_CHANGED,
                message=f"the folder of the session cannot be prepared: {type(error).__name__}",
            )
        changed = _changed(folder, hashlib.sha256(text.encode()).hexdigest())
        if changed is not None:
            shutil.rmtree(folder, ignore_errors=True)
            return ErrorMetadata(code=GUIDED_FOLDER_CHANGED, message=changed)
        client = ClaudeSDKClient(options=_options(reservation, plan, host, folder, launcher))
        session = _Session(client=client, folder=folder)
        self._running[plan.session] = session
        try:
            await client.connect()
        except Exception as error:
            self._running.pop(plan.session, None)
            shutil.rmtree(folder, ignore_errors=True)
            return ErrorMetadata(
                code=GUIDED_NOT_INSTALLED,
                message=f"the session did not start: {type(error).__name__}",
            )
        session.pid = _pid(client)
        if session.pid is not None:
            try:
                (folder / PID).write_text(f"{session.pid}\n", encoding="utf-8")
            except OSError as error:
                # A process the start-up after a crash could not find is not launched.
                await self._finish(session)
                self._running.pop(plan.session, None)
                shutil.rmtree(folder, ignore_errors=True)
                return ErrorMetadata(
                    code=GUIDED_FOLDER_CHANGED,
                    message=f"the pid of the session cannot be written: {type(error).__name__}",
                )
        ended = asyncio.ensure_future(self._run(plan, host, session))

        async def interrupt() -> None:
            await self._interrupt(session)

        return SessionHandle(ended=ended, interrupt=interrupt)

    async def sweep(self) -> int:
        """At start-up no session has a right to live — its gateway was the process that is
        starting again —: every folder under the sessions' is deleted, and a process whose pid it
        holds is killed first, with ``SIGKILL``, **if it is still the session's binary**. A pid is
        a number the kernel gives again, and after a crash and a restart it can name another
        program: that one is left alone. Answers how many folders it deleted."""
        if not self._root.is_dir():
            return 0
        swept = 0
        for folder in sorted(self._root.iterdir()):
            if not folder.is_dir() or folder.is_symlink():
                continue
            pid = _written_pid(folder)
            if pid is not None and _alive(pid) and await self._is_the_binary(pid):
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
            shutil.rmtree(folder, ignore_errors=True)
            swept += 1
        return swept

    async def _is_the_binary(self, pid: int) -> bool:
        """Whether ``pid`` runs the session's binary: its command, read with ``ps``, starts with
        the binary's path — the launcher ``exec``-s it, so ``claude`` is the process's command."""
        reading = await asyncio.create_subprocess_exec(
            PS,
            "-o",
            "command=",
            "-p",
            str(pid),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        said, _ = await reading.communicate()
        return said.decode(errors="replace").strip().startswith(str(self._binary))

    async def _run(self, plan: SessionPlan, host: SessionHost, session: _Session) -> SessionEnd:
        client = session.client
        try:
            await client.query(plan.goal)
            async for message in client.receive_response():
                if isinstance(message, SystemMessage):
                    await self._said(message, host, session)
                elif isinstance(message, ResultMessage):
                    session.result = message
        except Exception:  # the process went away under the reader: the end says it
            pass
        finally:
            session.done.set()
        await self._finish(session)
        self._running.pop(plan.session, None)
        closed = session.pid is None or not _alive(session.pid)
        shutil.rmtree(session.folder, ignore_errors=True)
        result = session.result
        return SessionEnd(
            text="" if result is None or result.result is None else result.result,
            subtype="killed" if result is None else result.subtype,
            reported_cost=(
                None
                if result is None or result.total_cost_usd is None
                else str(result.total_cost_usd)
            ),
            version=session.version,
            denials=session.denials
            + (0 if result is None else len(result.permission_denials or ())),
            closed=closed,
        )

    async def _said(self, message: SystemMessage, host: SessionHost, session: _Session) -> None:
        if message.subtype == "init":
            data: Mapping[str, Any] = message.data
            version = data.get("claude_code_version")
            session.version = version if isinstance(version, str) else None
            tools = data.get("tools")
            listed = tuple(str(one) for one in tools) if isinstance(tools, list) else ()
            if await host.started(listed) is not None:
                asyncio.ensure_future(self._interrupt(session))
        elif message.subtype == "permission_denied":
            session.denials += 1
            await host.asked()

    async def _interrupt(self, session: _Session) -> None:
        """The interrupt first, then the end of the input; ``SIGKILL`` after the grace."""
        if session.stopping:
            return
        session.stopping = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(session.client.interrupt(), self._grace)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(session.done.wait(), self._grace)
        await self._finish(session)

    async def _finish(self, session: _Session) -> None:
        transport = getattr(session.client, "_transport", None)
        with contextlib.suppress(Exception):
            if transport is not None:
                await transport.end_input()
        if session.pid is not None:
            deadline = asyncio.get_running_loop().time() + self._grace
            while _alive(session.pid) and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.05)
            if _alive(session.pid):
                with contextlib.suppress(ProcessLookupError):
                    os.kill(session.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            await session.client.disconnect()


def _options(
    reservation: Reservation,
    plan: SessionPlan,
    host: SessionHost,
    folder: Path,
    launcher: Path,
) -> ClaudeAgentOptions:
    notes = ToolAnnotations(maxResultSizeChars=RESULT_CHARS)

    async def gesture(name: str, arguments: JsonMapping) -> dict[str, Any]:
        text = await host.gesture(name, arguments)
        return {"content": [{"type": "text", "text": text}]}

    @tool("read", plan.read_description, READ_SCHEMA, annotations=notes)
    async def read(arguments: dict[str, Any]) -> dict[str, Any]:
        return await gesture("read", arguments)

    @tool("act", plan.act_description, ACT_SCHEMA, annotations=notes)
    async def act(arguments: dict[str, Any]) -> dict[str, Any]:
        return await gesture("act", arguments)

    return ClaudeAgentOptions(
        mcp_servers={SERVER: create_sdk_mcp_server(name=SERVER, version="1", tools=[read, act])},
        tools=[],
        allowed_tools=sorted(TOOLS),
        permission_mode="dontAsk",
        system_prompt=plan.instructions,
        model=plan.model,
        cwd=str(folder),
        env=closed_environment(plan, folder),
        setting_sources=[],
        strict_mcp_config=True,
        max_budget_usd=float(reservation.amount),
        cli_path=str(launcher),
        extra_args={
            "bare": None,
            "permission-prompts": "none",
            "no-session-persistence": None,
            "disable-slash-commands": None,
        },
    )


def _changed(folder: Path, fingerprint: str) -> str | None:
    """Why the folder is not exactly what ELA wrote, or ``None``: the launcher, with the fingerprint
    ELA wrote — and, once the process has started, its pid, a number and nothing else."""
    found = sorted(path.name for path in folder.iterdir())
    if found not in ([LAUNCHER], sorted([LAUNCHER, PID])):
        return f"the folder of the session holds {len(found)} entries, not ELA's own files"
    written = hashlib.sha256((folder / LAUNCHER).read_bytes()).hexdigest()
    if written != fingerprint:
        return "the launcher of the session is not the one ELA wrote"
    if PID in found and _written_pid(folder) is None:
        return "the pid in the folder of the session is not the one ELA wrote"
    return None


def _written_pid(folder: Path) -> int | None:
    """The pid ELA wrote in a session's folder, or ``None``: no file, or not a number."""
    try:
        said = (folder / PID).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(said) if said.isdigit() else None


def _pid(client: ClaudeSDKClient) -> int | None:
    """The process of the session, read from the SDK's transport (pinned in the lock)."""
    process = getattr(getattr(client, "_transport", None), "_process", None)
    pid = getattr(process, "pid", None)
    return pid if isinstance(pid, int) else None


def _alive(pid: int) -> bool:
    """Whether the kernel still knows ``pid`` as a process that has not ended."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
