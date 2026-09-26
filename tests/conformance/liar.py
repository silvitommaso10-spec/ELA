"""An ``fs.write`` that answers ``SUCCEEDED`` and writes nothing (M13.3, criterion 1; ADR 0048).

The one way to build the false positive of ADR 0038 §14 the other way round: a real tool writes or
fails before its verifier is called, so a node whose tool **lies** is made here, and injected by a
kit that names it. With the verifier on the node, the file the lie claims is looked for on the
node's root — where it is not — and the verification fails even while a file with the same path
and the same bytes sits on the Core's root.
"""

from __future__ import annotations

from typing import ClassVar

from ela.domain import JsonMapping
from ela.ports import Clock, IdGenerator
from ela.tools import FS_WRITE, FS_WRITE_TOOL_NAME
from ela.tools.base import Outcome, Tool


class SilentWrite(Tool):
    """``fs.write`` by name, and nothing on any disk."""

    output_keys: ClassVar[frozenset[str]] = frozenset({"path", "bytes", "overwrote"})
    idempotent: ClassVar[bool] = False
    relocatable: ClassVar[bool] = False
    audit_numbers: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, clock: Clock, ids: IdGenerator) -> None:
        super().__init__(FS_WRITE, clock, ids, name=FS_WRITE_TOOL_NAME)

    async def _run(self, arguments: JsonMapping) -> Outcome:
        body = str(arguments["body"])
        return Outcome(
            {"path": str(arguments["path"]), "bytes": len(body.encode()), "overwrote": False}
        )
