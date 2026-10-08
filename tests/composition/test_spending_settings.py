"""``ELA_SPENDING_CAP_USD``: the month's cap on the model's key, one line of the Core (M14.1).

Decision A: the cap is written by whoever pays, in dollars, and no number of the author's is in the
code — the default is **no cap**, which lets no call that spends out (decision B) but starts ELA
the same. Empty is no cap, as an empty key is no key. Zero is a cap: nothing is spent. A value
that is not a finite amount of at least zero stops the start-up with the variable named. And the
line is the Core's alone: a node has no cap of its own, so ``NodeConfig`` does not read it.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from ela.composition import ConfigurationError, NodeConfig, Settings
from ela.composition.settings import SpendingSettings
from ela.domain import ProviderResult
from ela.executive.spending import CAP_VARIABLE
from tests.composition.support import declare


def load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> Settings:
    declare(monkeypatch, tmp_path, **extra)
    return Settings.load()


def test_the_variable_is_the_one_every_refusal_names() -> None:
    """One name, written once in ``ela.executive.spending`` and read here by pydantic's prefix."""
    prefix = SpendingSettings.model_config.get("env_prefix", "")
    (field,) = SpendingSettings.model_fields
    assert f"{prefix}{field}".upper() == CAP_VARIABLE


def test_without_the_line_there_is_no_cap_and_ela_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert load(monkeypatch, tmp_path).spending.spending_cap_usd is None


def test_an_empty_line_is_no_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """As ``ELA_ANTHROPIC_API_KEY=`` is no key: the line of ``.env.example``, left blank."""
    assert load(monkeypatch, tmp_path, **{CAP_VARIABLE: ""}).spending.spending_cap_usd is None


@pytest.mark.parametrize(
    ("written", "read"),
    [("45", Decimal(45)), ("12.50", Decimal("12.50")), ("0", Decimal(0))],
    ids=["dollars", "cents", "zero-is-a-cap"],
)
def test_a_cap_is_read_in_dollars_exactly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str, read: Decimal
) -> None:
    cap = load(monkeypatch, tmp_path, **{CAP_VARIABLE: written}).spending.spending_cap_usd
    assert cap == read and isinstance(cap, Decimal)


def test_the_line_is_read_from_the_env_file_as_the_guide_writes_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text(f"{CAP_VARIABLE}=30\n", encoding="utf-8")

    assert Settings.load().spending.spending_cap_usd == Decimal(30)


@pytest.mark.parametrize("written", ["-1", "trenta", "inf", "nan", "30 USD"])
def test_a_cap_that_is_not_an_amount_stops_the_start_up_with_the_line_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str
) -> None:
    declare(monkeypatch, tmp_path, **{CAP_VARIABLE: written})

    with pytest.raises(ConfigurationError) as caught:
        Settings.load()

    assert CAP_VARIABLE in str(caught.value)


def test_a_node_does_not_read_it() -> None:
    """Decision B: the node keeps to what the Core reserved, and has no cap to read."""
    assert "spending" not in NodeConfig.model_fields
    assert all(
        "spending_cap_usd" not in section.annotation.model_fields  # type: ignore[union-attr]
        for section in NodeConfig.model_fields.values()
    )


def test_its_docstring_names_the_second_cap_as_the_organization_s_monthly_limit() -> None:
    """M14.1b (decision 17 of the review of M14.2): ADR 0057 §1 was revised on 2026-10-07 — the
    second cap is the **organization's** monthly limit, on the Billing page of the console; the
    workspace's could not be set on the real console —, and this docstring kept saying the
    workspace's. What ``SpendingSettings`` says of itself is read by whoever writes the line."""
    said = " ".join((inspect.getdoc(SpendingSettings) or "").split())

    assert "workspace" not in said
    assert "monthly limit of the organization" in said


def test_the_workspace_of_a_result_is_not_called_the_second_cap() -> None:
    """The same defect, in a second place the census of M14.1b found: what a result says of the
    workspace it was billed in. The workspace holds ELA's two keys together (ADR 0057 §1); its
    limit is not the second cap."""
    said = " ".join(inspect.getsource(ProviderResult).split())

    assert "whose monthly limit is the second cap" not in said
    assert "the second cap is the organization's monthly limit" in said
