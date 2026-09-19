"""Motion is made of tokens, and it stops (M17.1, criterio 13; dec. 4).

``prefers-reduced-motion`` is respected everywhere **by construction**: ``tokens.css`` takes
every duration to zero under ``reduce`` — the spin of the sphere is a duration like any other —
so every transition and every turn goes out because it reads a token (``test_tokens_only.py``
refuses a duration written by hand); and a hand-written ``animation`` may only be declared
inside ``@media (prefers-reduced-motion: no-preference)``. The light stands still, and the
colour and the word beneath still say everything.

The state is the light of the sphere, and the light arrives from the derived rule of the state:
``components.css`` names no state.
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
    """A pattern is used by the ambient halo of a state, or by a kind of core a state has."""
    module = generator()
    states = module.entries(source["state"]).values()
    used = {str(state["ambient"]["$value"]) for state in states}
    kinds = module.entries(source["presence"]["core"]["kind"])
    cores = {str(state["core"]["$value"]) for state in states}
    used |= {
        str(kind["motion"]["$value"])
        for name, kind in kinds.items()
        if "{presence.core.kind." + name + "}" in cores
    }
    return {
        name
        for name in module.entries(source["motion"]["pattern"])
        if "{motion.pattern." + name + "}" not in used
    }


def kinds_of_core_nobody_has(source: dict[str, Any]) -> set[str]:
    module = generator()
    cores = {str(state["core"]["$value"]) for state in module.entries(source["state"]).values()}
    return {
        name
        for name in module.entries(source["presence"]["core"]["kind"])
        if "{presence.core.kind." + name + "}" not in cores
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


def test_reduced_motion_takes_every_duration_to_zero_and_the_spin_is_a_duration() -> None:
    assert durations_left_running(read("tokens.css")) == set()
    module = generator()
    for key, state in module.entries(tokens()["state"]).items():
        path = module.target_of(state["spin"]["$value"])
        assert path is not None and path[:2] == ("motion", "duration"), key


def test_every_motion_is_defined_and_nothing_is_an_orphan() -> None:
    components = read("components.css")
    assert keyframes_named(tokens(), components) == keyframes_defined(components)
    assert patterns_nobody_uses(tokens()) == set()
    assert kinds_of_core_nobody_has(tokens()) == set()


def test_the_light_of_a_state_reaches_the_sphere_through_the_derived_rule() -> None:
    """The list of states is not in components.css: what a state is arrives in properties."""
    rules = stylesheet.parse(read("components.css"))
    moved = {
        selector: rule
        for rule in rules
        if rule.media == NO_PREFERENCE
        for selector in rule.selectors
    }
    assert moved[".ela-orb__core"].value("animation-name") == "var(--ela-state-core-motion)"
    assert moved[".ela-orb__ambient"].value("animation-name") == ("var(--ela-state-ambient-motion)")
    assert moved[".ela-orb__cloud"].value("animation-play-state") == "var(--ela-state-play)"
    for cloud in ("one", "two", "vortex"):
        duration = moved[f".ela-orb__cloud--{cloud}"].value("animation-duration") or ""
        assert "var(--ela-state-spin)" in duration, cloud
    assert 'data-ela-state="' not in read("components.css")


def test_a_state_that_stands_still_is_paused_and_the_others_turn() -> None:
    module = generator()
    source = tokens()
    still = [
        key
        for key, state in module.entries(source["state"]).items()
        if dict(module.state_declarations(source, state))["--ela-state-play"] == "paused"
    ]
    assert still == ["OFFLINE", "WAITING APPROVAL", "ATTENTION REQUIRED", "ERROR", "RECOVERING"], (
        "the states that ask for the user or report a fault stop moving: a change here is a"
        " change of the user's decision of 2026-09-19"
    )


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
    :root { --ela-motion-duration-fast: 120ms; --ela-motion-duration-spin-idle: 26s; }
    @media (prefers-reduced-motion: reduce) { :root { --ela-motion-duration-fast: 0s; } }
    """
    assert durations_left_running(derived) == {"--ela-motion-duration-spin-idle"}
    slowed = derived.replace("fast: 0s", "fast: 1ms")
    assert durations_left_running(slowed) == {
        "--ela-motion-duration-fast",
        "--ela-motion-duration-spin-idle",
    }


def test_an_undefined_or_orphan_keyframes_is_found() -> None:
    source = tokens()
    source["motion"]["pattern"]["core-breathe"]["keyframes"]["$value"] = "ela-nowhere"
    components = read("components.css")
    assert "ela-nowhere" in keyframes_named(source, components) - keyframes_defined(components)
    orphan = components + "\n@keyframes ela-unused { to { rotate: 1turn; } }\n"
    assert keyframes_defined(orphan) - keyframes_named(tokens(), orphan) == {"ela-unused"}


def test_a_pattern_and_a_kind_of_core_nobody_uses_are_found() -> None:
    source = tokens()
    source["state"]["ATTENTION REQUIRED"]["ambient"]["$value"] = "none"
    assert patterns_nobody_uses(source) == {"ambient-signal"}

    source = tokens()
    source["state"]["LISTENING"]["core"]["$value"] = "{presence.core.kind.steady}"
    assert kinds_of_core_nobody_has(source) == {"pulsing"}
    assert patterns_nobody_uses(source) == {"core-pulse"}
