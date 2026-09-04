from pathlib import Path

import pytest

from tests.architecture.violations import copy_package


@pytest.fixture
def package_copy(tmp_path: Path) -> Path:
    """A throwaway copy of ``src/ela`` the tests can freely corrupt."""
    return copy_package(tmp_path)
