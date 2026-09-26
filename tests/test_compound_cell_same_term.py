"""A ``Compound`` with an atom functor and arity >= 1 IS the cell ``(f, *args)``.

Operator ruling 2026-09-26: ``Compound`` is retired in favour of cells before
1.0, and ISO has ONE term ``f(1, 2)`` (13211-1 §7.1.5, §7.2).  Before this fix
the two spellings disagreed across the three identity relations::

    compare(O, Compound('f', (1, 2)), ('f', 1, 2))   O = '='
    ==(Compound f(1,2), ('f', 1, 2))                 fails
    =(Compound f(1,2), ('f', 1, 2))                  fails
    sort([Compound f(1,2), ('f', 1, 2)], L)          ONE element

which breaks ISO §8.4.2 (``compare(=, X, Y)`` iff ``X == Y``) and made sort/2
silently drop a term that ``==`` called different.

A ``Compound`` with NO cell equivalent -- a Var or non-atom functor, or arity
0 (``foo()``) -- is not an ISO term.  It stays DISTINCT from every cell in all
three relations, and compare/3 gives it a deterministic place:

* arity 0 keys in the compound band at arity 0 (after every atom, before
  every arity>=1 compound);
* a Var or non-atom functor keys AFTER every atom-named compound and every
  tuple-data cell of the same arity, ordered among themselves by the standard
  order of the functor (so two Var functors order by the Vars).
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, walk, deref, unify, \
    unify_with_occurs_check
from clausal.terms import Compound, compound_as_cell
import clausal.logic.constraints as CS
import clausal.logic.tabling as TB
from clausal.logic.builtins._helpers import _standard_order_key

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def C(f, *a):
    return Compound(f, tuple(a))


@pytest.fixture(scope="module")
def M(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("ccst")
    p = d / "ccst_mod.clausal"
    p.write_text(textwrap.dedent("""
        -module(ccst_mod, [tab(X, Y), sset(Xs, L)])
        -table(tab/2)
        tab(X, X),
        mem(X, [X, *_]),
        mem(X, [_, *T]) <- mem(X, T)
        sset(Xs, L) <- setof(X, mem(X, Xs), L)
    """).lstrip())
    sys.path.insert(0, str(d))
    try:
        mod = _load_module("ccst_mod", str(p))
    finally:
        sys.path.remove(str(d))
    return mod.__dict__["$module"]


def _q(M, name, *args, out=None):
    return [walk(out) if out is not None else True
            for _ in call(name, *args, module=M)]


def _cmp(M, a, b):
    O = Var()
    got = _q(M, "compare", O, a, b, out=O)
    assert len(got) == 1, got
    return got[0]


# ── the four-line repro, both argument orders ─────────────────────────────

CF12, CELL12 = C("f", 1, 2), ("f", 1, 2)


@pytest.mark.parametrize("a,b", [(CF12, CELL12), (CELL12, CF12)],
                         ids=["compound,cell", "cell,compound"])
class TestSameTerm:

    def test_compare_eq(self, M, a, b):
        assert _cmp(M, a, b) == "="

    def test_identical(self, M, a, b):
        assert _q(M, "==", a, b) == [True]
        assert _q(M, "\\==", a, b) == []

    def test_unify(self, M, a, b):
        assert _q(M, "=", a, b) == [True]

    def test_dif_fails(self, M, a, b):
        assert _q(M, "dif", a, b) == []

    def test_occurs_check_unify(self, a, b):
        assert unify_with_occurs_check(a, b, Trail())

    def test_tabling_key(self, a, b):
        assert TB._normalize_for_key(a) == TB._normalize_for_key(b)
        assert TB._normalize_for_key_py(a) == TB._normalize_for_key_py(b)


def test_sort_dedups_to_one_and_msort_keeps_both(M):
    L = Var()
    [out] = _q(M, "sort", [CF12, CELL12], L, out=L)
    assert len(out) == 1
    [out] = _q(M, "msort", [CF12, CELL12], L, out=L)
    assert len(out) == 2
    # interleaved with a genuinely different term, still one per term
    [out] = _q(M, "sort", [CELL12, ("f", 1, 3), CF12, C("f", 1, 3)], L, out=L)
    assert len(out) == 2


def test_setof_collapses_the_two_spellings(M):
    L = Var()
    [out] = _q(M, "sset", [CF12, CELL12], L, out=L)
    assert len(out) == 1, out
    [out] = _q(M, "sset", [("g", CF12), C("g", CELL12), ("g", CELL12)], L, out=L)
    assert len(out) == 1, out


def test_different_args_stay_different(M):
    assert _q(M, "=", C("f", 1, 2), ("f", 1, 3)) == []
    assert _q(M, "==", C("f", 1, 2), ("g", 1, 2)) == []
    assert _q(M, "=", C("f", 1), ("f", 1, 2)) == []
    assert _cmp(M, C("f", 1, 2), ("f", 1, 3)) == "<"
    assert _cmp(M, ("f", 1, 3), C("f", 1, 2)) == ">"


# ── partial terms and nesting ─────────────────────────────────────────────

def test_partial_terms_bind_argumentwise_both_directions(M):
    X, Y = Var(), Var()
    t = Trail()
    assert unify(C("f", X, 2), ("f", 1, Y), t)
    assert deref(X) == 1 and deref(Y) == 2
    X, Y = Var(), Var()
    t = Trail()
    assert unify(("f", X, 2), C("f", 1, Y), t)
    assert deref(X) == 1 and deref(Y) == 2


def test_partial_term_not_identical_until_bound(M):
    X = Var()
    assert _q(M, "==", C("f", X), ("f", X)) == [True]
    assert _q(M, "==", C("f", X), ("f", Var())) == []


@pytest.mark.parametrize("a,b", [
    (("g", C("f", 1)), C("g", ("f", 1))),
    (C("g", ("f", 1)), ("g", C("f", 1))),
    ([C("f", 1), ("h", C("k", 2))], [("f", 1), C("h", ("k", 2))]),
], ids=["cell(Compound)~Compound(cell)", "reverse", "in-a-list"])
def test_nested_mixes(M, a, b):
    assert _q(M, "=", a, b) == [True]
    assert _q(M, "==", a, b) == [True]
    assert _cmp(M, a, b) == "="
    assert _q(M, "dif", a, b) == []
    assert TB._normalize_for_key(a) == TB._normalize_for_key(b)
    assert TB._normalize_for_key_py(a) == TB._normalize_for_key_py(b)


def test_nested_numeric_type_objection_still_holds(M):
    """``==`` keeps ISO's 1 vs 1.0 distinction across the two spellings."""
    assert _q(M, "==", C("f", 1), ("f", 1.0)) == []
    assert _q(M, "==", ("f", 1.0), C("f", 1)) == []


def test_bound_var_functor_is_the_cell(M):
    F = Var()
    unify(F, "f", Trail())
    assert _q(M, "=", Compound(F, (1, 2)), CELL12) == [True]
    assert _q(M, "==", Compound(F, (1, 2)), CELL12) == [True]
    assert _cmp(M, Compound(F, (1, 2)), CELL12) == "="


def test_occurs_check_sees_through_the_mixed_pair():
    X = Var()
    assert not unify_with_occurs_check(C("f", X), ("f", ("g", X)), Trail())
    X = Var()
    assert not unify_with_occurs_check(("f", X), C("f", C("g", X)), Trail())


# ── dif/2 across a later binding ──────────────────────────────────────────

@pytest.mark.parametrize("a_is_compound", [True, False])
def test_dif_fires_when_the_binding_makes_them_equal(a_is_compound):
    X = Var()
    a, b = (C("f", X), ("f", 1)) if a_is_compound else (("f", X), C("f", 1))
    t = Trail()
    assert CS.dif(a, b, t)
    assert not unify(X, 1, t)
    X = Var()
    a, b = (C("f", X), ("f", 1)) if a_is_compound else (("f", X), C("f", 1))
    t = Trail()
    assert CS.dif(a, b, t)
    assert unify(X, 2, t)


# ── tabling: one table for both spellings ─────────────────────────────────

def test_tabled_call_with_each_spelling_hits_one_table(M):
    def tables():
        return [k for k in M.db._table_store if k[0] == "tab"]
    before = len(tables())
    Y1, Y2 = Var(), Var()
    assert len(_q(M, "tab", C("tabcc", 1, 2), Y1, out=Y1)) == 1
    assert len(tables()) == before + 1   # positive control: the probe sees a table
    assert len(_q(M, "tab", ("tabcc", 1, 2), Y2, out=Y2)) == 1
    assert len(tables()) == before + 1, "the cell spelling opened a second table"
    # and the reverse order, on a fresh variant
    assert len(_q(M, "tab", ("tabcc", 3), Var())) == 1
    assert len(_q(M, "tab", C("tabcc", 3), Var())) == 1
    assert len(tables()) == before + 2


# ── Compounds with no cell equivalent ─────────────────────────────────────

V_F, W_F = Var(), Var()
NO_CELL = [
    ("arity0", Compound("foo", ()), ["foo", ("f", 1), ("foo", 1)]),
    ("var-functor", Compound(V_F, (1,)), [("()", 1), ("f", 1), (V_F, 1)]),
    ("int-functor", Compound(3, (1,)), [("()", 1), ("f", 1), (3, 1)]),
]


@pytest.mark.parametrize("label,c,others", NO_CELL, ids=[n[0] for n in NO_CELL])
def test_no_cell_equivalent_stays_distinct(M, label, c, others):
    assert compound_as_cell(c) is None
    for o in others:
        assert _q(M, "=", c, o) == [], (label, o)
        assert _q(M, "==", c, o) == [], (label, o)
        assert _cmp(M, c, o) != "=", (label, o)
        # antisymmetric
        assert {_cmp(M, c, o), _cmp(M, o, c)} == {"<", ">"}, (label, o)


def test_no_cell_equivalent_positions():
    k = _standard_order_key
    # arity 0: after every atom, before every arity>=1 compound
    assert k("zzz") < k(Compound("foo", ())) < k(("a", 1))
    # non-atom functor: after named compounds and tuple-data of the same arity
    for odd in (Compound(V_F, (1,)), Compound(3, (1,))):
        assert k(("zzz", 1)) < k(("()", 1)) < k(odd) < k(("a", 1, 2))
    # two different Var functors are different terms, and order consistently
    a, b = Compound(V_F, (1,)), Compound(W_F, (1,))
    assert k(a) != k(b)
    assert (k(a) < k(b)) != (k(b) < k(a))
    # identical odd compounds are still '='
    assert k(Compound(V_F, (1,))) == k(Compound(V_F, (1,)))
    assert k(Compound("foo", ())) == k(Compound("foo", ()))


def test_var_functor_compounds_are_distinct(M):
    a, b = Compound(V_F, (1,)), Compound(W_F, (1,))
    assert _q(M, "==", a, b) == []
    assert _cmp(M, a, b) != "="


# ── Python twin <-> C parity (the convention of
#    tests/audit_2026_07_05/test_05_constraints_core.py::TestPythonCParity) ──

PARITY_SNIPPET = """
import sys
if sys.argv[1] == "py":
    sys.modules['clausal.logic._constraints_dif'] = None
    sys.modules['clausal.logic._tabling_core'] = None
import clausal.logic.builtins  # registers Compound with the C term cache
import clausal.logic.constraints as C
import clausal.logic.tabling as TB
assert C._USE_C_DIF == (sys.argv[1] == "c")
from clausal.logic.variables import Var, Trail, unify
from clausal.terms import Compound as K
def s(x):  # print keys without Var identities
    return repr(x).replace(repr(TB._VAR), "VAR")
cases = [
    (K("f", (1, 2)), ("f", 1, 2)),
    (("f", 1, 2), K("f", (1, 2))),
    (("g", K("f", (1,))), K("g", (("f", 1),))),
    (K("foo", ()), "foo"),
    (K("f", (1,)), ("f", 1.0)),
]
for a, b in cases:
    print(C.reify_eq(a, b, Trail()), C.structural_eq(a, b),
          s(TB._normalize_for_key(a)) == s(TB._normalize_for_key(b)))
x = Var()
print(C.reify_eq(K("f", (x,)), ("f", 1), Trail()))
t = Trail(); x = Var()
print(C.dif(K("f", (x,)), ("f", 1), t), unify(x, 1, t))
t = Trail(); x = Var()
print(C.dif(("f", x), K("f", (1,)), t), unify(x, 2, t))
x = Var(); print(len(C._collect_free_vars([K("f", (x,)), ("f", x)])))
print(C._structural_unify_oc(K("f", (x,)), ("f", ("g", x)), Trail()))
print(s(TB._normalize_for_key(K("f", (1, [2])))))
print(s(TB._normalize_for_key(K("foo", ()))))
"""


def test_python_and_c_twins_agree(tmp_path):
    p = tmp_path / "parity.py"
    p.write_text(textwrap.dedent(PARITY_SNIPPET))
    env = dict(os.environ, PYTHONPATH=REPO)
    outs = {}
    for impl in ("c", "py"):
        r = subprocess.run([sys.executable, str(p), impl], capture_output=True,
                           text=True, timeout=120, env=env, cwd=REPO)
        assert r.returncode == 0, r.stderr[-800:]
        outs[impl] = r.stdout
    assert outs["c"] == outs["py"]
    # positive control: the matrix actually carries the answers we expect
    first = outs["c"].splitlines()[0]
    assert first == "True True True", outs["c"]
