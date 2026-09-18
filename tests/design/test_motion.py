"""Motion is made of tokens, and it stops (M17.1, criterio 13; dec. 4, dec. H).

``prefers-reduced-motion`` is respected everywhere **by construction**: ``tokens.css`` takes
every duration to zero under ``reduce``, so every transition goes out because it reads a token
(``test_tokens_only.py`` refuses a duration written by hand); and a hand-written ``animation``
may only be declared inside ``@media (prefers-reduced-motion: no-preference)``.
"""

from __future__ import annotations

from typing import Any

from tests.design import stylesheet
from tests.design.tree import generator, handwritten_stylesheets, read, tokens

REDUCE = "(prefers-reduced-motion: reduce)"
NO_PREFERENCE = "(prefers-reduced-motion: no-preference)"


def animations_that_would_not_stop(text: str) -> list[str]:
    return [
        f"{', '.join(rule.selectors)}: {name} is declared outside {NO_PREFERENCE}"
        for rule in stylesheet.parse(text)
        if rule.keyframes is None and rule.media != NO_PREFERENCE
        for name, _ in rule.declarations
        if name == "animation" or name.startswith("animation-")
    ]


def durations_left_running(derived: str) -> set[str]:
    """Duration tokens that ``reduce`` does not take to zero."""
    rules = stylesheet.parse(derived)
    every = {
        name
        for name in stylesheet.custom_properties(rules)
        if name.startswith("--ela-motion-duration-")
    }
    assert every, "there must be durations, or this check is vacuous"
    stilled = {
        name
        for rule in rules
        if rule.media == REDUCE and ":root" in rule.selectors
        for name, value in rule.declarations
        if value == "0s"
    }
    return every - stilled


def keyframes_defined(text: str) -> set[str]:
    return {rule.keyframes for rule in stylesheet.parse(text) if rule.keyframes is not None}


def keyframes_named(source: dict[str, Any], text: str) -> set[str]:
    """By a pattern of ``tokens.json``, or by a hand-written ``animation-name``."""
    module = generator()
    named = {
        str(pattern["keyframes"]["$value"])
        for pattern in module.entries(source["motion"]["pattern"]).values()
    }
    for rule in stylesheet.parse(text):
        value = rule.value("animation-name")
        if value is not None and not value.startswith("var("):
            named.add(value)
    return named


def patterns_nobody_uses(source: dict[str, Any]) -> set[str]:
    module = generator()
    used = {str(state["motion"]["$value"]) for state in module.entries(source["state"]).values()}
    return {
        name
        for name in module.entries(source["motion"]["pattern"])
        if "{motion.pattern." + name + "}" not in used
    }


def test_every_handwritten_animation_stops_under_reduced_motion() -> None:
    declared = 0
    for name, text in handwritten_stylesheets().items():
        assert animations_that_would_not_stop(text) == [], name
        declared += sum(
            1
            for rule in stylesheet.parse(text)
            for prop, _ in rule.declarations
            if prop.startswith("animation")
        )
    assert declared, "something must be animated, or this test is vacuous"


def test_reduced_motion_takes_every_duration_to_zero() -> None:
    assert durations_left_running(read("tokens.css")) == set()


def test_every_motion_is_defined_and_no_keyframes_is_an_orphan() -> None:
    components = read("components.css")
    assert keyframes_named(tokens(), components) == keyframes_defined(components)
    assert patterns_nobody_uses(tokens()) == set()


def test_the_state_motion_reaches_the_indicator_through_the_derived_rule() -> None:
    """The list of states is not in components.css: the keyframes arrive in a property."""
    rules = stylesheet.parse(read("components.css"))
    names = [rule.value("animation-name") for rule in rules if ".ela-indicator" in rule.selectors]
    assert "var(--ela-state-motion)" in names
    assert 'data-ela-state="' not in read("components.css")


# ----------------------------------------------------------------------------------------
# Negatives
# ----------------------------------------------------------------------------------------


def test_an_animation_outside_the_media_query_is_found() -> None:
    text = """
    .a { animation-name: spin; }
    @media (prefers-reduced-motion: reduce) { .b { animation: spin var(--ela-x); } }
    @media (prefers-reduced-motion: no-preference) { .c { animation-name: spin; } }
    @keyframes spin { to { rotate: 1turn; } }
    """
    found = animations_that_would_not_stop(text)
    assert len(found) == 2 and found[0].startswith(".a:") and found[1].startswith(".b:")


def test_a_duration_reduce_forgets_is_found() -> None:
    derived = """
    :root { --ela-motion-duration-fast: 120ms; --ela-motion-duration-slow: 2s; }
    @media (prefers-reduced-motion: reduce) { :root { --ela-motion-duration-fast: 0s; } }
    """
    assert durations_left_running(derived) == {"--ela-motion-duration-slow"}
    slowed = derived.replace("fast: 0s", "fast: 1ms")
    assert durations_left_running(slowed) == {
        "--ela-motion-duration-fast",
        "--ela-motion-duration-slow",
    }


def test_an_undefined_or_orphan_keyframes_is_found() -> None:
    source = tokens()
    source["motion"]["pattern"]["breathe"]["keyframes"]["$value"] = "ela-nowhere"
    components = read("components.css")
    assert "ela-nowhere" in keyframes_named(source, components) - keyframes_defined(components)
    orphan = components + "\n@keyframes ela-unused { to { rotate: 1turn; } }\n"
    assert keyframes_defined(orphan) - keyframes_named(tokens(), orphan) == {"ela-unused"}


def test_a_pattern_no_state_uses_is_found() -> None:
    source = tokens()
    source["state"]["IDLE"]["motion"]["$value"] = "none"
    source["state"]["EVOLVING"]["motion"]["$value"] = "none"
    assert patterns_nobody_uses(source) == {"breathe"}
