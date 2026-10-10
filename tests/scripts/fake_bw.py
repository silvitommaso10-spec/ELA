#!/usr/bin/env python3
"""A ``bw`` of the tests: the commands ``scripts/misura_m13_9.py`` composes, and nothing of a vault.

**It is not the CLI of Bitwarden and proves nothing about it.** It answers what the real one
answers **without an account** — those answers were recorded from the real ``bw`` 2026.9.1 on
2026-10-10 and ``tests/scripts/test_misura_m13_9.py`` holds this file to them — and, with an
account, what the help and the sources of the real one say: a session key printed alone with
``--raw``, a new ``unlock`` that ends the keys before it, ``lock`` that ends them all, a status that
prints the account's address, a listing that carries every password.

Its state is one file in ``BITWARDENCLI_APPDATA_DIR``; beside this script it writes
``fake-bw-calls.jsonl`` — the arguments of each call, and the **names** of what it found in its
environment —, which is how a test reads what the measure handed a child.

What a test wants different it writes in ``fake-bw.json`` beside this script: ``"refuse"`` for
``login``, ``unlock``, ``logout`` or ``delete`` is that command turned down.
"""

from __future__ import annotations

import base64
import json
import os
import stat
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BITWARDENCLI_APPDATA_DIR") or HERE / "fake-bw-data")
STATE = DATA / "data.json"
ADDRESS = "finto@example.invalid"
VERSION = "2026.9.1"
NOT_LOGGED_IN = "You are not logged in."
LOCKED = "Vault is locked."


def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    DATA.mkdir(parents=True, exist_ok=True)
    return {"stateVersion": 85}


def save(state: dict) -> None:
    STATE.write_text(json.dumps(state), encoding="utf-8")
    STATE.chmod(0o600)


def wanted() -> dict:
    file = HERE / "fake-bw.json"
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}


def record(arguments: list[str], stdin: bytes) -> None:
    zero, one = os.fstat(0), os.fstat(1)
    row = {
        "argv": arguments,
        "stdin": [zero.st_dev, zero.st_ino],
        "stdin_is_the_null_device": stat.S_ISCHR(zero.st_mode)
        and zero.st_rdev == os.stat(os.devnull).st_rdev,
        "stdout_is_a_pipe": stat.S_ISFIFO(one.st_mode),
        "session_in_the_environment": "BW_SESSION" in os.environ,
        "no_interaction": os.environ.get("BW_NOINTERACTION"),
        "environment_names": sorted(os.environ),
        "stdin_bytes": len(stdin),
    }
    with (HERE / "fake-bw-calls.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(row) + "\n")


def fail(message: str) -> int:
    sys.stderr.write(message)
    return 1


def new_key(state: dict) -> str:
    state["keys_made"] = state.get("keys_made", 0) + 1
    key = f"chiave-finta-di-sessione-numero-{state['keys_made']}-" + "k" * 40
    state["valid_key"] = key
    return key


def host_of(address: str) -> str:
    return urlsplit(address).hostname or ""


def main(arguments: list[str]) -> int:
    stdin = b""
    if arguments[:1] == ["create"] and len(arguments) < 3:
        stdin = sys.stdin.buffer.read()
    record(arguments, stdin)
    raw = "--raw" in arguments
    words = [word for word in arguments if word != "--raw"]
    state = load()
    save(state)
    if words == ["--version"]:
        print(VERSION)
        return 0
    command, rest = words[0], words[1:]
    account = state.get("account")
    valid = state.get("valid_key")
    open_ = account is not None and valid is not None and os.environ.get("BW_SESSION") == valid

    if command == "status":
        if account is None:
            sys.stdout.write('{"serverUrl":null,"lastSync":null,"status":"unauthenticated"}')
            return 0
        sys.stdout.write(
            json.dumps(
                {
                    "serverUrl": state.get("server", "https://vault.bitwarden.com"),
                    "lastSync": "2026-10-10T10:00:00.000Z",
                    "userEmail": ADDRESS,
                    "userId": account,
                    "status": "unlocked" if open_ else "locked",
                },
                separators=(",", ":"),
            )
        )
        return 0
    if command == "config":
        if len(rest) == 1:
            sys.stdout.write(state.get("server", "https://bitwarden.com"))
        else:
            state["server"] = rest[1]
            save(state)
            sys.stdout.write("Saved setting `config`.")
        return 0
    if command == "login":
        if account is not None:
            return fail("You are already logged in as " + ADDRESS + ".")
        if wanted().get("login") == "refuse":
            return fail("Username or password is incorrect. Try again.")
        state["account"] = str(uuid.uuid4())
        key = new_key(state)
        save(state)
        sys.stdout.write(key if raw else f'You are logged in!\n\n$ export BW_SESSION="{key}"')
        return 0
    if account is None:
        return fail(NOT_LOGGED_IN)
    if command == "unlock":
        if wanted().get("unlock") == "refuse":
            return fail("Invalid master password.")
        key = new_key(state)
        save(state)
        sys.stdout.write(
            key if raw else f'Your vault is now unlocked!\n\n$ export BW_SESSION="{key}"'
        )
        return 0
    if command == "lock":
        state["valid_key"] = None
        save(state)
        sys.stdout.write("Your vault is locked.")
        return 0
    if command == "logout":
        if wanted().get("logout") == "refuse":
            return fail("A server that does not answer.")
        save({"stateVersion": 85})
        sys.stdout.write("You have logged out.")
        return 0
    if not open_:
        return fail(LOCKED)

    items: dict[str, dict] = state.setdefault("items", {})
    if command == "create" and rest[:1] == ["item"]:
        encoded = rest[1].encode() if len(rest) > 1 else stdin
        item = json.loads(base64.b64decode(encoded))
        item["id"] = str(uuid.uuid4())
        item["object"] = "item"
        items[item["id"]] = item
        save(state)
        sys.stdout.write(json.dumps(item))
        return 0
    if command == "list" and rest[:1] == ["items"]:
        found = list(items.values())
        if "--url" in rest:
            host = host_of(rest[rest.index("--url") + 1])
            found = [
                item
                for item in found
                if any(host_of(uri["uri"]) == host for uri in item["login"]["uris"])
            ]
        if "--search" in rest:
            term = rest[rest.index("--search") + 1].lower()
            found = [item for item in found if term in item["name"].lower()]
        sys.stdout.write(json.dumps(found))
        return 0
    if command == "get":
        what, identifier = rest[0], rest[1]
        if what == "template":
            sys.stdout.write(json.dumps({"type": 1, "name": "Item name", "login": None}))
            return 0
        item = items.get(identifier)
        if item is None:
            return fail("Not found.")
        answer = {
            "item": json.dumps(item),
            "uri": item["login"]["uris"][0]["uri"],
            "username": item["login"]["username"],
            "password": item["login"]["password"],
        }[what]
        sys.stdout.write(answer)
        return 0
    if command == "delete" and rest[:1] == ["item"]:
        if wanted().get("delete") == "refuse":
            return fail("A server that does not answer.")
        if items.pop(rest[1], None) is None:
            return fail("Not found.")
        save(state)
        return 0
    return fail(f"fake bw: no answer for {arguments!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
