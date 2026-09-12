"""The conformance suite of the work protocol (M12.2, dec. P; ADR 0038 §18).

The stories are written **once**, against :class:`~tests.conformance.driver.NodeDriver`, and
parametrised over the drivers. M12.3–M12.5 add a driver each and recite the same stories: the suite
is the contract, not a copy of it.
"""
