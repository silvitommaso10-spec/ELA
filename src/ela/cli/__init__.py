"""The command line of ELA (spec §54; M8.2, ADR 0024).

A **client**, not a second ELA: every command but two is one call to the local API, with the same
token and on the same port, and the answer rendered. ``serve`` starts the process — and is the one
module here allowed to import :mod:`ela.api` — and ``init`` prepares the machine before there is
any process to talk to.

Why a client and not a world built in-process (ADR 0024 §2): two worlds would be two processes
writing the same database with the ``run`` lock in only one of them; a built world declares the
``local`` node alive and then exits; and a "yes" would enter the system through a second door,
where architecture rule 19 allows exactly one.
"""

from ela.cli.app import main

__all__ = ["main"]
# Only ``main`` is re-exported: binding the Typer object here as ``app`` would shadow the module
# ``ela.cli.app`` on the package, and a name that means two things is a name that will be read
# wrong once.
