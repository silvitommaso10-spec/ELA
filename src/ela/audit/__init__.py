"""Audit of what ELA did (spec §32): the Core side, without storage.

:mod:`ela.audit.chain` defines what makes the append-only trail tamper-evident — the hash chain
and its verification — as pure functions. The persistent log that uses them is an adapter in
:mod:`ela.infrastructure.persistence`; this package never imports it (rule 4).
"""
