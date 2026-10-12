"""A ``-shallow`` predicate none of whose clauses yields must FAIL, not crash.

Found by the catch/3 review (2026-10-13).  The shallow strategy compiles a
predicate to a Python generator function whose clauses are ``match`` arms;
a clause YIELDS once per solution.  When no clause body can yield -- every
clause throws (``c3(2) <- throw(z)``) or fails (``c4(2) <- False``) -- the
emitted function had no ``yield`` at all, so CPython compiled a PLAIN
function: it returned ``None`` and the trampoline adapter's ``for`` raised

    TypeError: 'NoneType' object is not iterable

for every call -- including the ones whose head matches no clause, which ISO
answers by failing.  The trampoline strategy already forced a generator body
(``_stmts_force_generator``, A03-F003); the shallow builder only did so for
an EMPTY body.

Scryer and Trealla agree on every answer pinned here (the program is the same
text in ISO syntax: ``c3(2) :- throw(z).`` ...): no matching clause fails, a
matching clause that throws raises the ball, a matching clause that fails
fails.  The trampoline-strategy twin of each module is the control.

``-shallow`` is a seam directive only: the Clausal Prolog front end refuses
it as an unknown directive (``iso_l3_directives._DIRECTIVES``), so there is no
``.clausal`` twin.
"""
from __future__ import annotations

import sys
import textwrap
import warnings

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from tests._suffix import SEAM

_SRC = """
-module(NAME, [])
-private([z])
SHALLOW
c3(2) <- throw(z)
c4(2) <- False
c5(2) <- throw(z)
c5(3) <- False
c6(1) <- False
c6(2) <- False
c6(3) <- False
via_c3(X) <- c3(X)
via_c5(X) <- c5(X)
"""

_PREDS = "c3/1, c4/1, c5/1, c6/1, via_c3/1, via_c5/1"


@pytest.fixture(params=["shallow", "trampoline"])
def mod(request, tmp_path, monkeypatch):
    from clausal.import_hook import _load_module
    strategy = request.param
    name = f"shnoy_{strategy}"
    shallow = f"-shallow([{_PREDS}])" if strategy == "shallow" else ""
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(
        _SRC.replace("NAME", name).replace("SHALLOW", shallow)).lstrip())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = _load_module(name, str(path))
    try:
        db = m.__dict__["$module"]
        if strategy == "shallow":
            for p in _PREDS.split(", "):
                f, a = p.split("/")
                assert db.db.is_shallow(f, int(a)), p
        yield db
    finally:
        sys.modules.pop(name, None)


def _answers(m, goal):
    return [_deref_walk(goal) for _ in solve(goal, m)]


def _ball(m, goal):
    with pytest.raises(LogicException) as info:
        _answers(m, goal)
    return _deref_walk(info.value.term)


# ── no clause matches: fail ──────────────────────────────────────────────────


def test_no_clause_matches_a_throwing_predicate(mod):
    """The todo's repro: ``c3(2) <- throw(z)``, then ``c3(1)``."""
    assert _answers(mod, ("c3", 1)) == []


def test_no_clause_matches_a_failing_predicate(mod):
    assert _answers(mod, ("c4", 1)) == []


def test_no_clause_matches_a_mixed_predicate(mod):
    """Two ground first arguments: the shallow compile indexes them, so the
    no-match goes through the index's default bucket."""
    assert _answers(mod, ("c5", 1)) == []


# ── a clause matches and only throws: the ball ───────────────────────────────


def test_a_clause_that_only_throws_raises_its_ball(mod):
    assert _ball(mod, ("c3", 2)) == "z"


def test_a_throwing_clause_in_a_mixed_predicate_raises_its_ball(mod):
    assert _ball(mod, ("c5", 2)) == "z"


def test_an_unbound_call_reaches_the_throwing_clause(mod):
    """``c5(X)``: the first clause matches and throws (Scryer: ``z``)."""
    assert _ball(mod, ("c5", Var())) == "z"


# ── a clause matches and only fails: fail ────────────────────────────────────


def test_a_clause_that_only_fails_fails(mod):
    assert _answers(mod, ("c4", 2)) == []


def test_a_failing_clause_in_a_mixed_predicate_fails(mod):
    assert _answers(mod, ("c5", 3)) == []


def test_every_clause_fails_for_every_mode(mod):
    """``c6`` is three failing clauses: indexed buckets of one clause each,
    and the unindexed fallback for an unbound argument."""
    for arg in (1, 2, 3, 4, Var()):
        assert _answers(mod, ("c6", arg)) == [], arg


# ── through a caller ─────────────────────────────────────────────────────────


def test_a_caller_of_a_no_yield_predicate_fails_or_raises(mod):
    assert _answers(mod, ("via_c3", 1)) == []
    assert _ball(mod, ("via_c3", 2)) == "z"
    assert _answers(mod, ("via_c5", 3)) == []
    assert _ball(mod, ("via_c5", 2)) == "z"


def test_catch_around_a_no_yield_predicate(mod):
    """catch/3 sees the failure as a failure (no handler runs) and the ball
    as the ball -- the over-catching catch/3 that hid the TypeError is gone,
    so nothing may stand in for it."""
    e = Var()
    assert _answers(mod, ("catch", ("c3", 1), e, True)) == []
    e = Var()
    (answer,) = _answers(mod, ("catch", ("c3", 2), e, True))
    assert answer[2] == "z"
