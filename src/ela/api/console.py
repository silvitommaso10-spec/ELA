"""The pages of the Command Center: observe ELA, and answer it (M17.2; ADR 0044).

The console is a **client of the API like the CLI**, and here that is a property and not a
promise: every page is composed from what a route function returns, and this module never reaches
a port, a store, the catalogue or the executor through :class:`~ela.composition.Ela` — architecture
rule 55, whose set of page modules is **derived** and no longer a single name.

Four views when M17.2 built it (dec. G): the home with the presence, the Approval Center, the
Device Center, and a task as an **execution summary** — never a model's reasoning. **Five since
M13.12** (ADR 0062, decision 23 of the review): the policies of §59, by the rule that every
milestone adding a capacity adds its view (STATO 5.10). What a view shows has to exist in a route
first; nothing here reads the world a second way, and no route grew to serve these pages.

Two things it shares with the phone instead of writing them twice. The **conduct of a "yes"** —
answer, then run — lives in ``api/approvals.py``, on the routes' side of the boundary (dec. K.1).
The **projection and the ceiling** — ``presence``, ``may_see``, and the words for a number of
seconds — live in ``api/companion.py``, where the first surface wrote them: both modules are
walked by rule 55, so moving them to a module the rule does not walk would trade a tidier import
for a door nobody tends.

What is this surface's own is the **ceiling in force**, said in both directions (dec. 17 of the
review): from the tailnet, that the content stays on the Mac; on loopback, that it is visible
because the reader is on this machine. A page that spoke only while hiding would let somebody
believe there is no ceiling when it is not hiding — and it is the one way the risk of an inbound
forward through the loopback can be seen by eye.
"""

from __future__ import annotations

from typing import Annotated, Final
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from ela.api import pages
from ela.api.approvals import answered_and_resumed, pending_approvals
from ela.api.companion import (
    NO_FINISHED,
    NO_LIVE,
    TARGET,
    answered_said,
    counted,
    end_caption,
    end_said,
    finished_title,
    form,
    halt_phrase,
    live_title,
    may_see,
    presence,
    terms,
    when,
)
from ela.api.deps import ElaDep, IdentityDep, RunningDep
from ela.api.devices import list_devices
from ela.api.errors import ApiError
from ela.api.nodes import enrolled
from ela.api.policies import created, policies_of, preview_of, revoked_policy
from ela.api.results import read_results
from ela.api.schemas import (
    ApprovalOut,
    CancelIn,
    DeclarationIn,
    DeviceOut,
    ExecutionResultOut,
    FinishedOut,
    PolicyConfirmIn,
    PolicyIn,
    PolicyOut,
    PreviewOut,
    StepOut,
    TaskDetail,
    TaskOut,
    TermsOut,
)
from ela.api.security import CONSOLE_SURFACE, Anonymous, Identity, note, welcome
from ela.api.tasks import cancel_task, finished_tasks, list_tasks, read_task
from ela.domain import (
    ApprovalId,
    DeviceRole,
    Halt,
    OperatingSystem,
    PrivacyLevel,
    StepState,
    TaskState,
    listed,
    visible,
)
from ela.ports import (
    ApprovalOutOfReachError,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    EnrollmentRoleError,
    NotFoundError,
)
from ela.tasks.engine import LIVE_STATES

__all__ = ["HOME", "router", "summary"]

router = APIRouter(prefix="/console", tags=["console"])

HERE: Final = CONSOLE_SURFACE.templates
"""Which folder of ``apps/`` this module's markup comes from."""
WHERE: Final = CONSOLE_SURFACE.prefix
"""Where this surface's two stylesheets are served: the composer writes the ``href`` from it."""
HOME: Final = "/console/"

FROM_THIS_MACHINE: Final = (
    "Stai leggendo da questa macchina: il contenuto dei task locali è visibile."
)
"""The ceiling in force on loopback (dec. J, dec. 17 of the review)."""
FROM_AWAY: Final = (
    "Stai leggendo da fuori: di un task che resta sul Mac vedi l'id, non il contenuto."
)
"""The ceiling in force from anywhere else — the same one the phone lives under."""
STAYS_ON_THE_MAC: Final = "Il contenuto resta sul Mac: aprilo da lì."
NOTHING_WAITS: Final = "Nient'altro ti aspetta."
NOTHING_RUNS: Final = "Non sta facendo niente."
AFTER_YES: Final = "ELA riprende il task adesso; uno step affidato a un altro nodo aspetta."
STOPPED: Final = "fermato dal Command Center"
"""What the audit reads as the reason of a cancellation asked from the Command Center (§65)."""
RESULTS_ARE_ELSEWHERE: Final = (
    "Il contenuto di un risultato non si legge qui: è su GET /tasks/<id>/results, "
    "dietro il token del Core."
)
"""Dec. K.2: the summary **names** what it does not show, instead of ending at «completato»."""
NO_RESULTS: Final = "Nessun risultato: questo task non ha ancora prodotto niente."
NO_PLAN: Final = "Nessun piano: questo task non ne ha ancora uno, e nessuno step da percorrere."
"""Dec. K.2 where nobody had looked (the hand test of 2026-09-20, dec. 21 of the review).

An empty list renders as an empty list, and an empty ``<ol>`` reads as «1.» and nothing — which
says «there is nothing to say» in the one way that is indistinguishable from a bug. Every empty
case of the four views names itself, and each has its test.
"""
NO_DEVICES: Final = "Nessuna identità nel registro."
NO_TOOLS: Final = "nessuno"
TWO_FACTS: Final = (
    "La disponibilità è il fatto dell'heartbeat; l'ultimo contatto dice quando quell'identità "
    "ha parlato con ELA. Sono due fatti, e due colonne."
)
A_CONSOLE: Final = "Il Command Center è un browser: dai un nome e lascia il tuo sistema."
NO_SUCH_CODE: Final = "Questo codice non esiste. Coniane uno al Mac e incollalo qui."
TOO_LATE: Final = "Questo codice è scaduto: dura dieci minuti. Coniane un altro."
ALREADY_SPENT: Final = "Questo codice è già stato usato. Coniane un altro."
ANOTHER_ROLE: Final = "Questo codice non è di una console. Al Mac: --role console."
SHOWN: Final = 8
"""How many rows a list of tasks keeps on the home: the live ones, newest first, and the last to
finish, the last first — one number for the two lists of the tile (M17.2b dec. 1). A list without a
bound stops being readable, and when it cuts it says how much it is showing — the lesson of the
phone's home (ADR 0043). Not measured: it is the only answer this surface has given to «how many
rows», and a second number would be a second opinion on the same question."""
ANSWER_FIELD: Final = "answer"
YES: Final = "yes"


# ----------------------------------------------------------------------------------------
# What every page says about itself
# ----------------------------------------------------------------------------------------


def _nav() -> pages.Markup:
    """The three views a page links to. One template, not a copy in every page."""
    return pages.fragment(HERE, "nav")


def _ceiling(identity: Identity) -> pages.Markup:
    """Which ceiling is in force, said **in both directions** (dec. 17 of the review).

    The effective level is the middleware's (dec. J): ``LOCAL_ONLY`` only when both ends of the
    socket are loopback, and only for a console. The page does not look at the socket — that
    would be a second place deciding who is calling — it reads what the identity carries.
    """
    here = identity.privacy is PrivacyLevel.LOCAL_ONLY
    return pages.fragment(HERE, "notice", text=FROM_THIS_MACHINE if here else FROM_AWAY)


def _title(goal: str, identifier: object, identity: Identity, level: PrivacyLevel | None) -> str:
    """What a page calls a task: its goal, or its id when the ceiling keeps the goal on the Mac."""
    return goal if may_see(identity, level) else str(identifier)


# ----------------------------------------------------------------------------------------
# The home
# ----------------------------------------------------------------------------------------


@router.get("/")
async def home(ela: ElaDep, identity: IdentityDep) -> Response:
    """The presence, what is happening now, and the three tiles (§7, §8 of the design).

    Never every task (M17.2b, C6): the live ones by their states, and the last to finish with how
    many finished in all, through the route that answers exactly that — the finished grow for
    ever, and a home that loaded them all to show eight would be what the review of M8.1 took out
    of ``/diagnostics``.
    """
    approvals = await pending_approvals(ela)
    alive = await list_tasks(ela, state=sorted(LIVE_STATES))
    finished = await finished_tasks(ela, limit=SHOWN)
    working = next((one for one in alive if one.state is TaskState.EXECUTING), None)
    detail = None if working is None else await read_task(working.id, ela)
    devices = await list_devices(ela)
    return pages.page(
        HERE,
        "home",
        sheets=WHERE,
        nav=_nav(),
        state=presence(approvals, alive),
        now=_now(detail, identity),
        tiles=_tiles(alive, finished, approvals, devices, identity),
        ceiling=_ceiling(identity),
    )


def _now(detail: TaskDetail | None, identity: Identity) -> pages.Markup:
    """§8 of the design: what ELA is doing, answered without opening a task manager."""
    if detail is None:
        return pages.fragment(HERE, "nothing", text=NOTHING_RUNS)
    return pages.fragment(
        HERE,
        "now",
        id=detail.id,
        what=_title(detail.goal, detail.id, identity, detail.max_privacy),
        steps=_steps(detail.steps, identity, detail.max_privacy),
    )


def _steps(
    steps: tuple[StepOut, ...], identity: Identity, level: PrivacyLevel | None
) -> pages.Markup:
    """The plan, in topological order, with the one that is running marked.

    A step's goal is the user's content, so the ceiling applies to it as it does to the task's:
    what is shown instead is the capability the step asks for, which is the catalogue's word and
    not the user's.
    """
    if not steps:
        return pages.fragment(HERE, "empty", text=NO_PLAN)
    return pages.fragment(
        HERE,
        "steps",
        rows=pages.joined(_step(one, identity, level) for one in steps),
    )


def _step(one: StepOut, identity: Identity, level: PrivacyLevel | None) -> pages.Markup:
    """One step: done, running, or neither — three templates, each named where it is filled.

    Written as three calls and not as a lookup in a table: the closed world between the markup
    and the code that fills it is read from the source, and a name that arrives through a
    variable is a template nobody can see (``tests/command_center/test_templates.py``).
    """
    said = one.goal if may_see(identity, level) else ", ".join(one.required_capabilities) or "step"
    if one.state is StepState.COMPLETED:
        return pages.fragment(HERE, "step-done", what=said)
    if one.state is StepState.RUNNING:
        return pages.fragment(HERE, "step-now", what=said)
    return pages.fragment(HERE, "step", what=f"{said} · {one.state.value}")


def _row(one: TaskOut, identity: Identity, halt: Halt | None = None) -> pages.Markup:
    """A task as a row of the tile: its goal or its id, its state, and the way to its summary.

    Live or finished, the same row: a finished task has a summary too, and reaching it is what
    decision 22 of M17.2 had left to its id alone (M17.2b). A stopped one says what the step in
    progress had done (M6.3c, ADR 0054 §8); an ended one why it ended, and who said no, in the form
    its ceiling allows (M13.1e, ADR 0059)."""
    said = end_caption(one.end, may_see(identity, one.max_privacy))
    return pages.fragment(
        HERE,
        "row-task",
        state="WORKING" if one.state is TaskState.EXECUTING else "IDLE",
        what=_title(one.goal, one.id, identity, one.max_privacy),
        key=one.state.value,
        id=one.id,
        halt=_halt(halt),
        why=pages.fragment(HERE, "why", text=said) if said else pages.Markup(""),
    )


def _halt(halt: Halt | None) -> pages.Markup:
    if halt is None:
        return pages.Markup("")
    return pages.fragment(HERE, "halt", text=halt_phrase(halt))


def _tiles(
    alive: tuple[TaskOut, ...],
    finished: FinishedOut,
    approvals: tuple[ApprovalOut, ...],
    devices: tuple[DeviceOut, ...],
    identity: Identity,
) -> pages.Markup:
    """Tasks, devices, attention: the three tiles of §7 of the design.

    The tasks tile is a **list** and not only a number, because it is how a task is reached: its
    rows link to the execution summary. It holds two groups — the TASKS tile of §7 of the design has
    the running and the failed in one place —: **the live ones**, newest first, and **the last to
    finish**, the last first (M17.2b, ADR 0049). Each stops at :data:`SHOWN` and carries its cut in
    its own title, and each says what it holds when it holds nothing. Until M17.2b the tile listed
    the live ones alone, and the outcome the user was waiting for was the one it stopped showing.
    """
    usable = tuple(one for one in devices if one.available)
    recent = tuple(reversed(alive))[:SHOWN]
    return pages.joined(
        [
            pages.fragment(
                HERE,
                "tile-rows",
                title="Task",
                rows=pages.joined(
                    [
                        pages.fragment(HERE, "group", title=live_title(len(recent), len(alive))),
                        *(_row(one, identity) for one in recent),
                        *(() if recent else (pages.fragment(HERE, "notice", text=NO_LIVE),)),
                        pages.fragment(HERE, "group", title=finished_title(SHOWN, finished.total)),
                        *(_row(one, identity, one.halt) for one in finished.tasks),
                        *(
                            ()
                            if finished.tasks
                            else (pages.fragment(HERE, "notice", text=NO_FINISHED),)
                        ),
                    ]
                ),
            ),
            pages.fragment(
                HERE,
                "tile",
                title="Dispositivi",
                number=f"{len(usable)} / {len(devices)}",
                detail=f"disponibili adesso · {len(alive) + finished.total} task in tutto",
            ),
            pages.fragment(
                HERE,
                "tile",
                title="Attenzione",
                number=len(approvals),
                detail=counted(len(approvals), "una domanda", "domande") or NOTHING_WAITS,
            ),
        ]
    )


# ----------------------------------------------------------------------------------------
# The Approval Center (§14, §29 of the design)
# ----------------------------------------------------------------------------------------


@router.get("/approvals")
async def approvals(ela: ElaDep, identity: IdentityDep) -> Response:
    """Every question that waits, oldest first: the list the phone shows on its home."""
    waiting = await pending_approvals(ela)
    rows = (
        pages.fragment(HERE, "notice", text=NOTHING_WAITS)
        if not waiting
        else pages.joined(
            pages.fragment(
                HERE,
                "row-approval",
                id=one.id,
                what=one.capability_id,
                when=when(one.created_at),
                risk="" if one.risk is None else one.risk.value,
            )
            for one in waiting
        )
    )
    return pages.page(
        HERE, "approvals", sheets=WHERE, nav=_nav(), rows=rows, ceiling=_ceiling(identity)
    )


@router.get("/approval")
async def approval(ela: ElaDep, identity: IdentityDep, id: Annotated[UUID, Query()]) -> Response:
    """One question, with the parts of it a page can show (M12.5 dec. F).

    What is **not** shown is as deliberate, and for the reasons ADR 0043 already wrote: the
    **device**, because when the question is born the placement is not decided and the level is
    (ADR 0038 §16); the **consequences** and the **reversibility**, because the catalogue does not
    state them and a page that wrote them would be inventing them. There is no `EDIT`: changing a
    question is not something ELA can do.
    """
    found = await _answerable(ela, id)
    seen = may_see(identity, found.max_privacy)
    return pages.page(
        HERE,
        "approval",
        sheets=WHERE,
        nav=_nav(),
        capability=found.capability_id,
        description=found.description if seen else "",
        pairs=_pairs(found, seen),
        content=_content(found, seen),
        answer=pages.fragment(HERE, "answer", id=found.id)
        if seen
        else pages.fragment(HERE, "notice", text=STAYS_ON_THE_MAC),
        after=AFTER_YES if seen else "",
        task=pages.fragment(HERE, "open-task", id=found.task_id),
        ceiling=_ceiling(identity),
    )


def _pairs(found: ApprovalOut, seen: bool) -> pages.Markup:
    """The facts every question shows, whatever the ceiling: none of them is content."""
    pairs = [pages.fragment(HERE, "pair-risk", risk="" if found.risk is None else found.risk.value)]
    if found.max_privacy is not None:
        pairs.append(
            pages.fragment(
                HERE, "pair", key="Dove può andare", value=f"un nodo {found.max_privacy.value}"
            )
        )
    if found.grant_uses is not None and found.grant_seconds is not None:
        pairs.append(
            pages.fragment(
                HERE, "pair", key="Durata", value=terms(found.grant_uses, found.grant_seconds)
            )
        )
    if found.expires_at is not None:
        pairs.append(
            pages.fragment(HERE, "pair", key="Scade", value=f"alle {when(found.expires_at)}")
        )
    # What saying yes costs in money, for a call that spends (M14.1, ADR 0057; decision H): the
    # executor's lines, rendered as they stand. Not content, so whatever the ceiling.
    if found.worst_case:
        pairs.append(pages.fragment(HERE, "pair", key="Costo massimo", value=found.worst_case))
    if found.left:
        pairs.append(pages.fragment(HERE, "pair", key="Resta nel mese", value=found.left))
    # A guided session of the browser (M14.3, ADR 0060; decision 4): the model, the most it may
    # spend, the looks and what leaves the machine are ELA's numbers and words — whatever the
    # ceiling —; the sentence and the sites are the plan's, behind it like the goal.
    if found.model:
        pairs.append(pages.fragment(HERE, "pair", key="Modello", value=found.model))
    if found.max_cost:
        pairs.append(pages.fragment(HERE, "pair", key="Spesa massima", value=found.max_cost))
    if found.looks is not None:
        pairs.append(pages.fragment(HERE, "pair", key="Gesti massimi", value=str(found.looks)))
    if found.sends:
        pairs.append(pages.fragment(HERE, "pair", key="Che cosa esce", value=found.sends))
    # Why it asks, policy by policy (M13.12, ADR 0062; decision 8): short ids and numbers, never a
    # site — above the ceiling, so the yes is offered with it or not at all (ADR 0045 §11).
    if found.why is not None:
        pairs.append(
            pages.fragment(HERE, "pair", key="Perché te lo chiedo", value="; ".join(found.why))
        )
    if seen and found.phrase:
        pairs.append(
            pages.fragment(HERE, "pair", key="La frase", value=visible(found.phrase, lines=False))
        )
    if seen and found.sites is not None:
        pairs.append(pages.fragment(HERE, "pair", key="Siti", value=listed(found.sites)))
    if seen and found.targets:
        shown = ", ".join(visible(one, lines=False) for one in found.targets)
        pairs.append(pages.fragment(HERE, "pair", key="Su", value=shown))
    # The facts of the machine a question must name (M13.1 dec. G; M13.2 dec. 12), and the reason
    # this surface may answer it at all (dec. H): a surface that did not show them would be offering
    # a yes to something it has not said. The target is called what **the tool** calls it — a page
    # that wrote «Il file» beside a program would be true to the letter and wrong about the yes —
    # and every word of the machine or of the plan passes the one rendering (M13.2 dec. 13).
    if seen and found.machine:
        # Which machine's disk, when it is not this one (M13.3): a node's name and its id's start.
        pairs.append(
            pages.fragment(
                HERE, "pair", key="Su quale macchina", value=visible(found.machine, lines=False)
            )
        )
    if seen and found.target:
        key = found.label or TARGET
        pairs.append(
            pages.fragment(HERE, "pair", key=key, value=visible(found.target, lines=False))
        )
    if seen and found.runs:
        pairs.append(
            pages.fragment(HERE, "pair", key="Porta a", value=visible(found.runs, lines=False))
        )
    if seen and found.arguments is not None:
        pairs.append(pages.fragment(HERE, "pair", key="Argomenti", value=listed(found.arguments)))
    if seen and found.folder:
        pairs.append(
            pages.fragment(HERE, "pair", key="Parte da", value=visible(found.folder, lines=False))
        )
    if seen and found.timeout_seconds is not None:
        pairs.append(
            pages.fragment(HERE, "pair", key="Tempo massimo", value=f"{found.timeout_seconds} s")
        )
    if seen and found.expect_exit is not None:
        pairs.append(
            pages.fragment(HERE, "pair", key="Codice atteso", value=str(found.expect_exit))
        )
    if seen and found.address:
        # What a browser call opens and does (M13.4): the address, the gestures one by one — each
        # value the plan would type —, and the text the page must show after the click.
        pairs.append(
            pages.fragment(HERE, "pair", key="Indirizzo", value=visible(found.address, lines=False))
        )
    if seen and found.gestures is not None:
        pairs.append(pages.fragment(HERE, "pair", key="Gesti", value=listed(found.gestures)))
    if seen and found.expect:
        pairs.append(
            pages.fragment(
                HERE, "pair", key="Testo atteso", value=visible(found.expect, lines=False)
            )
        )
    if seen and found.does:
        # The sentence comes from the capability and is rendered as it stands (M13.1 dec. G):
        # a page that composed one would be lending a write's words to a read.
        pairs.append(pages.fragment(HERE, "pair", key="Che cosa fa", value=found.does))
    if seen and found.unseen:
        # And what ELA did not do on that machine, in the executor's sentence (M13.3, ADR 0048).
        pairs.append(pages.fragment(HERE, "pair", key="Il disco", value=found.unseen))
    return pages.joined(pairs)


def _content(found: ApprovalOut, seen: bool) -> pages.Markup:
    """The goal and the declared arguments — the part a ceiling can keep on the Mac."""
    if not seen:
        return pages.Markup("")
    return pages.fragment(
        HERE,
        "asked",
        goal=visible(found.goal, lines=False),
        stated=pages.joined(
            pages.fragment(HERE, "stated", pair=visible(one, lines=False)) for one in found.stated
        ),
    )


@router.post("/answer")
async def answer(
    request: Request, ela: ElaDep, identity: IdentityDep, running: RunningDep
) -> Response:
    """The "yes" or the "no", through the one conduct both surfaces share (dec. K.1)."""
    fields = form(await request.body())
    found = await _answerable(ela, UUID(fields.get("id", "")))
    if not may_see(identity, found.max_privacy):
        raise ApprovalOutOfReachError(ApprovalId(found.id))
    await answered_and_resumed(
        found,
        said_yes=fields.get(ANSWER_FIELD) == YES,
        ela=ela,
        identity=identity,
        running=running,
    )
    return RedirectResponse(f"/console/task?id={found.task_id}", status_code=303)


async def _answerable(ela: ElaDep, id: UUID) -> ApprovalOut:
    """The question with this id, among the ones that can still be answered.

    Read through the route (rule 55), and among the answerable ones for the reason the phone
    does it: a page must not offer an answer ELA would refuse (§33). Not answerable any more —
    already answered, or expired — is a ``404``, exactly as it is for the phone; a question the
    ceiling does not admit is a ``409`` (:class:`ApprovalOutOfReachError`), because it exists and
    the answer is the thing that cannot be given.
    """
    found = next((one for one in await pending_approvals(ela) if one.id == id), None)
    if found is None:
        raise NotFoundError("approval", str(id))
    return found


# ----------------------------------------------------------------------------------------
# The Device Center (§11, §12 of the design)
# ----------------------------------------------------------------------------------------


@router.get("/devices")
async def devices(ela: ElaDep, identity: IdentityDep) -> Response:
    """Every identity of the registry, with **availability and last contact apart**.

    The three labels of §11 of the design — WORK NODE, POWER NODE, COMPANION NODE — are not the
    three roles: the Mac and the PC are both ``WORKER``, and what tells them apart there is their
    power, which the registry keeps in ``performance``. The page shows the role *and* that, and
    invents no label the registry does not have.

    §12 of the design — a piece of work moving from one node to another — is not built: no route
    exposes an assignment, and ADR 0043 §9 gave that house to Fase 13.
    """
    rows = await list_devices(ela)
    return pages.page(
        HERE,
        "devices",
        sheets=WHERE,
        nav=_nav(),
        rows=pages.joined(_device(one) for one in rows)
        if rows
        else pages.fragment(HERE, "empty", text=NO_DEVICES),
        note=TWO_FACTS,
    )


def _device(one: DeviceOut) -> pages.Markup:
    """One identity: what it is, whether it can be used, and when it last spoke."""
    pairs = [
        pages.fragment(HERE, "pair", key="Disponibile", value="sì" if one.available else "no"),
        pages.fragment(HERE, "pair", key="Ultimo contatto", value=when(one.last_seen_at) or "mai"),
        pages.fragment(HERE, "pair", key="Sistema", value=one.os.value),
        pages.fragment(HERE, "pair", key="Potenza", value=one.performance.value),
        pages.fragment(HERE, "pair", key="Privacy", value=one.privacy.value),
        pages.fragment(HERE, "pair", key="Tool", value=", ".join(one.available_tools) or NO_TOOLS),
    ]
    if one.revoked_at is not None:
        pairs.append(pages.fragment(HERE, "pair", key="Revocato", value=when(one.revoked_at)))
    return pages.fragment(
        HERE,
        "device",
        state="WORKING" if one.available else "IDLE",
        name=one.name,
        role=one.role.value,
        key=one.status.value,
        pairs=pages.joined(pairs),
    )


# ----------------------------------------------------------------------------------------
# A task, as an execution summary (§10 of the design)
# ----------------------------------------------------------------------------------------


@router.get("/task")
async def task(ela: ElaDep, identity: IdentityDep, id: Annotated[UUID, Query()]) -> Response:
    """What ELA is doing on this task and why, **never** a model's reasoning.

    Two entries of §10's example have no source and are declared rather than invented: CONTEXT,
    because the context of §44 is the machine's and not a task's, and MODEL, because no route
    says which model ran a step — ``ProviderUsage`` has no name in it, and ``ErrorMetadata.model``
    exists only when something failed.
    """
    return await summary(ela, identity, id)


async def summary(ela: ElaDep, identity: IdentityDep, id: UUID) -> Response:
    """The execution summary, composed from ``GET /tasks/{id}`` and ``GET /tasks/{id}/results``."""
    detail = await read_task(id, ela)
    results = await read_results(id, ela)
    seen = may_see(identity, detail.max_privacy)
    pairs = [
        pages.fragment(HERE, "pair", key="Stato", value=detail.state.value),
        *_end_pairs(detail, seen),
        *(
            ()
            if detail.halt is None
            else (
                pages.fragment(
                    HERE, "pair", key="Lo step in corso", value=halt_phrase(detail.halt)
                ),
            )
        ),
        pages.fragment(HERE, "pair", key="Creato", value=when(detail.created_at)),
        pages.fragment(HERE, "pair", key="Dove può andare", value=detail.max_privacy.value),
        pages.fragment(
            HERE,
            "pair",
            key="Dispositivo",
            value=", ".join(
                sorted({str(one.device_id) for one in results if one.device_id is not None})
            )
            or "nessuno ancora",
        ),
        *(
            # The policy of §59 that covered a step (M13.12, decision 9): read by the route from the
            # grant of the step's result, never composed here.
            pages.fragment(HERE, "pair", key="Coperto dalla policy", value=str(one.policy)[:8])
            for one in detail.steps
            if one.policy is not None
        ),
    ]
    return pages.page(
        HERE,
        "task",
        sheets=WHERE,
        nav=_nav(),
        goal=_title(detail.goal, detail.id, identity, detail.max_privacy),
        pairs=pages.joined(pairs),
        steps=_steps(detail.steps, identity, detail.max_privacy),
        results=_results(results, seen),
        stop=pages.fragment(HERE, "stop", id=detail.id)
        if detail.state in LIVE_STATES
        else pages.Markup(""),
        ceiling=_ceiling(identity),
    )


def _end_pairs(detail: TaskDetail, seen: bool) -> list[pages.Markup]:
    """«Perché» and, for a no, «Ha risposto» (M13.1e, ADR 0059): whole from this machine, and from
    away for a task the ceiling lets through; otherwise only words of ELA — the operation, the
    code, the role (decision 2 of the review)."""
    if detail.end is None:
        return []
    pairs = [pages.fragment(HERE, "pair", key="Perché", value=end_said(detail.end, seen))]
    who = answered_said(detail.end.answered_by, seen)
    if who is not None:
        pairs.append(pages.fragment(HERE, "pair", key="Ha risposto", value=who))
    return pairs


def _results(produced: tuple[ExecutionResultOut, ...], seen: bool) -> pages.Markup:
    """That a result **exists**, and where it is read — never the content itself (dec. K.2).

    A summary that ended at «completato» would let somebody believe the task produced nothing.
    The content has its own route and its own rule (29), and a view for it belongs to the
    milestone that needs one.
    """
    rows = pages.joined(
        pages.fragment(
            HERE,
            "result",
            what=one.capability_id,
            outcome=one.status.value,
            detail="—" if one.duration_ms is None else f"{one.duration_ms} ms",
        )
        for one in produced
    )
    return pages.fragment(
        HERE,
        "results",
        rows=rows if produced else pages.fragment(HERE, "notice", text=NO_RESULTS),
        where=RESULTS_ARE_ELSEWHERE if seen else STAYS_ON_THE_MAC,
    )


@router.get("/cancel")
async def confirm(ela: ElaDep, identity: IdentityDep, id: Annotated[UUID, Query()]) -> Response:
    """The second page of stopping a task: without JavaScript, a confirmation is a page."""
    found = await _live(ela, id)
    return pages.page(
        HERE,
        "cancel",
        sheets=WHERE,
        nav=_nav(),
        what=_title(found.goal, found.id, identity, found.max_privacy),
        state=found.state.value,
        id=found.id,
    )


@router.post("/cancel")
async def cancel(
    request: Request, ela: ElaDep, identity: IdentityDep, running: RunningDep
) -> Response:
    """The form of the confirmation page: the task stops, signed by the Command Center.

    Stopping does not ask to see: it works for a task whose content stays on the Mac too, because
    what is being asked for is less and not more.
    """
    fields = form(await request.body())
    found = await _live(ela, UUID(fields.get("id", "")))
    await cancel_task(found.id, CancelIn(reason=STOPPED), ela, identity, running)
    return RedirectResponse(f"/console/task?id={found.id}", status_code=303)


async def _live(ela: ElaDep, id: UUID) -> TaskDetail:
    """The task with this id, if it can still be stopped; otherwise nothing.

    Read through the route (rule 55): a page must not offer what ELA would refuse (§33).
    """
    found = await read_task(id, ela)
    if found.state not in LIVE_STATES:
        raise NotFoundError("task", str(id))
    return found


# ----------------------------------------------------------------------------------------
# The policies of §59 (M13.12, ADR 0062): the fifth view
# ----------------------------------------------------------------------------------------

NO_POLICIES: Final = "Nessuna policy viva: ogni azione MEDIUM ti chiede il sì, una volta per volta."
SITES_STAY: Final = (
    "I siti di una policy restano sul Mac: crearne una si fa da lì. Revocarla si fa anche da qui."
)
"""Decision 18 of the review: a policy has no task, so no level — its sites are ``LOCAL_ONLY``
content, and a console under a narrower ceiling neither shows them nor creates. It revokes: that
takes away, it does not widen."""


class PolicyOutOfReachError(ApiError):
    """A creation from a console whose ceiling cannot show the sites a policy names (decision
    18): the preview is a question, and a surface that cannot show all of it does not create
    (ADR 0045 §11)."""

    def __init__(self) -> None:
        super().__init__(SITES_STAY)


def _sites_seen(identity: Identity) -> bool:
    """Whether this console may see the sites of a policy: ``LOCAL_ONLY`` content (decision 18)."""
    return may_see(identity, PrivacyLevel.LOCAL_ONLY)


@router.get("/policies")
async def policies(ela: ElaDep, identity: IdentityDep) -> Response:
    """The live policies, with «Revoca» for each, and the form of a new one — derived from the
    catalogue and the declaration, read through the route (rule 55)."""
    listed = await policies_of(ela, everything=False)
    seen = _sites_seen(identity)
    rows = (
        pages.joined(_policy(one, seen) for one in listed.policies)
        if listed.policies
        else pages.fragment(HERE, "notice", text=NO_POLICIES)
    )
    forms = (
        pages.joined(_policy_form(terms) for terms in listed.admitting)
        if seen
        else pages.fragment(HERE, "notice", text=SITES_STAY)
    )
    return pages.page(
        HERE,
        "policies",
        sheets=WHERE,
        nav=_nav(),
        rows=rows,
        forms=forms,
        ceiling=_ceiling(identity),
    )


def _policy(one: PolicyOut, seen: bool) -> pages.Markup:
    """One live policy: what it covers, until when, how often it served, who created it."""
    who = one.created_by.name or one.created_by.identity
    pairs = [
        pages.fragment(
            HERE, "pair", key="Siti", value=listed(one.scope) if seen else "restano sul Mac"
        ),
        pages.fragment(
            HERE,
            "pair",
            key="Tetti per sessione",
            value=", ".join(f"{name}={value}" for name, value in one.limits.items()),
        ),
        pages.fragment(HERE, "pair", key="Modello", value=one.model or "—"),
        pages.fragment(HERE, "pair", key="Scade", value=when(one.expires_at)),
        pages.fragment(HERE, "pair", key="Usi", value=str(one.uses)),
        pages.fragment(
            HERE,
            "pair",
            key="Creata da",
            value=f"{who} ({one.created_by.role or '—'}), {when(one.created_at)}",
        ),
    ]
    return pages.fragment(
        HERE,
        "policy",
        capability=one.capability,
        short=one.short,
        pairs=pages.joined(pairs),
        revoke=pages.fragment(HERE, "policy-revoke", id=one.id),
    )


def _policy_form(terms: TermsOut) -> pages.Markup:
    """The form of a new policy of one capability: its sites, one field per declared limit with
    the bounds of its schema, and the days with no value set (decision 3d)."""
    return pages.fragment(
        HERE,
        "policy-form",
        capability=terms.capability,
        description=terms.description,
        sites=pages.joined(pages.fragment(HERE, "policy-site", site=one) for one in terms.scope),
        limits=pages.joined(
            pages.fragment(
                HERE,
                "policy-limit",
                name=limit.name,
                bounds=_bounds(limit.minimum, limit.maximum, limit.pattern),
            )
            for limit in terms.limits
        ),
        days_min=terms.days_min,
        days_max=terms.days_max,
    )


def _bounds(minimum: int | None, maximum: int | None, pattern: str | None) -> str:
    if minimum is not None and maximum is not None:
        return f"un intero da {minimum} a {maximum}"
    if pattern is not None:
        return "una cifra in dollari, con il punto: 1.10"
    return "un valore"


def _request_of(body: bytes) -> dict[str, object]:
    """The form of a policy: the sites ticked — a key repeated —, a field per limit, the days."""
    pairs = parse_qsl(body.decode("utf-8", "replace"))
    fields = dict(pairs)
    return {
        "capability": fields.get("capability", ""),
        "scope": [value for key, value in pairs if key == "scope"],
        "limits": {
            key.removeprefix("limit-"): value for key, value in pairs if key.startswith("limit-")
        },
        "days": fields.get("days", ""),
        "model": fields.get("model", ""),
    }


@router.post("/policies/preview")
async def policy_preview(request: Request, ela: ElaDep, identity: IdentityDep) -> Response:
    """The preview: what the creation would approve, and «Crea» — only where the sites are seen."""
    if not _sites_seen(identity):
        raise PolicyOutOfReachError
    asked = _request_of(await request.body())
    body = PolicyIn.model_validate({key: value for key, value in asked.items() if key != "model"})
    shown = await preview_of(body, ela, identity)
    return pages.page(
        HERE,
        "policy-preview",
        sheets=WHERE,
        nav=_nav(),
        capability=shown.capability,
        description=shown.description,
        pairs=_preview_pairs(shown),
        never=pages.joined(pages.fragment(HERE, "why", text=line) for line in shown.never),
        create=pages.fragment(HERE, "policy-create", hidden=_hidden(body, shown)),
        ceiling=_ceiling(identity),
    )


def _preview_pairs(shown: PreviewOut) -> pages.Markup:
    return pages.joined(
        [
            pages.fragment(HERE, "pair", key="Siti", value=listed(shown.scope)),
            pages.fragment(
                HERE,
                "pair",
                key="Tetti per sessione",
                value=", ".join(f"{name}={value}" for name, value in shown.limits.items()),
            ),
            pages.fragment(
                HERE,
                "pair",
                key="Scade",
                value=f"fra {shown.days} giorni, il {when(shown.expires_at)}",
            ),
            pages.fragment(HERE, "pair", key="Modello", value=shown.model or "—"),
            pages.fragment(HERE, "pair", key="Che cosa esce", value=shown.sends or "—"),
            pages.fragment(HERE, "pair", key="Una chiamata", value=shown.one_call or "—"),
            pages.fragment(HERE, "pair", key="Il costo", value=shown.cost or "—"),
        ]
    )


def _hidden(body: PolicyIn, shown: PreviewOut) -> pages.Markup:
    """What «Crea» sends back: what the preview showed, with the model it named."""
    fields = [
        ("capability", body.capability),
        *(("scope", one) for one in body.scope),
        *((f"limit-{name}", value) for name, value in body.limits.items()),
        ("days", str(body.days)),
        ("model", shown.model or ""),
    ]
    return pages.joined(
        pages.fragment(HERE, "policy-hidden", name=name, value=value) for name, value in fields
    )


@router.post("/policies")
async def policy_create(request: Request, ela: ElaDep, identity: IdentityDep) -> Response:
    """The creation, through the route's function — and the list again."""
    if not _sites_seen(identity):
        raise PolicyOutOfReachError
    await created(PolicyConfirmIn.model_validate(_request_of(await request.body())), ela, identity)
    return RedirectResponse("/console/policies", status_code=303)


@router.post("/policies/revoke")
async def policy_revoke(request: Request, ela: ElaDep, identity: IdentityDep) -> Response:
    """The revocation, under any ceiling: it takes away, it does not widen (decision 18)."""
    fields = form(await request.body())
    await revoked_policy(UUID(fields.get("id", "")), ela, identity)
    return RedirectResponse("/console/policies", status_code=303)


# ----------------------------------------------------------------------------------------
# Enrolment, and the two sheets
# ----------------------------------------------------------------------------------------


@router.post("/enroll")
async def enrol(request: Request, ela: ElaDep, identity: IdentityDep) -> Response:
    """The browser presents the code the user pasted, and leaves with its credential.

    The same function the nodes' route spends a code with, asked for the third role: what differs
    is the answer. A node's secret comes back in a body, once; a browser's goes into a
    ``Set-Cookie`` and is never spoken again.

    **No declared system is refused, ``IOS`` included** (dec. 14 of the review). The declared
    system governs nothing in a console — not the routes, not the ceiling, not the pages — and the
    cookie works in any browser: refusing ``IOS`` would not have kept a phone out, it would only
    have kept it from *saying so*, leaving a row that reads ``MACOS`` where a phone is. That a
    phone does not see local content is dec. J's business, and dec. J looks at the socket and not
    at the declaration. A refusal that cannot reach what it names makes the registry less true,
    not safer.
    """
    assert identity.code is not None  # the middleware lets only a code through here
    fields = form(await request.body())
    try:
        declared = DeclarationIn(
            name=fields.get("name", "").strip(),
            os=OperatingSystem(fields.get("os", "").strip()),
        )
    except ValueError:
        return _again(A_CONSOLE, status=422)
    try:
        born = await enrolled(ela, code=identity.code, role=DeviceRole.CONSOLE, declared=declared)
    except NotFoundError:
        note(request, Anonymous.UNKNOWN_CODE)
        return _again(NO_SUCH_CODE)
    except EnrollmentExpiredError:
        note(request, Anonymous.EXPIRED_CODE)
        return _again(TOO_LATE)
    except EnrollmentConsumedError:
        return _again(ALREADY_SPENT)
    except EnrollmentRoleError:
        return _again(ANOTHER_ROLE, status=422)
    return welcome(CONSOLE_SURFACE, born.device.id, born.secret)


def _again(message: str, *, status: int = 401) -> Response:
    """The enrolment page, with the one sentence that says what happened."""
    return pages.page(HERE, "enrol", sheets=pages.INSIDE, status=status, message=message)


@router.get("/tokens.css")
async def tokens_css() -> Response:
    """The design system's tokens, read from ``apps/`` (ADR 0042), behind the identity like
    everything else: a sheet served to nobody would be the first anonymous route of ELA."""
    return pages.stylesheet("tokens.css")


@router.get("/components.css")
async def components_css() -> Response:
    """The design system's components, on the same terms as :func:`tokens_css`."""
    return pages.stylesheet("components.css")
