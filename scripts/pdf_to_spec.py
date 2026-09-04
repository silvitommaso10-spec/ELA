"""One-off conversion of ``docs/spec/ELA.pdf`` into ``docs/spec/ELA_spec.md``.

This script exists only for reproducibility of the M0.1 conversion. It is tied to the
exact text layout that PyMuPDF extracts from *this* PDF (one paragraph per line, ``●``
bullets followed by a zero-width space, page breaks as empty lines, section separators
as space-only lines, four section titles wrapped onto a second line). It is not project
tooling, has no tests and is not expected to work on any other document.

Usage (from the repository root, PyMuPDF is in the ``dev`` dependency group)::

    uv run python scripts/pdf_to_spec.py [docs/spec/ELA.pdf] [docs/spec/ELA_spec.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

ZWSP = "​"
FIRST_BODY_LINE = 10  # 1-based line of "1. Che cos'è ELA" in the extracted text
SECTION_COUNT = 70
WRAPPED_TITLES = [8, 36, 58, 65]  # titles the PDF wraps onto two lines

# Verbatim blocks (start line -> end line), matched on the cleaned, stripped line.
BLOCKS = {
    "Planner": "→ Audit",  # §27
    "ELA/": "└── tests/",  # §48
    "SPEC": "NEXT MILESTONE",  # §53
    "Foundation": "Evolution",  # §55
    "ELA CORE": "Task Graph",  # §56
}
DIAGRAM_START = "La struttura concettuale di ELA è:"  # §46, runs until the next heading

HEADING = re.compile(r"^(\d{1,2})\. (\S.*)$")
SUBHEADING = re.compile(r"^(\d{1,2})\.(\d+) (\S.*)$")
NUMBERED = re.compile(r"^(\d{1,2})\." + ZWSP + r"\s*(.*)$")
BULLET = re.compile(r"^●" + ZWSP + r"\s*(.*)$")
SENTENCE_END = re.compile(r"[.:;!?\"\\]$")
TITLE_PUNCTUATION = re.compile(r"[.:;,\"]")

PREAMBLE = """# ELA — Executive Life Assistant

*Definizione completa del sistema, architettura, funzionamento e visione*

- **Versione:** 1.0
- **Stato:** Documento di riferimento del progetto
- **Progetto:** ELA
- **Obiettivo:** costruire un assistente personale AI altamente autonomo, multimodale, \
distribuito e persistente.

> Questo documento è la conversione in Markdown di `ELA.pdf` (conservato in questa stessa \
cartella).
> La numerazione delle sezioni (1–70) è quella del PDF ed è la fonte di verità del progetto.
"""


def extract_lines(pdf_path: Path) -> list[str]:
    with pymupdf.open(pdf_path) as document:
        return "\n".join(page.get_text() for page in document).split("\n")


class Converter:
    """Turns the extracted lines into Markdown, one paragraph per source line."""

    def __init__(self) -> None:
        self.out: list[str] = []
        self.last = "blank"  # kind of the last emitted line
        self.expected = 1  # next section number
        self.joined: list[int] = []
        self.block_end: str | None = None
        self.in_diagram = False

    # -- emission helpers -------------------------------------------------------------

    def emit(self, kind: str, text: str) -> None:
        after_prose = ("text", "bullet", "numbered", "code")
        needs_gap = {
            "text": self.last in after_prose,
            "bullet": self.last in ("text", "numbered", "hardbreak", "code"),
            "numbered": self.last in ("text", "bullet", "hardbreak", "code"),
            "hardbreak": self.last in ("text", "bullet", "numbered"),
            "heading": self.last != "blank",
        }.get(kind, False)
        if needs_gap and self.out and self.out[-1] != "":
            self.out.append("")
        self.out.append(text)
        self.last = kind

    def emit_heading(self, text: str) -> None:
        self.emit("heading", text)
        self.out.append("")
        self.last = "blank"

    def open_fence(self, first_line: str) -> None:
        if self.out and self.out[-1] != "":
            self.out.append("")
        self.out.append("```")
        self.out.append(first_line)

    def close_fence(self) -> None:
        while self.out and self.out[-1] == "":
            self.out.pop()
        self.out.append("```")
        self.last = "code"

    # -- main loop --------------------------------------------------------------------

    def convert(self, raw: list[str]) -> str:
        i = FIRST_BODY_LINE - 1
        while i < len(raw):
            line = raw[i]
            i += 1
            if line == "":  # page break inserted by the extractor
                continue
            clean = line.replace(ZWSP, "").rstrip()
            heading = HEADING.match(clean)
            is_heading = heading is not None and int(heading.group(1)) == self.expected

            if self.in_diagram and not is_heading:
                self.out.append(clean)
                continue
            if self.in_diagram:
                self.close_fence()
                self.in_diagram = False
            if self.block_end is not None:
                self.out.append(clean)
                if clean.strip() == self.block_end:
                    self.close_fence()
                    self.block_end = None
                continue
            if clean == "":  # section separator in the PDF
                continue

            if heading is not None and is_heading:
                title = heading.group(2).strip()
                continuation = raw[i].replace(ZWSP, "").strip() if i < len(raw) else ""
                if self._is_wrapped_title(continuation):
                    title = f"{title} {continuation}"
                    self.joined.append(self.expected)
                    i += 1
                self.emit_heading(f"## {self.expected}. {title}")
                self.expected += 1
                continue
            sub = SUBHEADING.match(clean)
            if sub is not None and int(sub.group(1)) == self.expected - 1:
                self.emit_heading(f"### {sub.group(1)}.{sub.group(2)} {sub.group(3).strip()}")
                continue
            bullet = BULLET.match(line.rstrip())
            if bullet is not None:
                self.emit("bullet", f"- {bullet.group(1).strip()}")
                continue
            numbered = NUMBERED.match(line.rstrip())
            if numbered is not None:
                self.emit("numbered", f"{numbered.group(1)}. {numbered.group(2).strip()}")
                continue
            if clean.strip() in BLOCKS:
                self.open_fence(clean)
                self.block_end = BLOCKS[clean.strip()]
                continue
            if clean == DIAGRAM_START:
                self.emit("text", clean)
                self.out.append("")
                self.out.append("```")
                self.in_diagram = True
                continue
            if line.endswith(ZWSP):  # soft line break inside a paragraph
                self.emit("hardbreak", clean + "\\")
                continue
            if self._continues_wrapped_sentence():
                self.out[-1] = f"{self.out[-1]} {clean}"
                continue
            self.emit("text", clean)

        self._check()
        while self.out and self.out[-1] == "":
            self.out.pop()
        return PREAMBLE + "\n" + "\n".join(self.out) + "\n"

    @staticmethod
    def _is_wrapped_title(continuation: str) -> bool:
        return (
            bool(continuation)
            and continuation[0].islower()
            and len(continuation.split()) <= 3
            and TITLE_PUNCTUATION.search(continuation) is None
        )

    def _continues_wrapped_sentence(self) -> bool:
        """The PDF wrapped a long sentence: previous prose line has no terminal punctuation."""
        return (
            self.last == "text"
            and len(self.out[-1]) > 70
            and SENTENCE_END.search(self.out[-1]) is None
        )

    def _check(self) -> None:
        if self.expected != SECTION_COUNT + 1:
            raise RuntimeError(f"expected {SECTION_COUNT} sections, found {self.expected - 1}")
        if self.joined != WRAPPED_TITLES:
            raise RuntimeError(f"re-joined titles {self.joined}, expected {WRAPPED_TITLES}")
        if self.block_end is not None or self.in_diagram:
            raise RuntimeError("unterminated verbatim block")


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    pdf_path = Path(argv[1]) if len(argv) > 1 else root / "docs" / "spec" / "ELA.pdf"
    md_path = Path(argv[2]) if len(argv) > 2 else root / "docs" / "spec" / "ELA_spec.md"
    markdown = Converter().convert(extract_lines(pdf_path))
    md_path.write_text(markdown, encoding="utf-8")
    print(f"wrote {md_path} ({SECTION_COUNT} sections)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
