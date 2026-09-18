"""A reader for the HTML this repository writes, on the standard library's parser.

Named ``markup`` and not ``html``: a module called ``html`` would shadow the one it imports.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


@dataclass
class Element:
    tag: str
    attributes: dict[str, str | None] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)

    def get(self, name: str) -> str | None:
        return self.attributes.get(name)

    @property
    def classes(self) -> list[str]:
        return (self.get("class") or "").split()

    def walk(self) -> Iterator[Element]:
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def text(self) -> str:
        parts = [child if isinstance(child, str) else child.text() for child in self.children]
        return " ".join("".join(parts).split())


class Unbalanced(ValueError):
    """A tag closes that was never opened, or the document ends with one still open."""


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document")
        self.open = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs))
        self.open[-1].children.append(element)
        if tag not in VOID:
            self.open.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.open[-1].children.append(Element(tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if len(self.open) == 1 or self.open[-1].tag != tag:
            raise Unbalanced(f"</{tag}> closes {self.open[-1].tag!r}")
        self.open.pop()

    def handle_data(self, data: str) -> None:
        self.open[-1].children.append(data)


def parse(text: str) -> Element:
    builder = _Builder()
    builder.feed(text)
    builder.close()
    if len(builder.open) != 1:
        raise Unbalanced(f"<{builder.open[-1].tag}> is never closed")
    return builder.root
