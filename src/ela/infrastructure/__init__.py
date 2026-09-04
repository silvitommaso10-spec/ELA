"""Infrastructure adapters of ELA: the real implementations of the ports (spec §48, §54).

The only packages allowed to import infrastructure libraries are this one, ``providers/`` and
``api/`` (ADR 0002, rule 3). Nothing in the Core imports this package (rule 4).
"""
