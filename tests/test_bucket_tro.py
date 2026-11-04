"""Last-call optimisation (TRO) inside first-argument index buckets.

A predicate indexed on an argument is compiled into one function per index
bucket.  A bucket's tail-recursive clause hands its new arguments to the
dispatch loop, which restarts the predicate in place, so a loop through an
indexed predicate runs in constant space.

The TRO sweep found these clauses, but the bucket's own compile asked again
whether the tail call is a self call -- under the bucket function's name
(``count__p0_b1``), which no tail call names.  No bucket, default or fallback
function emitted the restart: every iteration made an ordinary call, and the
memory a loop held grew with its length (about 4.5 KB an iteration).

The fixtures hold the same predicate in the three source surfaces.
"""
from __future__ import annotations

import os
import tracemalloc

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_SURFACES = ["bucket_tro.pl", "bucket_tro.clausal", "bucket_tro.seam"]


@pytest.fixture(scope="module", params=_SURFACES)
def count_mod(request):
    name = "tests.fixtures." + request.param.replace(".", "_")
    return _load_module(name, os.path.join(_FIXTURES, request.param))


def _answers(mod, *args):
    lm = mod.__dict__["$module"]
    out = Var()
    return [deref(out) for _ in call("count", *args, out, module=lm)]


def _bucket_functions(mod):
    """The compiled bucket functions of count/4's first-argument index."""
    row = mod.__dict__["$module"].db.row("count", 4)
    found = {}
    stack = list(row.index_plans[0].values())
    seen = set()
    while stack:
        fn = stack.pop()
        if id(fn) in seen:
            continue
        seen.add(id(fn))
        code = getattr(fn, "__code__", None)
        if code is not None and "__p0_b" in code.co_name:
            found[code.co_name] = fn
        for cell in getattr(fn, "__closure__", None) or ():
            try:
                contents = cell.cell_contents
            except ValueError:
                continue
            if callable(contents):
                stack.append(contents)
    return found


def test_the_bucket_of_the_recursive_clause_restarts_in_place(count_mod):
    """The ``go`` bucket holds the recursive clause; its compiled code takes
    the in-place restart (``trail.commit_fresh`` guards it), the buckets
    without a tail call do not."""
    buckets = _bucket_functions(count_mod)
    assert len(buckets) == 3, sorted(buckets)
    restarting = sorted(name for name, fn in buckets.items()
                        if "commit_fresh" in fn.__code__.co_names)
    assert len(restarting) == 1 and "__p0_b1" in restarting[0], restarting


def test_answers(count_mod):
    assert _answers(count_mod, "go", 0, 0) == [0]
    assert _answers(count_mod, "go", 5, 10) == [15]
    assert _answers(count_mod, "stop", 7, 3) == [3]
    assert _answers(count_mod, "other", 7, 3) == [3]
    assert _answers(count_mod, "go", -1, 0) == []


def test_a_long_loop_runs_in_bounded_memory(count_mod):
    """30000 iterations: about 135 MB traced before the restart was emitted,
    under 1 MB with it."""
    n = 30000
    tracemalloc.start()
    try:
        assert _answers(count_mod, "go", n, 0) == [n]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8_000_000, f"peak {peak / 1e6:.1f} MB for {n} iterations"


# ── Order: only a restart that keeps clause order is taken ──────────────────
#
# The dispatch loop takes a signalled tail call after the bucket function
# has run out, so a restart from a clause with later clauses in its bucket
# would give their answers first.  Such a clause makes the ordinary call
# (tests/test_tro_nonlast_arm_clobber.py pins the order); a clause that cuts
# before its tail call has no later clauses left, so it restarts.

@pytest.fixture(scope="module")
def cut_mod():
    return _load_module("tests.fixtures.bucket_tro_cut",
                        os.path.join(_FIXTURES, "bucket_tro_cut.pl"))


def test_a_clause_that_cuts_before_its_tail_restarts(cut_mod):
    buckets = _bucket_functions(cut_mod)
    restarting = sorted(name for name, fn in buckets.items()
                        if "commit_fresh" in fn.__code__.co_names)
    assert len(restarting) == 1 and "__p0_b0" in restarting[0], restarting
    assert _answers(cut_mod, "go", 3, 0) == [3]
    assert _answers(cut_mod, "go", 0, 5) == [5]
    assert _answers(cut_mod, "more", 2, 0) == [0]
    n = 30000
    tracemalloc.start()
    try:
        assert _answers(cut_mod, "go", n, 0) == [n]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8_000_000, f"peak {peak / 1e6:.1f} MB for {n} iterations"
