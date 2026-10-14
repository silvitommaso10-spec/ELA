"""``scripts/misura_m13_10.py`` (decision 47 of the review of M13.10's SPEC): what it may write, and
what it never does on the page. The script itself runs on Tommaso's Terminal, with his profile and
his phone: the suite never launches it. What can be proved without it is proved here."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "misura_m13_10.py"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("misura_m13_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


misura = _script()

GESTURES = {
    "click",
    "dblclick",
    "press",
    "type",
    "fill",
    "check",
    "uncheck",
    "tap",
    "dispatch_event",
    "insert_text",
    "set_input_files",
    "select_option",
    "drag_to",
}
INPUT_DEVICES = {"keyboard", "mouse", "touchscreen"}


def _attributes_used(tree: ast.AST) -> set[str]:
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_the_script_never_makes_a_gesture_on_the_page() -> None:
    used = _attributes_used(ast.parse(SCRIPT.read_text(encoding="utf-8")))

    assert not used & GESTURES
    assert not used & INPUT_DEVICES


def test_the_check_of_the_gestures_finds_one_when_there_is_one() -> None:
    tree = ast.parse("async def f(page):\n    await page.locator('x').click()\n")

    assert _attributes_used(tree) & GESTURES == {"click"}


def test_what_the_page_is_asked_never_reads_the_text_of_an_element() -> None:
    assert not re.search(r"textContent|innerText|innerHTML|\.value\b", misura.CANDIDATES)
    assert "innerText" not in misura.EMPTY and "innerHTML" not in misura.EMPTY
    assert re.findall(r"textContent\.?\w*", misura.EMPTY) == ["textContent.length"]
    assert set(re.findall(r"\.value(?:\.\w+)?", misura.EMPTY)) == {".value", ".value.length"}
    assert "el.value === undefined" in misura.EMPTY


def test_a_candidate_keeps_only_the_declared_attributes_and_the_classes_made_of_words() -> None:
    found = misura.candidates_of(
        [
            {
                "tag": "div",
                "attributes": {
                    "contenteditable": "true",
                    "data-tab": "10",
                    "aria-label": "Scrivi a Mario",
                    "title": "Mario",
                    "data-id": "true_391234567890_ABC",
                    "role": "textbox",
                },
                "classes": ["message-out", "x1n2onr6", "selectable-text", "_ak1l"],
            },
            "not a candidate",
        ]
    )

    assert found == [
        misura.Candidate(
            "div",
            {"contenteditable": "true", "role": "textbox"},
            ("message-out", "selectable-text"),
        )
    ]


def test_a_value_with_a_space_or_that_begins_with_a_digit_is_not_a_value_a_selector_takes() -> None:
    (found,) = misura.candidates_of(
        [
            {
                "tag": "span",
                "attributes": {"data-icon": "send now", "data-testid": "1a"},
                "classes": [],
            }
        ]
    )

    assert found.attributes == {}


def test_a_selector_is_written_from_one_declared_fact_at_a_time_and_never_from_a_position() -> None:
    candidate = misura.Candidate("span", {"data-icon": "send", "role": "button"}, ("message-out",))

    written = misura.selectors_of(candidate, "footer")

    assert written == [
        'footer span[data-icon="send"]',
        'footer span[role="button"]',
        "footer span.message-out",
    ]
    assert not any(re.search(r"nth|has-text|text=|aria-label|title", one) for one in written)


def test_a_tag_that_is_not_a_tag_name_is_left_out_of_the_selector() -> None:
    candidate = misura.Candidate('div"] *', {"role": "button"}, ())

    assert misura.selectors_of(candidate, "footer") == ['footer [role="button"]']


@pytest.mark.parametrize(
    "line",
    [
        "il numero 393331234567",
        "+39 3331234567",
        "qualcuno@example.com",
        "una riga con il segreto-finto dentro",
    ],
)
def test_a_line_with_a_number_an_address_or_a_secret_is_not_written(line: str) -> None:
    assert misura.withheld(line, ["segreto-finto"])


def test_a_line_of_selectors_and_counts_is_written() -> None:
    assert not misura.withheld(
        '    la casella: footer div[data-tab="10"] — trova 1 elemento', ["393331234567"]
    )


def test_the_report_writes_in_place_of_a_withheld_line_that_a_line_was_withheld(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = misura.Report(secrets=["393331234567"])

    report.say("PASSATO — il numero 393331234567 apre la chat")
    report.say("PASSATO — un selettore")

    assert report.refused == 1
    assert "393331234567" not in "\n".join(report.lines)
    assert "393331234567" not in capsys.readouterr().out
    assert report.lines[1] == "PASSATO — un selettore"


def test_the_file_reread_with_a_number_in_it_says_failed(tmp_path: Path) -> None:
    report = misura.Report()
    report.lines = ["una riga", "393331234567"]

    assert misura.finish(report, tmp_path / "out.txt", 0) == 1
    assert misura.finish(misura.Report(lines=["una riga"]), tmp_path / "ok.txt", 0) == 0


def test_a_phone_number_is_digits_with_its_prefix_and_nothing_else() -> None:
    assert misura.PHONE.match("+393331234567")
    assert misura.PHONE.match("393331234567")
    assert not misura.PHONE.match("+39 333 1234567")
    assert not misura.PHONE.match("12345")
