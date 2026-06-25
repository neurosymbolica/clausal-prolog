"""Regression: a suspended clause choicepoint that is closed (as the garbage
collector does when it reclaims an abandoned generator mid-query) must NOT undo
bindings the live search made after that choicepoint's trail mark.

Background
----------
Each clause arm compiled to::

    _mark = trail.mark()
    try:
        <head guards + body goals, with yields>
    finally:
        trail.undo(_mark)

When such a generator is suspended at a choicepoint and later abandoned (e.g.
``once/1`` or ``\\+`` committed past it), CPython throws ``GeneratorExit`` into
it on collection and the ``finally`` ran ``trail.undo(_mark)`` — truncating the
*live* trail back to that old mark and destroying the in-flight search's
bindings. The symptom was non-deterministic lost/duplicate solutions in
long-lived multi-query harnesses, only with GC enabled. See
``todo/sequential-query-state-accumulation-bug.md`` (issue #3).

The fix skips the undo when the generator is being closed.
"""

from __future__ import annotations

import gc
import os

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, unify, deref


def _load(tmp_path, name, text):
    src = tmp_path / f"{name}.clausal"
    src.write_text(text)
    return _load_module(name, str(src))


def test_closing_suspended_choicepoint_preserves_live_bindings(tmp_path):
    # A two-clause predicate: enumerating opt(X) leaves clause 2 as a suspended
    # choicepoint after the first solution, inside its mark/undo try/finally.
    mod = _load(tmp_path, "gc_choicepoint", "opt(1),\nopt(2),\n")
    opt = mod.opt

    t = Trail()
    X = Var()
    gen = call(opt, X, trail=t)

    next(gen)                      # first solution: X = 1, clause-2 gen suspended
    assert deref(X) == 1

    # The live search continues and binds more variables on the SAME trail,
    # past the suspended choicepoint's mark.
    Y, Z = Var(), Var()
    unify(Y, 42, t)
    unify(Z, 99, t)

    # Simulate GC reclaiming the abandoned choicepoint generator.
    gen.close()
    gc.collect()

    # The bindings made after the choicepoint must survive (pre-fix: wiped).
    assert deref(Y) == 42
    assert deref(Z) == 99


def test_enumeration_still_correct(tmp_path):
    """Sanity: normal backtracking still undoes head bindings between clauses."""
    mod = _load(tmp_path, "gc_enum", "opt(1),\nopt(2),\nopt(3),\n")
    results = []
    X = Var()
    for _ in call(mod.opt, X):
        results.append(deref(X))
    assert sorted(results) == [1, 2, 3]
