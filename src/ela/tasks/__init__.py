"""The life cycle of tasks (spec §14, §15): the state machine (M1.2), the Task Engine (M3.1) and
the Task Graph (M3.2).

:mod:`ela.tasks.state_machine` says which moves of a task are legal; :mod:`ela.tasks.graph` says
which moves of a step are legal, in what order the steps of a plan run and what a failure takes
down; :mod:`ela.tasks.engine` is the only module that makes either kind of move, persisting the
task and its trail and writing the audit trail. Errors live in :mod:`ela.tasks.errors`.
"""
