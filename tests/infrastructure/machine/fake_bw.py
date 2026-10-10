"""A ``bw`` of the tests, for the adapter of the vault (M13.9): the commands ELA composes, and
nothing of a vault.

**It is not the CLI of Bitwarden and proves nothing about it.** It prints what the real one
prints for the commands the adapter launches — ``status``, ``list items --url``, ``get item``,
``lock`` —, in the shape measured on 2026-10-10 with the real ``bw`` 2026.9.1
(``docs/milestones/M13.9.md``, «Le misure di Tommaso»): a status that carries the account's
address, a listing and an entry that carry **every** field of an item, the password among them.

A test copies this file into a folder of its own, with the interpreter of the suite on its first
line, and writes beside it ``state.json``:

* ``status`` — ``unauthenticated``, ``locked`` or ``unlocked``: what the vault is;
* ``key`` — the session key that opens it: ``status`` says ``unlocked`` only to whoever carries it
  in ``BW_SESSION``;
* ``items`` — what the vault holds;
* ``hang``, ``garbage``, ``fail`` — lists of command words (``status``, ``list``, ``get``,
  ``lock``): that command never answers, answers something that is not JSON, or exits with 1.

Beside it, it writes ``calls.jsonl``: for each call the arguments, **the whole environment it
received**, how many bytes its stdin held, and its own pid — which is how a test reads what the
adapter handed a child, and whether a child that hung is still there.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADDRESS = "the-account-of-the-test@example.invalid"


def main(arguments: list[str]) -> int:
    state = json.loads((HERE / "state.json").read_text(encoding="utf-8"))
    stdin = sys.stdin.buffer.read()
    with (HERE / "calls.jsonl").open("a", encoding="utf-8") as calls:
        calls.write(
            json.dumps(
                {
                    "argv": arguments,
                    "environment": dict(os.environ),
                    "stdin": len(stdin),
                    "pid": os.getpid(),
                    "group": os.getpgid(0),
                }
            )
            + "\n"
        )
    word = arguments[0] if arguments else ""
    if word in state.get("hang", []):
        time.sleep(600)
    if word in state.get("fail", []):
        print("the command failed", file=sys.stderr)
        return 1
    if word in state.get("garbage", []):
        print("this is not JSON {" + json.dumps(state.get("items", [])))
        return 0
    opened = state["status"] == "unlocked" and os.environ.get("BW_SESSION") == state.get("key")
    if word == "status":
        said = state["status"] if state["status"] != "unlocked" or opened else "locked"
        print(
            json.dumps({"serverUrl": None, "lastSync": None, "userEmail": ADDRESS, "status": said})
        )
        return 0
    if word == "lock":
        state["status"] = "locked" if state["status"] != "unauthenticated" else state["status"]
        (HERE / "state.json").write_text(json.dumps(state), encoding="utf-8")
        print("Your vault is locked.")
        return 0
    if not opened:
        print("Vault is locked.", file=sys.stderr)
        return 1
    if arguments[:3] == ["list", "items", "--url"] and len(arguments) == 4:
        print(json.dumps(state.get("items", [])))
        return 0
    if arguments[:2] == ["get", "item"] and len(arguments) == 3:
        for item in state.get("items", []):
            if item["id"] == arguments[2]:
                print(json.dumps(item))
                return 0
        print("Not found.", file=sys.stderr)
        return 1
    print(f"a command the adapter of ELA does not compose: {arguments}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
