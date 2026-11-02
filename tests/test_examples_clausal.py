"""The shipped examples: every program in ``clausal/examples`` is there in
Clausal Prolog (``.clausal``), and each one's own ``test/1`` clauses pass.

The installed package ships these files (``tools/wheel_smoke.py`` runs them
again from a wheel); this keeps them passing between releases.
"""
import pathlib

import pytest

from clausal.testing import run_file

EXAMPLES = pathlib.Path(__file__).resolve().parent.parent / "clausal" / "examples"
CLAUSAL = sorted(EXAMPLES.glob("*.clausal"))


def test_every_seam_example_has_a_clausal_twin():
    missing = sorted(p.stem for p in EXAMPLES.glob("*.seam")
                     if not (EXAMPLES / (p.stem + ".clausal")).exists())
    assert CLAUSAL and not missing, f"no .clausal version of: {missing}"


@pytest.mark.parametrize("path", CLAUSAL, ids=lambda p: p.name)
def test_example_passes_its_own_tests(path):
    results = run_file(path).results
    failed = [f"{r.name}: {r.error}" for r in results if not r.passed]
    assert results and not failed, (
        f"{path.name}: {len(failed)} of {len(results)} failed:\n  "
        + "\n  ".join(failed))
