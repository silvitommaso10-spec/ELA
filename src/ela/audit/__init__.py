"""Audit of what ELA did (spec §32): the Core side, without storage.

:mod:`ela.audit.chain` defines what makes the append-only trail tamper-evident — the hash chain
and its verification — as pure functions, and :mod:`ela.audit.verifier` declares the one member
through which the rest of ELA asks a real log whether it still holds together. The persistent log
that uses them is an adapter in :mod:`ela.infrastructure.persistence`; this package never imports
it (rule 4).
"""
