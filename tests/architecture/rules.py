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
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

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
MACHINE_ADAPTER_DIR = Path("infrastructure") / "machine"
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
    MACHINE_ADAPTER_DIR / "textrecognition.py",
    MACHINE_ADAPTER_DIR / "vision.py",
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
#: The name **was** narrower than the rule — it said "capture" and held the voice too — and M11.2
#: paid that debt: the rule is ``content-stays-on-the-machine``, and the three ADRs that name the
#: old id keep naming it, resolved through :data:`RENAMED_RULES`. The tuples stayed separate
#: through the rename, which is the whole point of them.
VOICE_MODULES = (
    Path("tools") / "voice.py",
    Path("tools") / "voice_online.py",
    MACHINE_ADAPTER_DIR / "speech.py",
    MACHINE_ADAPTER_DIR / "audition.py",
)

#: M11.2: the same rule again, over the modules that hold **what ELA hears** — and this is the
#: fourth kind of the user's content to pass under it, after the pixels, the text of a capture and
#: ELA's own words. It is also the first that contains **people who are not the user**: a screen
#: capture photographs what the user chose to have in front of them, a recording takes whoever was
#: in the room, including somebody who never consented and does not know.
#:
#: **A third tuple, and for the reason the second one exists** (ADR 0033 §7): the halves have to be
#: reopenable one at a time. A milestone that one day sends ELA's words to a speech provider must
#: not be able to open the microphone's half by editing one list, and the reverse holds too. One
#: constant for all three would make every reopening a reopening of everything.
#:
#: Written **before** the modules exist, which is ADR 0030 §15 applied a fourth time: a defence
#: written after the thing it defends has a window in which the thing exists and the defence does
#: not, and in that window review looks at the new code and not at the missing rule.
LISTENING_MODULES = (
    Path("tools") / "listen.py",
    MACHINE_ADAPTER_DIR / "listening.py",
    MACHINE_ADAPTER_DIR / "microphone.py",
)

#: Rule 45 (M11.2 dec. E): **what ELA hears never gets a name.** The audio is the raw material and
#: the transcript is the useful datum, and M11.2 decided the raw material is not kept: it lives on
#: an anonymous inode — ``mkstemp`` then ``unlink`` at once, the transcriber given ``/dev/fd/N`` —
#: which is ADR 0034 §7's mechanism, reused for the direction it was not built for. The kernel
#: frees it when the descriptor closes, **even if ELA dies mid-recording**.
#:
#: Between that and a directory holding every conversation that ever happened near this machine
#: there is one missing ``unlink``, and this audio is the first of ELA's data that contains
#: **people who are not the user**.
#:
#: **Narrower than** :data:`LISTENING_MODULES` **on purpose:** ``tools/listen.py`` holds the
#: transcript, not the audio, and hands it to the store that writes it — legitimately, with a name
#: and an expiry. The rule is about the two modules the samples pass through, and so it needs no
#: exemption: the nameless file is made in ``darwin.py``, where the door to the operating system
#: already is (rule 32) and which is not a subject here. A rule with an exemption is a rule
#: somebody widens.
HEARD_AUDIO_MODULES = (
    MACHINE_ADAPTER_DIR / "listening.py",
    MACHINE_ADAPTER_DIR / "microphone.py",
)


#: Rules 41 and 45: **nothing that passes through this machine's speakers or microphone
#: survives with a name.** Named for the voice until M11.2, when the listening began reading
#: it too — one detector, two rules, and a name that describes what it detects.
#:
#: Rule 41 (M11.3 dec. F and G): **nothing ELA says survives with a name.** Rule 40 keeps the
#: local voice off the disk by forbidding ``say -o``; the online voice cannot be held that way,
#: because ``afplay`` refuses a pipe and a FIFO (measured: ``AudioFileOpen -40``) and the audio
#: must therefore be a *file* for as long as it takes to play it. What makes that acceptable is
#: that the file has **no name**: ``mkstemp`` then ``unlink`` at once, and the child receives
#: ``/dev/fd/N``. The rule is the difference between that and a directory of everything ELA has
#: ever said, which is one forgotten ``unlink`` away.
#:
#: Reads calls, not imports, for the reason rules 36 and 40 do: ``tempfile`` is a perfectly
#: ordinary import and the whole question is what happens on the next line.
#:
#: **No exception, and that is why the file lives elsewhere.** The nameless file is made by
#: ``spawn_with_audio`` in :mod:`ela.infrastructure.machine.darwin`, which is where the door
#: to the operating system already is (rule 32) and which holds no words of ELA's — so the
#: modules that *do* hold them can be told, with no allowance to remember, that they never touch
#: a filesystem. A rule with an exemption is a rule somebody widens; this one has none.
NAMED_FILE_WRITERS = frozenset(
    {
        "write_bytes",
        "write_text",
        "mkstemp",
        "mkdtemp",
        "NamedTemporaryFile",
        "TemporaryFile",
        "copyfile",
        "copy",
        "copy2",
    }
)
#: ``open(path, "w")`` and its relatives. ``open`` for reading is not the rule's business.
WRITE_MODES = frozenset({"w", "a", "x", "+"})

#: Rule 42 (M11.3 dec. H): **the voice goes only where it is declared.** One host, written as a
#: constant in the adapter, and no way to point it somewhere else without editing the file — a
#: base URL that came from configuration would be a way to redirect what ELA says to another
#: server with nobody able to see it in a diff. The same sentence as ADR 0029 §3 about the
#: absolute path of ``say``: *what speaks for the user must not be decided by an environment
#: variable.*
#:
#: The rule also keeps the reach of the adapter inside itself: it may hold ``httpx`` — that is
#: what it is for — and it may not hold a router or a provider registry, so the one module of ELA
#: that is allowed to send the user's words out cannot also be the module that decides where
#: they go.
ELEVENLABS_ENDPOINT = "https://api.elevenlabs.io"
#: What makes a string an address rather than a word: the scheme separator.
SCHEME_SEPARATOR = "://"
#: Names that turn an endpoint into a setting. Class-level annotations only: a local ``url`` built
#: from the constant is the ordinary way to write a request.
VOICE_ENDPOINT_FIELDS = frozenset({"base_url", "api_base", "endpoint", "host"})
#: Reading the environment directly is the other way to make the host configurable — and the
#: settings of ELA go through pydantic, never through ``os.environ`` (ADR 0001).
VOICE_ENVIRONMENT_READS = frozenset({"environ", "getenv"})

#: Rule 43 (M11.3 dec. I and J): **the audition says only what the repository says.** Hearing six
#: voices must not become a way to speak arbitrary text without a capability: what leaves the
#: machine during an audition is a literal anybody can read in ``git``, and the shape that keeps
#: it true is that no function on that path accepts text at all. It can fire, which is the only
#: reason to have it (ADR 0026 §7): ``--text`` is the obvious feature of tomorrow.
AUDITION_MODULE = MACHINE_ADAPTER_DIR / "audition.py"
AUDITION_TEXT_PARAMETERS = frozenset({"text", "phrase", "phrases", "message", "say", "words"})

#: Rule 44 (M6.1b dec. H, ADR 0035 §4): **a refresh touches only what is declared.** The row of a
#: node has two halves — what whoever composes ELA knows without probing anything (the name, the
#: system, the network, the privacy, the traits, the tools) and what only the heartbeat observes
#: (availability, the last sign of life, the status, the workload). A re-registration rewrites the
#: first and must not touch the second, or a node that was available becomes unavailable until the
#: next heartbeat — a hole opened by an update whose whole point was to keep the node usable.
#:
#: The error has a shape, and it is the obvious one: rebuild the row with ``local_device(...)``,
#: which is right for a **birth** — it sets ``UNKNOWN`` and ``None`` because nothing has been heard
#: yet — and wrong for an **update**. So the rule bans, in the module that builds the reconciled
#: row, both every name that is not declared and the birth constructor itself.
#:
#: Closed-world on names, like rules 5, 12, 15, 16, 20 and 23: a constant, an attribute, a keyword
#: or a bare name, because a field can be written through any of the four and a rule that read only
#: imports would be silent on all of them. It can fire — the shape it forbids is the shortest way to
#: write the reconciliation, which is the reason ADR 0026 §7 asks of every rule.
REFRESH_MODULE = Path(DEVICES_DIR) / "refresh.py"
#: The half the registry writes and no node declares: the observed half of ADR 0037 §10, which
#: M12.1 widened with ``network`` and ``power_source`` (ADR 0035 §2 had the first four).
OBSERVED_FIELDS = frozenset(
    {"availability", "last_seen_at", "status", "current_workload", "network", "power_source"}
)
#: Rule 44, extended by M12.1 (ADR 0037 §10, §16): what is not declared beyond the observed half —
#: the level the user imposed at enrollment, and the state of the node's identity. The builder of
#: the declared half is also the road of a remote announcement, so it must not name these either.
NOT_DECLARED_FIELDS = frozenset({"privacy", "revoked_at", "revision"})
#: The constructor of a *new* row: right for a birth, and a reset for everything else.
BIRTH_CONSTRUCTOR = "local_device"

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
#: Written once because rule 42 subtracts it: the voice adapter of M11.3 is the single module
#: allowed to hold an HTTP client, and "allowed to hold *this*" has to name the same string the
#: ban names, or the exception drifts away from the rule it is an exception to.
HTTP_CLIENT = "httpx"
CAPTURE_FORBIDDEN = frozenset(
    {"ModelRouter", "ModelRouterPort", "ProviderRegistry", "ProviderRegistryPort", HTTP_CLIENT}
)
#: Rule 42's half of the same ban: what rule 35 forbids everywhere else, minus the one thing the
#: voice adapter exists to hold. Written as its own constant rather than subtracted inside the
#: rule, so the door is something a reader looks at and not an expression in a function body
#: (ADR 0027).
VOICE_PROVIDER_FORBIDDEN = CAPTURE_FORBIDDEN - {HTTP_CLIENT}

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
TOKEN_NAMES = frozenset({"token", "presented", "node_secret", "presented_hash", "secret_hash"})
#: The secret of a node, in every name M12.1 gives it: what the node presents, its SHA-256, the hash
#: the registry keeps, the enrollment code and its hash (M12.1 dec. D, E). Read by two rules. By
#: rule 31, extended, through :data:`COMPARED_SECRET_NAMES`. By
#: rule 46: never inside an ``AuditEvent``, a wire shape of the API, or the entity every reader of
#: the registry holds. The names do not exist yet: the rules are written before the code (ADR 0030
#: §15), so the day it exists it is born inside the fence.
NODE_SECRET_NAMES = frozenset(
    {"node_secret", "presented_hash", "secret_hash", "enrollment_code", "code_hash"}
)
#: Rule 31, extended (ADR 0037 §16): the names of a node's secret that no module but
#: :data:`SECURITY_MODULE` compares **by value** — ``is None`` stays allowed anywhere, because
#: asking whether a hash exists says nothing about it. Not the enrollment code's: dec. D finds a
#: code by its hash, in the conditional ``UPDATE`` that spends it (``WHERE code_hash = :h``, ADR
#: 0037 §5), and a lookup by the hash of a 256-bit value can leak at most the hash, which is not
#: the code. A node is found by its id instead, and its hash is compared in the middleware.
COMPARED_SECRET_NAMES = frozenset({"node_secret", "presented_hash", "secret_hash"})
#: Rule 46 (M12.1): the three readable boundaries a node's secret must not cross. ``api/schemas.py``
#: is where every wire shape of the API is declared; ``Device`` is the entity the registry hands to
#: every reader — the orchestrator, ``/devices``, the context — so a hash on it would be read by
#: all of them. The ORM row may hold the hash (M12.1 dec. G): it is not a boundary, it is the vault.
#: A path, and so not :data:`DOMAIN_MODULE`, which is the dotted name rule 8 reads.
WIRE_SHAPES = Path("api") / "schemas.py"
#: Rule 46 (M12.1), in :data:`WIRE_SHAPES` only: the names the wire gives the two things §5 hands
#: out once — the enrollment code and the node's secret, ``{device_id, secret, revision}``
#: (ADR 0037 §5). Without them the two answers that carry them would be invisible to the rule that
#: must open their door, and a third shape that carried one would pass in silence.
WIRE_SECRET_NAMES = frozenset({"code", "secret"})
#: Rule 46 (M12.1), the door: the two answers of :data:`WIRE_SHAPES` that hand out, once, the code
#: and the secret (ADR 0037 §5) — and only for :data:`WIRE_SECRET_NAMES`. A hash on either of them
#: is still reported: what they may carry is the value handed out, never what ELA keeps.
ONCE_SECRET_SHAPES = frozenset({"EnrollmentCodeOut", "EnrolledOut"})
ENTITIES_FILE = Path("domain.py")
DEVICE_ENTITY = "Device"
#: Rule 47 (M12.1): who is calling is decided in one place — the middleware of
#: :data:`SECURITY_MODULE` — and every route reads the identity it resolved, never the header it
#: came in. Silent on today's tree, and its silence is asserted: it guards a door nobody has opened
#: yet, which D12 opens — the routes of approvals and cancellation will read the identity, and the
#: shortest way to write that is to read it from the header.
AUTHORIZATION_HEADER = "authorization"
#: Rule 48 (M12.2, ADR 0038): the port of the assignments returns the row *as written* — ``OFFERED``
#: even when it has expired — and whoever decides goes through the service, which derives the
#: expiry and writes the task's heartbeat before every expiry it sets (dec. G). The mirror of rule
#: 21, for the same reason as ADR 0016 §3. Born with no exemption: nobody names the port yet, and a
#: door opens with the code behind it (ADR 0027 §3).
ASSIGNMENT_PORT = f"{ROOT_PACKAGE}.ports.AssignmentStore"
#: Rule 49 (M12.2, ADR 0038): an assignment names a node and carries a bearer title, and one built
#: by hand skips ``ensure_placed`` and every check on the decision. The mirror of rule 30: «a
#: defence that can be bypassed by building by hand the object it defends is not a defence» (ADR
#: 0026 §5).
ASSIGNMENT_MODEL = "Assignment"
#: Rules 49, 51, 52 (M12.2): besides the call of the class, the doors pydantic leaves open to build
#: a model — one of them, ``model_construct``, without even validating it.
MODEL_CONSTRUCTORS = frozenset({"model_validate", "model_validate_json", "model_construct"})
#: Rule 50 (M12.2, ADR 0038): the engine cannot know whether the store holds anything for a step,
#: and releasing a step somebody may have run is the double execution the protocol exists to
#: prevent. The guard lives in the caller, so the caller is one. The mirror of rule 10 (ADR 0008
#: §12).
RELEASE_METHOD = "release_step"
#: Rule 51 (M12.2, ADR 0038, dec. N): an order carries the user's arguments to a node, and its one
#: way out is the answer to the request of the node it was assigned to. The composer of
#: :data:`WORK_ORDER_COMPOSER` builds it and no other module does, and the composer imports no
#: network client: that is the half an AST can see. The other half — the two ids compared — is a
#: test at runtime (criterion 21). Rule 35 does not look at ``ela.api``, and rule 3 lets it import
#: network libraries: this rule is the difference.
WORK_ORDER_MODEL = "WorkOrderOut"
WORK_ORDER_COMPOSER = Path("api") / "nodes.py"
NETWORK_CLIENTS = frozenset({"httpx", "urllib.request", "http.client", "socket"})
#: Rule 52 (M12.2, ADR 0038, dec. B): the node delivers an envelope, a DTO, and the Core mints the
#: result — an id derived from the assignment, a time from its own clock (M12.1, D1, D7). A route
#: that built the entity from the envelope would pass every other test and put the node's id and
#: the node's clock into the store and the chain of §32.
RESULT_MODEL = "ExecutionResult"

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

#: M11.3: where the words of ELA are put on the wire. Separate from :data:`VOICE_MODULES` because
#: this is the half ADR 0033 §7 promised M11.3 could reopen — **and only this half**: here
#: ``httpx`` is the job, so rule 35 cannot hold, and what holds instead is rule 42, which is
#: narrower and says where those words may go.
ELEVENLABS_ADAPTER_DIR = Path(PROVIDERS_DIR) / "elevenlabs"

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

    **Extended by M12.1 (dec. E)** to the secret of a node, which is compared the same way and in
    the same place: :data:`TOKEN_NAMES` learns its names, so inside the module a ``==`` on them is
    reported like one on the token; and **outside** the module, any comparison *by value* — ``==``,
    ``!=``, ``in``, ``not in`` — that names one of :data:`COMPARED_SECRET_NAMES` is reported too. A
    second place that compares a secret is a second place that can compare it in variable time.
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
    for other in _source_files(pkg_root):
        if other == path:
            continue
        found.extend(
            Violation(
                rule,
                module_name(other, pkg_root),
                f"{_operator(node)} on a node's secret",
                node.lineno,
            )
            for node in ast.walk(ast.parse(other.read_text(encoding="utf-8"), filename=str(other)))
            if isinstance(node, ast.Compare) and _compares_a_secret_by_value(node)
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


def _compares_a_secret_by_value(node: ast.Compare) -> bool:
    """A ``==``/``!=``/``in``/``not in`` with a node's secret on either side (rule 31, M12.1).

    :data:`COMPARED_SECRET_NAMES` and not all of :data:`NODE_SECRET_NAMES`: the enrollment code is
    looked up by its hash in SQL, which is what dec. D asks for (ADR 0037 §5, §16).
    """
    return isinstance(node.ops[0], (ast.Eq, ast.NotEq, ast.In, ast.NotIn)) and any(
        _names_a_node_secret(operand) in COMPARED_SECRET_NAMES
        for operand in [node.left, *node.comparators]
    )


def _names_a_node_secret(node: ast.AST) -> str | None:
    """How ``node`` names a node's secret — a name, an attribute, a keyword, a string — or ``None``.

    Through a call as well (``secret_hash.hex()``), the way :func:`_names_the_token` follows
    ``token.encode()``: the secret does not stop being the secret because a method was called on it.
    """
    if isinstance(node, ast.Name) and node.id in NODE_SECRET_NAMES:
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr if node.attr in NODE_SECRET_NAMES else _names_a_node_secret(node.value)
    if isinstance(node, ast.Call):
        return _names_a_node_secret(node.func)
    if isinstance(node, ast.keyword) and node.arg in NODE_SECRET_NAMES:
        return node.arg
    if isinstance(node, ast.Constant) and node.value in NODE_SECRET_NAMES:
        return str(node.value)
    return None


def check_machine_access(pkg_root: Path) -> list[Violation]:
    """Rule 32: only ``ela.infrastructure.machine`` reaches the operating system (ADR 0028 §1).

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
        if not path.is_relative_to(pkg_root / MACHINE_ADAPTER_DIR)
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
    return [path for path in _source_files(pkg_root / MACHINE_ADAPTER_DIR) if _is_child(path)]


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
    for path in _source_files(pkg_root / MACHINE_ADAPTER_DIR):
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


def _voice_paths(pkg_root: Path) -> list[Path]:
    """Every module that holds what ELA says, on either side of the wire (rules 41 and 42)."""
    named = [pkg_root / relative for relative in VOICE_MODULES]
    return [path for path in named if path.is_file()] + list(
        _source_files(pkg_root / ELEVENLABS_ADAPTER_DIR)
    )


def _writes_a_named_file(node: ast.AST) -> str | None:
    """The name of the file-writing call ``node`` is, or ``None``.

    ``open`` counts only with a writing mode: reading a file is nobody's business here, and a
    rule that reported every ``open`` would be turned off by the first person who needed one.
    """
    if not isinstance(node, ast.Call):
        return None
    called = node.func.attr if isinstance(node.func, ast.Attribute) else None
    called = called or (node.func.id if isinstance(node.func, ast.Name) else None)
    if called in NAMED_FILE_WRITERS:
        return called
    if called != "open":
        return None
    modes = [arg.value for arg in node.args[1:2] if isinstance(arg, ast.Constant)]
    modes += [
        kw.value.value
        for kw in node.keywords
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant)
    ]
    if any(isinstance(mode, str) and set(mode) & WRITE_MODES for mode in modes):
        return "open"
    return None


def check_the_voice_leaves_no_named_file(pkg_root: Path) -> list[Violation]:
    """Rule 41: nothing ELA says survives with a name (M11.3 dec. F, G).

    Rule 40 could say it in one word — the local voice never writes, because ``say`` speaks by
    itself and only ``-o`` would make it write. The online voice has no such luck: the audio
    arrives as bytes, and ``afplay`` cannot read a pipe or a FIFO. Measured, both of them:
    ``AudioFileOpen failed (-40)``. So there **is** a file, and what makes that acceptable is
    that it has no name — ``mkstemp`` and then ``unlink`` immediately, with the child given
    ``/dev/fd/N``. An inode nobody can open by path, freed when the descriptor closes, and freed
    even if ELA dies mid-sentence.

    Between that and a directory holding everything ELA has ever said there is one missing
    ``unlink``, and the rule does not try to check that pairing by reading: it puts the pairing
    somewhere else entirely. ``spawn_with_audio`` in
    :mod:`ela.infrastructure.machine.darwin` makes the nameless file, spawns the player and
    closes the descriptor in a ``finally`` — one function, in the module that already owns the
    door to the operating system (rule 32), holding no words of ELA's. Everything that *does*
    hold them may not touch a filesystem at all, which is a rule with no allowance to widen.
    """
    rule = "the-voice-leaves-no-named-file"
    found: list[Violation] = []
    for path in _voice_paths(pkg_root):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, written, node.lineno)
            for node in ast.walk(tree)
            if (written := _writes_a_named_file(node)) is not None
        )
    return found


def check_what_ela_hears_leaves_no_named_file(pkg_root: Path) -> list[Violation]:
    """Rule 45: the audio of a recording never gets a name (M11.2 dec. E).

    Rule 41 says it for what ELA *says*; this says it for what ELA *hears*, and it is a rule of
    its own rather than an extension because ``the-voice-leaves-no-named-file`` would then be the
    fourth name in this repository narrower than the thing it names — three commits after M11.2
    paid off two of them.

    The two are not symmetrical, either. What ELA says it composed itself; what ELA hears it took
    from a room, and a room contains people who never agreed to be recorded and do not know they
    were. That is the difference the rule is protecting, and it is why the subject is the modules
    the **samples** pass through and not the module that holds the transcript.

    Reads calls and not imports, for the reason rules 36, 40 and 41 do: ``tempfile`` is a
    perfectly ordinary import and the whole question is what happens on the next line.
    """
    rule = "what-ela-hears-leaves-no-named-file"
    found: list[Violation] = []
    for relative in HEARD_AUDIO_MODULES:
        path = pkg_root / relative
        if not path.is_file():
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, written, node.lineno)
            for node in ast.walk(tree)
            if (written := _writes_a_named_file(node)) is not None
        )
    return found


def check_the_voice_goes_only_where_it_is_declared(pkg_root: Path) -> list[Violation]:
    """Rule 42: the adapter talks to one host, and it is written here (M11.3 dec. H).

    This is the module M11.3 opened in rule 35's fence, and it is opened for exactly one thing:
    ``httpx`` towards ``api.elevenlabs.io``. Three ways that opening could quietly become
    something else, and each is reported:

    * **another address** — any string literal carrying a scheme separator that is not the
      constant. Not "starting with ``http``", which was the first spelling and was wrong in a way
      worth keeping: it also caught the word ``"https"`` used to *check* a scheme, so the adapter
      would have had to weaken the rule in order to validate a URL. An address is the thing with
      a ``://`` in it;
    * **a configurable host** — a field called ``base_url``, ``endpoint``, ``host``…, which would
      put the destination of ELA's words in an environment variable, where no diff shows it;
    * **the environment read directly** — the same move, one layer down.

    And the reach stays narrow: the one module allowed to send the user's words out must not also
    be the module that chooses where they go, so a router and a provider registry are as
    forbidden here as they are in :data:`VOICE_MODULES`.
    """
    rule = "the-voice-goes-only-where-it-is-declared"
    forbidden = VOICE_PROVIDER_FORBIDDEN
    files = list(_source_files(pkg_root / ELEVENLABS_ADAPTER_DIR))
    found = _violations(
        rule, files, pkg_root, lambda imported: imported.rpartition(".")[2] in forbidden
    )
    for path in files:
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if SCHEME_SEPARATOR in node.value and node.value != ELEVENLABS_ENDPOINT:
                    found.append(Violation(rule, name, node.value, node.lineno))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in VOICE_ENDPOINT_FIELDS:
                    found.append(Violation(rule, name, node.target.id, node.lineno))
            elif isinstance(node, ast.Attribute) and node.attr in (
                VOICE_ENVIRONMENT_READS | forbidden
            ):
                found.append(Violation(rule, name, node.attr, node.lineno))
    return found


def check_the_audition_speaks_only_the_repositorys_words(pkg_root: Path) -> list[Violation]:
    """Rule 43: an audition says the two sentences of §9 and nothing anybody typed (M11.3 dec. I).

    Hearing six voices cannot be allowed to become a way of saying arbitrary things out loud,
    and over the network, without a capability. What leaves the machine during an audition is a
    literal that is in the repository and in nobody's private context — and the shape that keeps
    that true is not a comment but an absence: **no function on the audition path takes text.**

    Reported: a parameter that would carry words. The audition chooses a voice and a model, which
    are names, and never a sentence.
    """
    rule = "the-audition-speaks-only-the-repositorys-words"
    path = pkg_root / AUDITION_MODULE
    if not path.is_file():
        return []
    name = module_name(path, pkg_root)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        arguments = node.args
        every = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            arguments.vararg,
            arguments.kwarg,
        ]
        found.extend(
            Violation(rule, name, argument.arg, argument.lineno)
            for argument in every
            if argument is not None and argument.arg in AUDITION_TEXT_PARAMETERS
        )
    return found


def check_a_refresh_touches_only_what_is_declared(pkg_root: Path) -> list[Violation]:
    """Rule 44: the row a re-registration writes names no field the heartbeat owns (M6.1b dec. H).

    ``ensure_local`` stopped being "register it once" in M6.1b: it reads the row, compares the
    declared half against what this process declares, and writes when they differ (ADR 0035 §2).
    What it must never rewrite is the other half — ``availability``, ``last_seen_at``, ``status``,
    ``current_workload`` — because those say what was *observed* of the node, and a start-up that
    reset them would make the node unavailable until the next heartbeat: an update whose only
    purpose is to keep the node usable would be the thing that stops it being used.

    Reported, in the module that builds the reconciled row: any of the names of
    :data:`OBSERVED_FIELDS` or :data:`NOT_DECLARED_FIELDS`, however it is written — a payload key,
    an attribute, a keyword, a bare name — and any mention of
    :func:`~ela.devices.local.local_device`, which builds a birth and would reset the observed half
    at once. That call is the shortest way to write this function and the reason the rule exists.

    **Extended by M12.1** (ADR 0037 §10, §16). The rule's name says "a refresh touches only what is
    declared", but it forbade only the observed half. With the imposed half and the identity, what
    is not declared grew — ``network`` and ``power_source`` joined the observed half, and
    ``privacy``, ``revoked_at`` and ``revision`` are nobody's to restate — and the builder of the
    declared half became the road of a remote announcement too. The extension entered with the
    commit that took ``network`` and ``privacy`` out of ``DECLARED_FIELDS``: before it, the rule
    would have been born red, and a rule born red defends nothing.
    """
    rule = "a-refresh-touches-only-what-is-declared"
    path = pkg_root / REFRESH_MODULE
    if not path.is_file():
        return []
    name = module_name(path, pkg_root)
    found: list[Violation] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        named = _names_what_is_not_declared(node)
        if named is not None:
            found.append(Violation(rule, name, named, node.lineno))
    return found


def _names_what_is_not_declared(node: ast.AST) -> str | None:
    """How ``node`` reaches a field no node declares, or ``None`` if it does not."""
    forbidden = OBSERVED_FIELDS | NOT_DECLARED_FIELDS
    if isinstance(node, ast.Constant) and node.value in forbidden:
        return str(node.value)
    if isinstance(node, ast.Attribute) and node.attr in forbidden:
        return node.attr
    if isinstance(node, ast.keyword) and node.arg in forbidden:
        return node.arg
    if isinstance(node, ast.Name) and node.id in forbidden | {BIRTH_CONSTRUCTOR}:
        return node.id
    return None


def check_adapter_names_no_state(pkg_root: Path) -> list[Violation]:
    """Rule 34: the perception adapter never names a domain state (ADR 0028 §1).

    The coverage gate covers what can be run on a runner, and no runner has a webcam. The
    adapter's exemption is therefore paid for structurally: it hands over primitives — an ``int``
    for an ``AVAuthorizationStatus``, ``None`` for "not read" — and :func:`ela.perception.interpret`
    decides what they mean, inside the package the gate does cover.

    Reported as an *import* and as a *name*: a module that never imports ``SensorState`` cannot
    build one, and one that mentions it by attribute is reaching for the same words the long way.
    """
    rule = "machine-adapter-decides-nothing"
    found = _violations(
        rule,
        _source_files(pkg_root / MACHINE_ADAPTER_DIR),
        pkg_root,
        lambda imported: imported.rpartition(".")[2] in PERCEPTION_VOCABULARY,
    )
    for path in _source_files(pkg_root / MACHINE_ADAPTER_DIR):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, node.attr, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in PERCEPTION_VOCABULARY
        )
    return found


def check_content_stays_on_the_machine(pkg_root: Path) -> list[Violation]:
    """Rule 35: nothing that holds the user's content can send it anywhere (ADR 0029 §12).

    M10.2's whole promise is that the image does not leave this machine: no OCR, no provider, no
    network. A promise like that is worth what the thing that holds it is worth, so it is held by
    the shape of the code — :mod:`ela.tools.screen` and :mod:`ela.tools.captures` do not name a
    router, a provider registry or an HTTP client, by import or by attribute.

    Not a rule about tools in general: ``ela.tools.model`` names the router on purpose and must.
    It is a rule about the modules that have the user's content in their hands.

    M10.3 reopened it, examined it and **confirmed** it: nothing goes out. M11.1 extended it in a
    direction the old name did not describe — :data:`VOICE_MODULES`, which hold **what ELA says**,
    and whose words come from the same places the capture's text does. The subjects are separate
    constants on purpose: M11.3 had to be able to open the voice's half without opening the
    screen's, and one list would have made that a single careless edit.

    **Named ``capture-stays-on-the-machine`` until M11.2**, which is where a fourth kind of the
    user's content — what ELA *hears* — made the word "capture" plainly wrong instead of merely
    narrow. The ADRs that gave it the old name keep it; :data:`RENAMED_RULES` is how they still
    resolve. :data:`LISTENING_MODULES` is the third subject, separate for the reason the second
    one is.
    """
    rule = "content-stays-on-the-machine"
    paths = [
        pkg_root / relative for relative in (*CAPTURE_MODULES, *VOICE_MODULES, *LISTENING_MODULES)
    ]
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


def check_a_nodes_secret_crosses_no_readable_boundary(pkg_root: Path) -> list[Violation]:
    """Rule 46: a node's secret enters no audit event, no wire shape, and not the entity (M12.1).

    The shape of rule 23, for a value worse than an argument: an argument is the user's content,
    and a node's secret is the key to speaking to ELA as a machine the user trusted. Whoever reads
    the audit, a response of the API, or a ``Device`` must not be able to read it — and the audit
    is the worst of the three, because it is append-only: a secret written there is written for
    ever, and revoking the node would not unwrite it.

    Reported, for any of :data:`NODE_SECRET_NAMES` as a name, an attribute, a keyword or a string:
    anywhere inside an ``AuditEvent(...)`` call in the package; anywhere in ``api/schemas.py`` —
    where :data:`WIRE_SECRET_NAMES`, the names the wire gives them, count too; and as a field of
    ``Device`` in ``domain.py``. **One door**, :data:`ONCE_SECRET_SHAPES`: the two answers that hand
    a node its code and its secret, once (ADR 0037 §5), opened by the commit that wrote them — and
    only for the wire names, so a hash on either is still reported.
    """
    rule = "a-nodes-secret-crosses-no-readable-boundary"
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
            found.extend(
                Violation(rule, name, named, node.lineno)
                for node in ast.walk(call)
                if (named := _names_a_node_secret(node)) is not None
            )
    shapes = pkg_root / WIRE_SHAPES
    if shapes.is_file():
        tree = ast.parse(shapes.read_text(encoding="utf-8"), filename=str(shapes))
        handed_out = {
            id(node)
            for shape in ast.walk(tree)
            if isinstance(shape, ast.ClassDef) and shape.name in ONCE_SECRET_SHAPES
            for node in ast.walk(shape)
        }
        found.extend(
            Violation(rule, module_name(shapes, pkg_root), named, node.lineno)
            for node in ast.walk(tree)
            if (
                named := _names_a_node_secret(node)
                or (None if id(node) in handed_out else _names_a_wire_secret(node))
            )
            is not None
        )
    entities = pkg_root / ENTITIES_FILE
    if not entities.is_file():
        return found
    for entity in ast.walk(ast.parse(entities.read_text(encoding="utf-8"), filename=str(entities))):
        if isinstance(entity, ast.ClassDef) and entity.name == DEVICE_ENTITY:
            found.extend(
                Violation(rule, module_name(entities, pkg_root), field.target.id, field.lineno)
                for field in entity.body
                if isinstance(field, ast.AnnAssign)
                and isinstance(field.target, ast.Name)
                and field.target.id in NODE_SECRET_NAMES
            )
    return found


def _names_a_wire_secret(node: ast.AST) -> str | None:
    """How ``node`` names a secret by its name on the wire (:data:`WIRE_SECRET_NAMES`)."""
    if isinstance(node, ast.Name) and node.id in WIRE_SECRET_NAMES:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in WIRE_SECRET_NAMES:
        return node.attr
    if isinstance(node, ast.keyword) and node.arg in WIRE_SECRET_NAMES:
        return node.arg
    if isinstance(node, ast.Constant) and node.value in WIRE_SECRET_NAMES:
        return str(node.value)
    return None


def check_identity_resolved_in_one_place(pkg_root: Path) -> list[Violation]:
    """Rule 47: no module of ``ela.api`` but the middleware reads the ``Authorization`` header.

    M12.1 (D10, D12): the middleware of ``api/security.py`` recognises three identities — the
    Core's token, a node's secret, an enrollment code on its own route — and hands the identity it
    resolved to the route. A route that read the header itself would be a second place where
    *who is calling* is decided, and the second place is the one that forgets the revocation.

    Reported: the header's name, as a string in any case, in every module under ``api/`` except
    the middleware. Silent on today's tree, where the middleware is the only reader
    (``api/security.py``), and asserted silent: the rule is written before the routes that will
    want to know who called (ADR 0030 §15).
    """
    rule = "identity-resolved-in-one-place"
    found: list[Violation] = []
    for path in sorted((pkg_root / API_DIR).rglob("*.py")):
        if path == pkg_root / SECURITY_MODULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, module_name(path, pkg_root), AUTHORIZATION_HEADER, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.lower() == AUTHORIZATION_HEADER
        )
    return found


def check_assignment_port_readers(pkg_root: Path) -> list[Violation]:
    """Rule 48: no module imports ``AssignmentStore``; the assignments are reached through the
    service that derives their expiry (M12.2, ADR 0038).

    The port returns the row as it is written, and an ``OFFERED`` row may have expired an hour ago:
    the reading that counts is the service's, which says what the row is *now* (ADR 0016 §3,
    applied to a second deadline). And every expiry the service sets is preceded by a heartbeat of
    the task, which is what keeps ``recover()`` from failing a task whose work is still out (dec.
    G) — a route that wrote the row through the port would set an expiry with no sign of life in
    front of it. The mirror of rule 21. Silent on today's tree, where nobody names the port.
    """
    return _violations(
        "assignments-reached-only-through-the-service",
        _source_files(pkg_root),
        pkg_root,
        lambda imported: _is_within(imported, ASSIGNMENT_PORT),
    )


def _builds(callee: ast.expr, model: str) -> str | None:
    """How a call builds ``model`` — the class called, or a constructor pydantic gives it."""
    if _is_named(callee, model):
        return f"{model}(...)"
    if (
        isinstance(callee, ast.Attribute)
        and callee.attr in MODEL_CONSTRUCTORS
        and _is_named(callee.value, model)
    ):
        return f"{model}.{callee.attr}(...)"
    return None


def check_assignment_builders(pkg_root: Path) -> list[Violation]:
    """Rule 49: nobody builds an ``Assignment`` but the service that assigns (M12.2, ADR 0038).

    An assignment names the node the work goes to and carries a ``PermissionDecision`` — a bearer
    title (ADR 0011 §9). The service builds it after ``ensure_placed`` and after checking that the
    decision is ``ALLOWED``, about that step and not expired; a module that built one by hand
    would hand work to a node nobody placed, under a decision nobody checked. The mirror of rule
    30 (ADR 0026 §5).

    Reported: a call of the class, and a call of the constructors pydantic gives it
    (``model_validate``, ``model_validate_json``, ``model_construct``). Silent on today's tree,
    where the class does not exist yet: the rule is written before it (ADR 0030 §15), and the two
    builders it will admit — the service and the mapper that reads a row back — open their door
    in the commit that writes them.
    """
    rule = "assignments-built-only-by-the-assigner"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (built := _builds(node.func, ASSIGNMENT_MODEL)):
                found.append(Violation(rule, module_name(path, pkg_root), built, node.lineno))
    return found


def check_release_step_callers(pkg_root: Path) -> list[Violation]:
    """Rule 50: ``release_step`` has one caller, the service of the assignments (M12.2, ADR 0038).

    RUNNING → PENDING puts a step back in play, and it is safe only for a step nobody can have
    run: no STARTED record, no outcome in the store (M12.1, D14). The engine does not know the
    tools or the results, so it cannot tell; the guard lives in the caller, and so the caller is
    one. The mirror of rule 10 (ADR 0008 §12). Silent on today's tree, where the operation does not
    exist yet, and its one caller opens its door in the commit that writes it.
    """
    rule = "release-step-has-one-caller"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, module_name(path, pkg_root), f".{RELEASE_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _is_named(node.func, RELEASE_METHOD)
        )
    return found


def check_a_work_order_goes_only_to_its_node(pkg_root: Path) -> list[Violation]:
    """Rule 51: the order is composed in one place, and that place cannot send it anywhere.

    M12.2 (dec. N; §57, «quale nodo»): the order that goes to a node carries the arguments of a
    step — the user's content — and its one way out is the answer to the request of the node the
    assignment names. Two halves, because an AST cannot compare two ids:

    * **built in one place**: outside the composer of ``api/nodes.py`` no module builds the order
      (``WorkOrderOut``, by the call or by a constructor pydantic gives it);
    * **with no way out but the answer**: the module that composes it imports no network client
      (``httpx``, ``urllib.request``, ``http.client``, ``socket``).

    The runtime half — the composer refuses an identity that is not the assignment's — is
    criterion 21. Silent on today's tree, where no order exists: the composer is written after this
    rule (ADR 0030 §15), and its exemption is proved by the allowed case until it is.
    """
    rule = "a-work-order-goes-only-to-its-node"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        built = [
            (description, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (description := _builds(node.func, WORK_ORDER_MODEL)) is not None
        ]
        if not built:
            continue
        name = module_name(path, pkg_root)
        if path.relative_to(pkg_root) != WORK_ORDER_COMPOSER:
            found.extend(Violation(rule, name, description, line) for description, line in built)
            continue
        found.extend(
            Violation(rule, name, imported, line)
            for imported, line in imported_modules(path, pkg_root)
            if any(_is_within(imported, client) for client in NETWORK_CLIENTS)
        )
    return found


def check_results_are_minted_by_the_core(pkg_root: Path) -> list[Violation]:
    """Rule 52: no module of ``ela.api`` builds an ``ExecutionResult``.

    M12.2 (dec. B; M12.1, D1, D7): a node does not deliver a result, it delivers an envelope, and
    the Core rebuilds the result from it — the id derived from the assignment, the time from the
    Core's clock, the decision and the grant stamped from the assignment. ``TOOL_EXECUTED`` takes
    its instant from the result (``executor.py``), so a result built by a route from the envelope
    would put the node's clock into the order of the chain of §32. The entity is minted by the
    executor; ``ela.api`` holds only the envelope. Silent on today's tree.
    """
    rule = "results-are-minted-by-the-core"
    found: list[Violation] = []
    for path in sorted((pkg_root / API_DIR).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, module_name(path, pkg_root), built, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (built := _builds(node.func, RESULT_MODEL)) is not None
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
    "content-stays-on-the-machine": check_content_stays_on_the_machine,
    "perception-children-import-only-stdlib": check_children_are_standalone,
    "perception-reads-no-window-titles": check_no_window_titles,
    "machine-adapter-decides-nothing": check_adapter_names_no_state,
    "platform-choice-is-a-statement": check_platform_choice_is_a_statement,
    "context-writes-nothing": check_context_writes_nothing,
    "context-is-not-recorded": check_context_is_not_recorded,
    "the-voice-writes-no-file": check_the_voice_writes_no_file,
    "the-voice-leaves-no-named-file": check_the_voice_leaves_no_named_file,
    "the-voice-goes-only-where-it-is-declared": check_the_voice_goes_only_where_it_is_declared,
    "the-audition-speaks-only-the-repositorys-words": (
        check_the_audition_speaks_only_the_repositorys_words
    ),
    "a-refresh-touches-only-what-is-declared": check_a_refresh_touches_only_what_is_declared,
    "what-ela-hears-leaves-no-named-file": check_what_ela_hears_leaves_no_named_file,
    "a-nodes-secret-crosses-no-readable-boundary": (
        check_a_nodes_secret_crosses_no_readable_boundary
    ),
    "identity-resolved-in-one-place": check_identity_resolved_in_one_place,
    "assignment-port-readers": check_assignment_port_readers,
    "assignments-built-only-by-the-assigner": check_assignment_builders,
    "release-step-has-one-caller": check_release_step_callers,
    "a-work-order-goes-only-to-its-node": check_a_work_order_goes_only_to_its_node,
    "results-are-minted-by-the-core": check_results_are_minted_by_the_core,
}


RENAMED_RULES: Final[Mapping[str, str]] = {
    # M10.3 (ADR 0030 §15): rule 33's subject stopped being one named file and became a derived
    # set, so its name went to the plural. Held in `tests/docs/test_adr_perception.py` until M11.2
    # moved it here — two alias tables for one purpose is the same defect one floor up.
    "perception-probe-imports-only-stdlib": "perception-children-import-only-stdlib",
    # M11.2: the package the rule guards was renamed in this milestone's first commit, so the
    # mismatch is this milestone's own — one line now rather than a debt somebody inherits.
    "perception-adapter-decides-nothing": "machine-adapter-decides-nothing",
    # M11.2 (dec. A): rule 35 was born holding a screen capture, then took the text of one, then
    # what ELA says, and now what ELA hears. "capture" stopped describing it two milestones ago,
    # and this is the milestone where the mismatch became plain rather than merely wide.
    "capture-stays-on-the-machine": "content-stays-on-the-machine",
}
"""Rules that changed name, old name to new (M11.2 dec. A).

**An ADR is immutable, and keeps naming the rule as it was called when it was written.** ADR 0029
§12 introduced ``capture-stays-on-the-machine``; ADR 0030 §15 and ADR 0033 §7 extended it under
that name. None of those documents may be edited, and two doc tests assert that the name an ADR
prints is a name that is *registered* — so a rename without this table breaks them, and the two
easy ways out are editing an ADR (forbidden) or loosening the tests (removing the defence they
exist to be).

The history of a name is data, not a comment: it lives here, where the tests can resolve through
it, and :func:`current_name` is how they do it.
"""


def current_name(rule: str) -> str:
    """The name ``rule`` goes by today — itself, unless it has been renamed."""
    return RENAMED_RULES.get(rule, rule)


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
    # a-nodes-secret-crosses-no-readable-boundary (rule 46, M12.1)
    Constant("a-nodes-secret-crosses-no-readable-boundary", "AUDIT_EVENT", DETECTOR),
    Constant("a-nodes-secret-crosses-no-readable-boundary", "DEVICE_ENTITY", DETECTOR),
    Constant("a-nodes-secret-crosses-no-readable-boundary", "ENTITIES_FILE", DETECTOR),
    Constant("a-nodes-secret-crosses-no-readable-boundary", "NODE_SECRET_NAMES", DETECTOR),
    Constant(
        "a-nodes-secret-crosses-no-readable-boundary",
        "ONCE_SECRET_SHAPES",
        EXEMPTION,
        adr="ADR 0037 §5",
    ),
    Constant(
        "a-nodes-secret-crosses-no-readable-boundary",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    Constant("a-nodes-secret-crosses-no-readable-boundary", "WIRE_SECRET_NAMES", DETECTOR),
    Constant("a-nodes-secret-crosses-no-readable-boundary", "WIRE_SHAPES", DETECTOR),
    # a-refresh-touches-only-what-is-declared (rule 44, M6.1b dec. H)
    Constant("a-refresh-touches-only-what-is-declared", "BIRTH_CONSTRUCTOR", DETECTOR),
    Constant("a-refresh-touches-only-what-is-declared", "NOT_DECLARED_FIELDS", DETECTOR),
    Constant("a-refresh-touches-only-what-is-declared", "OBSERVED_FIELDS", DETECTOR),
    Constant("a-refresh-touches-only-what-is-declared", "REFRESH_MODULE", DETECTOR),
    Constant(
        "a-refresh-touches-only-what-is-declared",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
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
    Constant("constant-time-token", "COMPARED_SECRET_NAMES", DETECTOR),
    Constant("constant-time-token", "NODE_SECRET_NAMES", DETECTOR),
    Constant("constant-time-token", "TOKEN_NAMES", DETECTOR),
    # core-isolation
    Constant("core-isolation", "CORE_FORBIDDEN", DETECTOR),
    Constant("core-isolation", "CORE_PACKAGES", DETECTOR),
    Constant("core-isolation", "ROOT_PACKAGE", SUBJECT, why=INEVITABLE, reason=_THE_PACKAGE_ITSELF),
    # identity-resolved-in-one-place (rule 47, M12.1)
    Constant("identity-resolved-in-one-place", "API_DIR", DETECTOR),
    Constant("identity-resolved-in-one-place", "AUTHORIZATION_HEADER", DETECTOR),
    Constant(
        "identity-resolved-in-one-place",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    Constant(
        "identity-resolved-in-one-place", "SECURITY_MODULE", EXEMPTION, by=WHOLE, adr="ADR 0023 §7"
    ),
    # assignment-port-readers (rule 48, M12.2)
    Constant("assignment-port-readers", "ASSIGNMENT_PORT", DETECTOR),
    Constant(
        "assignment-port-readers",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # assignments-built-only-by-the-assigner (rule 49, M12.2)
    Constant("assignments-built-only-by-the-assigner", "ASSIGNMENT_MODEL", DETECTOR),
    Constant("assignments-built-only-by-the-assigner", "MODEL_CONSTRUCTORS", DETECTOR),
    Constant(
        "assignments-built-only-by-the-assigner",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # release-step-has-one-caller (rule 50, M12.2)
    Constant("release-step-has-one-caller", "RELEASE_METHOD", DETECTOR),
    Constant(
        "release-step-has-one-caller",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # a-work-order-goes-only-to-its-node (rule 51, M12.2)
    Constant("a-work-order-goes-only-to-its-node", "MODEL_CONSTRUCTORS", DETECTOR),
    Constant("a-work-order-goes-only-to-its-node", "NETWORK_CLIENTS", DETECTOR),
    Constant(
        "a-work-order-goes-only-to-its-node",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    Constant(
        "a-work-order-goes-only-to-its-node",
        "WORK_ORDER_COMPOSER",
        EXEMPTION,
        by=WHOLE,
        adr="ADR 0038",
        proof="the-composer-builds-the-order",
        reason="the composer is written after the rule that fences it (ADR 0030 §15): until "
        "``api/nodes.py`` composes an order, the allowed case is what stands behind the door",
    ),
    Constant("a-work-order-goes-only-to-its-node", "WORK_ORDER_MODEL", DETECTOR),
    # results-are-minted-by-the-core (rule 52, M12.2)
    Constant("results-are-minted-by-the-core", "API_DIR", DETECTOR),
    Constant("results-are-minted-by-the-core", "MODEL_CONSTRUCTORS", DETECTOR),
    Constant("results-are-minted-by-the-core", "RESULT_MODEL", DETECTOR),
    Constant(
        "results-are-minted-by-the-core",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
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
    # content-stays-on-the-machine (rule 35, ADR 0029 §12; extended M11.1 dec. H)
    Constant("content-stays-on-the-machine", "CAPTURE_FORBIDDEN", DETECTOR),
    Constant("content-stays-on-the-machine", "CAPTURE_MODULES", DETECTOR),
    Constant("content-stays-on-the-machine", "LISTENING_MODULES", DETECTOR),
    Constant("content-stays-on-the-machine", "VOICE_MODULES", DETECTOR),
    Constant(
        "content-stays-on-the-machine",
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
    # the-voice-leaves-no-named-file (rule 41, M11.3 dec. F, G)
    Constant("the-voice-leaves-no-named-file", "ELEVENLABS_ADAPTER_DIR", DETECTOR),
    Constant("the-voice-leaves-no-named-file", "NAMED_FILE_WRITERS", DETECTOR),
    Constant("the-voice-leaves-no-named-file", "VOICE_MODULES", DETECTOR),
    # what-ela-hears-leaves-no-named-file (rule 45, M11.2 dec. E)
    Constant("the-voice-leaves-no-named-file", "WRITE_MODES", DETECTOR),
    Constant(
        "the-voice-leaves-no-named-file",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # the-voice-goes-only-where-it-is-declared (rule 42, M11.3 dec. H)
    Constant("the-voice-goes-only-where-it-is-declared", "ELEVENLABS_ADAPTER_DIR", DETECTOR),
    Constant("the-voice-goes-only-where-it-is-declared", "SCHEME_SEPARATOR", DETECTOR),
    Constant("the-voice-goes-only-where-it-is-declared", "VOICE_ENDPOINT_FIELDS", DETECTOR),
    Constant("the-voice-goes-only-where-it-is-declared", "VOICE_ENVIRONMENT_READS", DETECTOR),
    Constant("the-voice-goes-only-where-it-is-declared", "VOICE_PROVIDER_FORBIDDEN", DETECTOR),
    Constant(
        "the-voice-goes-only-where-it-is-declared",
        "ELEVENLABS_ENDPOINT",
        EXEMPTION,
        by=WHOLE,
        adr="ADR 0034 §5",
        reason="the single address that is allowed: restricted to something nobody writes, the "
        "real endpoint becomes another host and the rule reports it",
    ),
    Constant(
        "the-voice-goes-only-where-it-is-declared",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # the-audition-speaks-only-the-repositorys-words (rule 43, M11.3 dec. I, J)
    Constant(
        "the-audition-speaks-only-the-repositorys-words", "AUDITION_TEXT_PARAMETERS", DETECTOR
    ),
    # what-ela-hears-leaves-no-named-file (rule 45, M11.2 dec. E)
    Constant("what-ela-hears-leaves-no-named-file", "HEARD_AUDIO_MODULES", DETECTOR),
    Constant("what-ela-hears-leaves-no-named-file", "NAMED_FILE_WRITERS", DETECTOR),
    Constant("what-ela-hears-leaves-no-named-file", "WRITE_MODES", DETECTOR),
    Constant(
        "what-ela-hears-leaves-no-named-file",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    Constant("the-audition-speaks-only-the-repositorys-words", "AUDITION_MODULE", DETECTOR),
    Constant(
        "the-audition-speaks-only-the-repositorys-words",
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
        "MACHINE_ADAPTER_DIR",
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
    # machine-adapter-decides-nothing (rule 34, ADR 0028 §1)
    Constant("machine-adapter-decides-nothing", "MACHINE_ADAPTER_DIR", DETECTOR),
    Constant("machine-adapter-decides-nothing", "PERCEPTION_VOCABULARY", DETECTOR),
    Constant(
        "machine-adapter-decides-nothing",
        "ROOT_PACKAGE",
        SUBJECT,
        why=INEVITABLE,
        reason=_THE_PACKAGE_ITSELF,
    ),
    # perception-children-import-only-stdlib (rule 33, ADR 0028 §2; M10.3 dec. 6)
    Constant("perception-children-import-only-stdlib", "MAIN_GUARD", DETECTOR),
    Constant("perception-children-import-only-stdlib", "MACHINE_ADAPTER_DIR", DETECTOR),
    Constant("perception-children-import-only-stdlib", "ROOT_PACKAGE", DETECTOR),
    # perception-reads-no-window-titles (rule 36, M10.3 dec. 3)
    Constant("perception-reads-no-window-titles", "MACHINE_ADAPTER_DIR", DETECTOR),
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

How big this table is, :func:`constants_summary` counts. It used to be written out here by hand,
and it stopped being true without anything noticing — ADR 0035 §7 found it on 2026-09-09, dated
the debt and handed it to whoever added rule 45. That is M11.2, and this is it paid: a count
written by hand inside the file that holds the self-checking lists is the thing that file exists
to make impossible everywhere else.
"""


def constants_summary() -> str:
    """How many rows of each kind this table holds, counted now and never transcribed.

    **Rows, not distinct names**, and the reason is what the old sentence got wrong: a line at the
    head of a table says how big the table is, not the cardinality of a set — "thirty-three
    subjects" was read both ways, and neither reading matched. **And each number carries its
    unit**, because leaving the unit out is what made the sentence ambiguous rather than merely
    stale: a bare number invites the reader to guess what is being counted.

    Deriving it, instead of writing today's correct values by hand, is the whole point (M11.2, and
    the user's own reason): *a correct number written by hand is the same defect postponed by six
    months.* Once the code counts them, "which reading did whoever wrote ADR 0027 intend" stops
    being a question anybody has to answer.
    """
    kinds = Counter(row.kind for row in CONSTANTS)
    return (
        f"{kinds[EXEMPTION]} exemption rows, {kinds[DETECTOR]} detector rows, "
        f"{kinds[SUBJECT]} subject rows, {len(CONSTANTS)} rows in all"
    )
