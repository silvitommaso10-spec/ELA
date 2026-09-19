"""A reader for the CSS this repository writes — and for nothing more.

It knows comments, rules, ``@media`` one level deep, ``@keyframes`` and ``@font-face``. What it
does not recognise it **refuses** (:class:`Unrecognised`) instead of skipping: a reader that
skips in silence turns every check built on it into a check that cannot fail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class Unrecognised(ValueError):
    """The stylesheet uses a construct this reader was not written for."""


@dataclass(frozen=True)
class Rule:
    selectors: tuple[str, ...]
    declarations: tuple[tuple[str, str], ...]
    media: str | None = None
    keyframes: str | None = None

    def value(self, name: str) -> str | None:
        found = [value for prop, value in self.declarations if prop == name]
        return found[-1] if found else None


def _closing(text: str, opening: int) -> int:
    """The index of the brace that closes the one at ``opening``, strings respected."""
    depth, quote, index = 0, "", opening
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise Unrecognised("a block is never closed")


def _split(text: str, separator: str) -> list[str]:
    """Split outside parentheses and strings: a value may hold ``;`` or ``,`` in neither."""
    parts, depth, quote, current = [], 0, "", []
    for char in text:
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _declarations(body: str) -> tuple[tuple[str, str], ...]:
    if "{" in body:
        raise Unrecognised("a rule nested inside a rule")
    found = []
    for declaration in _split(body, ";"):
        name, colon, value = declaration.partition(":")
        if not colon or not name.strip() or not value.strip():
            raise Unrecognised(f"not a declaration: {declaration!r}")
        found.append((name.strip(), " ".join(value.split())))
    return tuple(found)


def _rules(text: str, media: str | None, keyframes: str | None) -> list[Rule]:
    found: list[Rule] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        opening = text.find("{", index)
        if opening == -1:
            raise Unrecognised(f"text outside any rule: {text[index : index + 40]!r}")
        prelude = " ".join(text[index:opening].split())
        if ";" in prelude:
            raise Unrecognised(f"an at-rule without a block: {prelude!r}")
        closing = _closing(text, opening)
        body = text[opening + 1 : closing]
        index = closing + 1

        if prelude.startswith("@"):
            if media is not None or keyframes is not None:
                raise Unrecognised(f"an at-rule nested more than one level: {prelude!r}")
            name, _, rest = prelude[1:].partition(" ")
            if name == "media":
                found += _rules(body, rest.strip(), None)
            elif name == "keyframes":
                found += _rules(body, None, rest.strip())
            elif name == "font-face" and not rest:
                found.append(Rule(("@font-face",), _declarations(body)))
            else:
                raise Unrecognised(f"an at-rule this reader does not know: @{name}")
            continue

        selectors = tuple(_split(prelude, ","))
        if not selectors:
            raise Unrecognised("a block without a selector")
        found.append(Rule(selectors, _declarations(body), media, keyframes))
    return found


def parse(text: str) -> list[Rule]:
    return _rules(COMMENT.sub("", text), None, None)


def custom_properties(rules: list[Rule]) -> set[str]:
    """Every custom property the stylesheet declares, wherever it declares it."""
    return {name for rule in rules for name, _ in rule.declarations if name.startswith("--")}


VAR = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")


def read_properties(rules: list[Rule]) -> set[str]:
    """Every custom property the stylesheet reads through ``var()``."""
    return {name for rule in rules for _, value in rule.declarations for name in VAR.findall(value)}
