"""A tail-recursive loop written in ISO text runs in constant memory.

The ISO surfaces (``.pl``, ``.clausal``) call ``is/2``, ``=/2`` and the
comparisons as built-in predicates, not as the seam's inline arithmetic and
unification; the tail-recursion rewrite (``compiler/tro.py``) did not count
them as deterministic, so ``spin(N) :- N1 is N + 1, spin(N1).`` kept one
generator frame per step and grew by over 100 MB a second (found through
``tests/test_quads.py::test_a_query_that_never_answers_times_out``).
"""
import tracemalloc

import pytest

from clausal.logic.solve import once
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_PROGRAM = """\
count(N, N).
count(I, N) :- I < N, I1 is I + 1, count(I1, N).
walk(N, A, N, A).
walk(I, _, N, R) :- I =< N, I \\== N, A1 = f(I), A1 \\= g, I1 is I + 1,
    walk(I1, A1, N, R).
"""

_STEPS = 20000


@pytest.fixture(params=["pl", "clausal"])
def module(request, tmp_path):
    path = tmp_path / f"loop.{request.param}"
    path.write_text(_PROGRAM)
    return load_clausal_module(str(path))


def _peak_bytes(goal, module):
    tracemalloc.start()
    try:
        assert once(goal, module) is not None
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize("goal", [
    lambda: ("count", 0, _STEPS),
    lambda: ("walk", 0, 0, _STEPS, Var()),
], ids=["is_and_compare", "unify_and_term_compare"])
def test_a_deterministic_tail_loop_does_not_grow(module, goal):
    # One frame per step was some 1.5 KB: 20000 steps held 30 MB and more.
    # Constant space leaves a fraction of a megabyte.
    peak = _peak_bytes(goal(), module)
    assert peak < 3_000_000, f"{_STEPS} steps peaked at {peak} bytes"


def test_the_loop_still_answers(module):
    a = Var()
    assert once(("walk", 0, 0, 5, a), module) is not None
    assert deref(a) == ("f", 4)
