"""``scripts/misura_m13_10.py`` (decision 47 of the review of M13.10's SPEC): what it may write, and
what it never does on the page. The script itself runs on Tommaso's Terminal, with his profile and
his phone: the suite never launches it. What can be proved without it is proved here."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

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
            {"contenteditable": "true", "data-tab": "10", "role": "textbox"},
            ("message-out", "selectable-text"),
        )
    ]


def test_a_space_letters_after_a_digit_or_a_long_number_is_not_a_value_a_selector_takes() -> None:
    (found,) = misura.candidates_of(
        [
            {
                "tag": "span",
                "attributes": {"data-icon": "send now", "data-testid": "1a", "data-tab": "1234"},
                "classes": [],
            }
        ]
    )

    assert found.attributes == {}


def test_a_small_number_is_a_value_a_selector_takes_as_whatsapp_declares_its_box() -> None:
    """``data-tab="10"`` tells the box from the search box when no place does (the first measure,
    2026-10-14): a value of three digits at most, which is nobody's number."""
    (found,) = misura.candidates_of([{"tag": "div", "attributes": {"data-tab": "10"}}])

    assert found.attributes == {"data-tab": "10"}


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


# ----------------------------------------------------------------------------------------
# The first measure, 2026-10-14: the loading bar of WhatsApp Web stood still and empty for two
# hours, and no chat came (Tommaso, decision 65). The script wrote «the page did not hold» from
# what it did not find — in the first ``footer`` of the page only —, and said nothing of why
# ----------------------------------------------------------------------------------------


class _Counted:
    async def count(self) -> int:
        return 0


class Quiet:
    """A page on which the script finds nothing: no element of any kind, no selector that finds
    one."""

    async def evaluate(self, script: str, argument: object = None) -> object:
        return []

    def locator(self, selector: str) -> _Counted:
        return _Counted()


def answering(said: dict[str, str]) -> Callable[[str], str]:
    """Tommaso at the Terminal: the answer to the question that has those words, Invio to the
    rest."""

    def ask(prompt: str) -> str:
        return next((answer for words, answer in said.items() if words in prompt), "")

    return ask


@pytest.mark.parametrize(
    ("answer", "word", "yes_or_no"), [("s", "PASSATO", "sì"), ("n", "SALTATO", "no")]
)
async def test_whether_the_page_held_is_told_by_your_eye_and_never_by_what_the_script_found(
    answer: str, word: str, yes_or_no: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(misura.getpass, "getpass", lambda prompt: "")
    report = misura.Report()

    await misura.measure(
        report,
        answering({"casella del messaggio in basso": answer, "messaggio che hai mandato tu": "n"}),
        Quiet(),
    )

    assert [line for line in report.lines if "ha retto" in line] == [
        f"{word} — la pagina ha retto senza service worker fino alla casella del messaggio, "
        f"a occhio: {yes_or_no}"
    ]


async def test_when_the_box_has_not_come_the_file_says_why_and_the_measure_ends_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision 63: with the bar standing still, what the browser said is the why — and nothing
    after it can be measured without the chat: no character to write in a box that is not
    there."""
    monkeypatch.setattr(misura.getpass, "getpass", lambda prompt: "")
    asked: list[str] = []
    said = answering({"casella del messaggio in basso": "n", "messaggio che hai mandato tu": "n"})
    seen = misura.Seen()
    seen.refused["https://static.example"] += 2
    seen.targets[("shared_worker", "https://web.example")] += 1
    seen.errors["un'eccezione TypeError"] += 1
    report = misura.Report()

    await misura.measure(report, lambda prompt: asked.append(prompt) or said(prompt), Quiet(), seen)

    assert all(line in report.lines for line in seen.lines())
    assert not any("Scrivi A MANO" in prompt for prompt in asked)
    assert report.lines[-1].startswith("SALTATO — il resto della misura vuole la chat")


def test_an_address_is_told_by_its_origin_and_nothing_else() -> None:
    assert misura.origin_of("https://web.whatsapp.com/send?phone=393331234567") == (
        "https://web.whatsapp.com"
    )
    assert misura.origin_of("http://127.0.0.1:8123/x?y=1") == "http://127.0.0.1:8123"
    assert misura.origin_of("blob:https://web.example/1b2c") == "blob:"
    assert misura.origin_of("about:blank") == "about:"
    assert misura.origin_of("not an address") == "?"


class Gate:
    """A gate with the two members the script listens to: it lets ``/in`` go."""

    async def _leaves(self, event: dict[str, Any]) -> bool:
        return bool(event["request"]["url"].endswith("/in"))

    def _born(self, event: dict[str, Any]) -> None:
        self.born = event


def asked_for(address: str) -> dict[str, Any]:
    return {"request": {"method": "GET", "url": address}}


async def test_the_gate_is_listened_to_by_origin_and_type_and_decides_as_it_did() -> None:
    leaves, born = Gate._leaves, Gate._born
    seen = misura.Seen()

    undo = misura.watching(Gate, seen)
    gate = Gate()
    decided = [
        await gate._leaves(asked_for("https://web.example/in")),
        await gate._leaves(asked_for("https://static.example/out?phone=393331234567")),
    ]
    gate._born({"targetInfo": {"type": "shared_worker", "url": "https://web.example/w.js?u=1"}})
    undo()

    assert decided == [True, False]
    assert gate.born["targetInfo"]["type"] == "shared_worker", "the gate is still told"
    assert seen.refused == {"https://static.example": 1}
    assert seen.targets == {("shared_worker", "https://web.example"): 1}
    assert Gate._leaves is leaves and Gate._born is born


async def test_a_judgement_that_raises_is_a_refusal_and_still_raises() -> None:
    class Broken(Gate):
        async def _leaves(self, event: dict[str, Any]) -> bool:
            raise RuntimeError("whoever judges could not say")

    seen = misura.Seen()
    undo = misura.watching(Broken, seen)
    try:
        with pytest.raises(RuntimeError):
            await Broken()._leaves(asked_for("https://web.example/x"))
    finally:
        undo()

    assert seen.refused == {"https://web.example": 1}


def test_what_the_browser_said_is_one_line_a_thing_and_says_so_when_it_said_nothing() -> None:
    seen = misura.Seen()
    seen.refused["https://static.example"] += 3
    seen.targets[("service_worker", "https://web.example")] += 1
    seen.errors["console.error"] += 2

    assert seen.lines() == [
        "    rifiutata dal cancello: https://static.example — 3 richieste",
        "    annunciato dal browser: service_worker — https://web.example — 1",
        "    errore della console: console.error — 2",
    ]
    assert misura.Seen().lines() == [
        "    rifiutata dal cancello: nessuna richiesta",
        "    annunciato dal browser: niente",
        "    errore della console: nessuno",
    ]


def test_a_type_that_is_not_a_word_is_not_written() -> None:
    assert misura.kind_of("shared_worker") == "shared_worker"
    assert misura.kind_of("TypeError") == "TypeError"
    assert misura.kind_of("Mario Rossi 393331234567") == "?"
    assert misura.kind_of(None) == "?"


def test_a_candidate_keeps_only_the_listed_places_narrowest_first_and_a_true_focus() -> None:
    (found,) = misura.candidates_of(
        [
            {
                "tag": "div",
                "attributes": {"data-tab": "10"},
                "classes": [],
                "places": ["footer", "body > div", "#main", "#main footer"],
                "focused": "yes",
            }
        ]
    )

    assert found.places == ("#main footer", "#main", "footer")
    assert found.focused is False
    assert misura.candidates_of([{"tag": "div", "focused": True}])[0].focused is True


def test_a_selector_is_written_in_each_place_of_the_element_narrowest_first_then_in_none() -> None:
    candidate = misura.Candidate("div", {"data-tab": "10"}, (), ("#main footer", "#main"))

    assert misura.selectors_for(candidate) == [
        '#main footer div[data-tab="10"]',
        '#main div[data-tab="10"]',
        'div[data-tab="10"]',
    ]


def test_a_number_that_is_not_one_is_asked_again_and_an_empty_one_skips_the_address(
    capsys: pytest.CaptureFixture[str],
) -> None:
    said = iter(["+39 333 1234567", "+393331234567"])

    assert misura.asked_number(lambda prompt: next(said)) == "+393331234567"
    assert misura.asked_number(lambda prompt: "") is None
    assert "1234567" not in capsys.readouterr().out
