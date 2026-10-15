"""retract/1 and clause/2 (ISO 8.9.3, 8.8.1): a clause's own body can call
ANY predicate -- static, dynamic, or undefined -- without the construction
that reads the body back for matching caring which.

Found 2026-10-15 via Ciao's ``iso_tests`` (``retract_test3``/``retract_test4``
in Ulrich Neumerkel's corpus, run against Clausal's native ``.pl`` frontend):
``retract((p(X, 2) :- T))`` raised ``permission_error(access,
private_procedure, p/2)`` whenever ``T`` unified with a call to a STATIC
locally-defined predicate (``animal(_) :- fail.``, no ``-dynamic``) -- but
not when it unified with a call to a DYNAMIC one, or to an undefined one.
``clause/2`` (which shares the same body-reconstruction machinery,
``clause_ops.clause_terms``) showed the identical split.

ROOT CAUSE: ``clause_ops._needs_cell`` decides whether an ordinary call
inside the body must be explicitly rewritten to the cell it denotes
(``TupleLiteral`` -> ``("p", Args...)``) before the body is recompiled as a
construction query, or whether the general compiler already builds that cell
on its own.  For a name bound to a predicate at the RIGHT arity it assumed
the latter -- true for a ``-dynamic`` (or still-unlocked) row, because the
P2 cell discipline backs those with a class usable as a value constructor,
but FALSE for an ordinary STATIC one: construction going through that
binding instead raised ``existence_error(procedure, ...)`` ("nothing
declares the functor"), which both ``retract/1`` and ``clause/2`` read as
"this clause has no term form" and refused with the private-procedure
permission error -- a refusal about the CLAUSE BEING INSPECTED that was
really triggered by an incidental property of what its body happens to
call.  Fixed by also wrapping a right-arity STATIC call, which never has a
class-based cell to fall back on.

retract/1's permission check must depend only on the clause being
retracted -- its own head functor/arity, and whether that functor is a
protected control-construct/static/grammar-rule indicator -- never on what
a defined, callable, well-formed body happens to invoke.
"""
from __future__ import annotations

import itertools
import os
import tempfile
import warnings

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.terms import term_writeq

_N = itertools.count()


def _load(tmp_path, monkeypatch, pl_src: str):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    name = f"retract_static_body{next(_N)}"
    path = tmp_path / f"{name}.pl"
    path.write_text(pl_src)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # singleton-variable lint
        return _load_module(name, str(path))


def _answers(mod, goal_name: str, limit: int = 5) -> list[str]:
    r = Var()
    out = []
    for _ in itertools.islice(solve((goal_name, r), mod), limit):
        out.append(term_writeq(deref(r), local_vars=True))
    return out


def _raises(mod, goal_name: str) -> tuple:
    r = Var()
    with pytest.raises(LogicException) as info:
        list(itertools.islice(solve((goal_name, r), mod), 1))
    return deref(info.value.term)


# The Ciao/ISO corpus program, trimmed to the two predicates under test:
# ``animal/1`` and ``bird/1`` are STATIC (no ``-dynamic``), always fail, and
# are the thing the retracted clauses' bodies call; ``p_insect/1`` is
# DYNAMIC, the known-green control that must keep working either way.
_SRC = """
animal(_) :- fail.
bird(_) :- fail.

:- dynamic(p_insect/1).
p_insect(ant).
p_insect(bee).

:- dynamic(legs/2).
legs(A, 4) :- animal(A).
legs(A, 6) :- p_insect(A).
legs(spider, 8).
legs(B, 2) :- bird(B).

retract_static(X, T) :- retract((legs(X, 2) :- T)).
retract_static_wrap(R) :- retract_static(X, T), T = bird(X), R = X-T.
retract_all_bodies(Result) :-
    findall([X, Y, Z], retract((legs(X, Y) :- Z)), Result).

clause_static(B) :- clause(legs(_, 4), B).
clause_dynamic(B) :- clause(legs(_, 6), B).
"""


@pytest.fixture
def mod(tmp_path, monkeypatch):
    return _load(tmp_path, monkeypatch, _SRC)


def test_retract_body_calling_static_predicate_succeeds(mod):
    """retract_test3 (Ciao/Ulrich): the clause ``legs(B, 2) :- bird(B)`` is
    retracted and the pattern binds, though its body calls the STATIC
    ``bird/1`` -- it must not raise permission_error(access,
    private_procedure, legs/2)."""
    got = _answers(mod, "retract_static_wrap", limit=2)
    assert len(got) == 1
    # R = X-T with T = bird(X): the two sides of '-' name the same variable.
    left, right = got[0].split("-", 1)
    assert right == f"bird({left})"


def test_retract_all_bodies_regardless_of_callee(mod):
    """retract_test4 (Ciao/Ulrich): retracting every clause of legs/2 and
    collecting (Head-args, Body) must see all four -- the two whose body
    calls a STATIC predicate (animal/1, bird/1), the one calling the
    DYNAMIC p_insect/1, and the plain fact -- identically."""
    r = Var()
    got = _answers(mod, "retract_all_bodies", limit=1)
    assert len(got) == 1
    # Order follows the clause list; bird/1's clause is last in the source.
    assert got[0] == (
        "[[_1,4,animal(_1)],[_2,6,p_insect(_2)],[spider,8,true],"
        "[_3,2,bird(_3)]]"
    )


def test_clause_2_shares_the_fix(mod):
    """clause/2 shares clause_ops.clause_terms with retract/1: the same
    construction powers both, so the same STATIC-callee body must answer
    here too, not raise."""
    assert _answers(mod, "clause_static") == ["animal(_)"]
    assert _answers(mod, "clause_dynamic") == ["p_insect(_)"]


def test_static_callee_is_never_actually_invoked(tmp_path, monkeypatch):
    """The fix must read the body back as a TERM, not run it: a predicate
    the retracted clause's body calls must see no call at all -- no
    increment of a counter it would otherwise bump."""
    src = """
    :- dynamic(counter/1).
    counter(0).
    bump :- retract(counter(N)), N1 is N + 1, assertz(counter(N1)).
    watched(_) :- bump, fail.
    :- dynamic(p/2).
    p(A, 4) :- watched(A).
    run(B) :- retract((p(_, 4) :- B)).
    """
    mod = _load(tmp_path, monkeypatch, src)
    got = _answers(mod, "run", limit=1)
    assert got == ["watched(_)"]
    assert _answers(mod, "counter", limit=1) == ["0"]


def test_control_construct_refusal_still_applies(tmp_path, monkeypatch):
    """The pre-existing refusals this session's earlier fixes added must
    not regress: retracting a control-construct head is still
    permission_error(modify, static_procedure, ...)."""
    src = "run(B) :- retract(((a, b) :- true))."
    mod = _load(tmp_path, monkeypatch, src)
    term = _raises(mod, "run")
    assert term[0] == "error"
    assert term[1][:3] == ("permission_error", "modify", "static_procedure")


def test_dcg_rule_functor_still_refused_on_retract(tmp_path, monkeypatch):
    """And the ``(-->)/2`` grammar-rule refusal from this session's earlier
    commits (da0ffcd9/cb76ec73) must not regress either."""
    src = "run(B) :- retract((a --> b))."
    mod = _load(tmp_path, monkeypatch, src)
    term = _raises(mod, "run")
    assert term[0] == "error"
    assert term[1][:3] == ("permission_error", "modify", "static_procedure")
    assert term[1][3] == ("/", "-->", 2)
