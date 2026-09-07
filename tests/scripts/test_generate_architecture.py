"""Behaviour of ``scripts/generate_architecture.py`` on synthetic package trees.

The point of the generator is that the diagram cannot stay true by accident, so the case that
matters is the negative one: a tree that grew an import while the document did not. It is checked
here on a tree built for the purpose rather than on ``src/ela``, so the test says something about
the generator and not about today's shape of ELA.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "generate_architecture.py"

INFRA_BLOCK = "i bordi che nominano una libreria di infrastruttura"
TEMPLATE = (
    """# Test

<!-- generato da scripts/generate_architecture.py: il grafo dei package -->

{packages}

<!-- fine del blocco generato: il grafo dei package -->

qualcosa scritto a mano, che non deve essere toccato

<!-- generato da scripts/generate_architecture.py: {block} -->

{infra}

<!-- fine del blocco generato: {block} -->
"""
).replace("{block}", INFRA_BLOCK)


@pytest.fixture(scope="module")
def generate_architecture() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Three packages: ``core`` alone, ``edge`` importing it and naming ``httpx``."""
    root = tmp_path / "ela"
    (root / "core").mkdir(parents=True)
    (root / "edge").mkdir()
    (root / "core" / "__init__.py").write_text("from ela.domain import Thing\n", encoding="utf-8")
    (root / "edge" / "__init__.py").write_text(
        "import httpx\nfrom ela.core import x\n", encoding="utf-8"
    )
    (root / "domain.py").write_text("import json\n", encoding="utf-8")
    return root


def test_the_graph_is_the_imports_and_every_package_is_a_node(
    tree: Path, generate_architecture: ModuleType
) -> None:
    graph = generate_architecture.package_graph(tree)

    assert graph == {"core": {"domain"}, "edge": {"core"}, "domain": set()}


def test_only_the_packages_that_name_a_library_are_edges(
    tree: Path, generate_architecture: ModuleType
) -> None:
    assert generate_architecture.infra_edges(tree) == {"edge": {"httpx"}}


def test_a_document_in_step_with_the_code_is_left_alone(
    tree: Path, generate_architecture: ModuleType
) -> None:
    blocks = generate_architecture.blocks(tree)
    document = TEMPLATE.format(
        packages=blocks["il grafo dei package"],
        infra=blocks["i bordi che nominano una libreria di infrastruttura"],
    )

    assert generate_architecture.generate(document, tree) == document
    assert "qualcosa scritto a mano" in generate_architecture.generate(document, tree)


def test_an_import_the_document_never_heard_of_is_detected(
    tree: Path, generate_architecture: ModuleType
) -> None:
    """The negative case: the code grew an edge and the diagram did not."""
    blocks = generate_architecture.blocks(tree)
    document = TEMPLATE.format(
        packages=blocks["il grafo dei package"],
        infra=blocks["i bordi che nominano una libreria di infrastruttura"],
    )
    (tree / "core" / "__init__.py").write_text(
        "from ela.domain import Thing\nfrom ela.edge import backwards\n", encoding="utf-8"
    )

    regenerated = generate_architecture.generate(document, tree)

    assert regenerated != document
    assert "core --> edge" in regenerated


def test_a_library_the_document_never_heard_of_is_detected(
    tree: Path, generate_architecture: ModuleType
) -> None:
    blocks = generate_architecture.blocks(tree)
    document = TEMPLATE.format(
        packages=blocks["il grafo dei package"],
        infra=blocks["i bordi che nominano una libreria di infrastruttura"],
    )
    (tree / "core" / "__init__.py").write_text("import sqlalchemy\n", encoding="utf-8")

    regenerated = generate_architecture.generate(document, tree)

    assert regenerated != document
    assert "| `ela.core` | `sqlalchemy` |" in regenerated


def test_a_document_without_the_markers_is_refused(
    tree: Path, generate_architecture: ModuleType
) -> None:
    """Rewriting a document that never asked to be generated would be worse than failing."""
    with pytest.raises(ValueError, match="markers"):
        generate_architecture.generate("# niente marcatori\n", tree)


def test_the_repository_document_is_up_to_date(generate_architecture: ModuleType) -> None:
    """``main --check`` is the form ``make check`` would use, exit code and all."""
    assert generate_architecture.main(["generate_architecture.py", "--check"]) == 0
