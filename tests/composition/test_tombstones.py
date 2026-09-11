"""``ela.tombstones``: one table of retired variables, and a validator that knows all of it.

Criterion 17 of M12.1: until then the refusal lived in one provider and read the *first* entry of
its table, so a second retired variable would have been accepted in silence. What is checked here
is the general form (ADR 0037 §15): every entry refused by its own name, from whichever settings
class declares it — and every entry declared by some class, or its refusal could not happen.
"""

from __future__ import annotations

import pytest
from pydantic import create_model

from ela.composition.settings import Settings
from ela.tombstones import RETIRED_SETTINGS, refuse_retired

PREFIX = "ELA_"


@pytest.mark.parametrize("variable", sorted(RETIRED_SETTINGS))
def test_every_retired_variable_is_refused_by_its_own_name(variable: str) -> None:
    field = variable.removeprefix(PREFIX).lower()
    tombstone = create_model("Tombstone", **{field: (str | None, None)})  # type: ignore[call-overload]
    retired = RETIRED_SETTINGS[variable]

    with pytest.raises(ValueError, match=f"{variable} was retired in {retired.milestone}"):
        refuse_retired(tombstone(**{field: ""}), prefix=PREFIX)
    refuse_retired(tombstone(), prefix=PREFIX)  # never set: nothing to refuse


def test_every_retired_variable_is_declared_by_a_settings_class() -> None:
    """A retired variable no class declares would fall to ``extra="ignore"`` and pass unseen."""
    declared = {
        f"{PREFIX}{field.upper()}"
        for group in Settings.model_fields.values()
        for field in group.annotation.model_fields  # type: ignore[union-attr]
    }
    assert set(RETIRED_SETTINGS) <= declared
