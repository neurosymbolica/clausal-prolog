"""Three wrong-answer bugs in clause selection, all found while making a
``Compound`` and its cell one term (2026-09-26).  Each gave FEWER answers than
``=``/2 allows.

1. A cell argument whose slot holds a Var BOUND to a cell missed its indexed
   bucket: the bucket's ``match`` pattern saw the raw Var, not the cell.
   ``w3(('k', V))`` with ``V = f(2)`` answered 0 times.
2. A clause asserted at runtime with a STRUCTURED argument in a cell head
   (``assertz(dz(f(1)))``) never answered an unbound caller: the runtime
   assert path did not lower structured head arguments to body ``=`` as the
   compiler does, so the head kept a ``case ['f', x]`` pattern that an
   unbound Var cannot match.
3. First-argument indexing keyed a KEYWORD data head ``box(Lo=g(1), Hi=2)``
   as ``('box', 0)`` -- positional arguments only -- while a caller keys
   ``('box', 2)``, so an unbound second argument sent even a cell caller
   past the clause.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, walk, unify
from clausal.terms import Compound, Call, LoadName, Unify


SRC = """
-module(ixw, [w3(X), dz(X), kp(X, Y)])
-private([z, a, b, c, d, f(A), g(A), k(A), box(Lo, Hi)])
-dynamic(dz/1)
-dynamic(kp/2)
w3(k(f(1))),
w3(k(f(2))),
w3(k(g(1))),
w3(z),
dz(7),
kp(g(9), c),
kp(7, d),
kp(z, c),
"""


@pytest.fixture
def M(tmp_path):
    from clausal.import_hook import _load_module
    p = tmp_path / "ixw.clausal"
    p.write_text(textwrap.dedent(SRC).lstrip())
    sys.path.insert(0, str(tmp_path))
    try:
        mod = _load_module("ixw", str(p))
    finally:
        sys.path.remove(str(tmp_path))
    return mod.__dict__["$module"]


def _n(M, name, *args):
    return len(list(call(name, *args, module=M)))


def _bound(value):
    v = Var()
    assert unify(v, value, Trail())
    return v


# ── 1. a bound Var inside a cell caller ─────────────────────────────────────

@pytest.mark.compound_retirement_slice8
@pytest.mark.parametrize("arg", [
    ("k", ("f", 2)),                                       # control
    ("k", "BOUND_CELL"),
    ("k", "BOUND_COMPOUND"),
    ("k", "BOUND_VAR_FUNCTOR"),
    ("k", "BOUND_TWICE"),
    "BOUND_OUTER",
], ids=["control", "slot-var-to-cell", "slot-var-to-compound",
        "slot-var-functor-compound", "slot-var-chain", "whole-arg-var"])
def test_a_bound_var_in_a_cell_slot_reaches_the_bucket(M, arg):
    assert M.db.row("w3", 1).index_plans, "w3 must be indexed for this test"
    make = {
        "BOUND_CELL": lambda: _bound(("f", 2)),
        "BOUND_COMPOUND": lambda: _bound(Compound("f", (2,))),
        "BOUND_VAR_FUNCTOR": lambda: Compound(_bound("f"), (2,)),
        "BOUND_TWICE": lambda: _bound(_bound(("f", 2))),
    }
    if arg == "BOUND_OUTER":
        arg = _bound(("k", _bound(("f", 2))))
    elif isinstance(arg[1], str) and arg[1] in make:
        arg = (arg[0], make[arg[1]]())
    assert _n(M, "w3", arg) == 1


def test_a_bound_var_to_a_non_matching_cell_still_misses(M):
    assert _n(M, "w3", ("k", _bound(("f", 3)))) == 0
    assert _n(M, "w3", ("k", _bound(("h", 2)))) == 0


# ── 2. an asserted structured head, unbound caller ──────────────────────────

@pytest.mark.compound_retirement_slice8
def test_an_asserted_structured_head_answers_an_unbound_caller(M):
    for term in (("dz", ("f", 1)), ("dz", Compound("g", (1,))),
                 ("dz", ("k", ("f", Var()))), ("dz", [1, 2])):
        list(call("assertz", term, module=M))
    X = Var()
    got = [walk(X) for _ in call("dz", X, module=M)]
    assert len(got) == 5, got
    assert 7 in got and ("f", 1) in got and [1, 2] in got
    assert any(unify(g, ("g", 1), Trail()) for g in got)
    # input mode is unchanged
    assert _n(M, "dz", ("f", 1)) == 1
    assert _n(M, "dz", Compound("f", (1,))) == 1
    assert _n(M, "dz", ("f", 2)) == 0
    assert _n(M, "dz", ("k", ("f", 5))) == 1


def test_clause_2_gives_back_the_asserted_head(M):
    """The lowering is invisible to clause/2: body ``true``, head as written."""
    list(call("assertz", ("dz", ("f", 1)), module=M))
    B = Var()
    got = [walk(B) for _ in call("clause", ("dz", ("f", 1)), B, module=M)]
    assert len(got) == 1 and got[0] in (True, "true"), got


# ── 3. a keyword data head and first-argument indexing ──────────────────────

def _kw_box(lo, hi):
    from clausal.pythonic_ast.nodes import Keyword
    return Call(func=LoadName(name="box"), args=[], kwargs=[
        Keyword(name="Lo", value=lo), Keyword(name="Hi", value=hi)])


def _g(x):
    return Call(func=LoadName(name="g"), args=[x], kwargs=[])


def test_a_keyword_head_keys_by_its_full_arity():
    from clausal.logic.compiler.arg_index import _arg_to_index_key, _runtime_arg_key
    assert _arg_to_index_key(_kw_box(_g(1), 2)) == ("box", 2)
    assert _arg_to_index_key(_kw_box(_g(1), 2)) == _runtime_arg_key(("box", ("g", 1), 2))


@pytest.mark.compound_retirement_slice8
def test_a_keyword_head_answers_with_an_unbound_second_argument(M):
    """Keyword data terms are refused in source since 2026-09-19, so the
    clause is added through the database API (the shape a programmatic
    producer writes)."""
    from clausal.logic.database import Clause
    V = Var()
    M.db.assertz(Clause(head=("kp", V, "a"),
                        body=[Unify(left=V, right=_kw_box(_g(1), 2))], hoisted=1))
    for arg in (("box", ("g", 1), 2), Compound("box", (("g", 1), 2)),
                ("box", Compound("g", (1,)), 2)):
        Y = Var()
        assert [walk(Y) for _ in call("kp", arg, Y, module=M)] == ["a"], arg
    Y = Var()
    assert [walk(Y) for _ in call("kp", ("box", ("g", 2), 2), Y, module=M)] == []
    # positive control: the answers above came through the first-arg index
    assert M.db.row("kp", 2).index_plans, "kp must be indexed for this test"
