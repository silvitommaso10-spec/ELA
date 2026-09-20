"""The pages of the Command Center: observe ELA, and answer it (M17.2; ADR 0044).

The console is a **client of the API like the CLI**, and here that is a property and not a
promise: every page is composed from what a route function returns, and this module never reaches
a port, a store, the catalogue or the executor through :class:`~ela.composition.Ela` — architecture
rule 55, whose set of page modules is **derived** and no longer a single name.

Four views, and not one more (dec. G): the home with the presence, the Approval Center, the Device
Center, and a task as an **execution summary** — never a model's reasoning. What a view shows has
to exist in a route first; nothing here reads the world a second way, and no route grew to serve
these pages.

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
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from ela.api import pages
from ela.api.approvals import answered_and_resumed, pending_approvals
from ela.api.companion import counted, form, may_see, presence, terms, when
from ela.api.deps import ElaDep, IdentityDep, RunningDep
from ela.api.devices import list_devices
from ela.api.nodes import enrolled
from ela.api.results import read_results
from ela.api.schemas import (
    ApprovalOut,
    CancelIn,
    DeclarationIn,
    DeviceOut,
    ExecutionResultOut,
    StepOut,
    TaskDetail,
    TaskOut,
)
from ela.api.security import CONSOLE_SURFACE, Anonymous, Identity, note, welcome
from ela.api.tasks import cancel_task, list_tasks, read_task
from ela.domain import (
    ApprovalId,
    DeviceRole,
    OperatingSystem,
    PrivacyLevel,
    StepState,
    TaskState,
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
TWO_FACTS: Final = (
    "La disponibilità è il fatto dell'heartbeat; l'ultimo contatto dice quando quell'identità "
    "ha parlato con ELA. Sono due fatti, e due colonne."
)
A_CONSOLE: Final = "Il Command Center è un browser: dai un nome e lascia il tuo sistema."
NO_SUCH_CODE: Final = "Questo codice non esiste. Coniane uno al Mac e incollalo qui."
TOO_LATE: Final = "Questo codice è scaduto: dura dieci minuti. Coniane un altro."
ALREADY_SPENT: Final = "Questo codice è già stato usato. Coniane un altro."
ANOTHER_ROLE: Final = "Questo codice non è di una console. Al Mac: --role console."
NO_TASKS: Final = "Nessun task vivo."
SHOWN: Final = 8
"""How many live tasks the home lists, newest first. A list without a bound stops being readable,
and when it cuts it says how much it is showing — the lesson of the phone's home (ADR 0043)."""
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
    """The presence, what is happening now, and the three tiles (§7, §8 of the design)."""
    approvals = await pending_approvals(ela)
    tasks = await list_tasks(ela)
    alive = tuple(one for one in tasks if one.state in LIVE_STATES)
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
        tiles=_tiles(tasks, alive, approvals, devices, identity),
        ceiling=_ceiling(identity),
    )


def _now(detail: TaskDetail | None, identity: Identity) -> pages.Markup:
    """§8 of the design: what ELA is doing, answered without opening a task manager."""
    if detail is None:
        return pages.fragment(HERE, "nothing", text=NOTHING_RUNS)
    return pages.fragment(
        HERE,
        "now",
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


def _tiles(
    tasks: tuple[TaskOut, ...],
    alive: tuple[TaskOut, ...],
    approvals: tuple[ApprovalOut, ...],
    devices: tuple[DeviceOut, ...],
    identity: Identity,
) -> pages.Markup:
    """Tasks, devices, attention: the three tiles of §7 of the design.

    The tasks tile is a **list** and not only a number, because it is how a task is reached: its
    rows link to the execution summary. It stops at :data:`SHOWN`, and when it cuts it says so in
    its own title.
    """
    usable = tuple(one for one in devices if one.available)
    recent = tuple(reversed(alive))[:SHOWN]
    return pages.joined(
        [
            pages.fragment(
                HERE,
                "tile-rows",
                title="Task"
                if len(recent) == len(alive)
                else f"Task · {len(recent)} di {len(alive)}",
                rows=pages.joined(
                    pages.fragment(
                        HERE,
                        "row-task",
                        state="WORKING" if one.state is TaskState.EXECUTING else "IDLE",
                        what=_title(one.goal, one.id, identity, one.max_privacy),
                        key=one.state.value,
                        id=one.id,
                    )
                    for one in recent
                )
                if recent
                else pages.fragment(HERE, "notice", text=NO_TASKS),
            ),
            pages.fragment(
                HERE,
                "tile",
                title="Dispositivi",
                number=f"{len(usable)} / {len(devices)}",
                detail=f"disponibili adesso · {len(tasks)} task in tutto",
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
    if seen and found.targets:
        pairs.append(pages.fragment(HERE, "pair", key="Su", value=", ".join(found.targets)))
    return pages.joined(pairs)


def _content(found: ApprovalOut, seen: bool) -> pages.Markup:
    """The goal and the declared arguments — the part a ceiling can keep on the Mac."""
    if not seen:
        return pages.Markup("")
    return pages.fragment(
        HERE,
        "asked",
        goal=found.goal,
        stated=pages.joined(pages.fragment(HERE, "stated", pair=one) for one in found.stated),
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
        rows=pages.joined(_device(one) for one in rows),
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
        pages.fragment(HERE, "pair", key="Tool", value=", ".join(one.available_tools) or "nessuno"),
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
async def cancel(request: Request, ela: ElaDep, identity: IdentityDep) -> Response:
    """The form of the confirmation page: the task stops, signed by the Command Center.

    Stopping does not ask to see: it works for a task whose content stays on the Mac too, because
    what is being asked for is less and not more.
    """
    fields = form(await request.body())
    found = await _live(ela, UUID(fields.get("id", "")))
    await cancel_task(found.id, CancelIn(reason=STOPPED), ela, identity)
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
    return pages.page(HERE, "enrol", status=status, message=message)


@router.get("/tokens.css")
async def tokens_css() -> Response:
    """The design system's tokens, read from ``apps/`` (ADR 0042), behind the identity like
    everything else: a sheet served to nobody would be the first anonymous route of ELA."""
    return pages.stylesheet("tokens.css")


@router.get("/components.css")
async def components_css() -> Response:
    """The design system's components, on the same terms as :func:`tokens_css`."""
    return pages.stylesheet("components.css")
