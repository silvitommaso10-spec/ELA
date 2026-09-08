"""Architecture rules of ELA as pure functions over a source tree (CLAUDE.md, spec §52).

Every rule takes the root directory of the ``ela`` package (``src/ela``) and returns the
violations it finds; an empty list means the rule holds. The rules read source files with
``ast`` and never import the modules they check, so they run unchanged on a temporary copy
of the tree (see ``test_rules_detect_violations.py``).
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT_PACKAGE = "ela"
STDLIB = frozenset(sys.stdlib_module_names)

#: The only third-party package the domain model may use.
DOMAIN_ALLOWED_EXTERNAL = frozenset({"pydantic"})
#: The only internal module the ports may use.
PORTS_ALLOWED_INTERNAL = f"{ROOT_PACKAGE}.domain"
#: Infrastructure libraries the Core must never import.
INFRA_LIBRARIES = frozenset(
    {
        "anthropic",
        "openai",
        "httpx",
        "sqlalchemy",
        "alembic",
        "aiosqlite",
        "fastapi",
        "typer",
        "uvicorn",
    }
)
#: Top-level packages of ``ela`` allowed to import INFRA_LIBRARIES. ``cli`` joined them in M8.2
#: (ADR 0024 §7): the command line speaks HTTP with ``httpx`` and is written with ``typer``, which
#: makes it the fourth edge — and the rule is about *edges*, not about how many there are.
INFRA_PACKAGES = frozenset({"providers", "infrastructure", "api", "cli"})
#: Core packages that must stay independent from providers and infrastructure.
#: ``routing`` joined them in M7.3 (ADR 0022 §2): the Model Router chooses *between* providers
#: and must not import one — it reaches them through ``ProviderRegistryPort``.
#: ``perception`` joined them in M10.1 (ADR 0028 §1): the Perception Core decides what a reading
#: *means* and must not import the adapter that produces it — it reaches the machine through
#: ``PerceptionProbe``, exactly as the router reaches a provider through a port.
CORE_PACKAGES = ("executive", "tasks", "permissions", "perception", "audit", "routing")
CORE_FORBIDDEN = tuple(f"{ROOT_PACKAGE}.{name}" for name in ("providers", "infrastructure"))
#: Rule 26 (ADR 0022 §2): the tools receive a router, they never build one.
TOOLS_PACKAGE = f"{ROOT_PACKAGE}.tools"
ROUTING_PACKAGE = f"{ROOT_PACKAGE}.routing"
TOOLS_DIR = "tools"
#: The only module allowed to change the state of a Task (ADR 0004).
STATE_MACHINE = Path("tasks") / "state_machine.py"
#: Rule 10 (ADR 0008): only the ``tasks`` package may import the state machine.
STATE_MACHINE_MODULE = f"{ROOT_PACKAGE}.tasks.state_machine"
TASKS_DIR = "tasks"
#: Rule 11 (ADR 0009): the ``TaskEvent`` types that move a step, written only by ``ela.tasks``.
STEP_EVENT_PREFIX = "STEP_"
#: The mapper rehydrates a Task in the state the database holds: exempt from rule 5 (ADR 0006).
PERSISTENCE_MAPPERS = Path("infrastructure") / "persistence" / "mappers.py"
STATE_EXEMPT = frozenset({STATE_MACHINE, PERSISTENCE_MAPPERS})
#: Rule 8 (ADR 0006): the ORM and the domain never meet in one module.
ORM_PACKAGE = "sqlalchemy.orm"
DOMAIN_MODULE = f"{ROOT_PACKAGE}.domain"
#: Rule 9 (ADR 0007): the audit adapter has no way to update or delete, not even raw SQL.
AUDIT_ADAPTER = Path("infrastructure") / "persistence" / "audit_log.py"
MUTATING_NAMES = frozenset({"update", "delete", "merge"})
MUTATING_SQL = re.compile(r"\b(update|delete|replace|drop)\b", re.IGNORECASE)
#: Rule 20 (ADR 0016 §3, ADR 0017 §7): the availability of a node is *derived* from its last
#: heartbeat, never read from the row. Outside ``ela.devices`` — which derives it — and the mapper
#: — which stores and rehydrates it — nobody touches the field at all.
DEVICES_DIR = "devices"
AVAILABILITY_FIELD = "availability"
#: Rule 21 (ADR 0017 §9, ADR 0027): whoever decides goes through ``DeviceRegistry``, not the raw
#: port. **One** exemption, the package that holds the decision. The other two — ``ela.ports``,
#: which *declares* the port and does not import it, and the SQL adapter, which is structural and
#: names the port only in its docstrings — were opened for modules that never knocked, and are
#: withdrawn by ADR 0027: restricting either of them made no rule speak.
DEVICE_REGISTRY_PORT = f"{ROOT_PACKAGE}.ports.DeviceRegistryPort"
DEVICE_PORT_ALLOWED = (f"{ROOT_PACKAGE}.{DEVICES_DIR}",)
#: Rule 30 (ADR 0026 §5): outside ``ela.devices`` nobody builds a ``PlacementDecision`` that
#: names a node. The mirror of rule 12: ``ensure_placed`` checks a claim, and a claim anybody can
#: forge is not checked at all. No exemption — no fake builds one, and M9.1 does not open a door
#: before somebody knocks.
PLACEMENT_MODEL = "PlacementDecision"
PLACEMENT_DEVICE_FIELD = "device"

#: Rule 32 (ADR 0028 §1): ELA touches the operating system in exactly one package. ``ctypes`` and
#: process spawning are how a Python program reaches outside its own runtime, and perception is
#: the first thing in ELA that reads the *machine* rather than the database — one door is easier
#: to guard than a habit, and a second one would have no reason to be found.
PERCEPTION_ADAPTER_DIR = Path("infrastructure") / "perception"
MACHINE_LIBRARIES = frozenset({"ctypes"})
#: Ways to start another process. Two spellings, because the rule is about *reaching outside* and
#: neither spelling is more honest than the other: ``import subprocess`` shows up as an import,
#: while ``asyncio.create_subprocess_exec(...)`` — the one this milestone actually uses — shows up
#: only as a call. A rule that read imports alone would have been a defence that looks active and
#: cannot fire, which is worse than none (ADR 0026 §7).
SPAWNING_MODULES = frozenset({"subprocess"})
SPAWNING_CALLS = frozenset(
    {
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "os.system",
        "os.popen",
        "os.spawnl",
        "os.spawnv",
        "os.execv",
        "os.execvp",
        "os.fork",
        "os.posix_spawn",
    }
)

#: Rule 33 (ADR 0028 §2, extended in M10.3): every helper *child* under the perception adapter
#: imports only the standard library, never ``ela``. What has to be able to die on its own must
#: not carry the Core's import graph with it, and the Core must not be able to reach into it: the
#: two sides agree on a JSON object and nothing else.
#:
#: M10.1 named one file. M10.2 needed no second one — its child is ``screencapture(1)``, Apple's.
#: M10.3 brings a second child of ours (Vision has no Apple CLI), so the rule had to grow, and a
#: hand-written tuple was the wrong way to grow it: a list is a thing somebody forgets to add to,
#: and the rule would go quietly mute on exactly the file that needed it. So the subject is
#: **derived** — a child is a module in this directory that is executable as a script, which is
#: what :data:`MAIN_GUARD` finds.
#:
#: The derivation is self-enforcing, which is why it is trustworthy: the property that makes the
#: rule apply is the same property that makes the child *work*. ``python -m <module>`` runs the
#: body with ``__name__ == "__main__"``, so a child that lost its guard would print nothing, and
#: its adapter would read an empty stdout and report "not observable". You cannot quietly step out
#: of this rule and still have a working helper.
MAIN_GUARD = "__main__"

#: Rule 34 (ADR 0028 §1): the perception adapter reports primitives and never names a domain
#: state. This is what makes the coverage exemption honest instead of promised — no runner has a
#: webcam, so the adapter cannot be covered, and a module that cannot be covered must not decide.
#: An adapter that does not know the words cannot use them wrongly.
PERCEPTION_VOCABULARY = frozenset({"SensorState", "SensorCause", "PermissionState"})

#: Rule 35 (M10.2, ADR 0029 §12): the captured image does not leave the machine. The modules that
#: hold a screen capture name no router, no provider registry and no HTTP client — the sentence
#: this milestone is built on, made a rule instead of a promise. It *can* fire, which is why it
#: is worth having: ``ela.tools.model`` really does import the router, so "a tool imports the
#: router" is legal code in this repository, and writing it in ``screen.py`` is exactly what M10.3
#: will be tempted to do (ADR 0026 §7: a defence that cannot fire is worse than none).
#: M10.3 extends it to the modules that hold the *text* of a capture, and extends it **before**
#: the code that produces that text exists (M10.3 dec. 15). The order is part of the decision: a
#: defence written after the thing it defends has a window in which the thing exists and the
#: defence does not, and in that window review looks at the new code and not at the missing rule.
#: The reason the extension is not optional is the sentence the milestone is built on — *text is
#: easier to send away than a PNG*: an OCR is a few kilobytes of searchable text that fits in a
#: prompt, where the image was an awkward megabyte.
CAPTURE_MODULES = (
    Path("tools") / "screen.py",
    Path("tools") / "captures.py",
    Path("tools") / "screen_text.py",
    PERCEPTION_ADAPTER_DIR / "textrecognition.py",
    PERCEPTION_ADAPTER_DIR / "vision.py",
)

#: M11.1 dec. H: the same rule, over the modules that hold **what ELA says**. The text of a
#: spoken answer is composed from the context of §44 and from the user's own ``Task.goal`` — the
#: very words rule 39 keeps out of an ``AuditEvent`` and a ``ProviderRequest`` — so a module that
#: holds it must not be able to reach a router, a provider registry or an HTTP client either.
#:
#: Extended **before** the code that speaks exists, which is M10.3 dec. 15 applied a second time:
#: a defence written after the thing it defends has a window in which the thing exists and the
#: defence does not.
#:
#: **A separate tuple, and that is the decision.** M11.3 will send ELA's words to a speech
#: provider, and that milestone has to be able to reopen *this* half — with the four answers of
#: §57 in the shape of ADR 0030 §17 — without touching the capture's half by accident. One
#: constant for both would have made relaxing the voice a relaxation of the screen, silently.
#:
#: The name of the rule is now narrower than the rule: it says "capture" and it also holds the
#: voice. Renaming it would touch three ADRs that are immutable, so the name stays and the
#: mismatch is written down instead — the same discipline as M11.1 dec. G, and the same third
#: time that will settle it.
VOICE_MODULES = (
    Path("tools") / "voice.py",
    PERCEPTION_ADAPTER_DIR / "speech.py",
)

#: Rule 40 (M11.1 dec. 7, approved by the user): **the voice writes no file.** ``say`` takes
#: ``-o`` and will happily render to AIFF instead of speaking, so "nothing of what ELA says is
#: kept" is one character away from being false. The decision was the user's — *mai su disco per
#: la voce in uscita* — and a decision that lives only in a document is a decision somebody
#: undoes without noticing.
#:
#: Reads **literals**, not imports, for the reason rule 36 does: a command-line flag is not a
#: symbol, it is a string in an ``argv`` list, and a rule reading imports would be silent on the
#: only code that could break it.
VOICE_OUTPUT_FLAGS = frozenset({"-o", "--output-file", "--file-format", "--data-format"})

#: Rule 36 (M10.3 dec. 3): ELA never reads a window title. ``kCGWindowOwnerName`` and the geometry
#: come free and are *state*; ``kCGWindowName`` costs the same TCC grant as a screenshot and is
#: *content* — a Chrome title carries a URL or an email subject, a TextEdit title a document name.
#:
#: The precedent is ADR 0028 §11, where the probe reads ``CGSessionCopyCurrentDictionary`` **by
#: named key** so the user's full name is never copied along. That discipline stayed a comment,
#: and the ADR itself calls it "one line of code". Here it becomes a rule for the reason ADR 0029
#: §12 gives for rule 35: it *can* fire. The dictionary-reading code now exists in the probe, so
#: reading titles is one string literal away, and it is precisely what the next milestone will be
#: tempted to do.
#:
#: It reads a **literal**, not an import: a CoreFoundation key is not a symbol, it is a string
#: handed to ``CFStringCreateWithCString``, so a rule reading imports would have been silent on
#: the only code that could break it.
WINDOW_TITLE_KEYS = frozenset({"kCGWindowName"})
CAPTURE_FORBIDDEN = frozenset(
    {"ModelRouter", "ModelRouterPort", "ProviderRegistry", "ProviderRegistryPort", "httpx"}
)

#: Rule 38 (M10.4, ADR 0032 §6): *if answering a context question requires a capability, that
#: answer is not context — it is an action*, and it goes through the Executor. The half that
#: reads names lives here; the half that reads imports is import-linter contract 14, because
#: "the composer cannot reach the Guardian" is exactly a forbidden import and does not need an
#: AST walk. This half exists because the other one is not enough: a port arrives through a
#: constructor, so a module can call ``save`` on something it never imported. The import is the
#: door, the call is the handle, and a rule holding only the door would be silent on the code
#: that can really break it — the same reason rule 32 had to read calls and not only imports.
CONTEXT_DIR = "context"
CONTEXT_WRITE_MEMBERS = frozenset(
    {
        "add",
        "add_plan",
        "append",
        "append_event",
        "authorize",
        "consume",
        "decide",
        "execute",
        "grant",
        "register",
        "respond",
        "save",
        "transition",
        "update",
        "verify",
    }
)
"""Every writing member of the closed port vocabulary. Closed because the ports are closed.

Matched **on the receiver too**, and only on ``self.<port>.<member>()``. Three of these names —
``add``, ``append``, ``update`` — are also list, set and dict methods, so a rule that read the
name alone would fire on ``answered.append(source)`` and the only way to satisfy it would be to
write the composer oddly instead of correctly. A rule that makes correct code contort itself
teaches people to work around rules. The receiver is not a loophole either: a composer holds what
it was given as instance attributes, which is the one shape in which it could write at all.
"""

#: Rule 39 (M10.4, ADR 0032 §7): a snapshot is neither recorded nor sent. Two errors, one shape:
#: an ``AuditEvent`` built from a snapshot would fill the chain of §32 with things ELA did not
#: decide (ADR 0028 §10) and would carry ``Task.goal`` into it, which rule 23 keeps out; a
#: ``ProviderRequest`` built from one is the day the context leaves the machine, and that day
#: needs the four answers of §57 written first (ADR 0030 §17) — a closed door, not a note.
#: Read as names and attributes, like rules 34, 35 and 36, so it costs no import-linter contract.
#: It is silent on today's tree, and that silence is asserted: the rule guards a door nobody has
#: walked through yet, which is the only moment at which such a door can still be shut.
CONTEXT_SNAPSHOT = "ContextSnapshot"
CONTEXT_NOT_RECORDED = frozenset({"AuditEvent", "ProviderRequest"})

#: Rule 31 (ADR 0026 §6): the API's token is compared only with ``secrets.compare_digest``.
#: The one mutation of eight the suite did not notice: ``compare_digest`` swapped for ``==``
#: leaves 3551 tests green, because 100% branch coverage proves the line runs and says nothing
#: about how long it takes. A property that cannot be timed without measuring the machine is
#: defended in the shape of the code instead.
SECURITY_MODULE = Path("api") / "security.py"
CONSTANT_TIME_COMPARE = "compare_digest"
TOKEN_NAMES = frozenset({"token", "presented"})

#: Rule 22 (ADR 0017 §6): the orchestrator advises and never commands. A package that cannot
#: reach the Task Engine cannot fail a task because it found no node.
DEVICES_PACKAGE = f"{ROOT_PACKAGE}.{DEVICES_DIR}"
DEVICES_FORBIDDEN = (f"{ROOT_PACKAGE}.{TASKS_DIR}",)
#: Rule 29 (ADR 0025 §4): what a tool produced is the user's content too, and one model of
#: ``ela.api`` carries it out. ``ExecutionResultOut`` lives in ``schemas.py`` because that is
#: where every wire shape of the API is declared, so the single reader is that file.
API_DIR = "api"
OUTPUT_NAME = "output"
OUTPUT_MODEL = "ExecutionResultOut"
OUTPUT_SCHEMAS = Path("api") / "schemas.py"
#: Rule 23 (ADR 0018 §5): the arguments of a step are the user's content (§57). They live in the
#: plan and in the private database; the audit log records the *targets* of a call, never what was
#: passed. With ADR 0018 the arguments became a persisted field read in three places, so the
#: convention of the executor's docstring becomes a rule.
AUDIT_EVENT = "AuditEvent"
ARGUMENTS_NAME = "arguments"

#: Rule 24 (ADR 0020 §11): ``anthropic`` is importable only from ``ela.providers.anthropic``.
#: Rule 3 lets *all* of ``providers``, ``infrastructure`` and ``api`` import an infrastructure
#: library; "one module imports the SDK" (§26, §50) needs its own rule, or it is a sentence in a
#: README. The exemption is a directory, not a name: everything under the adapter may import it.
ANTHROPIC_LIBRARY = "anthropic"
PROVIDERS_DIR = "providers"
PROVIDERS_PACKAGE = f"{ROOT_PACKAGE}.{PROVIDERS_DIR}"
ANTHROPIC_ADAPTER_DIR = Path(PROVIDERS_DIR) / ANTHROPIC_LIBRARY
ANTHROPIC_ADAPTER_MODULE = f"{PROVIDERS_PACKAGE}.{ANTHROPIC_LIBRARY}"

#: Rule 27 (ADR 0023 §12): the concrete implementations are named by the composition root and by
#: nobody else. Rule 4 asks the same question of five packages, because they were the only ones it
#: could be asked of; with a composition root it is asked of everything — ``ela.api`` included,
#: which receives the world already built and does not build it.
COMPOSITION_DIR = "composition"
COMPOSITION_PACKAGE = f"{ROOT_PACKAGE}.{COMPOSITION_DIR}"
CONCRETE_ALLOWED = frozenset({PROVIDERS_DIR, "infrastructure", COMPOSITION_DIR})
#: Rule 19's one exemption (ADR 0015 §9, ADR 0023 §8): the module of the API through which the
#: user answers. Promised when the rule was written, opened now that the code behind it exists.
APPROVAL_RESPONDER = Path("api") / "approvals.py"

#: Rule 28 (ADR 0024 §7): the CLI talks to the ELA that is running, and never becomes a second
#: one. Two clauses inside the package — no module of it names ``build`` or ``Ela``, and only
#: ``cli/serve.py`` may reach ``ela.api`` or the composition root, because starting the process is
#: the one command that is not a call — and one clause outside it: nobody imports ``ela.cli``, a
#: CLI that is imported having become a library without anyone deciding so.
CLI_DIR = "cli"
CLI_PACKAGE = f"{ROOT_PACKAGE}.{CLI_DIR}"
CLI_SERVE = Path(CLI_DIR) / "serve.py"
COMPOSED_NAMES = frozenset({"build", "Ela"})
CLI_FORBIDDEN_INTERNAL = (f"{ROOT_PACKAGE}.api", f"{COMPOSITION_PACKAGE}.root")

#: Rule 25 (ADR 0021 §5): ``ModelProvider.complete`` is called from one module, the tool of
#: ``model.complete``. It is where the user's content leaves this machine (§57), and it may leave
#: only under a decision of the Guardian (§27) — which is a property of *that* module, not of the
#: call. A second caller would be content going out on some other path. The definitions
#: (``ports.py``, the adapter, the fakes) are ``def complete``, not calls, and are not reported.
MODEL_TOOL_MODULE = Path("tools") / "model.py"
COMPLETE_METHOD = "complete"
#: The one homonym: ``TaskEngine.complete`` closes a task (ADR 0008). The exemption is the
#: receiver, an attribute named ``_engine``, and not the module — a field called ``_engine``
#: holding a provider would be reported, and a provider called through any other name is too.
ENGINE_RECEIVERS = frozenset({"_engine"})

#: The in-memory fakes: used by tests only, never by production code (ADR 0005).
TESTING_PACKAGE = f"{ROOT_PACKAGE}.testing"
TESTING_DIR = "testing"
#: What the fakes may import besides the standard library: the domain and the ports, which is
#: what ADR 0002 and contract 5 have always said this rule allows. ``ela.testing`` itself was in
#: the list and no module used it — ``fakes.py`` is one module — so the list said something the
#: documentation never did. Withdrawn by ADR 0027, which closes a doc-vs-code drift rather than a
#: decision: a second module under ``testing/`` will reopen it as an addition, with its reason.
TESTING_ALLOWED_INTERNAL = (f"{ROOT_PACKAGE}.domain", f"{ROOT_PACKAGE}.ports")
#: The only state a Task may be *born* in outside the state machine.
INITIAL_STATE = ("TaskState", "CREATED")
#: Rule 13 (ADR 0010): the permissions package imports the standard library, the domain, the
#: ports, itself and the JSON Schema validator — never a tool, a provider, the engine, the audit.
PERMISSIONS_DIR = "permissions"
PERMISSIONS_PACKAGE = f"{ROOT_PACKAGE}.permissions"
PERMISSIONS_ALLOWED_INTERNAL = (DOMAIN_MODULE, f"{ROOT_PACKAGE}.ports", PERMISSIONS_PACKAGE)
PERMISSIONS_ALLOWED_EXTERNAL = frozenset({"jsonschema"})
#: Rule 12 (ADR 0011): outside the Guardian nobody builds an allowing decision. The fakes may:
#: rule 6 keeps them out of production, and a table-driven fake must be able to answer ALLOWED.
DECISION_MODEL = "PermissionDecision"
DENIED_OUTCOME = ("PermissionOutcome", "DENIED")
DECISION_BUILDERS_EXEMPT = frozenset({PERMISSIONS_DIR, TESTING_DIR})
#: Rule 14 (ADR 0011): outside ``ela.permissions`` nobody calls ``decide`` — only ``authorize``,
#: which writes the audit event. No exemption: the fake *defines* ``decide``, it never calls it.
DECIDE_METHOD = "decide"
#: Rule 15 (ADR 0012): outside ``ela.permissions`` nobody builds an ``Authorization`` or widens one
#: by ``model_copy`` — every production grant is born from ``authorization_from_approval``. The
#: fakes may (rule 6 keeps them out of production); the persistence mapper reads grants back from
#: rows, it does not coin them, and is the one exact-path exemption.
AUTHORIZATION_MODEL = "Authorization"
AUTHORIZATION_WIDENING_FIELDS = frozenset(
    {"approval_id", "task_id", "step_id", "scope", "expires_at", "max_uses", "capability_id"}
)
#: ``ela.testing`` was exempt here too and never coined a grant — the fakes import
#: ``Authorization`` as a type, they do not build one. Withdrawn by ADR 0027; unlike rule 12,
#: whose fake must be able to answer ALLOWED, no fake is the legitimate author of a grant.
AUTHORIZATION_BUILDERS_EXEMPT = frozenset({PERMISSIONS_DIR})
AUTHORIZATION_READER = PERSISTENCE_MAPPERS
#: Rule 16 (ADR 0013): only the executor calls ``Tool.execute``. The exemption is one exact path;
#: a receiver named like a SQLAlchemy session or cursor is SQL's ``execute``, not a tool's — an
#: exemption by name, closed and tested.
EXECUTOR_MODULE = Path("executive") / "executor.py"
EXECUTE_METHOD = "execute"
#: Rule 16 (ADR 0019 §3): ``self._executor.execute(...)`` is the runner driving the executor, not
#: a second place where a tool runs. One receiver name **in one module**: the exemption belongs to
#: the runner, not to the name, so an attribute called ``_executor`` anywhere else does not
#: inherit it (review of M6.3). Everything else called ``.execute(...)`` outside the executor is
#: still reported.
RUNNER_MODULE = Path("executive") / "runner.py"
EXECUTOR_RECEIVERS = frozenset({"_executor"})
#: ``connection`` was in this set and no module ever used it: ADR 0013 §9 wrote three names and
#: the persistence has always executed through ``session`` and ``cursor``. Withdrawn by ADR 0027,
#: with its price written there: the day the persistence executes on a ``connection`` this rule
#: speaks, and reopening the name is one line plus a reason, not an accident.
SQL_EXECUTORS = frozenset({"session", "cursor"})
# Rule 17 (ADR 0014 §9): only the executor completes a step, and only after verification.
COMPLETE_STEP_METHOD = "complete_step"
RESPOND_METHOD = "respond"
# Rule 18 (ADR 0014 §10): the module of the verifiers, and the shared path classification the
# tool and the verifier both use, have no path that writes.
VERIFIERS_MODULE = Path("tools") / "verifiers.py"
PATHS_MODULE = Path("tools") / "paths.py"
READ_ONLY_MODULES = (VERIFIERS_MODULE, PATHS_MODULE)
OPENERS = frozenset({"open", "fdopen"})
WRITING_OPEN_MODES = frozenset("wax+")
WRITING_OPEN_FLAGS = frozenset({"O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND", "O_EXCL"})
WRITING_CALLS = frozenset(
    {
        "write",
        "writelines",
        "unlink",
        "remove",
        "removedirs",
        "rename",
        "replace",
        "rmdir",
        "mkdir",
        "makedirs",
        "write_text",
        "write_bytes",
        "touch",
        "chmod",
        "chown",
        "symlink",
        "link",
        "truncate",
        "ftruncate",
        "utime",
        "rmtree",
        "copy",
        "copyfile",
        "copytree",
        "move",
    }
)
SHUTIL = "shutil"


@dataclass(frozen=True)
class Violation:
    rule: str
    module: str
    imported: str
    line: int

    def __str__(self) -> str:
        return f"[{self.rule}] {self.module}:{self.line} imports {self.imported}"


def top_level_modules(pkg_root: Path) -> set[str]:
    """Dotted names of the packages and modules directly under ``pkg_root``."""
    names: set[str] = set()
    for path in pkg_root.iterdir():
        if path.is_dir() and (path / "__init__.py").is_file():
            names.add(f"{ROOT_PACKAGE}.{path.name}")
        elif path.suffix == ".py" and path.name != "__init__.py":
            names.add(f"{ROOT_PACKAGE}.{path.stem}")
    return names


def provider_modules_outside_the_adapter(pkg_root: Path) -> set[str]:
    """The modules under ``ela.providers`` that are not the Anthropic adapter (rule 24).

    Import-linter needs them listed one by one: naming ``ela.providers`` as a source would name
    the adapter too. What this cannot cover — ``ela/providers/__init__.py`` itself — is covered by
    the closed-world rule, which is why every contract has one (``test_import_linter.py``).
    """
    names: set[str] = set()
    for path in (pkg_root / PROVIDERS_DIR).iterdir():
        if path.name == ANTHROPIC_LIBRARY:
            continue
        if path.is_dir() and (path / "__init__.py").is_file():
            names.add(f"{PROVIDERS_PACKAGE}.{path.name}")
        elif path.suffix == ".py" and path.name != "__init__.py":
            names.add(f"{PROVIDERS_PACKAGE}.{path.stem}")
    return names


def module_name(path: Path, pkg_root: Path) -> str:
    parts = list(path.relative_to(pkg_root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join([ROOT_PACKAGE, *parts])


def _source_files(directory: Path) -> Iterator[Path]:
    yield from sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def imported_modules(path: Path, pkg_root: Path) -> list[tuple[str, int]]:
    """Absolute dotted names imported by ``path`` (relative imports resolved), with lines.

    ``from pkg import name`` yields ``pkg.name``: whether ``name`` is a submodule or an
    attribute, the dependency on ``pkg`` is captured by prefix matching in the rules.
    """
    current = module_name(path, pkg_root)
    package = current if path.name == "__init__.py" else current.rpartition(".")[0]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_base(node, package)
            if any(alias.name == "*" for alias in node.names):
                found.append((base, node.lineno))
            else:
                found.extend((f"{base}.{alias.name}", node.lineno) for alias in node.names)
    return found


def _resolve_base(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        assert node.module is not None
        return node.module
    parts = package.split(".")
    ancestor = ".".join(parts[: len(parts) - (node.level - 1)])
    return f"{ancestor}.{node.module}" if node.module else ancestor


def _is_within(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _top_level(module: str) -> str:
    return module.partition(".")[0]


def _violations(
    rule: str,
    files: Iterator[Path],
    pkg_root: Path,
    is_forbidden: Callable[[str], bool],
) -> list[Violation]:
    found: list[Violation] = []
    for path in files:
        name = module_name(path, pkg_root)
        found.extend(
            Violation(rule, name, imported, line)
            for imported, line in imported_modules(path, pkg_root)
            if is_forbidden(imported)
        )
    return found


def check_domain(pkg_root: Path) -> list[Violation]:
    """Rule 1: ``ela.domain`` imports only the standard library and pydantic."""
    allowed = STDLIB | DOMAIN_ALLOWED_EXTERNAL
    return _violations(
        "domain-imports-only-stdlib-and-pydantic",
        iter([pkg_root / "domain.py"]),
        pkg_root,
        lambda imported: _top_level(imported) not in allowed,
    )


def check_ports(pkg_root: Path) -> list[Violation]:
    """Rule 2: ``ela.ports`` imports only the standard library and ``ela.domain``."""
    return _violations(
        "ports-import-only-stdlib-and-domain",
        iter([pkg_root / "ports.py"]),
        pkg_root,
        lambda imported: (
            _top_level(imported) not in STDLIB and not _is_within(imported, PORTS_ALLOWED_INTERNAL)
        ),
    )


def check_infra_libraries(pkg_root: Path) -> list[Violation]:
    """Rule 3: only providers/, infrastructure/ and api/ import infrastructure libraries."""
    files = (
        path
        for path in _source_files(pkg_root)
        if path.relative_to(pkg_root).parts[0] not in INFRA_PACKAGES
    )
    return _violations(
        "core-does-not-import-infra-libraries",
        files,
        pkg_root,
        lambda imported: _top_level(imported) in INFRA_LIBRARIES,
    )


def check_core_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 4: executive/, tasks/, permissions/, audit/ import neither providers nor infra."""
    files = (path for name in CORE_PACKAGES for path in _source_files(pkg_root / name))
    return _violations(
        "core-packages-do-not-import-providers-or-infrastructure",
        files,
        pkg_root,
        lambda imported: any(_is_within(imported, prefix) for prefix in CORE_FORBIDDEN),
    )


def check_tools_routing_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 26: ``ela.tools`` does not import ``ela.routing`` (ADR 0022 §2).

    The tool of ``model.complete`` and its verifier are given a :class:`~ela.ports.ModelRouterPort`
    and know nothing else about routing: which table is in force, and how a route is chosen, is a
    policy of the Core that the composition root assembles. A tool that imported the policy could
    build one of its own — a second table, deciding where the user's content goes, next to the
    one an operator configured (§25, §33).
    """
    return _violations(
        "tools-do-not-import-the-router",
        _source_files(pkg_root / TOOLS_DIR),
        pkg_root,
        lambda imported: _is_within(imported, ROUTING_PACKAGE),
    )


def check_state_changes(pkg_root: Path) -> list[Violation]:
    """Rule 5: outside ``ela.tasks.state_machine`` nobody changes the state of a Task (ADR 0004).

    Reported: ``x.model_copy(update={... "state": ...})`` with a literal dict, and
    ``Task(..., state=<anything but TaskState.CREATED>)``. A heuristic on names, not on types:
    it catches the obvious bypass, the review catches the rest.
    """
    rule = "task-state-changes-only-in-the-state-machine"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root) in STATE_EXEMPT:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _copies_state(node):
                found.append(
                    Violation(rule, name, 'model_copy(update={"state": ...})', node.lineno)
                )
            elif _builds_task_in_a_state(node):
                found.append(Violation(rule, name, "Task(state=...)", node.lineno))
    return found


def _copies_state(call: ast.Call) -> bool:
    return _copies_field(call, "state")


def _copies_field(call: ast.Call, field: str) -> bool:
    """``x.model_copy(update={... field: ...})`` with a literal dict."""
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "model_copy"):
        return False
    for keyword in call.keywords:
        if keyword.arg == "update" and isinstance(keyword.value, ast.Dict):
            return any(
                isinstance(key, ast.Constant) and key.value == field for key in keyword.value.keys
            )
    return False


def _builds_task_in_a_state(call: ast.Call) -> bool:
    callee = call.func
    callee_name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
    if callee_name != "Task":
        return False
    for keyword in call.keywords:
        if keyword.arg == "state":
            return not _is_initial_state(keyword.value)
    return False


def _is_initial_state(value: ast.expr) -> bool:
    enum_name, member = INITIAL_STATE
    return (
        isinstance(value, ast.Attribute)
        and value.attr == member
        and isinstance(value.value, ast.Name)
        and value.value.id == enum_name
    )


def _is_testing(path: Path, pkg_root: Path) -> bool:
    return path.relative_to(pkg_root).parts[0] == TESTING_DIR


def check_testing_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 6: no production module imports ``ela.testing`` (ADR 0005).

    A fake that reaches production code is a security bug, not a style issue: a ``FakeGuardian``
    that allows everything must never be one import away from the real pipeline.
    """
    files = (path for path in _source_files(pkg_root) if not _is_testing(path, pkg_root))
    return _violations(
        "production-does-not-import-testing",
        files,
        pkg_root,
        lambda imported: _is_within(imported, TESTING_PACKAGE),
    )


def check_testing_imports(pkg_root: Path) -> list[Violation]:
    """Rule 7: ``ela.testing`` imports only the standard library, the domain and the ports."""
    files = (path for path in _source_files(pkg_root) if _is_testing(path, pkg_root))
    return _violations(
        "testing-imports-only-stdlib-domain-and-ports",
        files,
        pkg_root,
        lambda imported: (
            _top_level(imported) not in STDLIB
            and not any(_is_within(imported, prefix) for prefix in TESTING_ALLOWED_INTERNAL)
        ),
    )


def check_orm_separation(pkg_root: Path) -> list[Violation]:
    """Rule 8: no module imports both ``sqlalchemy.orm`` and ``ela.domain`` (ADR 0006).

    An ORM row that could see the domain could subclass it, or a domain model could be mapped
    imperatively; keeping the two imports in different modules makes the explicit mapper the only
    bridge. Reported: the domain import, in a module that also imports ``sqlalchemy.orm``.
    """
    rule = "orm-and-domain-never-meet"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        imports = imported_modules(path, pkg_root)
        if not any(_is_within(name, ORM_PACKAGE) for name, _ in imports):
            continue
        name = module_name(path, pkg_root)
        found.extend(
            Violation(rule, name, imported, line)
            for imported, line in imports
            if _is_within(imported, DOMAIN_MODULE)
        )
    return found


Rule = Callable[[Path], list[Violation]]


def check_audit_adapter_append_only(pkg_root: Path) -> list[Violation]:
    """Rule 9: ``audit_log.py`` never names ``update``, ``delete`` or ``merge`` (ADR 0007).

    Neither as an import, a name, an attribute (``session.delete``), nor as a word of a raw SQL
    string passed to ``text(...)``. The other adapters may update; the audit adapter has no such
    path at all, and the database and the ORM refuse one anyway.
    """
    rule = "audit-adapter-is-append-only"
    path = pkg_root / AUDIT_ADAPTER
    if not path.is_file():
        return []
    name = module_name(path, pkg_root)
    found: list[Violation] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.extend(
                Violation(rule, name, alias.name, node.lineno)
                for alias in node.names
                if alias.name in MUTATING_NAMES
            )
        elif isinstance(node, ast.Name) and node.id in MUTATING_NAMES:
            found.append(Violation(rule, name, node.id, node.lineno))
        elif isinstance(node, ast.Attribute) and node.attr in MUTATING_NAMES:
            found.append(Violation(rule, name, node.attr, node.lineno))
        elif isinstance(node, ast.Call) and _is_named(node.func, "text"):
            found.extend(
                Violation(rule, name, f"text: {match.group(1).upper()}", node.lineno)
                for argument in node.args
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                for match in [MUTATING_SQL.search(argument.value)]
                if match is not None
            )
    return found


def _is_named(callee: ast.expr, function: str) -> bool:
    return (isinstance(callee, ast.Name) and callee.id == function) or (
        isinstance(callee, ast.Attribute) and callee.attr == function
    )


def check_state_machine_callers(pkg_root: Path) -> list[Violation]:
    """Rule 10: outside ``ela.tasks`` nobody imports ``ela.tasks.state_machine`` (ADR 0008).

    The Task Engine is the only caller of ``transition``: a module that moved a task itself and
    saved it would change state without a trail event and without an audit event. The rest of
    ``ela.tasks`` (errors) stays importable from anywhere.
    """
    files = (
        path for path in _source_files(pkg_root) if path.relative_to(pkg_root).parts[0] != TASKS_DIR
    )
    return _violations(
        "state-machine-called-only-by-the-task-engine",
        files,
        pkg_root,
        lambda imported: _is_within(imported, STATE_MACHINE_MODULE),
    )


def check_step_event_writers(pkg_root: Path) -> list[Violation]:
    """Rule 11: outside ``ela.tasks`` nobody builds a ``TaskEvent`` of a ``STEP_*`` type (ADR 0009).

    The state of a step is folded from those events: a module that wrote one itself would move
    a step without the graph's checks and without an audit event. Reported: a ``TaskEvent(...)``
    call whose ``event_type`` is an attribute or a string starting with ``STEP_``. A heuristic on
    names, like rule 5: it catches the obvious bypass, the review catches the rest.
    """
    rule = "step-events-written-only-by-the-task-engine"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root).parts[0] == TASKS_DIR:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_named(node.func, "TaskEvent"):
                found.extend(
                    Violation(rule, name, "TaskEvent(event_type=STEP_*)", node.lineno)
                    for keyword in node.keywords
                    if keyword.arg == "event_type" and _is_step_event(keyword.value)
                )
    return found


def _is_step_event(value: ast.expr) -> bool:
    if isinstance(value, ast.Attribute):
        return value.attr.startswith(STEP_EVENT_PREFIX)
    return (
        isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and value.value.startswith(STEP_EVENT_PREFIX)
    )


def check_permissions_imports(pkg_root: Path) -> list[Violation]:
    """Rule 13: ``ela.permissions`` imports stdlib, domain, ports and ``jsonschema`` (ADR 0010).

    The Guardian must be independent enough to block ELA (§47): the package that hosts it and
    its catalogue reaches no tool, provider, engine, audit or infrastructure, and no pydantic
    directly — the domain is its only way to a model. ``jsonschema`` is the one library it needs.
    """
    files = (path for path in _source_files(pkg_root / PERMISSIONS_DIR))
    return _violations(
        "permissions-import-only-stdlib-domain-ports-and-jsonschema",
        files,
        pkg_root,
        lambda imported: (
            _top_level(imported) not in STDLIB | PERMISSIONS_ALLOWED_EXTERNAL
            and not any(_is_within(imported, prefix) for prefix in PERMISSIONS_ALLOWED_INTERNAL)
        ),
    )


def check_decision_builders(pkg_root: Path) -> list[Violation]:
    """Rule 12: outside ``ela.permissions`` nobody builds a ``PermissionDecision`` that could allow.

    Reported: ``PermissionDecision(...)`` whose ``outcome`` is not the literal
    ``PermissionOutcome.DENIED`` / ``"DENIED"`` — a variable, another member, or no ``outcome``
    keyword at all (``**kwargs``) is a doubt — and ``x.model_copy(update={"outcome": ...})``. The
    Guardian is the only producer of ``ALLOWED`` (ADR 0011); ``ela.testing`` is exempt because the
    table-driven fake must answer ``ALLOWED`` in tests and rule 6 keeps it out of production.
    A heuristic on names, like rules 5 and 11.
    """
    rule = "allowing-decisions-built-only-by-the-guardian"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root).parts[0] in DECISION_BUILDERS_EXEMPT:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_named(node.func, DECISION_MODEL) and not _denies(node):
                found.append(Violation(rule, name, "PermissionDecision(outcome=...)", node.lineno))
            elif _copies_field(node, "outcome"):
                found.append(
                    Violation(rule, name, 'model_copy(update={"outcome": ...})', node.lineno)
                )
    return found


def _denies(call: ast.Call) -> bool:
    """The call names ``outcome`` and it is the literal DENIED; anything else is a doubt."""
    enum_name, member = DENIED_OUTCOME
    for keyword in call.keywords:
        if keyword.arg == "outcome":
            value = keyword.value
            if isinstance(value, ast.Attribute):
                return (
                    value.attr == member
                    and isinstance(value.value, ast.Name)
                    and value.value.id == enum_name
                )
            return isinstance(value, ast.Constant) and value.value == member
    return False


def check_decide_callers(pkg_root: Path) -> list[Violation]:
    """Rule 14: outside ``ela.permissions`` nobody calls ``<something>.decide(...)`` (ADR 0011).

    ``decide`` is the pure port; ``authorize`` decides *and* writes ``PERMISSION_DECIDED``. A
    module that called ``decide`` directly would obtain a decision the audit log never saw.
    Reported: any call whose callee is an attribute named ``decide``. No exemption: the fake
    defines ``decide`` and never calls it; the Guardian's own ``self.decide`` lives inside the
    package.
    """
    rule = "decide-called-only-inside-permissions"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root).parts[0] == PERMISSIONS_DIR:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{DECIDE_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == DECIDE_METHOD
        )
    return found


def check_authorization_builders(pkg_root: Path) -> list[Violation]:
    """Rule 15: outside ``ela.permissions`` nobody builds or widens an ``Authorization`` (ADR 0012).

    Reported: any call ``Authorization(...)`` — by name or as an attribute — and any
    ``x.model_copy(update={...})`` whose literal dict names a field that could widen a grant
    (``max_uses``, ``expires_at``, ``scope``, the bindings). ``model_copy`` does not run the
    validators, so a copy is the one way to hold a grant the type would refuse. ``ela.testing``
    is exempt (rule 6 keeps it out of production); ``persistence/mappers.py`` reads rows back
    and is exempt by exact path. A heuristic on names, like rules 5, 11 and 12.
    """
    rule = "authorizations-built-only-by-permissions"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        relative = path.relative_to(pkg_root)
        if relative.parts[0] in AUTHORIZATION_BUILDERS_EXEMPT or relative == AUTHORIZATION_READER:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_named(node.func, AUTHORIZATION_MODEL):
                found.append(Violation(rule, name, f"{AUTHORIZATION_MODEL}(...)", node.lineno))
            else:
                widened = [
                    f for f in sorted(AUTHORIZATION_WIDENING_FIELDS) if _copies_field(node, f)
                ]
                if widened:
                    found.append(
                        Violation(
                            rule, name, f"model_copy(update={{{widened[0]!r}: ...}})", node.lineno
                        )
                    )
    return found


def check_tool_execute_callers(pkg_root: Path) -> list[Violation]:
    """Rule 16: outside ``executive/executor.py`` nobody calls ``<x>.execute(...)`` (ADR 0013).

    The executor is the only place where a tool runs, and it runs it only with an ``ALLOWED``
    decision in hand; a second caller would be a second place to get that wrong. Reported: any
    call whose callee is an attribute named ``execute``, unless the receiver is a bare name in
    :data:`SQL_EXECUTORS` (``session.execute(...)`` of SQLAlchemy in the persistence adapters) or
    an attribute in :data:`EXECUTOR_RECEIVERS` **inside** :data:`RUNNER_MODULE`
    (``self._executor.execute(...)``: the runner driving the executor, ADR 0019 §3 — one step
    still runs in one place, and this is that place being *called*, not a second tool call). The
    second exemption is bound to the module and not to the name: a field called ``_executor`` in
    any other module is reported like everything else (review of M6.3).
    A heuristic on names, like rules 5, 11, 12 and 15.
    """
    rule = "tool-execute-called-only-by-the-executor"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        relative = path.relative_to(pkg_root)
        if relative == EXECUTOR_MODULE:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{EXECUTE_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == EXECUTE_METHOD
            and not _is_sql_executor(node.func.value)
            and not (relative == RUNNER_MODULE and _is_the_executor(node.func.value))
        )
    return found


def _is_sql_executor(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Name) and receiver.id in SQL_EXECUTORS


def _is_the_executor(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Attribute) and receiver.attr in EXECUTOR_RECEIVERS


def check_step_completers(pkg_root: Path) -> list[Violation]:
    """Rule 17: outside ``executive/executor.py`` nobody calls ``<x>.complete_step(...)`` (ADR
    0014 §9).

    A step is COMPLETED only after its result was verified (§63), and the verification happens
    in one place, the executor; a second caller of ``complete_step`` would be a second place to
    complete a step on the tool's word alone. The definition in ``tasks/engine.py`` is not a
    call and is not reported. A heuristic on names, like rule 16.
    """
    rule = "step-completed-only-by-the-executor"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root) == EXECUTOR_MODULE:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{COMPLETE_STEP_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == COMPLETE_STEP_METHOD
        )
    return found


def check_approval_responders(pkg_root: Path) -> list[Violation]:
    """Rule 19: no module of ``src/ela`` calls ``<x>.respond(...)`` (ADR 0015 §9, ADR 0023 §8).

    The Core never answers its own requests for approval: a "yes" is the user's (§30, §62), and
    it reaches the store through the API — :data:`APPROVAL_RESPONDER`, the **one** exemption, by
    path, promised when this rule was written and opened in M8.1 now that the code behind it
    exists. A second caller anywhere is still a violation. The definitions in ``ports.py``, in
    the SQL store and in the fake are not calls and are not reported. A heuristic on names, like
    rules 16 and 17.
    """
    rule = "approval-answered-only-by-the-user"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root) == APPROVAL_RESPONDER:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{RESPOND_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == RESPOND_METHOD
        )
    return found


def check_verifier_read_only(pkg_root: Path) -> list[Violation]:
    """Rule 18: ``tools/verifiers.py`` and ``tools/paths.py`` have no path that writes (ADR 0014
    §10, decision I; review of M5.2 for the shared classification).

    A verifier is read-only by construction: it looks at the world and changes nothing, and so
    is the path classification it shares with the tool. Reported in those modules:
    ``open``/``fdopen`` in a writing mode (``w``, ``a``, ``x``, ``+``) or with a mode that is not
    a literal; ``os.open`` with a writing flag (``O_WRONLY``, ``O_RDWR``, ``O_CREAT``, ``O_TRUNC``,
    ``O_APPEND``, ``O_EXCL``); any call named after a write — ``write``, ``unlink``, ``rename``,
    ``mkdir``, ``chmod``, ``write_text``… (:data:`WRITING_CALLS`) — and any call through
    ``shutil``. Closed-world on names, like rules 5, 11, 12, 15 and 16.
    """
    rule = "verifier-read-only"
    found: list[Violation] = []
    for relative in READ_ONLY_MODULES:
        path = pkg_root / relative
        if not path.is_file():
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f"{callee}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for callee in [_callee(node.func)]
            if _writes(node, callee)
        )
    return found


def _callee(function: ast.expr) -> str:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return f".{function.attr}"
    return ""


def _writes(call: ast.Call, callee: str) -> bool:
    """Whether ``call`` may write, by the name of what it calls and its mode or flags."""
    bare = callee.lstrip(".")
    if bare in OPENERS:
        if callee == ".open":  # os.open(path, flags): the flags say
            return _has_writing_flag(_argument(call, 1, "flags"))
        return _is_writing_mode(_argument(call, 1, "mode"))
    if bare in WRITING_CALLS:
        return True
    receiver = call.func.value if isinstance(call.func, ast.Attribute) else None
    return isinstance(receiver, ast.Name) and receiver.id == SHUTIL


def _argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for item in call.keywords:
        if item.arg == keyword:
            return item.value
    return call.args[position] if len(call.args) > position else None


def _is_writing_mode(mode: ast.expr | None) -> bool:
    if mode is None:
        return False  # the default mode of ``open`` reads
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(letter in WRITING_OPEN_MODES for letter in mode.value)
    return True  # a mode that is not a literal is a doubt


def _has_writing_flag(flags: ast.expr | None) -> bool:
    if flags is None:
        return True  # ``os.open`` without flags is not a call this module may make
    for node in ast.walk(flags):
        if isinstance(node, ast.Attribute) and node.attr in WRITING_OPEN_FLAGS:
            return True
        if isinstance(node, ast.Name) and node.id in WRITING_OPEN_FLAGS:
            return True
    return False


def check_audit_arguments(pkg_root: Path) -> list[Violation]:
    """Rule 23: no ``AuditEvent`` is built with the arguments of a call anywhere inside it.

    ADR 0018 §5. What a tool was called *with* can be the user's content — the body of a note, the
    text of a message — and §57 keeps that in the private database: the plan holds it, the
    ``ExecutionResult`` holds it, the audit log holds the *targets* the scope constrains and the
    decision that allowed them. Until M6.3 the arguments were a parameter and the rule was a
    sentence in a docstring; now they are a field of ``TaskStep`` that three modules read, and a
    sentence is not a guarantee.
    Reported, anywhere in the subtree of an ``AuditEvent(...)`` call: the name ``arguments`` as a
    variable, as an attribute, as a keyword or as a string literal (a payload key). Closed-world
    on names, like rules 5, 12, 15, 16 and 20: in a repository where the word has one meaning, a
    false positive costs less than a false negative.
    """
    rule = "arguments-never-enter-the-audit"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in ast.walk(tree):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == AUDIT_EVENT
            ):
                continue
            for node in ast.walk(call):
                mention = _mentions_arguments(node)
                if mention is not None:
                    found.append(Violation(rule, name, mention, node.lineno))
    return found


def _mentions_arguments(node: ast.AST) -> str | None:
    """How ``node`` names the arguments of a call, or ``None`` if it does not."""
    if isinstance(node, ast.Name) and node.id == ARGUMENTS_NAME:
        return ARGUMENTS_NAME
    if isinstance(node, ast.Attribute) and node.attr == ARGUMENTS_NAME:
        return f".{ARGUMENTS_NAME}"
    if isinstance(node, ast.keyword) and node.arg == ARGUMENTS_NAME:
        return f"{ARGUMENTS_NAME}="
    if isinstance(node, ast.Constant) and node.value == ARGUMENTS_NAME:
        return f'"{ARGUMENTS_NAME}"'
    return None


def check_device_availability_readers(pkg_root: Path) -> list[Violation]:
    """Rule 20: outside ``ela.devices`` and the mapper nobody touches ``availability``.

    ADR 0016 §3 and ADR 0017 §9. A stored ``availability`` says what was true when someone wrote
    it and keeps saying it after the node went quiet; the answer a decision needs comes from
    ``DeviceRegistry``, which derives it from the last heartbeat. The orchestrator (§17) is the
    first reader with a motive to trust the column — it is indexed and one ``SELECT`` away — so
    the convention becomes a rule here.
    Reported: any ``.availability`` attribute and any ``availability=`` keyword. Closed-world on
    names, like rules 5, 11, 12, 15 and 16: in a repository where the word has one meaning, a
    false positive costs less than a false negative.
    """
    rule = "availability-derived-not-read"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        relative = path.relative_to(pkg_root)
        if relative.parts[0] == DEVICES_DIR or relative == PERSISTENCE_MAPPERS:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == AVAILABILITY_FIELD:
                found.append(Violation(rule, name, f".{AVAILABILITY_FIELD}", node.lineno))
            elif isinstance(node, ast.keyword) and node.arg == AVAILABILITY_FIELD:
                found.append(Violation(rule, name, f"{AVAILABILITY_FIELD}=", node.lineno))
    return found


def check_device_port_readers(pkg_root: Path) -> list[Violation]:
    """Rule 21: outside ``ela.devices`` nobody names ``DeviceRegistryPort`` (ADR 0017 §9).

    Rule 20 forbids reading the stale field (ADR 0016 §3); this one removes the temptation, by
    keeping the raw port out of the hands of whoever decides. ``ela.devices`` holds the decision:
    everybody else asks ``DeviceRegistry``, and gets an availability that is already judged.

    Two more modules were exempt and neither used it (ADR 0027). The rule looks at *imports*:
    ``ela.ports`` **declares** ``DeviceRegistryPort`` and cannot import what it defines, and the
    SQL adapter satisfies it structurally — it is a ``Protocol`` — so it names the port only in
    its docstrings. Restricting either exemption made no rule speak, so both are withdrawn, and
    the day one of those modules imports the port this rule says so.
    """
    files = (
        path
        for path in _source_files(pkg_root)
        if not any(
            _is_within(module_name(path, pkg_root), prefix) for prefix in DEVICE_PORT_ALLOWED
        )
    )
    return _violations(
        "device-registry-port-reached-only-through-the-registry",
        files,
        pkg_root,
        lambda imported: _is_within(imported, DEVICE_REGISTRY_PORT),
    )


def check_devices_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 22: ``ela.devices`` does not import ``ela.tasks`` (ADR 0017 §6).

    "The orchestrator only advises" is the property that makes a missing node an *attesa* and not
    a failure (§17, §33). Kept structurally rather than promised in a docstring: a package with no
    path to the Task Engine cannot move a task, whatever a future ``place`` decides to do.
    """
    files = _source_files(pkg_root / DEVICES_DIR)
    return _violations(
        "devices-advise-and-never-move-a-task",
        files,
        pkg_root,
        lambda imported: any(_is_within(imported, prefix) for prefix in DEVICES_FORBIDDEN),
    )


def check_anthropic_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 24: only ``ela.providers.anthropic`` imports the Anthropic SDK (ADR 0020 §11).

    The adapter is the whole boundary with the vendor: what a provider's API is called, how it
    fails, what it charges. A second module importing it would be a second boundary, and §26
    ("il Core deve parlare con una Model Provider abstraction") would hold only by habit.

    Note that ``ela.providers.anthropic`` — ELA's own package — is not the library: an import of
    ``ela.providers.anthropic.settings`` is an internal import and is not reported.
    """
    files = (
        path
        for path in _source_files(pkg_root)
        if ANTHROPIC_ADAPTER_DIR not in path.relative_to(pkg_root).parents
    )
    return _violations(
        "anthropic-imported-only-by-its-adapter",
        files,
        pkg_root,
        lambda imported: _top_level(imported) == ANTHROPIC_LIBRARY,
    )


def check_provider_complete_callers(pkg_root: Path) -> list[Violation]:
    """Rule 25: outside ``tools/model.py`` nobody calls ``<x>.complete(...)`` (ADR 0021 §5).

    ``model.complete`` is the capability through which the user's content leaves this machine
    (§29, §57), and the guarantee that it leaves only under an ``ALLOWED`` decision is not a
    property of ``ModelProvider.complete`` — which will answer anyone — but of the one module
    that calls it, a :class:`~ela.tools.base.Tool` whose base class checks the decision first.
    A second caller anywhere in ``src/ela`` would be a second way out with no such check, which
    is the same argument rule 16 makes for ``Tool.execute``.

    Reported: any call whose callee is an attribute named ``complete``, unless the receiver is an
    attribute in :data:`ENGINE_RECEIVERS` — ``self._engine.complete(...)``, the Task Engine
    closing a task (ADR 0008), which shares the name and nothing else. A heuristic on the name,
    like rules 5, 11, 12, 15, 16 and 17: ``complete_step`` is a different name and is rule 17's.
    """
    rule = "provider-complete-called-only-by-the-model-tool"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root) == MODEL_TOOL_MODULE:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{COMPLETE_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == COMPLETE_METHOD
            and not _is_the_engine(node.func.value)
        )
    return found


def _is_the_engine(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Attribute) and receiver.attr in ENGINE_RECEIVERS


def check_concrete_names(pkg_root: Path) -> list[Violation]:
    """Rule 27: only ``ela.composition`` imports ``ela.providers`` or ``ela.infrastructure``.

    ADR 0023 §12. A composition root is worth having only if it is the *one* place that knows
    what ELA is wired to: a second module naming an adapter is a second wiring, and §50 ("il Core
    deve parlare con una Model Provider abstraction") would hold by habit rather than by
    construction. The two packages themselves are exempt — an adapter may import its neighbours —
    and so is the composition root, which exists to name them.
    """
    files = (
        path
        for path in _source_files(pkg_root)
        if path.relative_to(pkg_root).parts[0] not in CONCRETE_ALLOWED
    )
    return _violations(
        "concretes-named-only-by-the-composition-root",
        files,
        pkg_root,
        lambda imported: any(_is_within(imported, prefix) for prefix in CORE_FORBIDDEN),
    )


def check_cli_over_the_api(pkg_root: Path) -> list[Violation]:
    """Rule 28: the CLI is a client of the local API, and nobody imports the CLI (ADR 0024 §7).

    Three things would each turn the command line into a second ELA, and each has a consequence
    that is not a matter of taste: a second world writing the same database has the ``run`` lock
    of ADR 0023 §9 in only one of the two processes; a world built to answer one command declares
    the ``local`` node alive (ADR 0023 §5-bis) and then exits; and a "yes" typed into a CLI that
    called ``respond`` itself would be a second door into the system, where rule 19 allows exactly
    one — the API's.

    So: no module under ``cli/`` names ``build`` or ``Ela``, and none of them imports ``ela.api``
    or ``ela.composition.root`` — except ``cli/serve.py``, an exemption by path, for the one
    command whose job is to start the process there is nothing to talk to without.
    ``ela.composition.settings`` stays open to all of them: reading the token is not composing.

    Reported: the forbidden import, or the composing name wherever it appears — imported, called
    or annotated. Closed-world on names, like rules 5, 11, 12, 15, 16 and 17.
    """
    rule = "cli-talks-over-the-api"
    found: list[Violation] = []
    for path in _source_files(pkg_root / CLI_DIR):
        relative, name = path.relative_to(pkg_root), module_name(path, pkg_root)
        if relative != CLI_SERVE:
            found.extend(
                Violation(rule, name, imported, line)
                for imported, line in imported_modules(path, pkg_root)
                if any(_is_within(imported, prefix) for prefix in CLI_FORBIDDEN_INTERNAL)
            )
        found.extend(_composing_names(path, name, rule))
    outside = (
        path for path in _source_files(pkg_root) if path.relative_to(pkg_root).parts[0] != CLI_DIR
    )
    return found + _violations(
        rule, outside, pkg_root, lambda imported: _is_within(imported, CLI_PACKAGE)
    )


def _composing_names(path: Path, name: str, rule: str) -> Iterator[Violation]:
    """``build`` and ``Ela`` wherever they are written: the CLI holds no built world."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.alias) and node.name in COMPOSED_NAMES:
            yield Violation(rule, name, node.name, getattr(node, "lineno", 0))
        elif isinstance(node, ast.Name) and node.id in COMPOSED_NAMES:
            yield Violation(rule, name, node.id, node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr in COMPOSED_NAMES:
            yield Violation(rule, name, node.attr, node.lineno)


def check_tool_output_readers(pkg_root: Path) -> list[Violation]:
    """Rule 29: inside ``ela.api``, what a tool produced has one model and one reader (M8.3).

    ADR 0025 §4. ``ExecutionResult.output`` is the user's own content (§57) — the answer of a
    model, the body of a note — and until M8.3 it left the machine nowhere. Now one route
    returns it, and this rule is what keeps that "one" true: an ``output`` field added to
    ``StepOut`` or to ``AuditEventOut`` would carry the same content out through a route that
    was never meant to, and nothing in the type system would object.

    The mirror of rule 23, at the opposite boundary: 23 says where the user's content may not
    **enter** (an ``AuditEvent``), 29 says where it may **leave**. Two things are reported:

    * a class field named ``output`` in any module of ``ela.api``, unless the class is
      :data:`OUTPUT_MODEL`;
    * the name ``output`` — as an attribute, a variable, a keyword or a string literal — in any
      module of ``ela.api`` other than :data:`OUTPUT_SCHEMAS`, which is where the one model
      reads it.

    Closed-world on the name, like rules 5, 12, 15, 16, 20 and 23: in this package the word has
    one meaning, and a false positive costs less than a false negative.
    """
    rule = "tool-output-readers"
    found: list[Violation] = []
    for path in _source_files(pkg_root / API_DIR):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name != OUTPUT_MODEL:
                found.extend(
                    Violation(rule, name, f"{node.name}.{OUTPUT_NAME}", field.lineno)
                    for field in node.body
                    if isinstance(field, ast.AnnAssign)
                    and isinstance(field.target, ast.Name)
                    and field.target.id == OUTPUT_NAME
                )
        if path.relative_to(pkg_root) == OUTPUT_SCHEMAS:
            continue
        found.extend(
            Violation(rule, name, mention, node.lineno)
            for node in ast.walk(tree)
            if (mention := _mentions_output(node)) is not None
        )
    return found


def _mentions_output(node: ast.AST) -> str | None:
    """How ``node`` names the output of an execution, or ``None`` if it does not."""
    if isinstance(node, ast.Name) and node.id == OUTPUT_NAME:
        return OUTPUT_NAME
    if isinstance(node, ast.Attribute) and node.attr == OUTPUT_NAME:
        return f".{OUTPUT_NAME}"
    if isinstance(node, ast.keyword) and node.arg == OUTPUT_NAME:
        return f"{OUTPUT_NAME}="
    if isinstance(node, ast.Constant) and node.value == OUTPUT_NAME:
        return f'"{OUTPUT_NAME}"'
    return None


def check_placement_builders(pkg_root: Path) -> list[Violation]:
    """Rule 30: outside ``ela.devices`` nobody builds a ``PlacementDecision`` that names a node.

    The mirror of rule 12 (ADR 0026 §5). ``ensure_placed`` lets the executor check the
    orchestrator's claim instead of believing it — but a claim anybody can forge is not a claim.
    A module that could write ``PlacementDecision(device=some_node, ...)`` would hand the executor
    a signature it cannot tell from the real one.

    Reported: ``PlacementDecision(...)`` whose ``device`` is not the literal ``None`` — another
    value, a variable, or no ``device`` keyword at all (``**kwargs``) is a doubt (§33) — and
    ``x.model_copy(update={"device": ...})``, which would widen one that named nobody. A
    heuristic on names, like rules 5, 11, 12 and 15.

    No exemption. ``ela.testing`` has none because no fake builds a placement; the tests that need
    a forged one live outside ``src/ela``, where the rules do not look, which is the honest place
    for a forgery.
    """
    rule = "placement-decisions-built-only-by-the-orchestrator"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root).parts[0] == DEVICES_DIR:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_named(node.func, PLACEMENT_MODEL) and not _places_nobody(node):
                found.append(Violation(rule, name, "PlacementDecision(device=...)", node.lineno))
            elif _copies_field(node, PLACEMENT_DEVICE_FIELD):
                found.append(
                    Violation(rule, name, 'model_copy(update={"device": ...})', node.lineno)
                )
    return found


def _places_nobody(call: ast.Call) -> bool:
    """The call names ``device`` and it is the literal ``None``; anything else is a doubt."""
    for keyword in call.keywords:
        if keyword.arg == PLACEMENT_DEVICE_FIELD:
            return isinstance(keyword.value, ast.Constant) and keyword.value.value is None
    return False


def check_constant_time_token(pkg_root: Path) -> list[Violation]:
    """Rule 31: the API's token is compared only with ``secrets.compare_digest`` (ADR 0026 §6).

    Two things are reported in :data:`SECURITY_MODULE`:

    * the module does not call ``compare_digest`` at all — the comparison has been replaced;
    * a ``==``/``!=``/``in`` whose operands name the token (:data:`TOKEN_NAMES`, as a bare name or
      as ``.encode()`` on one) — the comparison has been *added* beside it, which is the same
      leak with the safe call left in place as decoration.

    The scheme is compared with ``!=`` on purpose and stays allowed: it is not a secret, it is in
    every request, and comparing it in variable time tells an attacker nothing they did not send.

    Why a rule and not a test: the property is *how long the comparison takes*, and a test that
    measured it would measure the runner instead — the mistake M9.1 spent its first commit
    undoing (ADR 0006 §13). The shape of the code is the only place this can be pinned.
    """
    rule = "token-compared-in-constant-time"
    path = pkg_root / SECURITY_MODULE
    name = module_name(path, pkg_root)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = [
        Violation(rule, name, f"{CONSTANT_TIME_COMPARE}(...)", 1)
        for node in [tree]
        if not any(
            isinstance(call, ast.Call) and _is_named(call.func, CONSTANT_TIME_COMPARE)
            for call in ast.walk(node)
        )
    ]
    found.extend(
        Violation(rule, name, f"{_operator(node)} on the token", node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare) and _compares_the_token(node)
    )
    return found


def _operator(node: ast.Compare) -> str:
    return {ast.Eq: "==", ast.NotEq: "!=", ast.In: "in", ast.NotIn: "not in"}.get(
        type(node.ops[0]), type(node.ops[0]).__name__
    )


def _names_the_token(node: ast.expr) -> bool:
    """``token``/``presented``, bare or through a call on it (``token.encode()``)."""
    if isinstance(node, ast.Name):
        return node.id in TOKEN_NAMES
    if isinstance(node, ast.Call):
        return _names_the_token(node.func)
    if isinstance(node, ast.Attribute):
        return _names_the_token(node.value)
    return False


def _compares_the_token(node: ast.Compare) -> bool:
    return any(_names_the_token(operand) for operand in [node.left, *node.comparators])


def check_machine_access(pkg_root: Path) -> list[Violation]:
    """Rule 32: only ``ela.infrastructure.perception`` reaches the operating system (ADR 0028 §1).

    ``ctypes`` and starting a process are the two ways a Python program leaves its own runtime.
    Before M10.1 ``ela`` used neither, anywhere; perception is the first thing that needs them,
    and the value of writing the rule the same day is that "ELA touches the machine in one place"
    is a fact a reader can check instead of a claim they have to trust.

    Everything else reaches the machine through :class:`~ela.ports.PerceptionProbe`, which is
    also what lets the whole Core be tested with no hardware at all.
    """
    rule = "machine-access-in-one-place"
    files = [
        path
        for path in _source_files(pkg_root)
        if not path.is_relative_to(pkg_root / PERCEPTION_ADAPTER_DIR)
    ]
    found = _violations(
        rule,
        iter(files),
        pkg_root,
        lambda imported: (
            _top_level(imported) in MACHINE_LIBRARIES
            or _top_level(imported) in SPAWNING_MODULES
            or imported in SPAWNING_CALLS
        ),
    )
    for path in files:
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f"{_dotted(node.func)}(...)", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _dotted(node.func) in SPAWNING_CALLS
        )
    return found


def _dotted(function: ast.expr) -> str:
    """``asyncio.create_subprocess_exec`` for an attribute chain, ``""`` for anything else."""
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        base = _dotted(function.value)
        return f"{base}.{function.attr}" if base else ""
    return ""


def _is_child(path: Path) -> bool:
    """Whether this module is a helper child: executable as a script (M10.3).

    Derived rather than listed, so a child added tomorrow is covered by rule 33 **by default**
    instead of when somebody remembers to add it — the same fail-safe direction as
    ``fingerprint()`` deriving its keys from the model's fields (ADR 0028 §5).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(operand, ast.Constant) and operand.value == MAIN_GUARD
            for operand in [node.test.left, *node.test.comparators]
        )
        for node in ast.walk(tree)
    )


def perception_children(pkg_root: Path) -> list[Path]:
    """Every helper child under the perception adapter, in path order."""
    return [path for path in _source_files(pkg_root / PERCEPTION_ADAPTER_DIR) if _is_child(path)]


def check_children_are_standalone(pkg_root: Path) -> list[Violation]:
    """Rule 33: every perception helper child imports only the standard library (ADR 0028 §2).

    A child process exists to be allowed to die: a mistaken Objective-C message kills it, and that
    is the containment working rather than failing — M10.3 saw it again, a first attempt at Vision
    through ``ctypes`` ending in SIGSEGV. A child that imported ``ela`` would drag the Core's
    import graph into the thing designed to crash, and would give the Core a path into the modules
    no runner can cover. The contract between the two sides is a JSON object.

    The subject is derived (:func:`perception_children`) and not listed, so the rule cannot go
    mute on a child somebody forgot to declare.
    """
    return _violations(
        "perception-children-import-only-stdlib",
        iter(perception_children(pkg_root)),
        pkg_root,
        lambda imported: _is_within(imported, ROOT_PACKAGE),
    )


def check_no_window_titles(pkg_root: Path) -> list[Violation]:
    """Rule 36: nothing under the perception adapter ever names a window-title key (M10.3 dec. 3).

    Window owners, PIDs and geometry come with no permission at all and are *state*. A window
    **title** needs the same Screen Recording grant a screenshot needs — measured, from a process
    that was its own TCC responsible process: owners present, titles absent — and it is *content*.
    So it does not enter the perception ring, and "it does not" is a rule rather than a habit.

    Scoped to the adapter because that is where ``ctypes`` is allowed to be (rule 32): the key
    cannot be used anywhere else, so this is the whole surface, derived rather than named.
    """
    rule = "perception-reads-no-window-titles"
    found: list[Violation] = []
    for path in _source_files(pkg_root / PERCEPTION_ADAPTER_DIR):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            text = node.value if isinstance(node.value, str) else None
            if isinstance(node.value, bytes):
                text = node.value.decode("utf-8", "replace")
            if text is None:
                continue
            found.extend(
                Violation(rule, name, key, node.lineno)
                for key in sorted(WINDOW_TITLE_KEYS)
                if key in text
            )
    return found


def check_the_voice_writes_no_file(pkg_root: Path) -> list[Violation]:
    """Rule 40: nothing of what ELA says is ever written to a file (M11.1 dec. 7).

    The user's decision, in their words: *mai su disco per la voce in uscita*. What makes it a
    rule rather than a note is that ``say`` makes the opposite trivial — ``say -o out.aiff`` is
    a supported, documented flag, and one character stands between "ELA spoke" and "ELA kept a
    recording of everything it told you".

    A recording of what ELA said is a record of what ELA knew: the answers are composed from the
    context of §44 and from the user's own goal, so a directory of them is the accumulation §57
    exists to forbid — and unlike a capture it would have no TTL, no ceiling and no store, because
    nobody designed one.

    Reads the **literals** in the voice modules, the way rule 36 reads a CoreFoundation key: a
    flag is a string in an ``argv`` list, never an import, so a rule that read imports would be
    mute on the only line that could break it.
    """
    rule = "the-voice-writes-no-file"
    found: list[Violation] = []
    for relative in VOICE_MODULES:
        path = pkg_root / relative
        if not path.is_file():
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, node.value, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in VOICE_OUTPUT_FLAGS
        )
    return found


def check_adapter_names_no_state(pkg_root: Path) -> list[Violation]:
    """Rule 34: the perception adapter never names a domain state (ADR 0028 §1).

    The coverage gate covers what can be run on a runner, and no runner has a webcam. The
    adapter's exemption is therefore paid for structurally: it hands over primitives — an ``int``
    for an ``AVAuthorizationStatus``, ``None`` for "not read" — and :func:`ela.perception.interpret`
    decides what they mean, inside the package the gate does cover.

    Reported as an *import* and as a *name*: a module that never imports ``SensorState`` cannot
    build one, and one that mentions it by attribute is reaching for the same words the long way.
    """
    rule = "perception-adapter-decides-nothing"
    found = _violations(
        rule,
        _source_files(pkg_root / PERCEPTION_ADAPTER_DIR),
        pkg_root,
        lambda imported: imported.rpartition(".")[2] in PERCEPTION_VOCABULARY,
    )
    for path in _source_files(pkg_root / PERCEPTION_ADAPTER_DIR):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, node.attr, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in PERCEPTION_VOCABULARY
        )
    return found


def check_capture_stays_on_the_machine(pkg_root: Path) -> list[Violation]:
    """Rule 35: nothing that holds a screen capture can send one anywhere (ADR 0029 §12).

    M10.2's whole promise is that the image does not leave this machine: no OCR, no provider, no
    network. A promise like that is worth what the thing that holds it is worth, so it is held by
    the shape of the code — :mod:`ela.tools.screen` and :mod:`ela.tools.captures` do not name a
    router, a provider registry or an HTTP client, by import or by attribute.

    Not a rule about tools in general: ``ela.tools.model`` names the router on purpose and must.
    It is a rule about the modules that have the user's content in their hands.

    M10.3 reopened it, examined it and **confirmed** it: nothing goes out. M11.1 extends it in a
    direction the name does not describe — :data:`VOICE_MODULES`, which hold **what ELA says**,
    and whose words come from the same places the capture's text does. The two subjects are two
    constants on purpose: M11.3 has to be able to open the voice's half without opening the
    screen's, and one list would have made that a single careless edit.
    """
    rule = "capture-stays-on-the-machine"
    paths = [pkg_root / relative for relative in (*CAPTURE_MODULES, *VOICE_MODULES)]
    found = _violations(
        rule,
        [path for path in paths if path.is_file()],
        pkg_root,
        lambda imported: imported.rpartition(".")[2] in CAPTURE_FORBIDDEN,
    )
    for path in paths:
        if not path.is_file():
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, node.attr, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in CAPTURE_FORBIDDEN
        )
    return found


PLATFORM_WORDS = frozenset(
    {
        "platform",  # ``platform.system()``, ``sys.platform``, ``platform.machine()``
        "uname",
        "darwin",
        "linux",
        "windows",
        "macos",
        "win32",
        "cygwin",
        "posix",
        "nt",
    }
)
"""The words that make a condition a question about *which machine this is* (ADR 0031).

Matched as whole identifiers and whole string constants, never as substrings: ``nt`` is a word in
``os.name != "nt"`` and a coincidence in ``count``. ``os.name`` needs no entry of its own — the
value it is compared against is always one of these.
"""


def _condition_words(test: ast.expr) -> set[str]:
    """Every identifier, attribute name and string constant in a condition, lowercased."""
    words: set[str] = set()
    for node in ast.walk(test):
        if isinstance(node, ast.Name):
            words.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            words.add(node.attr.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            words.add(node.value.lower())
    return words


def check_platform_choice_is_a_statement(pkg_root: Path) -> list[Violation]:
    """Rule 37: a choice made on which machine this is is an ``if``, never ``X if p else Y``.

    This is a rule about the *measuring instrument*, and it is why it is worth a rule. The
    ``cov-critical`` gate at 100% branch is what proves that no decision goes unproved — but the
    side a conditional **expression** does not take costs it nothing: no missing line and no
    missing arc, because a ternary is a single statement (measured, ADR 0031 §1). So a platform
    choice written as an expression is invisible exactly where the invisibility is dangerous, and
    the only trace it leaves surfaces one frame lower, in whatever pure function the arm that did
    not run would have called — a line that has nothing to do with the platform, in another
    package, on the other runner. That is how ``ela.tools.settings.ocr_timeout`` came to be the
    single uncovered line of a green macOS build (M10.3).

    Written as a statement, the same choice becomes two arcs the gate measures and refuses to
    leave unproved, so the test that names the other system stops being optional.

    Scoped to all of ``src/ela`` and not to the composition root: the root is where the choice
    belongs today (rule 27), and this rule is what the *next* one — a Windows node in Fase 12 —
    runs into wherever it is written.
    """
    rule = "platform-choice-is-a-statement"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, ast.unparse(node.test), node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.IfExp) and _condition_words(node.test) & PLATFORM_WORDS
        )
    return found


def _named(path: Path) -> set[str]:
    """Every name and attribute a module mentions, however it reached for it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.asname or node.name.rpartition(".")[2])
    return found


def _writes_through_self(func: ast.expr) -> bool:
    """``self.<something>.<writing member>`` — the one shape in which a composer could write."""
    return (
        isinstance(func, ast.Attribute)
        and func.attr in CONTEXT_WRITE_MEMBERS
        and isinstance(func.value, ast.Attribute)
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "self"
    )


def check_context_writes_nothing(pkg_root: Path) -> list[Violation]:
    """Rule 38: the Context Core reads, and calls nothing that writes (ADR 0032 §6).

    The rule that makes the content/state line automatic instead of case-by-case: everything
    that costs a ``PermissionDecision`` is out by construction, because a composer that cannot
    reach the Guardian cannot ask it for one and a composer that cannot call a writing member
    cannot change anything it was handed.

    Reads **calls**, where contract 14 reads imports. A port comes through a constructor, so
    ``self._repository.save(...)`` names no module and would pass every import contract there is.
    """
    rule = "context-writes-nothing"
    found: list[Violation] = []
    for path in _source_files(pkg_root / CONTEXT_DIR):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, node.func.attr, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _writes_through_self(node.func)
        )
    return found


def check_context_is_not_recorded(pkg_root: Path) -> list[Violation]:
    """Rule 39: whatever names a snapshot names no audit event and no provider request.

    Symmetric on purpose, and per module rather than per package: the day somebody writes the
    line that puts the context into a prompt, that line is in a module that already holds the
    snapshot, and this is what it meets. ADR 0032 §7 says what has to happen before the door
    reopens — the four questions of §57, answered, not the four questions of §57, remembered.
    """
    rule = "context-is-not-recorded"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        named = _named(path)
        if CONTEXT_SNAPSHOT not in named:
            continue
        name = module_name(path, pkg_root)
        found.extend(
            Violation(rule, name, forbidden, 0)
            for forbidden in sorted(named & CONTEXT_NOT_RECORDED)
        )
    return found


RULES: dict[str, Rule] = {
    "domain": check_domain,
    "ports": check_ports,
    "infra-libraries": check_infra_libraries,
    "core-isolation": check_core_isolation,
    "tools-routing-isolation": check_tools_routing_isolation,
    "state-changes": check_state_changes,
    "testing-isolation": check_testing_isolation,
    "testing-imports": check_testing_imports,
    "orm-separation": check_orm_separation,
    "audit-append-only": check_audit_adapter_append_only,
    "state-machine-callers": check_state_machine_callers,
    "step-event-writers": check_step_event_writers,
    "permissions-imports": check_permissions_imports,
    "decision-builders": check_decision_builders,
    "decide-callers": check_decide_callers,
    "authorization-builders": check_authorization_builders,
    "tool-execute-callers": check_tool_execute_callers,
    "step-completers": check_step_completers,
    "verifier-read-only": check_verifier_read_only,
    "approval-responders": check_approval_responders,
    "device-availability-readers": check_device_availability_readers,
    "device-port-readers": check_device_port_readers,
    "devices-isolation": check_devices_isolation,
    "audit-arguments": check_audit_arguments,
    "anthropic-import-isolation": check_anthropic_isolation,
    "provider-complete-callers": check_provider_complete_callers,
    "concrete-names": check_concrete_names,
    "cli-over-the-api": check_cli_over_the_api,
    "tool-output-readers": check_tool_output_readers,
    "placement-builders": check_placement_builders,
    "constant-time-token": check_constant_time_token,
    "machine-access-in-one-place": check_machine_access,
    "capture-stays-on-the-machine": check_capture_stays_on_the_machine,
    "perception-children-import-only-stdlib": check_children_are_standalone,
    "perception-reads-no-window-titles": check_no_window_titles,
    "perception-adapter-decides-nothing": check_adapter_names_no_state,
    "platform-choice-is-a-statement": check_platform_choice_is_a_statement,
    "context-writes-nothing": check_context_writes_nothing,
    "context-is-not-recorded": check_context_is_not_recorded,
    "the-voice-writes-no-file": check_the_voice_writes_no_file,
}


# --------------------------------------------------------------------------------------------
# What each rule reads, and what kind of thing it is (ADR 0027)
# --------------------------------------------------------------------------------------------

#: A door: who is *exempt* from the rule. Restricted, the rule must report at least one
#: violation — otherwise nobody is behind the door and it is an opening the next person will read
#: as a permission already granted (review of M6.2, ADR 0017 §9).
EXEMPTION = "exemption"
#: What the rule *looks for* or *looks at*: a library, a method name, a field, a file. Restricted,
#: it can only make the rule quieter, never louder — so the rule must report nothing.
DETECTOR = "detector"
#: What the rule could not be asked about at all. Not asserted, and the row carries **why** in
#: one word plus the reason in full — so a reader sees a declared exception and not an oversight.
SUBJECT = "subject"
#: There is no way to ask the question: restricting the constant removes the subject of the rule.
INEVITABLE = "inevitable"
#: Restricting it makes the rule raise, or speak about itself. What comes out is an artefact of
#: the restriction, not a signal about a door.
ARTEFACT = "artefact"

#: Restrict the constant as a whole: to a path that exists nowhere, a name nobody has, an empty
#: set, a pattern that matches nothing.
WHOLE = "whole"
#: Restrict one element at a time. The elements are **read from the constant**, never listed
#: here: a value added to an allowlist is covered without anybody remembering to add it twice.
EACH = "each"

_THE_PACKAGE_ITSELF = (
    "the name of the package every rule walks: restricting it does not open or close a door, "
    "it removes the subject"
)


@dataclass(frozen=True)
class Constant:
    """One constant, as one rule reads it.

    ``tests/architecture/test_exemptions.py`` derives the (rule, constant) pairs from the AST of
    this module and requires that they be exactly the rows below — so a constant added to an
    existing rule has to be classified before the suite goes green — and then asserts the two
    opposite properties: an ``EXEMPTION`` restricted makes its rule speak, a ``DETECTOR``
    restricted leaves it silent. Misfiling a live door therefore fails; the shape it could still
    hide in is a ``SUBJECT`` row, and there are three of those.
    """

    rule: str
    name: str
    kind: str
    by: str = WHOLE
    #: The ADR that opened the door, for an ``EXEMPTION``; ``"—"`` when no ADR documents it.
    adr: str = ""
    #: Required for a ``SUBJECT``: ``INEVITABLE`` or ``ARTEFACT``, the reason in one word.
    why: str = ""
    #: Required for a ``SUBJECT``, and for an ``EXEMPTION`` the real tree cannot prove.
    reason: str = ""
    #: The ``violations.ALLOWED`` case that stands in when the real tree is silent. An exemption
    #: is proved by the real tree or by a case named here — never by nothing.
    proof: str = ""


CONSTANTS: tuple[Constant, ...] = (
    # anthropic-import-isolation
    Constant(
        "anthropic-import-isolation",
        "ANTHROPIC_ADAPTER_DIR",
        EXEMPTION,
        by=WHOLE,
        adr="ADR 0020 §11",
    ),
    Constant("anthropic-import-isolation", "ANTHROPIC_LIBRARY", DETECTOR),
    Constant(
        "anthropic-import-isolation",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # approval-responders
    Constant(
        "approval-responders",
        "APPROVAL_RESPONDER",
        EXEMPTION,
        by=WHOLE,
        adr="ADR 0015 §9; ADR 0023 §12",
    ),
    Constant("approval-responders", "RESPOND_METHOD", DETECTOR),
    Constant(
        "approval-responders", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # audit-append-only
    Constant("audit-append-only", "AUDIT_ADAPTER", DETECTOR),
    Constant("audit-append-only", "MUTATING_NAMES", DETECTOR),
    Constant("audit-append-only", "MUTATING_SQL", DETECTOR),
    Constant(
        "audit-append-only", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # audit-arguments
    Constant("audit-arguments", "ARGUMENTS_NAME", DETECTOR),
    Constant("audit-arguments", "AUDIT_EVENT", DETECTOR),
    Constant(
        "audit-arguments", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # authorization-builders
    Constant(
        "authorization-builders",
        "AUTHORIZATION_BUILDERS_EXEMPT",
        EXEMPTION,
        by=EACH,
        adr="ADR 0012 §7; ADR 0027",
    ),
    Constant("authorization-builders", "AUTHORIZATION_MODEL", DETECTOR),
    Constant(
        "authorization-builders", "AUTHORIZATION_READER", EXEMPTION, by=WHOLE, adr="ADR 0012 §7"
    ),
    Constant("authorization-builders", "AUTHORIZATION_WIDENING_FIELDS", DETECTOR),
    Constant(
        "authorization-builders",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # cli-over-the-api
    Constant(
        "cli-over-the-api",
        "CLI_DIR",
        SUBJECT,
        why=ARTEFACT,
        reason="the package the rule is about, on both sides of it: restricted, every module "
        'becomes "outside the CLI" and the rule reports itself',
    ),
    Constant("cli-over-the-api", "CLI_FORBIDDEN_INTERNAL", DETECTOR),
    Constant("cli-over-the-api", "CLI_PACKAGE", DETECTOR),
    Constant("cli-over-the-api", "CLI_SERVE", EXEMPTION, by=WHOLE, adr="ADR 0024 §7"),
    Constant("cli-over-the-api", "COMPOSED_NAMES", DETECTOR),
    Constant(
        "cli-over-the-api", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # concrete-names
    Constant("concrete-names", "CONCRETE_ALLOWED", EXEMPTION, by=EACH, adr="ADR 0023 §12"),
    Constant("concrete-names", "CORE_FORBIDDEN", DETECTOR),
    Constant("concrete-names", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    # constant-time-token
    Constant(
        "constant-time-token", "CONSTANT_TIME_COMPARE", EXEMPTION, by=WHOLE, adr="ADR 0026 §6"
    ),
    Constant(
        "constant-time-token", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant(
        "constant-time-token",
        "SECURITY_MODULE",
        SUBJECT,
        why=ARTEFACT,
        reason="the one file this rule reads: restricted, the rule has nothing to open and "
        "raises instead of speaking",
    ),
    Constant("constant-time-token", "TOKEN_NAMES", DETECTOR),
    # core-isolation
    Constant("core-isolation", "CORE_FORBIDDEN", DETECTOR),
    Constant("core-isolation", "CORE_PACKAGES", DETECTOR),
    Constant("core-isolation", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    # decide-callers
    Constant("decide-callers", "DECIDE_METHOD", DETECTOR),
    Constant("decide-callers", "PERMISSIONS_DIR", EXEMPTION, by=WHOLE, adr="ADR 0011"),
    Constant("decide-callers", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    # decision-builders
    Constant(
        "decision-builders", "DECISION_BUILDERS_EXEMPT", EXEMPTION, by=EACH, adr="ADR 0011 §11"
    ),
    Constant("decision-builders", "DECISION_MODEL", DETECTOR),
    Constant("decision-builders", "DENIED_OUTCOME", DETECTOR),
    Constant(
        "decision-builders", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # device-availability-readers
    Constant("device-availability-readers", "AVAILABILITY_FIELD", DETECTOR),
    Constant(
        "device-availability-readers",
        "DEVICES_DIR",
        EXEMPTION,
        by=WHOLE,
        adr="ADR 0016 §3; ADR 0017 §7",
    ),
    Constant(
        "device-availability-readers", "PERSISTENCE_MAPPERS", EXEMPTION, by=WHOLE, adr="ADR 0016 §3"
    ),
    Constant(
        "device-availability-readers",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # device-port-readers
    Constant(
        "device-port-readers",
        "DEVICE_PORT_ALLOWED",
        EXEMPTION,
        by=EACH,
        adr="ADR 0017 §9; ADR 0027",
    ),
    Constant("device-port-readers", "DEVICE_REGISTRY_PORT", DETECTOR),
    Constant(
        "device-port-readers", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # devices-isolation
    Constant("devices-isolation", "DEVICES_DIR", DETECTOR),
    Constant("devices-isolation", "DEVICES_FORBIDDEN", DETECTOR),
    Constant(
        "devices-isolation", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # domain
    Constant("domain", "DOMAIN_ALLOWED_EXTERNAL", EXEMPTION, by=EACH, adr="ADR 0002 §1"),
    Constant("domain", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    Constant("domain", "STDLIB", EXEMPTION, by=WHOLE, adr="ADR 0002 §1"),
    # infra-libraries
    Constant("infra-libraries", "INFRA_LIBRARIES", DETECTOR),
    Constant("infra-libraries", "INFRA_PACKAGES", EXEMPTION, by=EACH, adr="ADR 0002 §3"),
    Constant(
        "infra-libraries", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # orm-separation
    Constant("orm-separation", "DOMAIN_MODULE", DETECTOR),
    Constant("orm-separation", "ORM_PACKAGE", DETECTOR),
    Constant("orm-separation", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    # permissions-imports
    Constant(
        "permissions-imports", "PERMISSIONS_ALLOWED_EXTERNAL", EXEMPTION, by=EACH, adr="ADR 0010"
    ),
    Constant(
        "permissions-imports", "PERMISSIONS_ALLOWED_INTERNAL", EXEMPTION, by=EACH, adr="ADR 0010"
    ),
    Constant("permissions-imports", "PERMISSIONS_DIR", DETECTOR),
    Constant(
        "permissions-imports", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant("permissions-imports", "STDLIB", EXEMPTION, by=WHOLE, adr="ADR 0010"),
    # placement-builders
    Constant("placement-builders", "DEVICES_DIR", EXEMPTION, by=WHOLE, adr="ADR 0026 §5"),
    Constant("placement-builders", "PLACEMENT_DEVICE_FIELD", DETECTOR),
    Constant("placement-builders", "PLACEMENT_MODEL", DETECTOR),
    Constant(
        "placement-builders", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # ports
    Constant("ports", "PORTS_ALLOWED_INTERNAL", EXEMPTION, by=WHOLE, adr="ADR 0002 §2"),
    Constant("ports", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    Constant("ports", "STDLIB", EXEMPTION, by=WHOLE, adr="ADR 0002 §2"),
    # provider-complete-callers
    Constant("provider-complete-callers", "COMPLETE_METHOD", DETECTOR),
    Constant(
        "provider-complete-callers", "ENGINE_RECEIVERS", EXEMPTION, by=EACH, adr="ADR 0021 §5"
    ),
    Constant(
        "provider-complete-callers", "MODEL_TOOL_MODULE", EXEMPTION, by=WHOLE, adr="ADR 0021 §5"
    ),
    Constant(
        "provider-complete-callers",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # state-changes
    Constant("state-changes", "INITIAL_STATE", EXEMPTION, by=WHOLE, adr="ADR 0004"),
    Constant("state-changes", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    Constant("state-changes", "STATE_EXEMPT", EXEMPTION, by=EACH, adr="ADR 0004; ADR 0006"),
    # state-machine-callers
    Constant(
        "state-machine-callers", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant("state-machine-callers", "STATE_MACHINE_MODULE", DETECTOR),
    Constant("state-machine-callers", "TASKS_DIR", EXEMPTION, by=WHOLE, adr="ADR 0008"),
    # step-completers
    Constant("step-completers", "COMPLETE_STEP_METHOD", DETECTOR),
    Constant("step-completers", "EXECUTOR_MODULE", EXEMPTION, by=WHOLE, adr="ADR 0014 §9"),
    Constant(
        "step-completers", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # step-event-writers
    Constant(
        "step-event-writers", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant("step-event-writers", "STEP_EVENT_PREFIX", DETECTOR),
    Constant(
        "step-event-writers",
        "TASKS_DIR",
        EXEMPTION,
        by=WHOLE,
        adr="ADR 0009",
        proof="step-event-built-by-engine",
        reason="the Task Engine is the legitimate writer, and it is silent on the real tree "
        "only because it passes ``event_type=op.event_type`` from ``STEP_OPERATIONS`` — a "
        "variable the name heuristic cannot see (ADR 0027)",
    ),
    # testing-imports
    Constant(
        "testing-imports", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant("testing-imports", "STDLIB", EXEMPTION, by=WHOLE, adr="ADR 0002 §7"),
    Constant(
        "testing-imports",
        "TESTING_ALLOWED_INTERNAL",
        EXEMPTION,
        by=EACH,
        adr="ADR 0002 §7; ADR 0005",
    ),
    Constant("testing-imports", "TESTING_DIR", DETECTOR),
    # testing-isolation
    Constant(
        "testing-isolation", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant("testing-isolation", "TESTING_DIR", DETECTOR),
    Constant("testing-isolation", "TESTING_PACKAGE", DETECTOR),
    # tool-execute-callers
    Constant("tool-execute-callers", "EXECUTE_METHOD", DETECTOR),
    Constant("tool-execute-callers", "EXECUTOR_MODULE", EXEMPTION, by=WHOLE, adr="ADR 0013 §9"),
    Constant("tool-execute-callers", "EXECUTOR_RECEIVERS", EXEMPTION, by=EACH, adr="ADR 0019 §3"),
    Constant(
        "tool-execute-callers", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant("tool-execute-callers", "RUNNER_MODULE", EXEMPTION, by=WHOLE, adr="ADR 0019 §3"),
    Constant(
        "tool-execute-callers", "SQL_EXECUTORS", EXEMPTION, by=EACH, adr="ADR 0013 §9; ADR 0027"
    ),
    # capture-stays-on-the-machine (rule 35, ADR 0029 §12; extended M11.1 dec. H)
    Constant("capture-stays-on-the-machine", "CAPTURE_FORBIDDEN", DETECTOR),
    Constant("capture-stays-on-the-machine", "CAPTURE_MODULES", DETECTOR),
    Constant("capture-stays-on-the-machine", "VOICE_MODULES", DETECTOR),
    Constant(
        "capture-stays-on-the-machine",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # the-voice-writes-no-file (rule 40, M11.1 dec. 7)
    Constant("the-voice-writes-no-file", "VOICE_MODULES", DETECTOR),
    Constant("the-voice-writes-no-file", "VOICE_OUTPUT_FLAGS", DETECTOR),
    Constant(
        "the-voice-writes-no-file",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # context-is-not-recorded (rule 39, ADR 0032 §7)
    Constant("context-is-not-recorded", "CONTEXT_NOT_RECORDED", DETECTOR),
    Constant("context-is-not-recorded", "CONTEXT_SNAPSHOT", DETECTOR),
    Constant(
        "context-is-not-recorded",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # context-writes-nothing (rule 38, ADR 0032 §6)
    Constant("context-writes-nothing", "CONTEXT_DIR", DETECTOR),
    Constant("context-writes-nothing", "CONTEXT_WRITE_MEMBERS", DETECTOR),
    Constant(
        "context-writes-nothing",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # machine-access-in-one-place (rule 32, ADR 0028 §1)
    Constant("machine-access-in-one-place", "MACHINE_LIBRARIES", DETECTOR),
    Constant(
        "machine-access-in-one-place",
        "PERCEPTION_ADAPTER_DIR",
        EXEMPTION,
        by=WHOLE,
        adr="ADR 0028 §1",
    ),
    Constant(
        "machine-access-in-one-place",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    Constant("machine-access-in-one-place", "SPAWNING_CALLS", DETECTOR),
    Constant("machine-access-in-one-place", "SPAWNING_MODULES", DETECTOR),
    # perception-adapter-decides-nothing (rule 34, ADR 0028 §1)
    Constant("perception-adapter-decides-nothing", "PERCEPTION_ADAPTER_DIR", DETECTOR),
    Constant("perception-adapter-decides-nothing", "PERCEPTION_VOCABULARY", DETECTOR),
    Constant(
        "perception-adapter-decides-nothing",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # perception-children-import-only-stdlib (rule 33, ADR 0028 §2; M10.3 dec. 6)
    Constant("perception-children-import-only-stdlib", "MAIN_GUARD", DETECTOR),
    Constant("perception-children-import-only-stdlib", "PERCEPTION_ADAPTER_DIR", DETECTOR),
    Constant("perception-children-import-only-stdlib", "ROOT_PACKAGE", DETECTOR),
    # perception-reads-no-window-titles (rule 36, M10.3 dec. 3)
    Constant("perception-reads-no-window-titles", "PERCEPTION_ADAPTER_DIR", DETECTOR),
    Constant(
        "perception-reads-no-window-titles",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    Constant("perception-reads-no-window-titles", "WINDOW_TITLE_KEYS", DETECTOR),
    # platform-choice-is-a-statement (rule 37, ADR 0031)
    Constant("platform-choice-is-a-statement", "PLATFORM_WORDS", DETECTOR),
    Constant(
        "platform-choice-is-a-statement",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # tool-output-readers
    Constant("tool-output-readers", "API_DIR", DETECTOR),
    Constant("tool-output-readers", "OUTPUT_MODEL", EXEMPTION, by=WHOLE, adr="ADR 0025 §4"),
    Constant("tool-output-readers", "OUTPUT_NAME", DETECTOR),
    Constant("tool-output-readers", "OUTPUT_SCHEMAS", EXEMPTION, by=WHOLE, adr="ADR 0025 §4"),
    Constant(
        "tool-output-readers", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    # tools-routing-isolation
    Constant(
        "tools-routing-isolation",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    Constant("tools-routing-isolation", "ROUTING_PACKAGE", DETECTOR),
    Constant("tools-routing-isolation", "TOOLS_DIR", DETECTOR),
    # verifier-read-only
    Constant("verifier-read-only", "OPENERS", DETECTOR),
    Constant("verifier-read-only", "READ_ONLY_MODULES", DETECTOR),
    Constant(
        "verifier-read-only", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF
    ),
    Constant("verifier-read-only", "SHUTIL", DETECTOR),
    Constant("verifier-read-only", "WRITING_CALLS", DETECTOR),
    Constant("verifier-read-only", "WRITING_OPEN_FLAGS", DETECTOR),
    Constant("verifier-read-only", "WRITING_OPEN_MODES", DETECTOR),
)
"""Every (rule, constant) pair the rules read, one row each (ADR 0027).

Thirty-six doors, forty-seven detectors, thirty-three subjects — of which thirty-one are
``ROOT_PACKAGE``, read by every rule.
"""
