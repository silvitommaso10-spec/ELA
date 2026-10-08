"""``scripts/misura_m14_3.py`` on a world of its own: the numbers it counts and the facts it reads.

The measure runs once, on Tommaso's Mac, with the real key, and its file decides the road of
M14.3. What it decides on the way — what a call costs with ELA's price list, when its own cap of
one dollar stops it, what a stream of events says about a call, what the session is given, and
how the three facts of the rule written before the numbers are read — is tested here, each with
its negative, so that the run that spends is not the first one to execute that logic.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "misura_m14_3.py"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5-5"
MILLION = Decimal(1_000_000)


@cache
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("misura_m14_3_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def call(**fields: Any) -> Any:
    found = script().Call(1, "run", "POST", "/v1/messages", 0.0)
    for name, value in {"forwarded": True, "complete": True, **fields}.items():
        setattr(found, name, value)
    return found


def world(**fields: Any) -> Any:
    return script().World(token="t" * 43, key="k" * 40, upstream="u", browser=None, **fields)


# --- the price list ------------------------------------------------------------------------------


def test_a_call_costs_what_elas_price_list_says() -> None:
    plain = call(model=HAIKU, input_tokens=1000, output_tokens=100)
    assert plain.nocache == (1000 * Decimal(1) + 100 * Decimal(5)) / MILLION
    assert plain.billed == plain.nocache


def test_a_cached_call_prices_write_and_read_and_without_the_cache_every_token_in_full() -> None:
    cached = call(
        model=SONNET,
        input_tokens=100,
        cache_write_5m=1000,
        cache_write_1h=10,
        cache_read=2000,
        output_tokens=10,
    )
    assert (
        cached.billed
        == (
            100 * Decimal(2)
            + 1000 * Decimal(2) * Decimal("1.25")
            + 10 * Decimal(2) * Decimal(2)
            + 2000 * Decimal("0.2")
            + 10 * Decimal(10)
        )
        / MILLION
    )
    assert cached.nocache == (3110 * Decimal(2) + 10 * Decimal(10)) / MILLION


def test_a_call_without_its_end_counts_its_output_budget_and_one_with_its_end_does_not() -> None:
    cut = call(model=HAIKU, input_tokens=10, output_tokens=1, max_tokens=8192, complete=False)
    assert cut.counted == (10 * Decimal(1) + 8192 * Decimal(5)) / MILLION
    whole = call(model=HAIKU, input_tokens=10, output_tokens=1, max_tokens=8192)
    assert whole.counted == (10 * Decimal(1) + 1 * Decimal(5)) / MILLION


def test_a_call_that_was_not_sent_counts_nothing_and_has_no_price() -> None:
    kept = call(model=HAIKU, input_tokens=1000, forwarded=False)
    assert kept.counted == 0
    assert kept.nocache is None


def test_a_model_the_list_does_not_price_has_no_cost() -> None:
    assert call(model="claude-unknown", input_tokens=10).nocache is None


# --- the cap of the measure ----------------------------------------------------------------------


def test_the_measure_stops_itself_at_one_dollar_and_not_before() -> None:
    here = world()
    big = call(model=SONNET, input_tokens=400_000, output_tokens=0)  # 0.80 $
    here.counted(big)
    assert not here.capped.is_set()
    here.counted(call(model=SONNET, input_tokens=100_000, output_tokens=0))  # 0.20 $ more
    assert here.capped.is_set()
    assert here.spent == Decimal("1.00")


# --- a stream of events ---------------------------------------------------------------------------


def events(*pairs: tuple[str, dict[str, Any]]) -> bytes:
    return b"".join(f"event: {k}\ndata: {json.dumps(v)}\n\n".encode() for k, v in pairs)


def test_the_usage_of_a_stream_is_read_across_chunks_cut_anywhere() -> None:
    body = events(
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "usage": {
                        "input_tokens": 50,
                        "cache_read_input_tokens": 7,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 3,
                            "ephemeral_1h_input_tokens": 0,
                        },
                        "output_tokens": 1,
                    }
                },
            },
        ),
        (
            "content_block_start",
            {"type": "content_block_start", "content_block": {"type": "tool_use", "name": "x"}},
        ),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 42},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    )
    found = call(complete=False)
    reader = script().SseUsage(found)
    for start in range(0, len(body), 7):
        reader.feed(body[start : start + 7])
    assert (found.input_tokens, found.cache_read, found.cache_write_5m) == (50, 7, 3)
    assert found.output_tokens == 42
    assert found.stop_reason == "tool_use"
    assert found.tool_uses == ["x"]
    assert found.complete


def test_a_stream_that_ends_before_message_stop_is_not_complete() -> None:
    found = call(complete=False)
    script().SseUsage(found).feed(
        events(
            ("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 5}}})
        )
    )
    assert found.input_tokens == 5
    assert not found.complete


# --- what the cycle reads ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ('{"read": {"site": "a.b", "path": "/"}}', "read"),
        ('```json\n{"done": "fatto"}\n```', "done"),
        ('Ecco: {"impossible": "no"} grazie', "impossible"),
        ('{"read": {}, "done": "x"}', "illeggibile"),
        ('{"click": "x"}', "illeggibile"),
        ("una frase", "illeggibile"),
        ("{non json}", "illeggibile"),
    ],
)
def test_the_answer_of_the_cycle_is_one_object_with_one_known_key(text: str, kind: str) -> None:
    assert script().parse_answer(text)[0] == kind


def test_a_phrase_succeeds_on_a_word_it_wants_whatever_the_case_and_says_none_without_one() -> None:
    succeeded = script().succeeded
    assert succeeded("Il canale è youtube.com/@MrBeast", ("@mrbeast",)) is True
    assert succeeded("Non l'ho trovato", ("@mrbeast",)) is False
    assert succeeded(None, ("@mrbeast",)) is False
    assert succeeded("3.14.8", ()) is None


# --- the network of the session ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME", False),
        ("claude 1 u 20u IPv4 0x1 0t0 TCP 127.0.0.1:50000->127.0.0.1:8080 (ESTABLISHED)", False),
        ("claude 1 u 21u IPv6 0x1 0t0 TCP [::1]:50000->[::1]:8080 (ESTABLISHED)", False),
        ("claude 1 u 22u IPv4 0x1 0t0 TCP 127.0.0.1:8080 (LISTEN)", False),
        ("claude 1 u 23u IPv4 0x1 0t0 TCP 192.168.1.5:50000->34.36.57.103:443 (ESTABLISHED)", True),
        ("claude 1 u 24u IPv4 0x1 0t0 UDP 192.168.1.5:61000->192.168.1.1:53", True),
    ],
)
def test_only_a_connection_that_leaves_the_machine_is_kept(line: str, kept: bool) -> None:
    assert (script().remote_of(line) is not None) is kept


def test_the_session_is_given_the_token_and_never_the_key(tmp_path: Path) -> None:
    measure = script()
    here = world(port=1234)
    environment = measure.session_environment(here, tmp_path, HAIKU)
    argv = measure.session_argv("claude", tmp_path, HAIKU, ("example.com",))
    assert environment["ANTHROPIC_API_KEY"] == here.token
    assert environment["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:1234"
    assert not any(here.key in value for value in environment.values())
    assert not any(here.key in one for one in argv)
    assert here.key not in json.dumps(measure.mcp_config(here))
    assert {"--bare", "--strict-mcp-config", "--no-session-persistence"} <= set(argv)
    assert argv[argv.index("--tools") + 1] == ""


def test_a_key_left_in_the_folder_of_the_session_is_found(tmp_path: Path) -> None:
    measure = script()
    (tmp_path / "left.json").write_text("…" + "k" * 40 + "…", encoding="utf-8")
    (tmp_path / "clean.json").write_text("nothing here", encoding="utf-8")
    assert measure.key_in(tmp_path, "k" * 40) == ["left.json"]
    assert measure.key_in(tmp_path, "") == []


# --- the three facts --------------------------------------------------------------------------


def facts(tmp_path: Path, here: Any, runs: list[Any]) -> str:
    measure = script()
    out = measure.Out(tmp_path / "out.txt")
    measure.facts(out, here, runs)
    out.close()
    return (tmp_path / "out.txt").read_text(encoding="utf-8")


def session(label: str, **fields: Any) -> Any:
    run = script().Run(label, "sessione", HAIKU, 1, ("example.com",))
    run.init = {"tools": list(script().TOOLS), "mcp_servers": [{"name": "ela"}]}
    for name, value in fields.items():
        setattr(run, name, value)
    return run


def test_fact_a_is_found_for_a_tool_that_is_not_elas_and_not_otherwise(tmp_path: Path) -> None:
    clean = facts(tmp_path, world(), [session("sessione-haiku-1")])
    assert "(a) strumenti o server che non sono di ELA: nessuno → non trovato" in clean
    dirty = session("sessione-haiku-1", init={"tools": ["Bash", *script().TOOLS]})
    found = facts(tmp_path, world(), [dirty]).split("(b)")[0]
    assert "['Bash']" in found
    assert "→ TROVATO" in found


def test_fact_a_reads_the_tools_each_request_offers_not_only_the_start(tmp_path: Path) -> None:
    here = world()
    here.calls.append(call(run="sessione-haiku-1", model=HAIKU, tools=["web_search"]))
    found = facts(tmp_path, here, [session("sessione-haiku-1")])
    assert "web_search" in found.split("(b)")[0]


def test_fact_b_is_found_when_the_session_declares_more_than_the_gateway_saw(
    tmp_path: Path,
) -> None:
    here = world()
    here.calls.append(call(run="sessione-haiku-1", model=HAIKU, input_tokens=10, output_tokens=2))
    same = {HAIKU: {"inputTokens": 10, "outputTokens": 2}}
    assert (
        "non trovato"
        in facts(tmp_path, here, [session("sessione-haiku-1", result={"modelUsage": same})])
        .split("(b)")[1]
        .split("\n")[0]
    )
    more = {HAIKU: {"inputTokens": 11, "outputTokens": 2}}
    assert (
        "TROVATO"
        in facts(tmp_path, here, [session("sessione-haiku-1", result={"modelUsage": more})])
        .split("(b)")[1]
        .split("\n")[0]
    )
    other = {"claude-other": {"inputTokens": 1, "outputTokens": 1}}
    assert (
        "TROVATO"
        in facts(tmp_path, here, [session("sessione-haiku-1", result={"modelUsage": other})])
        .split("(b)")[1]
        .split("\n")[0]
    )


def test_fact_b_is_found_for_a_connection_that_leaves_the_machine(tmp_path: Path) -> None:
    run = session("sessione-haiku-1", connections=["claude TCP 1.2.3.4:443"])
    assert "TROVATO" in facts(tmp_path, world(), [run]).split("(b)")[1].split("\n")[0]


def pair(here: Any, session_cost_tokens: int, cycle_cost_tokens: int, phrase: int = 1) -> list[Any]:
    measure = script()
    s = session(f"sessione-haiku-{phrase}", phrase=phrase)
    c = measure.Run(f"ciclo-haiku-{phrase}", "ciclo", HAIKU, phrase, ("example.com",))
    here.calls.append(call(run=s.label, model=HAIKU, input_tokens=session_cost_tokens))
    here.calls.append(call(run=c.label, model=HAIKU, input_tokens=cycle_cost_tokens))
    return [s, c]


def test_fact_c_is_found_above_twice_the_cycle_and_not_at_it(tmp_path: Path) -> None:
    here = world()
    assert "rapporto 3.00 → TROVATO" in facts(tmp_path, here, pair(here, 3000, 1000))
    again = world()
    assert "rapporto 2.00 → non trovato" in facts(tmp_path, again, pair(again, 2000, 1000))


def test_fact_c_leaves_out_a_phrase_the_cap_of_the_measure_stopped(tmp_path: Path) -> None:
    here = world()
    runs = pair(here, 3000, 1000, phrase=1) + pair(here, 1000, 1000, phrase=2)
    runs[0].ended_by = "il tetto di 1 $ della misura"
    found = facts(tmp_path, here, runs)
    assert "sulle 1 frasi" in found
    assert "rapporto 1.00 → non trovato" in found
