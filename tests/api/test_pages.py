"""The composer of the pages, and what it refuses (M12.5 dec. D; ADR 0043 §5).

The pages themselves are proved in ``tests/api/test_companion.py``, through the application. What
is here is the part a page cannot show: the mistakes of whoever writes a template or fills one —
a slot nobody filled, a value with no slot, an include that names nothing, a sheet that is not one
of the two. Each of them is a ``ValueError`` at composition, which is to say **before** anybody
sees a page with ``{risk}`` written on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.api import pages
from ela.composition import ConfigurationError


def test_a_fragment_escapes_what_it_is_given_and_keeps_markup_as_it_is() -> None:
    """The escape is by construction: only :class:`~ela.api.pages.Markup` goes in raw, and only
    this module makes one."""
    escaped = pages.fragment("notice", text="<script>alert(1)</script>")

    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped
    assert pages.joined([escaped]) == escaped


def test_a_slot_with_nothing_given_for_it_is_refused() -> None:
    with pytest.raises(ValueError, match="slot"):
        pages.fragment("notice")


def test_a_value_with_no_slot_is_refused() -> None:
    """A page that silently dropped what it was given would show less than it was asked to."""
    with pytest.raises(ValueError, match="no slot for risk"):
        pages.fragment("notice", text="ciao", risk="MEDIUM")


def test_a_template_that_does_not_exist_is_refused() -> None:
    with pytest.raises(ValueError, match="not a template"):
        pages.fragment("una-pagina-che-non-esiste")


def test_an_include_that_names_no_partial_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative case of the sphere: the include resolves a file of the design system, and a
    name nobody has is a page with a hole in it."""
    monkeypatch.setattr(pages, "_templates", lambda: {"x": "<b>{include:_alone}</b>"})

    with pytest.raises(ValueError, match="no partial"):
        pages.fragment("x")


def test_a_partial_that_includes_another_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """One level, like the generator of M17.1: two would be a template language, and this is not
    one."""
    monkeypatch.setattr(pages, "_templates", lambda: {"x": "<b>{include:_one}</b>"})
    monkeypatch.setattr(pages, "_partials", lambda: {"_one": "{include:_two}", "_two": "<i></i>"})

    with pytest.raises(ValueError, match="one level"):
        pages.fragment("x")


def test_only_the_two_sheets_of_the_design_system_are_served() -> None:
    """What the browser asks for chooses **between two files**, and cannot describe one."""
    for sheet in pages.STYLESHEETS:
        assert "--ela-" in pages.stylesheet(sheet).body.decode()
    with pytest.raises(ValueError, match="not one of the sheets"):
        pages.stylesheet("../../.env")


def test_a_missing_folder_stops_the_start_up_with_a_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ELA runs from its repository (5.5): a companion with no markup is a configuration ELA
    cannot serve, and that is an exit code and not a traceback on the first request."""
    monkeypatch.setattr(pages, "TEMPLATES", tmp_path / "nowhere")

    with pytest.raises(ConfigurationError, match="markup is missing"):
        pages.ensure_readable()
    with pytest.raises(ConfigurationError, match="markup is missing"):
        pages._read(tmp_path / "nowhere")


def test_the_templates_are_read_once_and_the_check_forgets_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ensure_readable`` clears the cache: a start-up reads the folder as it is now, not as it
    was for whatever ran before it in the same process."""
    pages.ensure_readable()
    first = pages._templates()

    assert pages._templates() is first
    pages.ensure_readable()
    assert pages._templates() is not first
