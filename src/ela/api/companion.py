"""The pages of the iPhone: see what waits, and answer it (M12.5 dec. A, D, F, H; ADR 0043).

The companion is a **client of the API like the CLI**, and here that is a property and not a
promise: every page is composed from what a route function returns, and this module never reaches
a port, a store, the catalogue or the executor through :class:`~ela.composition.Ela` — architecture
rule 55, with its negative case. What a page needs and a route does not give is a route that grows
(that is how ``ApprovalOut`` grew, dec. F), never a second read of the world from here.

The perimeter is **see and answer, not command** (the user's fixed point 3): the pages show the
questions that wait and the tasks that are alive, answer a question, and stop a task. Nothing
creates a task, nothing edits a plan, nothing touches a node.

Three things this module holds that have nowhere else to be, and each has its reason:

* the **projection** of the presence — three states of §6 of the design, computed at every read and
  stored nowhere (5.10);
* the **ceiling** of what the iPhone may be shown: the comparison of F2 of the orchestrator, with
  the level the identity carries (dec. F.2);
* the **order of a "yes"**: answer first, then run, in this request (dec. H1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from ela.api import pages
from ela.api.approvals import answered_and_resumed, pending_approvals
from ela.api.deps import ElaDep, IdentityDep, RunningDep
from ela.api.nodes import enrolled
from ela.api.schemas import ApprovalOut, CancelIn, DeclarationIn, TaskOut
from ela.api.security import COMPANION_SURFACE, Anonymous, Identity, note, welcome
from ela.api.tasks import cancel_task, list_tasks
from ela.devices import PRIVACY_ORDER
from ela.domain import ApprovalId, DeviceRole, OperatingSystem, PrivacyLevel, TaskId, TaskState
from ela.ports import (
    ApprovalOutOfReachError,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    EnrollmentRoleError,
    NotFoundError,
)
from ela.tasks.engine import LIVE_STATES

__all__ = [
    "HOME",
    "SPOKEN_ALOUD",
    "counted",
    "form",
    "how_long",
    "may_see",
    "presence",
    "router",
    "terms",
    "when",
]

router = APIRouter(prefix="/companion", tags=["companion"])

HERE: Final = COMPANION_SURFACE.templates
"""Which folder of ``apps/`` this module's markup comes from (M17.2 dec. E)."""
WHERE: Final = COMPANION_SURFACE.prefix
"""Where this surface's two stylesheets are served: the composer writes the ``href`` from it."""
HOME: Final = "/companion/"
WAITING_APPROVAL: Final = "WAITING APPROVAL"
WORKING: Final = "WORKING"
IDLE: Final = "IDLE"
"""The three states of the presence this milestone can derive (dec. D).

Every other state of §6 of the design has a source that would make the sphere say something ELA
does not know — ``PLANNING`` while it waits for a plan written by hand, ``ERROR`` for ever after a
failure, ``WAITING`` without knowing whether a step is *at* a node or waiting *for* one. M17.2
extends them; a test pins these three inside the keys of ``tokens.json``.
"""

SPOKEN_ALOUD: Final = frozenset({"voice.speak", "voice.speak_online"})
"""The capabilities whose words are not in the question (M11.1 dec. B), read from far away (F.4).

M11.1 kept the text out of the question because «you hear the words a second later». From the
iPhone that is not true: the Mac speaks in a room the user is not in, and the page says so instead
of reopening that decision.
"""
SPEAKS: Final = "ELA parlerà ad alta voce su una macchina tua: le parole non sono nella domanda."
STAYS_ON_THE_MAC: Final = "Il contenuto resta sul Mac: rispondi da lì."
NOTHING: Final = "Nient'altro ti aspetta."
AFTER_YES: Final = "ELA riprende il task adesso; uno step affidato a un altro nodo aspetta."
STOPPED: Final = "fermato dall'iPhone"
"""What the audit reads as the reason of a cancellation asked from the phone (§65)."""
AN_IPHONE: Final = "Il companion è un iPhone: lascia «IOS» nel campo Sistema e dai un nome."
NO_SUCH_CODE: Final = "Questo codice non esiste. Coniane uno al Mac e incollalo qui."
TOO_LATE: Final = "Questo codice è scaduto: dura dieci minuti. Coniane un altro."
ALREADY_SPENT: Final = "Questo codice è già stato usato. Coniane un altro."
A_NODES_CODE: Final = "Questo è il codice di un nodo. Per il telefono serve --role companion."
SHOWN: Final = 6
"""How many live tasks a page lists, newest first."""
CODE_FIELD: Final = "code"
ANSWER_FIELD: Final = "answer"
YES: Final = "yes"


# ----------------------------------------------------------------------------------------
# What the pages are allowed to say
# ----------------------------------------------------------------------------------------


def presence(approvals: tuple[ApprovalOut, ...], tasks: tuple[TaskOut, ...]) -> str:
    """The state the sphere shows, derived at every read and kept nowhere (5.10, dec. D).

    In this order of precedence: a question that waits is what ELA needs *from the user*, and it
    comes first; then work; then rest.
    """
    if approvals:
        return WAITING_APPROVAL
    if any(task.state is TaskState.EXECUTING for task in tasks):
        return WORKING
    return IDLE


def may_see(identity: Identity, max_privacy: PrivacyLevel | None) -> bool:
    """Whether what this identity is allowed to receive covers a task's content (dec. F2-a).

    The comparison of the orchestrator's F2 filter, with the ceiling the user imposed on **this**
    identity at enrolment: showing the goal of a ``LOCAL_ONLY`` task on the iPhone is making it
    leave the Mac, and ``PrivacyLevel`` says of itself «what data may leave a node».

    Unknown on either side is a no (§33): a question with no ceiling and an identity with no level
    are both cases where nobody declared that this may travel.
    """
    if identity.privacy is None or max_privacy is None:
        return False
    return PRIVACY_ORDER[identity.privacy] <= PRIVACY_ORDER[max_privacy]


def form(body: bytes) -> dict[str, str]:
    """An ``application/x-www-form-urlencoded`` body, read with the standard library.

    Not ``request.form()``: Starlette parses a form only with ``python-multipart`` installed, and
    a third-party parser for file uploads is a large thing to add for three fields — a page able
    to read ``multipart/form-data`` is a page that accepts a file. The middleware reads the same
    way, and a test pins that the body it consumed reaches the route whole (dec. C.3, §«Rischi»).
    """
    return dict(parse_qsl(body.decode("utf-8", "replace")))


def counted(how_many: int, one: str, many: str) -> str:
    """``how_many`` in words: nothing at all, the singular, or the number and the plural."""
    if how_many == 0:
        return ""
    return one if how_many == 1 else f"{how_many} {many}"


def how_long(seconds: int) -> str:
    """A number of seconds as the page says it: the units it really is, and no rounding.

    Derived and never written by hand, because ``ELA_AUTHORIZATION_TTL_SECONDS`` is the **user's**
    setting: at 1800 a phrase with the hours divided out said «entro 0 ora», and at 7200 «2 ora».
    This is the page where consent is given, and what is approved has to name what it is.
    """
    hours, rest = divmod(seconds, 3600)
    minutes, moments = divmod(rest, 60)
    said = [
        part
        for part in (
            counted(hours, "un'ora", "ore"),
            counted(minutes, "un minuto", "minuti"),
            counted(moments, "un secondo", "secondi"),
        )
        if part
    ]
    return " e ".join(said) if said else "nessun tempo"


def terms(uses: int, seconds: int) -> str:
    """What a "yes" grants, in one line: how many times it may be spent, and until when.

    ``ADR 0012 §2``: a grant born from an approval is single use and lives for the configured TTL.
    Both numbers come from the question (dec. F), and both are said as they are — a promise that
    rounded itself would be a promise about something else.
    """
    return f"{counted(uses, 'un uso', 'usi')}, entro {how_long(seconds)} dal tuo sì"


def when(moment: datetime | None) -> str:
    """An instant as a page shows it: the time, and nothing that says what it is about.

    Shared with the Command Center, like :func:`presence` and :func:`may_see` (M17.2): both
    modules are walked by architecture rule 55, so the projection stays where the first surface
    wrote it rather than moving to a module the rule does not walk.
    """
    return "" if moment is None else moment.astimezone().strftime("%H:%M")


# ----------------------------------------------------------------------------------------
# The pages
# ----------------------------------------------------------------------------------------


@router.get("/")
async def home(
    ela: ElaDep,
    identity: IdentityDep,
    task: Annotated[UUID | None, Query()] = None,
) -> Response:
    """Everything that waits, and everything that is alive (dec. D).

    ``task`` is the one a "yes" was just given to: it is shown with its **true** state even when
    that state is final, because what the user wants to know after answering is what happened —
    and a task that closed would otherwise vanish from the page that was supposed to report it.
    """
    approvals = await pending_approvals(ela)
    tasks = await list_tasks(ela)
    alive = tuple(one for one in tasks if one.state in LIVE_STATES)
    answered = tuple(one for one in tasks if task is not None and one.id == task)
    return pages.page(
        HERE,
        "home",
        sheets=WHERE,
        state=presence(approvals, alive),
        waiting=_waiting(approvals),
        tasks=_tasks(alive, answered, identity),
    )


def _waiting(approvals: tuple[ApprovalOut, ...]) -> pages.Markup:
    if not approvals:
        return pages.fragment(HERE, "notice", text=NOTHING)
    return pages.fragment(
        HERE,
        "waiting",
        rows=pages.joined(
            pages.fragment(
                HERE,
                "row-approval",
                id=one.id,
                what=one.capability_id,
                when=when(one.created_at),
                risk="" if one.risk is None else one.risk.value,
            )
            for one in approvals
        ),
    )


def _tasks(
    alive: tuple[TaskOut, ...], answered: tuple[TaskOut, ...], identity: Identity
) -> pages.Markup:
    """The answered one first, then the live ones, newest first and no more than :data:`SHOWN`.

    A phone is not a dashboard: a list that grows without a bound stops being readable on the
    screen it was made for, and what the user opens the page for is what is happening now. What it
    does **not** do is let the cut pass in silence — the title carries it, because a page that
    showed six of nine under a title saying «the tasks» would be a page that lies quietly.
    """
    live = tuple(one for one in reversed(alive) if one not in answered)
    recent = live[:SHOWN]
    if not answered and not recent:
        return pages.Markup("")
    return pages.fragment(
        HERE,
        "tasks",
        # A list that stops at six and calls itself «I task» says something false the day there
        # are nine (the review of 2026-09-20): when it cuts, it says how much it is showing.
        title="I task" if len(recent) == len(live) else f"I task · {len(recent)} di {len(live)}",
        rows=pages.joined(
            [
                # The one just answered is shown as it *is*, and it is not offered a "stop": it may
                # have closed a second ago, and a page that invited the user to stop what is over
                # would be a page that does not know what happened (dec. D, dec. I).
                *(
                    pages.fragment(
                        HERE, "row-done", what=_title(one, identity), key=one.state.value
                    )
                    for one in answered
                ),
                *(
                    pages.fragment(
                        HERE,
                        "row-task",
                        state=WORKING if one.state is TaskState.EXECUTING else IDLE,
                        what=_title(one, identity),
                        key=one.state.value,
                        id=one.id,
                    )
                    for one in recent
                ),
            ]
        ),
    )


def _title(task: TaskOut, identity: Identity) -> object:
    """What a row calls a task: its goal, or its id when the ceiling keeps the goal on the Mac."""
    return task.goal if may_see(identity, task.max_privacy) else task.id


@router.post("/enroll")
async def enrol(request: Request, ela: ElaDep, identity: IdentityDep) -> Response:
    """The browser presents the code the user pasted, and leaves with its credential (dec. C.5).

    The same function the nodes' route spends a code with, asked for the other role: what differs
    is the answer. A node's secret comes back in a body, once; a browser's goes into a
    ``Set-Cookie`` and is never spoken again — which is why a companion's code on
    ``POST /nodes/enroll`` gets a ``422`` instead.

    Every refusal is **this page again**, with the sentence that says what to do: unknown, expired
    or already spent is a ``401``; a code minted for a node, or a declaration that is not an
    iPhone, is a ``422``. The page carries the command that mints the right code, so the user
    never has to go looking for it.
    """
    assert identity.code is not None  # the middleware lets only a code through here
    fields = form(await request.body())
    try:
        declared = DeclarationIn(
            name=fields.get("name", "").strip(),
            os=OperatingSystem(fields.get("os", "").strip()),
        )
    except ValueError:
        return _again(AN_IPHONE, status=422)
    if declared.os is not OperatingSystem.IOS:
        # Dec. A: a companion that declared another system would be a row that lies about what it
        # is — and the declared half is never rewritten, so the lie would outlive the mistake.
        return _again(AN_IPHONE, status=422)
    try:
        born = await enrolled(ela, code=identity.code, role=DeviceRole.COMPANION, declared=declared)
    except NotFoundError:
        note(request, Anonymous.UNKNOWN_CODE)
        return _again(NO_SUCH_CODE)
    except EnrollmentExpiredError:
        note(request, Anonymous.EXPIRED_CODE)
        return _again(TOO_LATE)
    except EnrollmentConsumedError:
        return _again(ALREADY_SPENT)
    except EnrollmentRoleError:
        return _again(A_NODES_CODE, status=422)
    return welcome(COMPANION_SURFACE, born.device.id, born.secret)


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


@router.get("/cancel")
async def confirm(ela: ElaDep, identity: IdentityDep, id: Annotated[UUID, Query()]) -> Response:
    """The second page of stopping a task (dec. I): without JavaScript, a confirmation is a page.

    §65 wants ELA «estremamente governabile», and a route that only **takes away** is the first
    one that makes sense to give a phone: a cancelled task does nothing more, and stopping is the
    direction of §33. The price is said on the page: it cannot be undone.
    """
    found = await _live(ela, id)
    return pages.page(
        HERE,
        "cancel",
        sheets=WHERE,
        what=found.goal if may_see(identity, found.max_privacy) else found.id,
        state=found.state.value,
        id=found.id,
    )


@router.post("/cancel")
async def cancel(request: Request, ela: ElaDep, identity: IdentityDep) -> Response:
    """The form of the confirmation page: the task stops, signed by the iPhone (dec. I).

    Stopping does not ask to see: it works for a task whose content stays on the Mac too (F.2),
    because what is being asked for is less and not more.
    """
    fields = form(await request.body())
    found = await _live(ela, UUID(fields.get("id", "")))
    await cancel_task(found.id, CancelIn(reason=STOPPED), ela, identity)
    return RedirectResponse(HOME, status_code=303)


async def _live(ela: ElaDep, id: UUID) -> TaskOut:
    """The task with this id, among the ones that can still be stopped, or nothing.

    Read through the route (rule 55), and among the live ones for the reason the approval page
    reads the answerable ones: a page must not offer what ELA would refuse (§33).
    """
    found = next(
        (one for one in await list_tasks(ela) if one.id == id and one.state in LIVE_STATES), None
    )
    if found is None:
        raise NotFoundError("task", str(id))
    return found


@router.get("/approval")
async def approval(ela: ElaDep, identity: IdentityDep, id: Annotated[UUID, Query()]) -> Response:
    """One question, with the parts of it a page can show (dec. F).

    Everything it shows comes from ``ApprovalOut``: the description of the capability, the risk of
    the catalogue, how far the task may travel, the terms of the grant a "yes" mints. What is not
    shown is as deliberate: **the node**, because the level is immutable and the placement is not
    (ADR 0038 §16), and the consequences, because the catalogue does not state them and a page
    that wrote them would be inventing them.
    """
    found = await _answerable(ela, id)
    seen = may_see(identity, found.max_privacy)
    return pages.page(
        HERE,
        "approval",
        sheets=WHERE,
        capability=found.capability_id,
        description=found.description if seen else "",
        pairs=_pairs(found, seen),
        content=_content(found, seen),
        answer=pages.fragment(HERE, "answer", id=found.id)
        if seen
        else pages.fragment(HERE, "notice", text=STAYS_ON_THE_MAC),
        after=AFTER_YES if seen else "",
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
    # The two facts of the machine a question about a file must name (M13.1 dec. G), and the
    # reason this surface may answer it at all (dec. H): a surface that did not show them would
    # be offering a yes to something it has not said.
    if seen and found.target:
        pairs.append(pages.fragment(HERE, "pair", key="Il file", value=found.target))
    if seen and found.does:
        # The sentence comes from the capability and is rendered as it stands (M13.1 dec. G):
        # a page that composed one would be lending a write's words to a read.
        pairs.append(pages.fragment(HERE, "pair", key="Che cosa fa", value=found.does))
    return pages.joined(pairs)


def _content(found: ApprovalOut, seen: bool) -> pages.Markup:
    """The goal and the declared arguments — the part a ceiling can keep on the Mac (F2-a)."""
    if not seen:
        return pages.Markup("")
    said = (
        [pages.fragment(HERE, "notice", text=SPEAKS)] if found.capability_id in SPOKEN_ALOUD else []
    )
    return pages.joined(
        [
            pages.fragment(
                HERE,
                "asked",
                goal=found.goal,
                stated=pages.joined(
                    pages.fragment(HERE, "stated", pair=one) for one in found.stated
                ),
            ),
            *said,
        ]
    )


@router.post("/answer")
async def answer(
    request: Request, ela: ElaDep, identity: IdentityDep, running: RunningDep
) -> Response:
    """The "yes" or the "no" — and, after a "yes", the run it would otherwise wait for (dec. H1).

    The two things the user does at the Mac, ``ela task approve`` and ``ela task run``, each from
    its own function: a "yes" that sat there until the user came home would not make ELA usable
    away from the Mac. A "no" runs nothing — the task is DENIED.

    The browser may stop waiting before a long run ends — the page closes, the phone locks, the
    tailnet drops. The run goes on, exactly as it does when ``ela task run`` is interrupted at the
    terminal, and the next page shows the task's true state (declared, dec. H).
    """
    fields = form(await request.body())
    found = await _answerable(ela, UUID(fields.get("id", "")))
    if not may_see(identity, found.max_privacy):
        raise ApprovalOutOfReachError(ApprovalId(found.id))
    task_id = TaskId(found.task_id)
    said_yes = fields.get(ANSWER_FIELD) == YES
    await answered_and_resumed(
        found, said_yes=said_yes, ela=ela, identity=identity, running=running
    )
    return RedirectResponse(f"{HOME}?task={task_id}", status_code=303)


async def _answerable(ela: ElaDep, id: UUID) -> ApprovalOut:
    """The question with this id, among the ones that can still be answered, or nothing.

    Read through the route and not from the store (rule 55), which also settles a question this
    module would otherwise have to ask itself: ``GET /approvals`` already leaves out what expired
    and what belongs to a task that moved on, and a page must not offer an answer ELA would
    refuse (§33).
    """
    found = next((one for one in await pending_approvals(ela) if one.id == id), None)
    if found is None:
        raise NotFoundError("approval", str(id))
    return found
