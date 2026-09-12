"""The seven acts a node performs over HTTP, and nothing it decides (M12.1 D4; ADR 0038 §11).

The node *pulls*: it opens no listening socket and receives no webhook, so the latency of a work
order is its own polling cycle and that is declared rather than hidden (D4). Every act answers with
what the Core said — a :class:`Reply`, status and body — instead of raising on a refusal, because
what the node does about a ``409`` is not the same thing as what it does about a ``410``, and a
layer that turned both into an exception would have thrown the difference away before the decision.

One credential on every request, ``<id>.<secret>`` after ``Bearer`` (ADR 0037 §4), and no id in any
path: the identity *is* the id, a node speaks only for itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import httpx

from ela.node.state import NodeIdentity

__all__ = [
    "ASK_TIMEOUT_SECONDS",
    "CONNECT_TIMEOUT_SECONDS",
    "NodeClient",
    "Reply",
    "open_node_client",
]

CONNECT_TIMEOUT_SECONDS: Final = 5.0
"""How long to wait for the Core to answer at all before calling it unreachable."""

ASK_TIMEOUT_SECONDS: Final = 300.0
"""How long a request for work may stay open before the node treats it as a dead connection.

``POST /nodes/work`` is a long poll: the Core holds it for up to ``ELA_NODE_POLL_SECONDS`` — 25 by
default — and answers ``204`` if nothing arrived. A node cannot read the Core's environment, so
this has to be a ceiling over that setting rather than equal to it, and it is deliberately far
above: a read timeout shorter than the Core's hold would turn the normal case into a dropped
connection every cycle. To be measured against a real node together with the rest of dec. K.
"""


@dataclass(frozen=True, slots=True)
class Reply:
    """What the Core answered: the status, the body, and the ``ETag`` where there is one."""

    status: int
    body: Mapping[str, Any]
    etag: str | None = None

    @property
    def code(self) -> str | None:
        """The ``error.code`` of a refusal (ADR 0023 §10), or ``None`` if this is not one.

        The node branches on this and not on the status: ``409`` is two different answers —
        ``already_running``, which means keep the envelope and come back, and ``delivery.conflict``,
        which means the Core has already decided and the envelope is nobody's.
        """
        error = self.body.get("error")
        if isinstance(error, Mapping):
            code = error.get("code")
            if isinstance(code, str):
                return code
        return None


def _body(response: httpx.Response) -> Mapping[str, Any]:
    """The JSON of an answer, or nothing for the ``204`` that says there was no work."""
    if response.status_code == httpx.codes.NO_CONTENT:
        return {}
    parsed: Any = response.json()
    return parsed if isinstance(parsed, Mapping) else {"body": parsed}


class NodeClient:
    """The Core, as a node sees it: seven acts, one credential, no decisions."""

    def __init__(self, client: httpx.AsyncClient, identity: NodeIdentity | None = None) -> None:
        self._client = client
        self._identity = identity

    @property
    def identity(self) -> NodeIdentity | None:
        return self._identity

    @property
    def _bearer(self) -> dict[str, str]:
        if self._identity is None:  # pragma: no cover - the cycle enrolls before it speaks
            raise RuntimeError("this node has no identity yet")
        return {"Authorization": f"Bearer {self._identity.bearer}"}

    # ----------------------------------------------------------------------------------
    # Becoming a node, and reading what the Core knows of it
    # ----------------------------------------------------------------------------------

    async def enroll(self, code: str, declaration: Mapping[str, Any]) -> Reply:
        """Present the code once and receive the identity: id, secret, revision (ADR 0037 §5).

        The one answer of ELA that carries a node's secret, and it carries it once. On ``201`` the
        identity is kept here so the caller can write it down before anything else happens: a
        secret received and not stored is a row nobody can revoke because nobody can name it.
        """
        answered = await self._client.post(
            "/nodes/enroll", json=dict(declaration), headers={"Authorization": f"Bearer {code}"}
        )
        body = _body(answered)
        if answered.status_code == httpx.codes.CREATED:
            self._identity = NodeIdentity(
                device_id=str(body["device_id"]), secret=str(body["secret"])
            )
        return Reply(answered.status_code, body)

    async def whoami(self) -> Reply:
        """``GET /nodes/me``: the node's own row, and the revision in the ``ETag`` (M12.3 dec. L).

        What a process that came back asks first. It kept its id and its secret on disk and nothing
        else, so the revision is a thing it has to ask for — and the answer puts it exactly where
        the announcement looks for it.
        """
        answered = await self._client.get("/nodes/me", headers=self._bearer)
        return Reply(answered.status_code, _body(answered), answered.headers.get("ETag"))

    async def announce(self, declaration: Mapping[str, Any], revision: int) -> Reply:
        """``PUT /nodes/me`` at the revision last seen: ``If-Match`` in, ``ETag`` out (§9).

        Conditional and never unconditional: a node that announced without the condition would
        overwrite whatever another process claiming its identity had written, and the conflict
        ADR 0035 §5 exists to name would stop being visible to anyone.
        """
        answered = await self._client.put(
            "/nodes/me",
            json=dict(declaration),
            headers={**self._bearer, "If-Match": f'"{revision}"'},
        )
        return Reply(answered.status_code, _body(answered), answered.headers.get("ETag"))

    async def report(self, **observed: Any) -> Reply:
        """``POST /nodes/heartbeat``: a sign of life, and no event (ADR 0016 §6)."""
        answered = await self._client.post(
            "/nodes/heartbeat", json=dict(observed), headers=self._bearer
        )
        return Reply(answered.status_code, _body(answered))

    # ----------------------------------------------------------------------------------
    # The work (ADR 0038 §11)
    # ----------------------------------------------------------------------------------

    async def ask(self) -> Reply:
        """``POST /nodes/work``: ask, and wait there. ``200`` an order, ``204`` nothing."""
        answered = await self._client.post(
            "/nodes/work", headers=self._bearer, timeout=ASK_TIMEOUT_SECONDS
        )
        return Reply(answered.status_code, _body(answered))

    async def deliver(self, envelope: Mapping[str, Any]) -> Reply:
        """``POST /nodes/work/result``: the envelope, with the id of the work in the body."""
        answered = await self._client.post(
            "/nodes/work/result", json=dict(envelope), headers=self._bearer
        )
        return Reply(answered.status_code, _body(answered))

    async def renew(self, assignment_id: str) -> Reply:
        """``POST /nodes/work/renew``: ask for more time on the work in hand, never take it."""
        answered = await self._client.post(
            "/nodes/work/renew", json={"assignment_id": assignment_id}, headers=self._bearer
        )
        return Reply(answered.status_code, _body(answered))

    async def aclose(self) -> None:
        await self._client.aclose()


def open_node_client(
    core_url: str,
    identity: NodeIdentity | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> NodeClient:
    """A client pointed at the Core, with the identity it has if it has one.

    ``transport`` is the seam, and it is the same one ``cli/client.py`` has for the same reason:
    the conformance suite passes one that reaches the application in this process, so the stories
    are recited against the real routes without a socket — ``tests/conftest.py`` forbids the suite
    a real one, and §57 is why.
    """
    return NodeClient(
        httpx.AsyncClient(base_url=core_url, transport=transport, timeout=CONNECT_TIMEOUT_SECONDS),
        identity,
    )
