"""The conformance suite of the work protocol (M12.2, dec. P; ADR 0038 §18).

The stories are written **once**, against :class:`~tests.conformance.driver.NodeDriver`, and
parametrised over the drivers. M12.3 and M12.4 add a driver each and recite the same stories: the
suite is the contract, not a copy of it.

**The companion of M12.5 is not among them, and that is the correction of 2026-09-20.** The
thirteen stories are the stories of the **work**, and an identity that takes none leaves twelve of
them with nothing to play: a kit with thirteen entries in ``UNSUPPORTED`` would be a driver that
recites nothing. The companion has a contract of its own — nine stories, one bearer, in
``test_companion_contract.py`` — and ADR 0043 says so. Dec. P is untouched for whoever does work.
"""
