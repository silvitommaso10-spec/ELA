"""A sheet that would close the block it travels in (M17.2c correction C; ADR 0050).

The pages that reach whoever ELA does not recognise carry the two sheets inside a ``<style>``, and
a sheet that contained ``</style`` would end the block there: what follows would be read as HTML.
**One function of ``ela.api.pages`` says whether a text would close the block** — ``</style`` in
any case, which is more than the exact rule of the parser (``</style`` followed by a space, ``/``
or ``>``) and contains it. The start-up uses it, and so does this test; nobody writes a second,
wider rule «to be safe», because two wordings of one rule are two opinions.
"""

from __future__ import annotations

import pytest

from tests.design.tree import DESIGN_SYSTEM


@pytest.mark.parametrize(
    ("text", "closes"),
    [
        ("</style>", True),
        ("</STYLE>", True),
        ("</StYlE>", True),
        ("</style/", True),
        ("</style ", True),
        ("a { color: red } </style", True),
        ("</p>", False),
        ("/* </ is not a close */", False),
        ("<style>", False),
        ("</styl", False),
        ("", False),
    ],
)
def test_the_one_function_says_what_would_close_the_block(text: str, closes: bool) -> None:
    from ela.api.pages import closes_the_block

    assert closes_the_block(text) is closes


def test_no_sheet_ela_serves_would_close_the_block() -> None:
    from ela.api.pages import STYLESHEETS, closes_the_block

    for sheet in STYLESHEETS:
        assert not closes_the_block((DESIGN_SYSTEM / sheet).read_text(encoding="utf-8")), sheet
