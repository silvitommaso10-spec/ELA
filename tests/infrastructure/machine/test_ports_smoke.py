"""``port_holder`` against the real ``lsof`` of this machine: the process it names is this one.

Declared with its ``skipif``: a machine without ``lsof`` cannot say who holds a port, and the fake
of ``test_ports.py`` already proves what ELA does then (ADR 0031 §6).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket

import pytest

from ela.infrastructure.machine.ports import port_holder


@pytest.mark.skipif(shutil.which("lsof") is None, reason="this machine has no lsof")
def test_the_process_that_listens_is_the_one_named() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    try:
        port = listener.getsockname()[1]
        holder = asyncio.run(port_holder(port))
    finally:
        listener.close()

    assert holder is not None
    assert holder.endswith(f"(pid {os.getpid()})")
