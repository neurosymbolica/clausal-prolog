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
from clausal.terms import Compound, DictTerm, compound_as_cell
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


# ── clause-head matching and first-argument indexing (roborev 201 MEDIUM) ──
#
# The argument-index bucket path LIFTS a hoisted head ``Unify`` back into a
# ``match`` pattern.  Before the fix that pattern was ``case ['f', x]`` for a
# cell head and ``case $Compound(functor='f', ...)`` for a Compound head, so a
# caller in the OTHER spelling missed a clause ``=`` says it matches.

HEAD_SRC = """
-module(ccst_head, [p(X), w(X), w3(X), m(X, Y), j(X, Y), t(X), dz(X)])
-private([a, b, z, f(A), g(A), k(A)])
-dynamic(dz/1)
p(f(X)) <- (X == 1)
w(f(1)),
w(f(2)),
w(g(1)),
w(1),
w(a),
w3(k(f(1))),
w3(k(f(2))),
w3(k(g(1))),
w3(z),
m([f(X), *_], X),
m([g(X), *_], X),
j(f(1), a),
j(g(1), a),
j(f(2), b),
t([f(X), *_]) <- (X == 1)
"""


@pytest.fixture(scope="module")
def H(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("ccst_head")
    p = d / "ccst_head.clausal"
    p.write_text(textwrap.dedent(HEAD_SRC).lstrip())
    sys.path.insert(0, str(d))
    try:
        mod = _load_module("ccst_head", str(p))
    finally:
        sys.path.remove(str(d))
    return mod.__dict__["$module"]


def _n(M, name, *args):
    return len(list(call(name, *args, module=M)))


@pytest.mark.parametrize("name,args", [
    ("p", (C("f", 1),)),
    ("w", (C("f", 2),)),                       # indexed, 2-clause bucket
    ("w", (C("g", 1),)),                       # indexed, 1-clause bucket
    ("w3", (("k", C("f", 2)),)),               # nested, inner Compound
    ("w3", (C("k", ("f", 2)),)),               # nested, outer Compound
    ("w3", (C("k", C("f", 2)),)),              # nested, both
    ("m", ([C("g", 1), 2], Var())),            # list dispatch
    ("j", (C("f", 2), "b")),                   # two indexed positions
    ("t", ([C("f", 1), 3],)),                  # list-dispatch head rebuild
], ids=["rule", "idx-bucket2", "idx-bucket1", "nested-inner", "nested-outer",
        "nested-both", "list-dispatch", "joint", "list-head"])
def test_a_compound_caller_matches_a_cell_head(H, name, args):
    assert _n(H, name, *args) == 1


def test_a_partial_compound_caller_enumerates_the_bucket(H):
    assert _n(H, "w", ("f", Var())) == 2
    assert _n(H, "w", C("f", Var())) == 2


def test_a_bound_var_functor_compound_caller_matches(H):
    F = Var()
    unify(F, "f", Trail())
    assert _n(H, "w", Compound(F, (2,))) == 1


def test_no_cell_compound_callers_still_miss(H):
    assert _n(H, "w", Compound("a", ())) == 0
    assert _n(H, "w", Compound(Var(), (1,))) == 0


def test_a_compound_head_matches_a_cell_caller_and_the_reverse(H):
    """The reverse direction: a clause HEAD holding a Compound (asserted from
    Python), called with the cell, and a cell head called with a Compound."""
    list(call("assertz", ("dz", C("f", 1)), module=H))
    list(call("assertz", ("dz", C("g", 1)), module=H))
    list(call("assertz", ("dz", ("f", 2)), module=H))
    assert _n(H, "dz", ("f", 1)) == 1
    assert _n(H, "dz", ("g", 1)) == 1
    assert _n(H, "dz", C("f", 2)) == 1
    assert _n(H, "dz", C("g", 1)) == 1
    assert _n(H, "dz", ("f", 3)) == 0


def test_runtime_index_key_is_the_cell_key():
    from clausal.logic.compiler.arg_index import _runtime_arg_key, _INDEX_VAR
    assert _runtime_arg_key(C("f", 1)) == _runtime_arg_key(("f", 1)) == ("f", 1)
    # the deep-ground gate applies to the Compound exactly as to its cell
    assert _runtime_arg_key(C("f", Var())) is _INDEX_VAR
    assert _runtime_arg_key(("f", Var())) is _INDEX_VAR


# ── '$chars' is not a cell functor (roborev 201 Low (a)) ──────────────────

def test_a_chars_compound_is_not_the_carrier(M):
    """``('$chars', s)`` is the chars CARRIER (text, equal to its char list),
    so ``Compound('$chars', (s,))`` must not become it: ``=`` would stop being
    transitive (Compound = carrier = char list, Compound != char list)."""
    from clausal.logic.cells import chars
    k, text, charlist = Compound("$chars", ("abc",)), chars("abc"), ["a", "b", "c"]
    assert compound_as_cell(k) is None
    assert unify(text, charlist, Trail())            # control: the carrier IS text
    for other in (text, charlist):
        assert not unify(k, other, Trail())
        assert _q(M, "==", k, other) == []
        assert _cmp(M, k, other) != "="
        assert TB._normalize_for_key(k) != TB._normalize_for_key(other)
        assert TB._normalize_for_key_py(k) != TB._normalize_for_key_py(other)
    # an ordinary '$'-functor is NOT excluded: '$VAR'(1) is an ISO term
    assert unify(C("$VAR", 1), ("$VAR", 1), Trail())


def test_a_tuple_tag_compound_is_not_tuple_data(M):
    """The cell ``('()', a, b)`` is tuple DATA (``TUPLE_TAG``), keyed and
    unified as data -- a ``Compound('()', ...)`` stays an ordinary compound."""
    from clausal.logic.cells import TUPLE_TAG
    k, data = Compound(TUPLE_TAG, (1, 2)), (TUPLE_TAG, 1, 2)
    assert compound_as_cell(k) is None
    assert not unify(k, data, Trail())
    assert _q(M, "==", k, data) == []
    assert _cmp(M, k, data) != "="
    assert TB._normalize_for_key(k) != TB._normalize_for_key(data)
    assert TB._normalize_for_key_py(k) != TB._normalize_for_key_py(data)


# ── subject normalisation (roborev 203): linear, and the sinks still work ──
#
# Head patterns are cell-only; the compiled ``match`` subject goes through
# ``$as_cells`` (``terms.as_cells_for_match``, C twin in ``_variables.c``) at
# the positions and depth where a cell pattern exists.  The previous
# or-pattern doubled every level: 45,046 pattern nodes at depth 12.

SINK_SRC = """
-module(ccst_sink, [rv(X), nl2(X, Y), dd(X, Y), deep(X)])
-private([z, w, f(A), h(A, B), g(A)])
rv(h(X, X)),
rv(g(1)),
rv(g(2)),
rv(3),
nl2(f([1, X]), X),
nl2(f("ab"), z),
nl2(g(1), w),
nl2(4, w),
dd(f({"a": X}), X),
dd(g(2), w),
dd(g(3), w),
dd(5, w),
deep(f(f(f(f(f(f(f(f(f(f(f(f(1))))))))))))),
deep(f(f(f(f(f(f(f(f(f(f(f(f(2))))))))))))),
deep(g(1)),
deep(0),
"""


@pytest.fixture(scope="module")
def SK(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("ccst_sink")
    p = d / "ccst_sink.clausal"
    p.write_text(textwrap.dedent(SINK_SRC).lstrip())
    sys.path.insert(0, str(d))
    try:
        mod = _load_module("ccst_sink", str(p))
    finally:
        sys.path.remove(str(d))
    M = mod.__dict__["$module"]
    for name, arity in (("rv", 1), ("nl2", 2), ("dd", 2), ("deep", 1)):
        assert M.db.row(name, arity).index_plans, f"{name} is not indexed"
    return M


def _answers(M, name, arg):
    Y = Var()
    args = (arg,) if name in ("rv", "deep") else (arg, Y)
    return [walk(Y) for _ in call(name, *args, module=M)]


def _nest(d, leaf, mk):
    t = leaf
    for _ in range(d):
        t = mk("f", t)
    return t


@pytest.mark.parametrize("name,cell,expected", [
    ("rv", ("h", 1, 1), 1),                         # repeated variable
    ("rv", ("h", 1, 2), 0),
    ("nl2", ("f", [1, 5]), [5]),                    # list literal in a cell
    ("nl2", ("f", [2, 5]), []),
    ("nl2", ("f", "ab"), ["z"]),                    # str (atom) literal
    ("dd", ("f", DictTerm({"a": 3})), [3]),         # dict literal
], ids=["repeated-var", "repeated-var-miss", "list", "list-miss", "str", "dict"])
def test_head_sinks_answer_alike_for_both_spellings(SK, name, cell, expected):
    comp = Compound(cell[0], tuple(cell[1:]))
    assert unify(comp, cell, Trail())                # the two ARE one term
    got_cell, got_comp = _answers(SK, name, cell), _answers(SK, name, comp)
    if isinstance(expected, int):
        assert len(got_cell) == len(got_comp) == expected
    else:
        assert got_cell == got_comp == expected


def test_a_deep_compound_caller_matches_a_deep_cell_head(SK):
    for mk in (lambda f, a: (f, a), lambda f, a: Compound(f, (a,))):
        assert len(_answers(SK, "deep", _nest(12, 2, mk))) == 1
        assert len(_answers(SK, "deep", _nest(12, 3, mk))) == 0
    # a mixed spelling, Compound only in the middle
    mixed = ("f", ("f", Compound("f", (_nest(9, 1, lambda f, a: (f, a)),))))
    assert len(_answers(SK, "deep", mixed)) == 1


def test_head_patterns_are_linear_in_depth():
    from clausal.logic.compiler.head_match import head_to_match_pattern
    import ast as _ast
    sizes = []
    for d in (4, 8, 12):
        pat = head_to_match_pattern(_nest(d, 1, lambda f, a: (f, a)), {}, [], [],
                                    None, globals_={})
        sizes.append(sum(1 for _ in _ast.walk(pat)))
    assert sizes[2] - sizes[1] == sizes[1] - sizes[0], sizes


def test_subject_normaliser_twins_agree():
    from clausal.logic.variables._variables import as_cells_for_match as c_twin
    from clausal.terms import as_cells_for_match as py_twin
    F = Var()
    unify(F, "f", Trail())
    bound = Var()
    unify(bound, C("g", 1), Trail())
    plain = ("k", ("f", 2), 9)
    cases = [
        (C("f", 1), 1), (("k", C("f", 2)), 1), (("k", C("f", 2)), 2),
        (C("k", C("f", C("g", 1))), 3), (Compound(F, (2,)), 1), (("k", bound), 2),
        (plain, 3), (Compound("$chars", ("a",)), 2), (Compound("()", (1,)), 1),
        (Compound("a", ()), 1), (Var(), 2), (7, 3),
        # below a class pattern: a no-cell Compound's args, an instance's fields
        (Compound(3, (C("g", 1),)), 2), (Compound(3, (C("g", 1),)), 1),
        (_Box(C("g", 1)), 2), (_Box(("g", 1)), 2), (("k", _Box(C("g", 1))), 3),
    ]
    for term, depth in cases:
        a, b = c_twin(term, depth), py_twin(term, depth)
        assert type(a) is type(b) and a == b, (term, depth, a, b)
    # nothing copied when there is nothing to convert
    assert c_twin(plain, 3) is plain and py_twin(plain, 3) is plain
    # depth bounds the walk: a Compound below it is left alone
    assert c_twin(("k", C("f", 2)), 1) == ("k", C("f", 2))


# ── depth read off the BUILT pattern (roborev 204) ─────────────────────────
#
# The normaliser's depth used to come from a parallel analysis of the head
# term: it missed keyword slots of a data reference, stopped at class
# patterns (a Compound with no cell, a term instance), and was capped at 64.
# It is now read off the final match AST (``head_match.pattern_structure_
# depth`` / ``finalize_subject_depths``), so the two agree by construction.

from dataclasses import dataclass as _dataclass
from typing import Any as _Any


@_dataclass
class _Box:
    a: _Any


def _run_fn(fn, *args):
    from tests.test_compiler_optimizations import _run_trampoline
    return _run_trampoline(fn, *args)


def _compile(functor, clauses, globals_):
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.database import Database
    return compile_predicate_trampoline(functor, 2, clauses, Database(),
                                        globals_=globals_)


@pytest.fixture(scope="module")
def KW(tmp_path_factory):
    """A module declaring the data functors ``box/2`` and ``g/1``."""
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("ccst_kw")
    p = d / "ccst_kw.clausal"
    p.write_text("-module(ccst_kw, [])\n-private([box(Lo, Hi), g(A)])\n")
    sys.path.insert(0, str(d))
    try:
        mod = _load_module("ccst_kw", str(p))
    finally:
        sys.path.remove(str(d))
    return dict(mod.__dict__)


def _kw_box(lo, hi):
    from clausal.terms import Call, LoadName
    from clausal.pythonic_ast.nodes import Keyword
    return Call(func=LoadName(name="box"), args=[], kwargs=[
        Keyword(name="Lo", value=lo), Keyword(name="Hi", value=hi)])


def _g(x):
    from clausal.terms import Call, LoadName
    return Call(func=LoadName(name="g"), args=[x], kwargs=[])


def test_a_keyword_data_head_counts_its_keyword_slots(KW):
    """Keyword data terms are refused in source since 2026-09-19, so this
    head is built programmatically.  Its keyword slot holds a nested cell
    pattern: the depth must be 2 (the old head analysis said 0)."""
    from clausal.logic.compiler.head_match import (
        head_to_match_pattern, pattern_structure_depth)
    pat = head_to_match_pattern(_kw_box(_g(Var()), 2), {}, [], [], None,
                                globals_=KW)
    assert pattern_structure_depth(pat) == 2


def test_a_keyword_data_head_matches_the_compound_spelling(KW):
    from clausal.logic.database import Clause
    clauses = [Clause(head=("kq", _kw_box(_g(1), 2), "a"), body=[]),
               Clause(head=("kq", _kw_box(_g(2), 3), "b"), body=[]),
               Clause(head=("kq", ("g", 9), "c"), body=[]),
               Clause(head=("kq", 7, "d"), body=[])]
    fn = _compile("kq", clauses, KW)
    # The second argument is bound so the call reaches the keyword clause:
    # with it unbound, first-argument indexing keys the keyword head as
    # ('box', 0) (it counts positional args only) -- a separate, older gap.
    for arg in (("box", ("g", 1), 2), C("box", ("g", 1), 2),
                ("box", C("g", 1), 2), C("box", C("g", 1), 2)):
        assert len(_run_fn(fn, arg, "a")) == 1, arg


def test_a_cell_pattern_under_a_class_pattern_meets_a_compound():
    """A no-cell Compound head (functor 3) and a term-instance head each hold
    a cell pattern below their class pattern."""
    from clausal.logic.database import Clause
    X1, X2 = Var(), Var()
    clauses = [Clause(head=Compound("cq", (Compound(3, (("g", X1),)), X1)), body=[]),
               Clause(head=Compound("cq", (_Box(("g", X2)), X2)), body=[]),
               Clause(head=Compound("cq", (("h", 1), 0)), body=[]),
               Clause(head=Compound("cq", (9, 0)), body=[])]
    fn = _compile("cq", clauses, {"_Box": _Box})
    for arg, want in ((Compound(3, (("g", 5),)), 5),
                      (Compound(3, (C("g", 5),)), 5),
                      (_Box(("g", 6)), 6),
                      (_Box(C("g", 6)), 6)):
        Y = Var()
        assert [r[0] for r in _run_fn(fn, arg, Y)] == [want], arg


def _nest_s(d, mk):
    t = "z"
    for _ in range(d):
        t = mk(t)
    return t


def test_a_pattern_deeper_than_64_meets_an_all_compound_caller():
    """No cap: an 80-deep head pattern normalises all 80 levels."""
    from clausal.logic.database import Clause
    cell = lambda t: ("s", t)
    clauses = [Clause(head=Compound("dq", (_nest_s(80, cell), "a")), body=[]),
               Clause(head=Compound("dq", (_nest_s(79, cell), "b")), body=[]),
               Clause(head=Compound("dq", ("z", "c")), body=[]),
               Clause(head=Compound("dq", (7, "d")), body=[])]
    fn = _compile("dq", clauses, {})
    for mk in (cell, lambda t: Compound("s", (t,))):
        Y = Var()
        assert [r[0] for r in _run_fn(fn, _nest_s(80, mk), Y)] == ["a"]


def test_an_80_deep_lifted_source_fact_meets_an_all_compound_caller(tmp_path):
    from clausal.import_hook import _load_module
    d = 80
    src = ("-module(ccst_nat, [nat(X, Y)])\n-private([z, s(A), a, b, c, d])\n"
           f"nat({'s(' * d}z{')' * d}, a),\n"
           f"nat({'s(' * (d - 1)}z{')' * (d - 1)}, b),\n"
           "nat(z, c),\nnat(7, d),\n")
    p = tmp_path / "ccst_nat.clausal"
    p.write_text(src)
    sys.path.insert(0, str(tmp_path))
    try:
        M = _load_module("ccst_nat", str(p)).__dict__["$module"]
    finally:
        sys.path.remove(str(tmp_path))
    assert M.db.row("nat", 2).index_plans
    for mk in (lambda t: ("s", t), lambda t: Compound("s", (t,))):
        Y = Var()
        assert [walk(Y) for _ in call("nat", _nest_s(d, mk), Y, module=M)] == ["a"]
