"""The ballast of the observation (decision 127 of the branch m13.11-il-browser-sul-pc), on the
branch diag-m13.11-osservazione only, which never enters main. It writes test files that are not
tracked: each id an empty test that passes, so that a tree runs with the counts of the other.

Usage: python3 zavorra.py <controllo|nuovo> <tree>
- «controllo»: on da241f8, the files the new code has more, with their names and the number of
  their ids, and the +4 and the +1 of two files that exist in both, in two files beside them;
- «nuovo»: on the tip, a test_the_proofs_never_launch_for_real.py with the eleven ids da241f8 has.
It writes nothing over a file that is there, and says every file and its count. Only the standard
library: it runs before the tree's own Python is installed.
"""

import sys
from pathlib import Path

FILES = {
    "controllo": {
        "tests/scripts/test_a_script_never_reaches_the_real_world.py": 30,
        "tests/scripts/test_every_way_a_test_runs_a_script.py": 15,
        "tests/scripts/test_misura_m13_11.py": 196,
        "tests/scripts/test_misura_m13_11_windows.py": 8,
        "tests/scripts/test_the_fences_on_windows.py": 7,
        "tests/test_the_environment_of_the_suite.py": 6,
        "tests/docs/test_adr_ci_runner_zavorra.py": 4,
        "tests/test_suite_log_zavorra.py": 1,
    },
    "nuovo": {
        "tests/scripts/test_the_proofs_never_launch_for_real.py": 11,
    },
}
TEMPLATE = '''"""Zavorra della decisione 127 del branch m13.11-il-browser-sul-pc, sul branch
diag-m13.11-osservazione soltanto: {count} test vuoti che passano, non tracciati, perché l'albero
giri con i conti dell'altro."""

import pytest


@pytest.mark.parametrize("numero", range({count}))
def test_zavorra(numero: int) -> None:
    assert numero >= 0
'''

mode, tree = sys.argv[1], Path(sys.argv[2])
files = FILES[mode]
there = [path for path in files if (tree / path).exists()]
if there:
    sys.exit(f"zavorra: c'è già {there}: non scrivo niente")
for path, count in files.items():
    (tree / path).write_text(TEMPLATE.format(count=count), encoding="utf-8")
    print(f"zavorra: {path}, {count} id")
print(f"zavorra: {sum(files.values())} id in {len(files)} file")
