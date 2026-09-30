"""copy_term/2, term_variables/2, ground/1, numbervars/3 and bagof/setof/
findall read through a PARTIAL list nested in a term, and copy_term/2
copies dif/2 constraints.

Two silent wrong answers (the ISO differential sweep, 2026-09-30):

* the C term walkers treated a partial list (``SegList`` with a variable
  tail), a partial string / byte string and a dict term as LEAVES below the
  top level: ``term_variables(f([A|T]), Vs)`` gave ``[]``,
  ``copy_term(f([A|T]), f([B|U]))`` left ``A == B``, ``ground(f([a|T]))``
  succeeded, and bagof/3's free-variable analysis and findall/3's
  per-solution copy -- the same walkers -- went wrong with them;
* copy_term/2 dropped a dif/2 constraint: ``dif(A, a), copy_term(A, B),
  B = a`` succeeded.

Every expected answer below is Scryer's for the same goal (the clean
Scryer build, 2026-09-30).
"""
from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var, Trail, deref, unify

PL = """\
t(w01, N, (copy_term([A, _B, A|_C], X), term_variables(X, Vs), length(Vs, N))).
t(w02, x, (copy_term(f([A|T]), f([B|U])), A == B)).
t(w03, x, (X = f([A|T]), term_variables(X, [P, Q]), P == A, Q == T)).
t(w04, N, (term_variables(f([A|T]), Vs), length(Vs, N))).
t(w05, N, (term_variables(g([[A|T]], x), Vs), length(Vs, N))).
t(w06, N, (term_variables(g(h([p, A|T]), [B|U]), Vs), length(Vs, N))).
t(w07, x, (copy_term(g([[A|T]]), g([[B|U]])), (A == B ; T == U))).
t(w08, L, bagof(X, member(X-Y, [1-[A|T], 2-[A|T]]), L)).
t(w09, N, (findall(L, bagof(X, member(X-[Y|T], [1-[a|T1], 2-[b|T2]]), L), Ls), length(Ls, N))).
t(w10, x, (setof(X, member(X, [f([A|T]), f([A|T])]), [f([P|Q])]), P \\== A)).
t(w11, x, (findall(X, member(X, [f([A|T])]), [f([P|Q])]), P \\== A, Q \\== T)).
t(w12, x, (copy_term(f([A|T], A), f(B, C)), B = [D|_], D == C)).
t(w22, N, (term_variables([A|T], Vs), length(Vs, N))).
t(w24, N, (term_variables(f([a, [b|T]]), Vs), length(Vs, N))).
t(w25, x, (copy_term(f([a, [b|T]]), f([_, [_|U]])), T == U)).
t(w26, N, (term_variables(f([A|T], [A|T]), Vs), length(Vs, N))).
t(w28, x, ground(f([a|T]))).
t(w29, x, ground([[a|T]])).
t(w30, x, (X = f([a|T]), T = [], ground(X))).
t(w32, N, (functor(X, '.', 2), term_variables(X, Vs), length(Vs, N))).
t(w33, x, (functor(X, '.', 2), copy_term(f(X), f(Y)), X = [P|_], Y = [Q|_], P \\== Q)).
t(w41, x, (copy_term([A, B, A|C], [P, Q, R|S]), P == R, P \\== A, Q \\== B, S \\== C, var(S))).
t(w42, x, (copy_term(f([A|T]), f([B|U])), T == U)).
t(w44, x, (findall(X, member(X, [f([A|T])]), [f([P|Q])], []), P \\== A, Q \\== T)).
t(w45, L, bagof(X, member(X-Y, [1-[a|T], 2-[a|T], 3-[a, T]]), L)).
t(w46, N, (findall(L, bagof(X, member(X-Y, [1-[a|T], 2-[a|T2], 3-[a, T]]), L), Ls), length(Ls, N))).
t(d15, x, (dif(A, a), copy_term(A, B), B = a)).
t(d16, x, (dif(A, a), copy_term(A, B), B = b)).
t(d17, x, (dif(A, a), copy_term(f(A), f(B)), A = a)).
t(d18, x, (dif(A, a), copy_term(A, B), A = b, B = a)).
t(d19, x, (dif(A, B0), copy_term(A-B0, C-D), C = D)).
t(d07, x, (dif(A, B0), copy_term(A, C), C = B0)).
t(d08, x, (dif(f(A, B0), f(a, b)), copy_term(A-B0, C-D), C = a, D = b)).
t(d21, x, (dif(f(A, B0), f(a, b)), copy_term(A-B0, C-D), C = a, D = c)).
t(d22, x, (dif(f(A, B0), f(a, b)), copy_term(A, C), C = a, B0 = b)).
t(d09, x, (dif(A, a), copy_term([x, [y|T], A], L), L = [_, _, a])).
t(d10, x, (dif(A, a), copy_term(A, B), dif(B, b), B = a)).
t(d12, x, (dif(A, a), findall(A, true, [B]), B = a)).
t(d13, x, (dif(A, a), bagof(A, true, [B]), B = a)).
t(d14, x, (dif(A, a), copy_term(A, B), A = a)).
t(d15b, x, (dif(A, a), copy_term(A, a))).
t(d16b, x, (dif(A, a), copy_term(f(A, A), f(B, C)), C = a)).
t(d17b, x, (dif(A, a), copy_term([A|T], [B|U]), B = a)).
t(d18b, x, (dif(A, a), copy_term(A, B), B = C, C = a)).
t(d19b, x, (dif(A, a), dif(A, b), copy_term(A, B), B = b)).
t(d20, x, (dif(A, a), copy_term(A, B), B = c, A = c)).
row(Id, L) :- t(Id, T, G), findall(T, G, L).
nv(L) :- findall(N-A-B-V, (numbervars(f([A|T], B), 0, N), (var(T), V = var ; nonvar(T), V = bound)), L).
nvw(L) :- findall(x, (X = g([A|T], B), numbervars(X, 0, _), writeq(X), nl), L).
"""

WANT = {
    "w01": [3], "w02": [], "w03": ["x"], "w04": [2], "w05": [2], "w06": [4],
    "w07": [], "w08": [[1, 2]], "w09": [2], "w10": [], "w11": ["x"],
    "w12": ["x"], "w22": [2], "w24": [1], "w25": [], "w26": [2],
    "w28": [], "w29": [], "w30": ["x"], "w32": [2], "w33": ["x"],
    "w41": ["x"], "w42": [], "w44": ["x"], "w45": [[3], [1, 2]], "w46": [3],
    "d15": [], "d16": ["x"], "d17": [], "d18": [], "d19": [], "d07": ["x"],
    "d08": [], "d21": ["x"], "d22": ["x"], "d09": [], "d10": [], "d12": ["x"],
    "d13": ["x"], "d14": [], "d15b": [], "d16b": [], "d17b": [], "d18b": [],
    "d19b": [], "d20": ["x"],
}


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("walkers")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    (d / "term_walkers_pl.pl").write_text(PL)
    sys.modules.pop("term_walkers_pl", None)
    importlib.invalidate_caches()
    try:
        m = importlib.import_module("term_walkers_pl")
        assert type(m.__loader__).__name__ == "NativePrologLoader"
        yield m
    finally:
        sys.modules.pop("term_walkers_pl", None)
        shutil.rmtree(d / "__pycache__", ignore_errors=True)
        mp.undo()


@pytest.mark.parametrize("row", sorted(WANT))
def test_matches_scryer(pl_mod, row):
    v = Var()
    got = [_deref_walk(v) for _ in solve(("row", row, v), pl_mod)]
    assert got == [WANT[row]]


def test_every_row_is_checked():
    import re
    ids = re.findall(r"^t\((\w+),", PL, re.M)
    assert ids and len(ids) == len(set(ids)) == len(WANT)
    assert set(ids) == set(WANT)


# ── the two walker implementations report the same attributed variables ──


@pytest.mark.parametrize("impl", ["c", "py"])
def test_copy_reports_attributed_variables(impl):
    from clausal.logic.builtins.inspection import _copy_term_py
    from clausal.logic.constraints import dif
    from clausal.terms import SegList, ConcreteSeg, VarSeg
    if impl == "c":
        c = pytest.importorskip("clausal.logic.variables._variables")
        copy = c._copy_term_impl
    else:
        copy = _copy_term_py
    a, b, t = Var(), Var(), Var()
    tr = Trail()
    assert dif(a, "x", tr)
    term = ("f", SegList([ConcreteSeg([b, a]), VarSeg(t)]), a)
    attvars: list = []
    copied = copy(term, {}, attvars)
    assert [orig for orig, _ in attvars] == [a]
    fresh = attvars[0][1]
    assert deref(copied[2]) is fresh and fresh is not a
    # Without the list, nothing is reported (findall/bagof copies).
    assert copy(term, {}) is not None


def test_numbervars_leaves_a_list_tail_unbound(pl_mod):
    """numbervars/3 cannot bind the T of [A|T] to '$VAR'(N): a list with a
    non-list tail has no representation, and every later walk of the term
    (writeq, the answer snapshot) would raise.  It numbers every other
    variable, and the numbered term still prints.  (ISO / Scryer number T
    too: N = 3.)"""
    v = Var()
    got = [_deref_walk(v) for _ in solve(("nv", v), pl_mod)]
    assert got == [[("-", ("-", ("-", 2, ("$VAR", 0)), ("$VAR", 1)), "var")]]
    w = Var()
    assert [_deref_walk(w) for _ in solve(("nvw", w), pl_mod)] == [["x"]]


def test_bagof_variant_key_over_partial_strings_and_bytes():
    """bagof/3 groups by the VARIANT key of its witness; a partial string /
    byte string hole in the witness gets a text / bytes marker (a list
    marker there was refused by the walk)."""
    from clausal.logic.compiler.globals_env import _variant_key
    from clausal.terms import SegList, SegString, SegBytes, ConcreteSeg, VarSeg
    def k(mk):
        return _variant_key(("f", mk(Var())))
    s1, s2 = (k(lambda v: SegString(["ab", VarSeg(v)])) for _ in range(2))
    b1, b2 = (k(lambda v: SegBytes([b"ab", VarSeg(v)])) for _ in range(2))
    l1 = k(lambda v: SegList([ConcreteSeg(["a"]), VarSeg(v)]))
    assert s1 == s2 and b1 == b2
    assert len({s1, b1, l1}) == 3
    # [a|T] keys apart from the proper list [a, X].
    assert l1 != _variant_key(("f", ["a", Var()]))
