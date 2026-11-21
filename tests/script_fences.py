"""**A test of a script never reaches the real world, and no test reaches the configuration of
whoever runs the suite** (M13.17b): the fences of one rule, installed once per process by
``tests/conftest.py`` in ``pytest_configure``, before any fixture of any scope.

**The rule.** A launch of a program, or the opening of a connection, or the resolution of a name,
whose stack — in the thread that does it — holds a frame of a file inside ``scripts/`` **fails
loudly instead of happening**, with a ``BaseException``: a script's ``except Exception`` cannot
turn it into a step that merely failed. The script is recognised **at the moment of the call, from
the file of the frame, resolved**: no prefix of a name, no list — a new file of ``scripts/`` is
covered the day it is there, and a copy elsewhere is not.

1. **The launches**, in front of every way of starting a program the repository names
   (``SPAWNING_CALLS`` of ``tests/architecture/rules.py``): ``subprocess.Popen._execute_child``,
   the functions of ``os`` this system has, ``_posixsubprocess.fork_exec``. **One judgement per
   launch**: what a launch let through calls inside itself is not judged again, and the pass closes
   even when the launch raises.
2. **The connections**, at the point every client of ``NETWORK_CLIENTS`` passes through — measured
   (M13.17b, «Le sonde»): ``socket.socket.connect`` and ``connect_ex``, and the ``sock_connect`` of
   asyncio's proactor loop, which on Windows does not pass there. **The resolution of a name** that
   is not of this machine, at ``socket.getaddrinfo``, before the resolver is asked (answer 37). And
   **the transports of ``httpx`` and ``httpx2`` are unusable for every test** — the refusal of a
   test without a script on its stack is the one of M7.1, ``AssertionError(NO_NETWORK)``.
3. **The environment** (answers 39, 54 and 56): the ``ELA_`` variables of the process are taken
   away; **the working folder and the home of the process are folders of the test** —
   ``PLAYWRIGHT_BROWSERS_PATH`` pinned on the real registry first, where the browsers are —; and a
   load of settings that would read a ``.env`` outside the test's folders fails loudly, in every
   scope (:class:`DotenvOutsideTheTest`).

**What is let through names what it lets through, never a whole test** (decision 6): **derived** — a
program that, resolved as the system would launch it, is a file inside pytest's temporary folder;
a connection to a listener this process bound —; or **named** by the test with the fixture
``script_may`` of ``tests/conftest.py``, exactly, with its reason. A named exemption the test does
not use fails it.

**What the rule does not see**, by name (M13.17b, «La proposta», §8): a launch or a connection from
a thread or an executor whose target is a library's — the rule looks at the thread that launches —;
the driver of Playwright started from ``sync_playwright``'s greenlet, or from a loop the script did
not start; the resolution of a name in asyncio's executor; a child process; what launched programs
do by themselves. And the other doors of the resolver (``gethostbyname`` and its family): no client
of ``NETWORK_CLIENTS`` passes there, and a test says so.
"""

from __future__ import annotations

import functools
import inspect
import ipaddress
import os
import shutil
import socket
import subprocess
import sys
import threading
import weakref
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any, Final

from tests.architecture.rules import SPAWNING_CALLS

ROOT: Final = Path(__file__).resolve().parents[1]
SCRIPTS: Final = os.path.realpath(ROOT / "scripts")
"""The folder of the scripts, resolved: a frame of a file inside it is a frame of a script."""
GUARDED: Final = "_ela_guarded_against_a_script"
"""The attribute every function a fence wraps carries: what says it is wrapped."""
NO_NETWORK: Final = "a test tried to open a network connection"
"""The refusal of M7.1, for a test without a script on its stack: the same words as ever."""
OS_LAUNCHERS: Final[tuple[str, ...]] = tuple(
    sorted(
        name.removeprefix("os.")
        for name in SPAWNING_CALLS
        if name.startswith("os.") and hasattr(os, name.removeprefix("os."))
    )
)
"""The functions of ``os`` that start a program, of the repository's list, that this system has."""
PLAYWRIGHT_BROWSERS: Final = "PLAYWRIGHT_BROWSERS_PATH"
WORKING_FOLDER: Final = "cartella-di-lavoro"
HOME: Final = "casa"


class ReachedOutFromAScript(BaseException):  # noqa: N818 — what happened, not an «Error»
    """A script of ``scripts/`` reached for the real world in a test that had not replaced it."""


class LaunchFromAScript(ReachedOutFromAScript):
    """It was about to start a program."""


class ConnectionFromAScript(ReachedOutFromAScript):
    """It was about to open a connection, or to ask the resolver for a name."""


class DotenvOutsideTheTest(BaseException):  # noqa: N818 — what happened, not an «Error»
    """A load of settings would have read a ``.env`` outside the test's folders."""


@dataclass
class Named:
    """What a test lets a script do, exactly and with its reason (decision 6 (b), answer 36): a
    program with its arguments, a line of the shell, a listener. An entry serves as many times as
    the test needs; one never used fails the test that passed."""

    launches: dict[tuple[str, ...], str] = field(default_factory=dict)
    lines: dict[str, str] = field(default_factory=dict)
    listeners: dict[tuple[str, int], str] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)

    def launch(self, *argv: str, why: str) -> None:
        """The program exactly as the script passes it, argument by argument."""
        assert argv and why.strip(), "a program and a reason"
        self.launches[tuple(argv)] = why

    def run(self, line: str, why: str) -> None:
        """A line of the shell, character by character: naming ``/bin/sh`` would let any line
        pass."""
        assert line and why.strip(), "a line and a reason"
        self.lines[line] = why

    def connect(self, host: str, port: int, why: str) -> None:
        """A listener, by its address and port — never a name (answer 37)."""
        ipaddress.ip_address(host)
        assert why.strip(), "a reason"
        self.listeners[(host, port)] = why

    def names(self) -> list[str]:
        return [
            *(f"launch {list(argv)!r}" for argv in self.launches),
            *(f"run {line!r}" for line in self.lines),
            *(f"connect {host}:{port}" for host, port in self.listeners),
        ]

    def unused(self) -> list[str]:
        return [name for name in self.names() if name not in self.used]


def named_for_a_test(passed: Callable[[], bool]) -> Iterator[Named]:
    """What the fixture ``script_may`` is, while its test runs: the list of what the test names,
    open from here to the closing — which pytest runs before the closing of a fixture of a module —
    and **an entry never used fails the test**, only if it passed (decision 6 (c)): one that fell
    keeps its one failure."""
    named = Named()
    STATE.named = named
    try:
        yield named
    finally:
        STATE.named = None
    unused = named.unused()
    if unused and passed():
        raise AssertionError(
            f"named for a script and never used: {unused} — an exemption that lets nothing pass "
            "has become false (M13.17b, decision 6 (c))"
        )


class _State:
    """What the fences know of this process: pytest's temporary folder, the listeners it bound,
    what the running test named, and the launches being let through in each thread."""

    def __init__(self) -> None:
        self.base: Path | None = None
        self.named: Named | None = None
        self.bound: weakref.WeakSet[socket.socket] = weakref.WeakSet()
        self.passing = threading.local()


STATE: Final = _State()


# ----------------------------------------------------------------------------------------
# The rule
# ----------------------------------------------------------------------------------------


def from_a_script(frame: FrameType | None) -> str | None:
    """The file of the nearest frame of a script on the stack of ``frame``, or ``None``."""
    inside = SCRIPTS + os.sep
    while frame is not None:
        name = frame.f_code.co_filename
        if os.path.isabs(name) and os.path.realpath(name).startswith(inside):
            return name
        frame = frame.f_back
    return None


def _depth() -> int:
    return getattr(STATE.passing, "depth", 0)


def _passing(step: int) -> None:
    STATE.passing.depth = _depth() + step


def _named() -> str:
    named = STATE.named
    return "nothing" if named is None or not named.names() else "; ".join(named.names())


# ----------------------------------------------------------------------------------------
# The first fence: the launches
# ----------------------------------------------------------------------------------------


def resolved_program(
    chosen: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    env: Mapping[str, str] | None,
    cwd: str | bytes | os.PathLike[str] | os.PathLike[bytes] | None,
    *,
    search: bool = True,
) -> Path | None:
    """The file the system would launch for ``chosen``, or ``None`` when that cannot be said for
    sure (answer 35 (b)): a bare name looked up in the ``PATH`` of ``env`` — the child's
    environment, or this process's when ``env`` is ``None`` —, a relative path against the
    child's folder. **On Windows only an absolute path with its extension is sure**:
    ``CreateProcess`` does not look in the ``PATH`` alone, resolves a relative path against other
    folders than the child's, and appends ``.exe`` to a name without one."""
    program = os.fsdecode(chosen)
    if sys.platform == "win32":
        sure = os.path.isabs(program) and bool(os.path.splitext(program)[1])
        return Path(os.path.realpath(program)) if sure else None
    if os.path.isabs(program):
        return Path(os.path.realpath(program))
    if os.sep in program or (os.altsep is not None and os.altsep in program):
        folder = os.fsdecode(cwd) if cwd is not None else os.getcwd()
        return Path(os.path.realpath(os.path.join(folder, program)))
    if not search:
        return None
    environment = os.environ if env is None else env
    found = shutil.which(program, path=environment.get("PATH", os.defpath))
    return Path(os.path.realpath(found)) if found is not None and os.path.isabs(found) else None


def derived(program: Path | None) -> bool:
    """Whether ``program`` is a file inside pytest's temporary folder: the fake the test put
    there."""
    base = STATE.base
    return (
        program is not None
        and base is not None
        and program.is_relative_to(base)
        and program.is_file()
    )


def judge_launch(
    script: str, *, argv: Iterable[Any] | None, line: str | None, program: Path | None
) -> None:
    """Let the launch through if it is derived or named; otherwise refuse it, loudly."""
    if line is None and derived(program):
        return
    named = STATE.named
    words = None if argv is None else tuple(os.fsdecode(one) for one in argv)
    if named is not None:
        if line is not None and line in named.lines:
            named.used.add(f"run {line!r}")
            return
        if words is not None and words in named.launches:
            named.used.add(f"launch {list(words)!r}")
            return
    what = f"the line {line!r}" if line is not None else f"{list(words or ())!r}"
    raise LaunchFromAScript(
        f"{Path(script).name} launched a real process in a test that had not replaced the launch: "
        f"{what}. Replace the launch with a double, put a fake inside the test's temporary folder, "
        f"or name it with the fixture script_may and its reason. The test named: {_named()}."
    )


def _popen(real: Callable[..., Any]) -> Callable[..., Any]:
    signature = inspect.signature(real)

    def describe(args: tuple[Any, ...], named: dict[str, Any]) -> tuple[Any, ...]:
        bound = signature.bind(*args, **named).arguments
        given, shell = bound["args"], bound.get("shell", False)
        if shell:
            line = given if isinstance(given, (str, bytes)) else next(iter(given))
            return None, os.fsdecode(line), None
        argv = [given] if isinstance(given, (str, bytes, os.PathLike)) else list(given)
        chosen = bound.get("executable") or argv[0]
        return argv, None, resolved_program(chosen, bound.get("env"), bound.get("cwd"))

    return _guarded_launch(real, describe)


def _of_os(name: str) -> Callable[[tuple[Any, ...], dict[str, Any]], tuple[Any, ...]]:
    """How each launcher of ``os`` says what it starts."""
    if name in ("system", "popen"):
        return lambda args, named: (None, os.fsdecode(args[0]), None)
    if name in ("fork", "forkpty"):
        return lambda args, named: ((), None, None)
    if name.startswith("posix_spawn"):
        search = name == "posix_spawnp"

        def spawned(args: tuple[Any, ...], named: dict[str, Any]) -> tuple[Any, ...]:
            # posix_spawnp looks in the PATH of this process, as execvp does: not in ``env``'s
            return list(args[1]), None, resolved_program(args[0], None, None, search=search)

        return spawned
    kind, tail = ("exec", name[4:]) if name.startswith("exec") else ("spawn", name[5:])
    first = 0 if kind == "exec" else 1

    def executed(args: tuple[Any, ...], named: dict[str, Any]) -> tuple[Any, ...]:
        rest = list(args[first + 1 :])
        env = rest.pop() if "e" in tail and rest else None
        argv = rest[0] if "v" in tail and rest else rest
        program = resolved_program(args[first], env, None, search="p" in tail)
        return list(argv), None, program

    return executed


def fork_exec_described(args: tuple[Any, ...], named: dict[str, Any]) -> tuple[Any, ...]:
    """``_posixsubprocess.fork_exec(args, executable_list, close_fds, pass_fds, cwd, env, …)``:
    the first program of the list, a relative one against the child's folder."""
    program = resolved_program(args[1][0], None, args[4]) if args[1] else None
    return list(args[0]), None, program


def create_process_described(args: tuple[Any, ...], named: dict[str, Any]) -> tuple[Any, ...]:
    """``_winapi.CreateProcess(application_name, command_line, …)``: the program only when the
    application is named by its absolute path — a command line is never read."""
    program = resolved_program(args[0], None, None, search=False) if args[0] else None
    return [args[1]], None, program


def _guarded_launch(
    real: Callable[..., Any],
    describe: Callable[[tuple[Any, ...], dict[str, Any]], tuple[Any, ...]],
) -> Callable[..., Any]:
    """``real``, with the judgement in front of it — once per launch."""

    @functools.wraps(real)
    def check(*args: Any, **named: Any) -> Any:
        if _depth():
            return real(*args, **named)
        script = from_a_script(sys._getframe(1))
        if script is not None:
            argv, line, program = describe(args, named)
            judge_launch(script, argv=argv, line=line, program=program)
        _passing(+1)
        try:
            return real(*args, **named)
        finally:
            _passing(-1)

    setattr(check, GUARDED, True)
    return check


# ----------------------------------------------------------------------------------------
# The second fence: the connections and the resolution of a name
# ----------------------------------------------------------------------------------------


def _host(text: Any) -> str | None:
    try:
        return str(ipaddress.ip_address(os.fsdecode(text).split("%", 1)[0]))
    except ValueError:
        return None


def of_this_machine(host: Any) -> bool:
    """A literal address, ``localhost``, or no name at all (answer 37)."""
    if host is None:
        return True
    text = os.fsdecode(host)
    return text in ("", "localhost") or _host(text) is not None


def ours(sock: socket.socket, address: Any) -> bool:
    """Whether ``address`` is a listener this process bound and still holds: the same address and
    the same port, and nothing more — ``::1`` is not ``127.0.0.1``, and a listener on every
    interface is not one on an address (M13.17b, «La proposta», §4)."""
    if sock.family == getattr(socket, "AF_UNIX", None):
        for one in list(STATE.bound):
            try:
                if one.fileno() != -1 and one.getsockname() == address:
                    return True
            except OSError:
                continue
        return False
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    host = _host(address[0])
    if host is None:
        return False
    for one in list(STATE.bound):
        if one.fileno() == -1 or one.family != sock.family:
            continue
        try:
            name = one.getsockname()
        except OSError:
            continue
        if _host(name[0]) == host and name[1] == address[1]:
            return True
    return False


def judge_connection(script: str, sock: socket.socket, address: Any) -> None:
    if ours(sock, address):
        return
    named = STATE.named
    if named is not None and isinstance(address, tuple) and len(address) >= 2:
        key = (_host(address[0]) or "", address[1])
        if key in named.listeners:
            named.used.add(f"connect {key[0]}:{key[1]}")
            return
    raise ConnectionFromAScript(
        f"{Path(script).name} opened a connection to {address!r} in a test that had not replaced "
        f"it. Replace the client with a double, point it at a listener this process bound, or "
        f"name the listener with the fixture script_may and its reason. The test named: "
        f"{_named()}."
    )


def _guarded_connect(real: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(real)
    def connect(self: socket.socket, address: Any) -> Any:
        script = from_a_script(sys._getframe(1))
        if script is not None:
            judge_connection(script, self, address)
        return real(self, address)

    setattr(connect, GUARDED, True)
    return connect


def _guarded_sock_connect(real: Callable[..., Any]) -> Callable[..., Any]:
    """The proactor's own door (Windows), where ``socket.connect`` is not passed."""

    @functools.wraps(real)
    async def sock_connect(self: Any, sock: socket.socket, address: Any) -> Any:
        script = from_a_script(sys._getframe(1))
        if script is not None:
            judge_connection(script, sock, address)
        return await real(self, sock, address)

    setattr(sock_connect, GUARDED, True)
    return sock_connect


def _guarded_getaddrinfo(real: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(real)
    def getaddrinfo(host: Any, *args: Any, **named: Any) -> Any:
        if not of_this_machine(host):
            script = from_a_script(sys._getframe(1))
            if script is not None:
                raise ConnectionFromAScript(
                    f"{Path(script).name} asked the resolver for {os.fsdecode(host)!r} in a "
                    "test: a name that is not of this machine is never resolved for a script. "
                    "Point the script at an address of a listener of the test, or replace its "
                    "client."
                )
        return real(host, *args, **named)

    setattr(getaddrinfo, GUARDED, True)
    return getaddrinfo


def _guarded_bind(real: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(real)
    def bind(self: socket.socket, address: Any) -> Any:
        done = real(self, address)
        STATE.bound.add(self)
        return done

    setattr(bind, GUARDED, True)
    return bind


def refuse_the_network(*args: Any, **named: Any) -> Any:
    """The transports of ``httpx`` and ``httpx2``, for every test (M7.1, answer 34): a script on
    the stack has its own refusal, every other test the one of ever."""
    script = from_a_script(sys._getframe(1))
    if script is not None:
        request = args[1] if len(args) > 1 else named.get("request")
        what = f"{request.method} {request.url}" if hasattr(request, "url") else repr(request)
        raise ConnectionFromAScript(
            f"{Path(script).name} sent a request with an HTTP transport in a test: {what}. "
            "Replace the client with a double: no transport of httpx is let through, named or "
            f"not. The test named: {_named()}."
        )
    raise AssertionError(NO_NETWORK)


setattr(refuse_the_network, GUARDED, True)


# ----------------------------------------------------------------------------------------
# The third fence: the environment
# ----------------------------------------------------------------------------------------


def playwright_registry(environment: Mapping[str, str], home: Path, system: str) -> Path | None:
    """Where Playwright looks for its browsers when nothing is declared — as its driver says it
    (``coreBundle.js``, ``computeDefaultCacheDirectory``): under the home on a Mac and on Linux,
    under ``LOCALAPPDATA`` on Windows, which the fence does not move."""
    if system == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    if system.startswith("linux"):
        return Path(environment.get("XDG_CACHE_HOME") or home / ".cache") / "ms-playwright"
    return None


def pin_the_browsers(environment: MutableMapping[str, str], home: Path, system: str) -> None:
    """``PLAYWRIGHT_BROWSERS_PATH`` written on the registry where the browsers are, **before the
    home moves** — unless somebody wrote it already."""
    if PLAYWRIGHT_BROWSERS not in environment:
        registry = playwright_registry(environment, home, system)
        if registry is not None:
            environment[PLAYWRIGHT_BROWSERS] = str(registry)


def inside_the_test(path: Path) -> bool:
    base = STATE.base
    return base is not None and path.resolve().is_relative_to(base)


def _guarded_dotenv(real: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(real)
    def read(self: Any) -> Any:
        files = self.env_file
        if files is not None:
            for one in [files] if isinstance(files, (str, os.PathLike)) else files:
                path = Path(one).expanduser().absolute()
                if not inside_the_test(path):
                    raise DotenvOutsideTheTest(
                        f"a load of settings would read {path}, outside the test's folders: the "
                        "suite reads no .env of whoever runs it. Load in the test's folder "
                        "(tests/composition/support.py, _only_the_declared_environment), or pass "
                        "_env_file=None."
                    )
        return real(self)

    setattr(read, GUARDED, True)
    return read


def cleared(environment: MutableMapping[str, str]) -> list[str]:
    """Every ``ELA_`` variable taken away from ``environment``: their names."""
    names = sorted(name for name in environment if name.startswith("ELA_"))
    for name in names:
        del environment[name]
    return names


def settle(base: Path) -> None:
    """The environment of this process, once, at its configuration: no ``ELA_``, the browsers
    where they are, and a home of the test's."""
    STATE.base = base.resolve()
    cleared(os.environ)
    pin_the_browsers(os.environ, Path.home(), sys.platform)
    # The variant «casa ferma» of the observation (decision 82 (i) of the branch
    # m13.11-il-browser-sul-pc), on the branch diag-m13.11-osservazione only, which never enters
    # main: the home stays where it is; the folder of work moves as always.
    if os.environ.get("DIAG_CASA_FERMA") == "1":
        return
    home = STATE.base / HOME
    home.mkdir(exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)


def work_in_the_test_s_folder() -> None:
    """The folder of work of this process, a folder of the test's — **once the collection is
    done**, before any fixture: the paths given on the command line are read against the folder
    pytest was started from, by the collection and by the workers of xdist, which start where the
    process that spawns them is. No load of the settings happens at the collection (the count of
    M13.17b, «La conta della risposta 39 (g)»), and one that did would be refused."""
    assert STATE.base is not None, "the fences are installed at the configuration"
    work = STATE.base / WORKING_FOLDER
    work.mkdir(exist_ok=True)
    os.chdir(work)


# ----------------------------------------------------------------------------------------
# The installation
# ----------------------------------------------------------------------------------------


def install(base: Path) -> None:
    """Once per process, before any fixture of any scope: the fences."""
    settle(base)
    popen: Any = subprocess.Popen
    if not getattr(popen._execute_child, GUARDED, False):
        popen._execute_child = _popen(popen._execute_child)
    for name in OS_LAUNCHERS:
        if not getattr(getattr(os, name), GUARDED, False):
            setattr(os, name, _guarded_launch(getattr(os, name), _of_os(name)))
    try:
        import _posixsubprocess  # type: ignore[import-not-found]
    except ImportError:  # Windows: there is none
        pass
    else:
        if not getattr(_posixsubprocess.fork_exec, GUARDED, False):
            _posixsubprocess.fork_exec = _guarded_launch(
                _posixsubprocess.fork_exec, fork_exec_described
            )
    try:
        import _winapi
    except ImportError:  # not Windows
        pass
    else:
        # The door under Popen on Windows, as fork_exec is on POSIX — multiprocessing knocks there
        # directly —; and os.startfile, the shell's ``ShellExecute``, never derived.
        winapi: Any = _winapi
        if not getattr(winapi.CreateProcess, GUARDED, False):
            winapi.CreateProcess = _guarded_launch(winapi.CreateProcess, create_process_described)
        if hasattr(os, "startfile") and not getattr(os.startfile, GUARDED, False):
            os.startfile = _guarded_launch(  # type: ignore[attr-defined,unused-ignore]
                os.startfile,  # type: ignore[attr-defined,unused-ignore]
                lambda args, named: ([os.fsdecode(args[0])], None, None),
            )
    sockets: Any = socket.socket
    for door in ("connect", "connect_ex"):
        if not getattr(getattr(sockets, door), GUARDED, False):
            setattr(sockets, door, _guarded_connect(getattr(sockets, door)))
    if not getattr(sockets.bind, GUARDED, False):
        sockets.bind = _guarded_bind(sockets.bind)
    if not getattr(socket.getaddrinfo, GUARDED, False):
        socket.getaddrinfo = _guarded_getaddrinfo(socket.getaddrinfo)  # type: ignore[assignment]
    from asyncio import proactor_events

    proactor: Any = proactor_events.BaseProactorEventLoop
    if not getattr(proactor.sock_connect, GUARDED, False):
        proactor.sock_connect = _guarded_sock_connect(proactor.sock_connect)
    import httpx
    import httpx2

    for library in (httpx, httpx2):
        library.HTTPTransport.handle_request = refuse_the_network  # type: ignore[method-assign]
        library.AsyncHTTPTransport.handle_async_request = refuse_the_network  # type: ignore[method-assign]
    from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource

    dotenv: Any = DotEnvSettingsSource
    if not getattr(dotenv._read_env_files, GUARDED, False):
        dotenv._read_env_files = _guarded_dotenv(dotenv._read_env_files)
