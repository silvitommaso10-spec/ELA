"""Generate the two derived blocks of ``docs/ARCHITECTURE.md`` by reading ``src/ela``.

The package graph and the four edges that may name an infrastructure library are **facts about
the code**, so they are read off it with ``ast`` and never written by hand: a diagram that cannot
notice it has become false is decoration. The third block of the document — the path a call takes
from a ``POST`` to an effect — is not derivable from imports, is written by hand, and says so;
``tests/docs/test_architecture.py`` checks what can be checked about it.

Usage::

    uv run python scripts/generate_architecture.py            # rewrite the generated blocks
    uv run python scripts/generate_architecture.py --check    # fail if they are out of date
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT_PACKAGE = "ela"
BEGIN = "<!-- generato da scripts/generate_architecture.py: {name} -->"
END = "<!-- fine del blocco generato: {name} -->"
PACKAGES = "il grafo dei package"
INFRA = "i bordi che nominano una libreria di infrastruttura"

INFRA_LIBRARIES = (
    "anthropic",
    "openai",
    "httpx",
    "sqlalchemy",
    "alembic",
    "aiosqlite",
    "fastapi",
    "typer",
    "uvicorn",
)
"""The libraries architecture rule 3 keeps out of the Core (ADR 0002 §3).

Written out here rather than imported from ``tests.architecture.rules`` because a script does not
depend on the test suite; that the two lists agree is asserted by
``tests/docs/test_architecture.py``, which may import both.
"""


def modules(pkg_root: Path) -> Iterator[tuple[str, Path]]:
    """Every module of the package, as ``(top-level package name, path)``."""
    for path in sorted(pkg_root.rglob("*.py")):
        parts = path.relative_to(pkg_root).parts
        yield (parts[0] if len(parts) > 1 else path.stem), path


def imported(path: Path) -> Iterator[str]:
    """Every dotted name this module imports, module-level and nested alike."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def package_of(dotted: str) -> str | None:
    """The top-level ``ela`` package a dotted name belongs to, or ``None`` if it is not one."""
    parts = dotted.split(".")
    if parts[0] != ROOT_PACKAGE or len(parts) < 2:
        return None
    return parts[1]


def package_graph(pkg_root: Path) -> dict[str, set[str]]:
    """Package -> the packages of ``ela`` it imports. Every package is a key, edges or not."""
    graph: dict[str, set[str]] = {
        path.name if path.is_dir() else path.stem: set()
        for path in sorted(pkg_root.iterdir())
        if (path.is_dir() and path.name != "__pycache__")
        or (path.suffix == ".py" and path.stem != "__init__")
    }
    for package, path in modules(pkg_root):
        for dotted in imported(path):
            target = package_of(dotted)
            if target is not None and target != package and target in graph:
                graph[package].add(target)
    return graph


def infra_edges(pkg_root: Path) -> dict[str, set[str]]:
    """Package -> the infrastructure libraries it names. Only the packages that name one."""
    edges: dict[str, set[str]] = {}
    for package, path in modules(pkg_root):
        for dotted in imported(path):
            library = dotted.split(".")[0]
            if library in INFRA_LIBRARIES:
                edges.setdefault(package, set()).add(library)
    return edges


def render_packages(graph: dict[str, set[str]]) -> str:
    lines = ["```mermaid", "graph TD"]
    for package in sorted(graph):
        lines.append(f"    {package}[{ROOT_PACKAGE}.{package}]")
    for package in sorted(graph):
        for target in sorted(graph[package]):
            lines.append(f"    {package} --> {target}")
    lines.append("```")
    return "\n".join(lines)


def render_infra(edges: dict[str, set[str]]) -> str:
    lines = ["| Package | Librerie che nomina |", "|---|---|"]
    for package in sorted(edges):
        libraries = ", ".join(f"`{name}`" for name in sorted(edges[package]))
        lines.append(f"| `{ROOT_PACKAGE}.{package}` | {libraries} |")
    return "\n".join(lines)


def blocks(pkg_root: Path) -> dict[str, str]:
    """The generated blocks by name: what the document must contain, byte for byte."""
    return {
        PACKAGES: render_packages(package_graph(pkg_root)),
        INFRA: render_infra(infra_edges(pkg_root)),
    }


def replace(document: str, name: str, body: str) -> str:
    """The document with the block ``name`` replaced by ``body``; the markers stay."""
    begin, end = BEGIN.format(name=name), END.format(name=name)
    start, stop = document.find(begin), document.find(end)
    if start < 0 or stop < 0 or stop < start:
        raise ValueError(f"{name}: the markers are missing or out of order")
    return document[: start + len(begin)] + "\n\n" + body + "\n\n" + document[stop:]


def generate(document: str, pkg_root: Path) -> str:
    for name, body in blocks(pkg_root).items():
        document = replace(document, name, body)
    return document


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / "docs" / "ARCHITECTURE.md"
    current = target.read_text(encoding="utf-8")
    wanted = generate(current, root / "src" / ROOT_PACKAGE)
    if current == wanted:
        print(f"{target}: up to date")
        return 0
    if "--check" in argv:
        print(
            f"{target} is out of date: the code changed and the diagram did not.\n"
            "Rigenera con: uv run python scripts/generate_architecture.py",
            file=sys.stderr,
        )
        return 1
    target.write_text(wanted, encoding="utf-8")
    print(f"{target}: rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
