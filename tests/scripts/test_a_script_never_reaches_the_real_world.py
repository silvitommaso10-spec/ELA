"""**A script of ``scripts/`` never reaches the real world in a test that did not replace it**
(M13.17b): the fences of ``tests/script_fences.py`` — a launch, a connection, the resolution of a
name —, installed once per process by ``tests/conftest.py``, for every script of ``scripts/`` and
not by the prefix of its name.

**Nothing here can reach the real world even with the fences broken** — the run of a mutant
breaks them: a launch finds a fake program first on ``PATH``, in a folder of the test **outside
pytest's temporary folder** (answer 35: one inside it would be let through as derived); a
connection finds a listener the test started **in a child process** — another process, as a
provider and the real ELA are —, which leaves a mark and closes; no name of a real site is
resolved. What would have happened is read from the mark.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests import script_fences
from tests.composition.support import (  # noqa: F401 — it names the scripts of the proofs
    _only_the_declared_environment,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

LISTENER = """
import pathlib, socket, sys
mark = pathlib.Path(sys.argv[1])
listening = socket.socket()
listening.bind(("127.0.0.1", 0))
listening.listen()
print(listening.getsockname()[1], flush=True)
while True:
    connection, _ = listening.accept()
    mark.write_text("arrived", encoding="utf-8")
    connection.close()
"""
"""A listener of another process: whatever connects leaves the mark, and is closed at once."""


def loaded(name: str) -> ModuleType:
    """A script of ``scripts/``, loaded from its file, as its own tests load it."""
    spec = importlib.util.spec_from_file_location(f"_fences_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def outside_pytest(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A folder of the test **outside** ``getbasetemp()`` — and the precondition said, not
    assumed (answer 35 (a))."""
    folder = Path(tempfile.mkdtemp(prefix="ela-finto-"))
    base = tmp_path_factory.getbasetemp().resolve()
    assert not folder.resolve().is_relative_to(base), "the fake must lie outside pytest's folder"
    return folder


@pytest.fixture
def a_fake_ps(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    folder = outside_pytest(tmp_path_factory)
    mark = tmp_path / "ps-started"
    fake = folder / "ps"
    fake.write_text(f"#!/bin/sh\ntouch {mark}\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    yield mark
    shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture(scope="module")
def a_listener_of_another_process(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[int, Path]]:
    mark = tmp_path_factory.mktemp("listener") / "arrived"
    child = subprocess.Popen(  # noqa: S603 — this interpreter, and the listener above
        [sys.executable, "-c", LISTENER, str(mark)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert child.stdout is not None
        yield int(child.stdout.readline()), mark
    finally:
        child.kill()
        child.wait()


def caught(what: Callable[[], Any]) -> BaseException | None:
    """``what()``, and what it raised — a refusal is a ``BaseException``."""
    try:
        what()
    except BaseException as raised:  # noqa: BLE001 — the refusal is one on purpose
        return raised
    return None


# ----------------------------------------------------------------------------------------
# Decision 8 (a): a launch of a script that is not a proof
# ----------------------------------------------------------------------------------------


def test_a_launch_of_a_measure_s_script_is_refused_before_it_starts(a_fake_ps: Path) -> None:
    """``descendants()`` of ``misura_m14_3.py`` launches ``ps`` by name: the fake is first on
    ``PATH``."""
    measure = loaded("misura_m14_3")

    refusal = caught(lambda: measure.descendants(os.getpid()))

    assert not a_fake_ps.exists(), "the script of a measure started a program in a test"
    assert type(refusal).__name__ == "LaunchFromAScript"


# ----------------------------------------------------------------------------------------
# Decision 8 (b): a call to a provider, from a fixture of a module
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def the_gateway_from_a_module_fixture(
    a_listener_of_another_process: tuple[int, Path],
) -> tuple[BaseException | None, Path]:
    """``gateway()`` of ``misura_m14_3.py`` forwards to its upstream — here the listener of
    another process, as the provider is —, called while a fixture of a module is set up: before
    any fixture of a function."""
    from starlette.requests import Request

    port, mark = a_listener_of_another_process
    measure = loaded("misura_m14_3")
    upstream = f"http://127.0.0.1:{port}"
    world = measure.World(token="t" * 43, key="k" * 40, upstream=upstream, browser=None)
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": 10, "messages": []}).encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/messages",
            "query_string": b"",
            "headers": [(b"x-api-key", world.token.encode())],
        },
        receive,
    )
    return caught(lambda: asyncio.run(measure.gateway(world, request))), mark


def test_a_call_to_a_provider_from_a_module_fixture_is_refused(
    the_gateway_from_a_module_fixture: tuple[BaseException | None, Path],
) -> None:
    refusal, mark = the_gateway_from_a_module_fixture

    assert not mark.exists(), "the script of a measure reached a listener from a module fixture"
    assert type(refusal).__name__ == "ConnectionFromAScript"


# ----------------------------------------------------------------------------------------
# Decision 8 (c): a connection with urllib from a script
# ----------------------------------------------------------------------------------------


def test_a_connection_of_urllib_from_a_script_is_refused(
    a_listener_of_another_process: tuple[int, Path],
) -> None:
    """``answers()`` of ``prova_m13_1c_m13_1d_m9_6.py`` opens a site with ``urllib``: here the
    listener of another process, by its address — no name is resolved."""
    from tests.docs.test_prova_eyes import loaded as a_proof  # its siblings hidden while it loads

    port, mark = a_listener_of_another_process
    mark.unlink(missing_ok=True)
    proof = a_proof(SCRIPTS / "prova_m13_1c_m13_1d_m9_6.py")

    refusal = caught(lambda: proof.answers(f"127.0.0.1:{port}"))

    assert not mark.exists(), "the script of a proof reached a listener of another process"
    assert type(refusal).__name__ == "ConnectionFromAScript"


# ----------------------------------------------------------------------------------------
# The rule: a frame of a file inside scripts/, resolved at the moment of the call
# ----------------------------------------------------------------------------------------


def a_script(where: Path) -> Callable[[Callable[[], Any]], Any]:
    """A function whose frame is of the file ``where`` — code compiled with that name, so that the
    rule is tried without writing anything in ``scripts/``: the guard reads the name of the file of
    the frame, and nothing else."""
    namespace: dict[str, Any] = {}
    exec(compile("def walk(what):\n    return what()\n", str(where), "exec"), namespace)  # noqa: S102
    walk: Callable[[Callable[[], Any]], Any] = namespace["walk"]
    return walk


A_SCRIPT = SCRIPTS / "a_script_that_is_not_there.py"
"""A name of ``scripts/`` that no file has: the rule is the folder, not a list of what is in it."""


def test_any_file_of_the_folder_of_the_scripts_is_a_script_and_a_copy_elsewhere_is_not(
    tmp_path: Path,
) -> None:
    linked = tmp_path / "linked.py"
    linked.symlink_to(SCRIPTS / "prova_m6_3c.py")

    def seen(where: Path) -> str | None:
        return a_script(where)(lambda: script_fences.from_a_script(sys._getframe()))

    assert seen(A_SCRIPT) == str(A_SCRIPT)
    assert seen(tmp_path / "prova_m6_3c.py") is None, "a copy elsewhere is not a script"
    assert seen(linked) == str(linked), "a link to a script is, once resolved"
    assert seen(ROOT / "tests" / "scripts" / "prova_m6_3c.py") is None


def test_the_refusals_are_not_exceptions_a_script_can_swallow() -> None:
    """A script's ``except Exception`` would turn a refusal into a step that merely failed."""
    for refusal in (
        script_fences.ReachedOutFromAScript,
        script_fences.LaunchFromAScript,
        script_fences.ConnectionFromAScript,
        script_fences.DotenvOutsideTheTest,
    ):
        assert issubclass(refusal, BaseException) and not issubclass(refusal, Exception)


# ----------------------------------------------------------------------------------------
# The first fence: the launches (the tests of M13.17, carried here)
# ----------------------------------------------------------------------------------------


@pytest.fixture
def harmless(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: Any) -> Any:
    """A fake ``uv`` first on ``PATH``, **outside pytest's temporary folder** (answer 35), which
    leaves the mark it returns and nothing else."""
    folder = outside_pytest(tmp_path_factory)
    mark = tmp_path / "uv-started"
    fake = folder / "uv"
    fake.write_text(f"#!/bin/sh\ntouch {mark}\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    yield mark
    shutil.rmtree(folder, ignore_errors=True)


def test_a_line_of_the_guide_left_to_the_real_runner_is_refused_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harmless: Path
) -> None:
    from tests.docs.test_prova_eyes import loaded as a_proof

    base = a_proof(SCRIPTS / "prova_m6_3c.py")
    monkeypatch.setattr(base, "ROOT", tmp_path)
    made = tmp_path / "made"

    with pytest.raises(script_fences.LaunchFromAScript, match="prova_m6_3c.py launched a real"):
        base.run(f"touch {made}")
    with pytest.raises(script_fences.LaunchFromAScript):
        base.run(f"touch {made}", 5)
    with pytest.raises(script_fences.LaunchFromAScript):
        base.started(f"touch {made}")
    with pytest.raises(script_fences.LaunchFromAScript):
        base.run("uv run ela status")

    assert not made.exists() and not harmless.exists(), "nothing started"


@pytest.mark.parametrize("name", ["prova_m13_12.py", "prova_m14_2.py"])
def test_a_script_s_own_launch_is_refused_too(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harmless: Path
) -> None:
    """``migrated()`` would read the real ``.env`` and open the real database — here, with the
    fences broken, it would only start the fake ``uv``, which lies outside pytest's folder and so
    is not derived."""
    from tests.docs.test_prova_eyes import loaded as a_proof

    module = a_proof(SCRIPTS / name)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(script_fences.LaunchFromAScript, match=name):
        module.migrated()

    assert not harmless.exists(), "nothing started"


def test_a_launch_that_does_not_come_from_a_script_starts(tmp_path: Path) -> None:
    made = tmp_path / "made"

    subprocess.run(["touch", str(made)], check=True)

    assert made.exists()


def test_a_fake_inside_pytest_s_folder_is_derived_and_starts(tmp_path: Path) -> None:
    """Decision 6 (a): the program the system would launch is a file of the test's temporary
    folder — by its path, by a bare name on the ``PATH`` of the child, by a path relative to the
    child's folder."""
    mark = tmp_path / "started"
    folder = tmp_path / "bin"
    folder.mkdir()
    fake = folder / "finto"
    fake.write_text(f"#!/bin/sh\necho x >> {mark}\n", encoding="utf-8")
    fake.chmod(0o755)
    walk = a_script(A_SCRIPT)
    path = f"{folder}{os.pathsep}{os.environ.get('PATH', '')}"

    walk(lambda: subprocess.run([str(fake)], check=True))
    walk(lambda: subprocess.run(["finto"], env={**os.environ, "PATH": path}, check=True))
    walk(lambda: subprocess.run(["./finto"], cwd=folder, check=True))

    assert mark.read_text(encoding="utf-8").count("x") == 3


def test_a_line_of_the_shell_is_never_derived(tmp_path: Path) -> None:
    fake = tmp_path / "finto"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)

    with pytest.raises(script_fences.LaunchFromAScript, match="the line"):
        a_script(A_SCRIPT)(lambda: subprocess.run(str(fake), shell=True, check=True))  # noqa: S602


def test_a_named_line_launches_and_an_unnamed_one_is_refused_saying_what_was_named(
    tmp_path: Path, script_may: Any
) -> None:
    """Decision 6 (b) and answer 36: the line exactly, as many times as the test needs; and the
    refusal of another says what the test had named."""
    made = tmp_path / "made"
    script_may.run(f"touch {made}", why="the runner of a proof with a line of the shell")
    walk = a_script(A_SCRIPT)

    walk(lambda: subprocess.run(f"touch {made}", shell=True, check=True))  # noqa: S602
    walk(lambda: subprocess.run(f"touch {made}", shell=True, check=True))  # noqa: S602
    with pytest.raises(script_fences.LaunchFromAScript, match=r"The test named: run 'touch"):
        walk(lambda: subprocess.run(f"touch {made}2", shell=True, check=True))  # noqa: S602

    assert made.exists() and not Path(f"{made}2").exists()


def test_the_pass_of_one_launch_closes_even_when_the_launch_raises(
    tmp_path: Path, script_may: Any
) -> None:
    """Answer 36: «one judgement per launch» lets the launcher's own inner calls through — and the
    pass closes when the launch raises, or the next launch would never be judged."""
    missing = str(tmp_path / "not-there")
    script_may.launch(missing, why="a launch that raises")
    made = tmp_path / "made"
    walk = a_script(A_SCRIPT)

    with pytest.raises(FileNotFoundError):
        walk(lambda: subprocess.run([missing], check=True))
    with pytest.raises(script_fences.LaunchFromAScript):
        walk(lambda: subprocess.run(["touch", str(made)], check=True))

    assert not made.exists()


def test_an_exemption_the_test_never_used_fails_it_and_only_if_it_passed() -> None:
    """Decision 6 (c), on the body of ``script_may``: an entry never used is an error at the
    closing of a test that passed, and nothing for one that fell."""
    for passed, fails in ((True, True), (False, False)):
        named = script_fences.named_for_a_test(lambda passed=passed: passed)
        next(named).launch("echo", "never", why="named and never used")
        if fails:
            with pytest.raises(AssertionError, match="never used"):
                next(named, None)
        else:
            assert next(named, None) is None
        assert script_fences.STATE.named is None


def test_every_launcher_the_repository_names_is_guarded() -> None:
    """The list is ``SPAWNING_CALLS`` of ``tests/architecture/rules.py``: on this system its ``os``
    functions, ``subprocess.Popen._execute_child`` and ``_posixsubprocess.fork_exec``; and the
    doors of the other two fences."""
    import _posixsubprocess  # type: ignore[import-not-found]

    from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource

    assert {"system", "popen", "fork", "forkpty", "posix_spawn", "execv", "spawnv"} <= set(
        script_fences.OS_LAUNCHERS
    )
    for name in script_fences.OS_LAUNCHERS:
        assert getattr(getattr(os, name), script_fences.GUARDED, False), name
    for guarded in (
        subprocess.Popen._execute_child,  # type: ignore[attr-defined]
        _posixsubprocess.fork_exec,
        socket.socket.connect,
        socket.socket.connect_ex,
        socket.socket.bind,
        socket.getaddrinfo,
        asyncio.proactor_events.BaseProactorEventLoop.sock_connect,
        DotEnvSettingsSource._read_env_files,
    ):
        assert getattr(guarded, script_fences.GUARDED, False), guarded


def test_a_launch_of_os_from_a_script_is_refused(tmp_path: Path) -> None:
    made = tmp_path / "made"
    walk = a_script(A_SCRIPT)

    with pytest.raises(script_fences.LaunchFromAScript):
        walk(lambda: os.system(f"touch {made}"))  # noqa: S605
    with pytest.raises(script_fences.LaunchFromAScript):
        walk(lambda: os.posix_spawn("/usr/bin/touch", ["touch", str(made)], dict(os.environ)))

    assert not made.exists(), "nothing started"


def test_a_subprocess_of_asyncio_from_a_script_is_refused(tmp_path: Path) -> None:
    made = tmp_path / "made"

    async def touch() -> None:
        process = await asyncio.create_subprocess_exec("touch", str(made))
        await process.wait()

    with pytest.raises(script_fences.LaunchFromAScript):
        a_script(A_SCRIPT)(lambda: asyncio.run(touch()))

    assert not made.exists(), "nothing started"


@pytest.fixture(scope="module")
def walked_in_a_module_fixture(
    tmp_path_factory: pytest.TempPathFactory, a_listener_of_another_process: tuple[int, Path]
) -> tuple[Any, Any, Path]:
    """A fixture of a module that walks a script, as ``real`` of ``test_prova_m13_1e.py`` does: set
    up before any fixture of a function, and under the fences all the same — a launch and a
    connection."""
    made = tmp_path_factory.mktemp("module") / "made"
    port, _ = a_listener_of_another_process
    walk = a_script(A_SCRIPT)
    launched = caught(lambda: walk(lambda: subprocess.run(["touch", str(made)], check=True)))
    connected = caught(lambda: walk(lambda: socket.create_connection(("127.0.0.1", port))))
    return launched, connected, made


def test_a_fixture_of_a_module_that_walks_a_script_is_under_the_fences(
    walked_in_a_module_fixture: tuple[Any, Any, Path],
) -> None:
    launched, connected, made = walked_in_a_module_fixture

    assert isinstance(launched, script_fences.LaunchFromAScript)
    assert isinstance(connected, script_fences.ConnectionFromAScript)
    assert not made.exists(), "nothing started"


# ----------------------------------------------------------------------------------------
# The second fence: every client of NETWORK_CLIENTS, the listeners, the resolution of a name
# ----------------------------------------------------------------------------------------


def _with_socket(port: int) -> None:
    socket.create_connection(("127.0.0.1", port), timeout=5).close()


def _with_http_client(port: int) -> None:
    import http.client

    http.client.HTTPConnection("127.0.0.1", port, timeout=5).request("GET", "/")


def _with_urllib(port: int) -> None:
    import urllib.request

    urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)  # noqa: S310


def _with_httpx(port: int) -> None:
    import httpx

    httpx.get(f"http://127.0.0.1:{port}/", timeout=5)


def _with_httpx2(port: int) -> None:
    import httpx2

    httpx2.get(f"http://127.0.0.1:{port}/", timeout=5)


CLIENTS: dict[str, Callable[[int], None]] = {
    "socket": _with_socket,
    "http.client": _with_http_client,
    "urllib.request": _with_urllib,
    "httpx": _with_httpx,
    "httpx2": _with_httpx2,
}
"""A way to open a connection with each client of ``NETWORK_CLIENTS`` — and ``httpx2``, the one the
vendor's SDK calls with, which the list does not name (M9.2, its note of 2026-11-20)."""


def test_every_client_the_repository_names_is_refused_from_a_script(
    a_listener_of_another_process: tuple[int, Path],
) -> None:
    """The connections are derived from ``NETWORK_CLIENTS`` as the launches from
    ``SPAWNING_CALLS`` (decision 4): a client added to the list without a way here makes this
    speak, and every one of them, from a script, reaches nothing."""
    from tests.architecture.rules import NETWORK_CLIENTS

    port, mark = a_listener_of_another_process
    assert set(CLIENTS) == set(NETWORK_CLIENTS) | {"httpx2"}
    walk = a_script(A_SCRIPT)

    for name, client in CLIENTS.items():
        mark.unlink(missing_ok=True)
        refusal = caught(lambda client=client: walk(lambda: client(port)))
        assert isinstance(refusal, script_fences.ConnectionFromAScript), name
        assert not mark.exists(), name


def test_no_client_of_the_list_asks_the_other_doors_of_the_resolver(
    a_listener_of_another_process: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answer 37: the fence of the resolution is ``getaddrinfo``; ``gethostbyname`` and its family
    are not wrapped, because no client of the list passes there — asked of each, with the name of
    this machine and from the test, where nothing refuses them."""
    port, _ = a_listener_of_another_process
    asked: list[str] = []
    for door in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        real = getattr(socket, door)
        monkeypatch.setattr(
            socket, door, lambda *a, door=door, real=real: (asked.append(door), real(*a))[1]
        )

    for client in CLIENTS.values():
        caught(lambda client=client: client(port))

    assert asked == []


def test_a_listener_this_process_bound_is_derived_and_its_neighbours_are_not() -> None:
    """The same address and the same port: a listener of this process lets a script in; ``::1`` is
    not ``127.0.0.1``, and a listener on every interface is not one on an address."""
    walk = a_script(A_SCRIPT)
    with socket.socket() as mine:
        mine.bind(("127.0.0.1", 0))
        mine.listen()
        port = mine.getsockname()[1]
        walk(lambda: socket.create_connection(("127.0.0.1", port), timeout=5).close())
        if socket.has_ipv6:
            with pytest.raises(script_fences.ConnectionFromAScript):
                walk(lambda: socket.create_connection(("::1", port), timeout=5))
    with socket.socket() as everywhere:
        everywhere.bind(("0.0.0.0", 0))  # noqa: S104 — the test's own, and closed at once
        everywhere.listen()
        port = everywhere.getsockname()[1]
        with pytest.raises(script_fences.ConnectionFromAScript):
            walk(lambda: socket.create_connection(("127.0.0.1", port), timeout=5))


def test_a_named_listener_lets_a_script_connect(
    a_listener_of_another_process: tuple[int, Path], script_may: Any
) -> None:
    port, mark = a_listener_of_another_process
    mark.unlink(missing_ok=True)
    script_may.connect("127.0.0.1", port, why="the listener of the test, by its address")

    a_script(A_SCRIPT)(lambda: socket.create_connection(("127.0.0.1", port), timeout=5).close())

    assert script_fences.STATE.named is not None and script_fences.STATE.named.unused() == []


def test_a_name_of_the_world_is_never_resolved_for_a_script() -> None:
    """Answer 37, on a resolver of the test's: the guarded door refuses before it asks."""
    asked: list[Any] = []

    def resolver(host: Any, *args: Any, **named: Any) -> list[Any]:
        asked.append(host)
        return []

    door = script_fences._guarded_getaddrinfo(resolver)
    walk = a_script(A_SCRIPT)

    with pytest.raises(script_fences.ConnectionFromAScript, match="asked the resolver"):
        walk(lambda: door("a-name-of-the-world.example", 443))
    for of_this_machine in ("localhost", "127.0.0.1", "::1", None):
        walk(lambda host=of_this_machine: door(host, 80))
    door("a-name-of-the-world.example", 443)  # from the test: not the scripts' fence

    assert asked == ["localhost", "127.0.0.1", "::1", None, "a-name-of-the-world.example"]


def test_the_transports_of_httpx_refuse_a_test_with_the_words_of_ever() -> None:
    import httpx

    with pytest.raises(AssertionError, match=script_fences.NO_NETWORK):
        httpx.HTTPTransport().handle_request(httpx.Request("GET", "http://127.0.0.1:9/"))


@pytest.fixture(scope="module")
def a_request_of_httpx_from_a_module_fixture(
    a_listener_of_another_process: tuple[int, Path],
) -> tuple[BaseException | None, Path]:
    """A fixture of a module, **without** a script on its stack, that sends a request with
    ``httpx``: before M13.17b the refusal was a fixture of a function, and this one ran before
    it."""
    import httpx

    port, mark = a_listener_of_another_process
    mark.unlink(missing_ok=True)
    return caught(lambda: httpx.get(f"http://127.0.0.1:{port}/", timeout=5)), mark


def test_the_transports_of_httpx_are_unusable_for_a_fixture_of_a_module_too(
    a_request_of_httpx_from_a_module_fixture: tuple[BaseException | None, Path],
) -> None:
    refusal, mark = a_request_of_httpx_from_a_module_fixture

    assert isinstance(refusal, AssertionError) and script_fences.NO_NETWORK in str(refusal)
    assert not mark.exists()
