"""A program of the tests where Chrome for Testing would be, for the window of the browser with
the user's accounts (M13.9): what ELA starts, and nothing of a browser.

**It is not a browser and proves nothing about one.** It stands where the adapter looks for the
binary, so that what the adapter does to *a process* — what it starts it with, how it tells it to
end, when it kills it, what it keeps of it — is asserted on every machine the suite runs on, with
no window on anybody's screen. What only the real binary can say is in ``test_account_browser.py``.

A test copies this file where the binary would be, with the interpreter of the suite on its first
line, and may write beside it ``behaviour.json``:

* ``deaf`` — it ignores ``SIGTERM``: the browser that was told to end and did not;
* ``exits`` — it ends at once: a binary that does not stay.

Beside it, it writes ``launched.jsonl`` — **once it is ready to be told anything**: its arguments,
the whole environment it received, its pid and its session, and whether each of its three streams
goes nowhere.
"""

from __future__ import annotations

import json
import os
import signal
import stat
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAYS = 120
"""How long it stays if nobody ends it: longer than any wait of a test, and short enough that one
a broken run left behind ends by itself."""


def _nowhere(descriptor: int) -> bool:
    found, null = os.fstat(descriptor), os.stat(os.devnull)
    return stat.S_ISCHR(found.st_mode) and found.st_rdev == null.st_rdev


def main(arguments: list[str]) -> int:
    file = HERE / "behaviour.json"
    behaviour = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    if behaviour.get("deaf"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    with (HERE / "launched.jsonl").open("a", encoding="utf-8") as launched:
        launched.write(
            json.dumps(
                {
                    "argv": arguments,
                    "environment": dict(os.environ),
                    "pid": os.getpid(),
                    "session": os.getsid(0),
                    "nowhere": [_nowhere(0), _nowhere(1), _nowhere(2)],
                }
            )
            + "\n"
        )
    if behaviour.get("exits"):
        return 0
    time.sleep(STAYS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
