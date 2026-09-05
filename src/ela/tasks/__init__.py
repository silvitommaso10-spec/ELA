"""The life cycle of tasks (spec §14): the state machine (M1.2) and the Task Engine (M3.1).

:mod:`ela.tasks.state_machine` says which moves are legal; :mod:`ela.tasks.engine` is the only
module that makes them, persisting the task and its trail and writing the audit trail. Errors
live in :mod:`ela.tasks.errors`.
"""
