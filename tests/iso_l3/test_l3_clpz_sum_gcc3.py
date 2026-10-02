"""clpz's sum/3 and global_cardinality/3 on the native ``.pl`` front end.

* ``sum(Vs, Op, Value)`` resolves ONLY in a ``.pl`` file that imports
  library(clpz): it comes from ``clausal.stdlib.clpz_sum`` through the
  library-override table, never as a global builtin (a global ``sum``
  would shadow Python's ``sum`` inside a seam ``++`` escape).
* ``global_cardinality(Vs, Pairs, Options)`` with Scryer's options
  ``consistency(value)`` and ``cost(Cost, Matrix)`` (/2 is untouched).

Every answer and error below is Scryer's clpz for the same goal (the clean
build at ``SCRYER``, measured 2026-09-30); ``test_the_tables_are_scryers``
re-measures them.
"""
from __future__ import annotations

import os
import subprocess

import pytest
from tests._suffix import SEAM

SCRYER = "/workspace/scryer-prolog-clpq/target/release/scryer-prolog"

SRC = """\
:- use_module(library(clpz)).
:- use_module(library(lists)).
s1(R) :- findall(A-B, (sum([A,B],#=,5), A in 0..5, B in 0..5, label([A,B])), R).
s2(R) :- findall([A,B], (X = 3, sum([A,B],#<,X+1), [A,B] ins 0..3, label([A,B])), R).
s3(R) :- findall([A,B], (sum([A,B],#>=,4), [A,B] ins 0..2, label([A,B])), R).
s4(R) :- findall([A,B], (sum([A,B],#\\=,2), [A,B] ins 0..1, label([A,B])), R).
s5(R) :- findall([A,B], (sum([A,B],#=<,1), [A,B] ins 0..1, label([A,B])), R).
s6(R) :- findall(X, sum([1,2],#=,X), R).
s7(R) :- findall(X, sum([],#=,X), R).
s8(R) :- findall(x, sum([],#<,0), R).
s9(R) :- findall(Z, (sum([X,Y],#=,Z+1), X=1, Y=2), R).
s10(R) :- findall([A,B], (sum([A,B],#>,2*B), [A,B] ins 0..2, label([A,B])), R).
se(R) :- findall(E, (member(G, [sum(foo,#=,3), sum([a],foo,3), sum([_],foo,foo), sum([_],#=,foo),
         sum([1|_],#=,3), sum([_],_,foo), sum([1.0],#=,1), sum(_,#=,3), sum([_],=,3), sum([_],#=,1.5)]),
         catch((G, E = none), error(E, _), true)), R).
g1(R) :- findall(L, (L = [A,B,C], L ins 1..2, global_cardinality(L, [1-2, 2-1], []), label(L)), R).
g2(R) :- findall(L, (L = [A,B,C], global_cardinality(L, [1-2, 2-1], [consistency(value)]), label(L)), R).
g3(R) :- findall(L-Cost, (L = [A,B], global_cardinality(L, [1-1, 2-1], [cost(Cost, [[3,5],[4,7]])]), label(L)), R).
g4(R) :- findall(Cost, (L = [A,B], global_cardinality(L, [1-1, 2-1], [cost(Cost, [[3,5],[4,7]])]), Cost #< 10, label(L)), R).
g5(R) :- findall(L-N, (L = [A,B], global_cardinality(L, [1-N, 2-1], [foo]), label([A,B,N])), R).
g6(R) :- findall(L-C, (L=[A,B], global_cardinality(L, [5-1, 7-1], [cost(C, [[1,2],[3,4]]), consistency(value)]), label(L)), R).
g7(R) :- findall(x, global_cardinality([_,_], [1-_], [cost(_, [[1]])]), R).
g8(R) :- findall(C, global_cardinality([_], [1-_], [cost(C, [[1,2]])]), R).
g9(R) :- findall(C, (global_cardinality([X], [1-_], [cost(C, [[9]])]), var(X)), R).
ge(R) :- findall(E, (member(G, [global_cardinality([_], [1-_, 1-_], []), global_cardinality([_], [1-_], foo),
         global_cardinality([_], [1-_], _), global_cardinality([_], [1-_], [_]), global_cardinality([_], [1-_], [cost(_, [[a]])]),
         global_cardinality([_], [1-_], [cost(_, foo)]), global_cardinality([_], [1-_], [cost(_, _)]),
         global_cardinality(foo, [1-_], []), global_cardinality([_], [1-_|_], []),
         global_cardinality([_], [1-_], [cost(_, [[1]]) | _]), global_cardinality([a], [1-_], []),
         global_cardinality([_], [1-a], []), global_cardinality([_], [a-1], []), global_cardinality([_], [x], [])]),
         catch((G, E = none), error(E, _), true)), R).
"""

#: Scryer's writeq of each row's findall.
SCRYER_ROWS = {
    "s1": "[0-5,1-4,2-3,3-2,4-1,5-0]",
    "s2": "[[0,0],[0,1],[0,2],[0,3],[1,0],[1,1],[1,2],[2,0],[2,1],[3,0]]",
    "s3": "[[2,2]]",
    "s4": "[[0,0],[0,1],[1,0]]",
    "s5": "[[0,0],[0,1],[1,0]]",
    "s6": "[3]",
    "s7": "[0]",
    "s8": "[]",
    "s9": "[2]",
    "s10": "[[1,0],[2,0],[2,1]]",
    "se": "[type_error(list,foo),type_error(integer,a),"
          "domain_error(scalar_product_relation,foo),"
          "domain_error(clpz_expression,foo),instantiation_error,"
          "instantiation_error,type_error(integer,1.0),instantiation_error,"
          "domain_error(scalar_product_relation,=),"
          "domain_error(clpz_expression,1.5)]",
    "g1": "[[1,1,2],[1,2,1],[2,1,1]]",
    "g2": "[[1,1,2],[1,2,1],[2,1,1]]",
    "g3": "[[1,2]-10,[2,1]-9]",
    "g4": "[9]",
    "g5": "[[1,2]-1,[2,1]-1]",
    "g6": "[[5,7]-5,[7,5]-5]",
    "g7": "[]",
    "g8": "[1]",
    "g9": "[]",
    "ge": "[domain_error(gcc_unique_key_pairs,[1-_A,1-_B]),type_error(list,foo),"
          "instantiation_error,instantiation_error,type_error(integer,a),"
          "type_error(list,foo),instantiation_error,type_error(list,foo),"
          "instantiation_error,instantiation_error,type_error(integer,a),"
          "type_error(integer,a),type_error(integer,a),domain_error(gcc_pair,x)]",
}


def _writeq(t) -> str:
    """Scryer's writeq for the shapes above (variables as _A, _B, ...)."""
    from clausal.logic.variables import is_var
    names: dict = {}

    def w(x):
        if is_var(x):
            return names.setdefault(id(x), f"_{chr(ord('A') + len(names))}")
        if isinstance(x, list):
            return "[" + ",".join(w(e) for e in x) + "]"
        if type(x) is tuple:
            if x[0] == "-" and len(x) == 3:
                return f"{w(x[1])}-{w(x[2])}"
            return f"{x[0]}(" + ",".join(w(e) for e in x[1:]) + ")"
        return str(x)
    return w(t)


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    """Every row's answer, written as Scryer writes it."""
    import importlib
    import sys
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, walk
    tmp = tmp_path_factory.mktemp("clpz_sum_gcc3")
    (tmp / "l3_sum_gcc3.pl").write_text(SRC)
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(tmp))
    try:
        sys.modules.pop("l3_sum_gcc3", None)
        importlib.invalidate_caches()
        mod = importlib.import_module("l3_sum_gcc3")
        from clausal import import_hook as ih
        assert type(mod.__loader__) is ih.NativePrologLoader
        out = {}
        for name in SCRYER_ROWS:
            r = Var()
            try:
                got = [walk(r) for _ in call(name, r, module=mod)]
            except Exception as e:
                out[name] = f"EXC {e}"
                continue
            assert len(got) == 1, (name, got)
            out[name] = _writeq(got[0])
        return out
    finally:
        sys.modules.pop("l3_sum_gcc3", None)
        mp.undo()


@pytest.mark.parametrize("name", sorted(SCRYER_ROWS))
def test_the_answer_is_scryers(rows, name):
    assert rows[name] == SCRYER_ROWS[name]


def test_the_tables_are_scryers(tmp_path):
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    f = tmp_path / "oracle.pl"
    f.write_text(SRC)
    goal = ("(member(N, [" + ",".join(SCRYER_ROWS) + "]), G =.. [N, R], "
            "call(G), write(N), write(' '), writeq(R), nl, fail ; true)")
    proc = subprocess.run([SCRYER, str(f), "-g", goal, "-g", "halt"],
                          cwd=tmp_path, capture_output=True, text=True,
                          timeout=120, stdin=subprocess.DEVNULL)
    import re
    got = {}
    for line in proc.stdout.splitlines():
        name, _, text = line.partition(" ")
        if name in SCRYER_ROWS:
            got[name] = re.sub(r"_\d+", "_", text)
    want = {k: re.sub(r"_[A-Z]", "_", v) for k, v in SCRYER_ROWS.items()}
    assert got == want, proc.stderr


# ── sum/3 resolves only under library(clpz) ─────────────────────────────────


def test_sum_3_without_the_clpz_import_is_an_existence_error(native, ans):
    from clausal.predicate_diagnostics import PredicateNotFoundError
    mod = native.load("l3_sum_noimp", "t(X) :- sum([1,2], #=, X).\n")
    with pytest.raises(PredicateNotFoundError, match="sum/3"):
        ans(mod, "t")


def test_sum_3_by_an_import_list(native, ans):
    mod = native.load("l3_sum_list",
                      ":- use_module(library(clpz), [sum/3, (#=)/2]).\n"
                      "t(X) :- sum([1,2], #=, X).\n")
    assert ans(mod, "t") == [3]


def test_a_local_sum_2_loads_beside_the_import(native, ans):
    """A file that defines its own sum/2 (a common name) loads: the sum/3
    import is dropped rather than refused, since no global sum/3 stands
    behind it to answer in its place."""
    mod = native.load("l3_sum_local2",
                      ":- use_module(library(clpz)).\n"
                      "sum([], 0).\n"
                      "sum([H|T], S) :- sum(T, S0), S is S0 + H.\n"
                      "t(S) :- sum([1,2,3], S).\n"
                      "u(X) :- X #= 2 + 1.\n")
    assert ans(mod, "t") == [6]
    assert ans(mod, "u") == [3]


def test_a_local_sum_3_wins(native, ans):
    mod = native.load("l3_sum_local3",
                      ":- use_module(library(clpz)).\n"
                      "sum(_, _, mine).\n"
                      "t(X) :- sum([1], #=, X).\n")
    assert ans(mod, "t") == ["mine"]


def test_no_global_sum_builtin_shadows_pythons_sum(tmp_path):
    """The seam's ``++sum(...)`` is still Python's sum, and sum/3 is no
    engine builtin."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, walk
    from clausal.tools.iso_l3_directives import _engine_goal
    assert not _engine_goal("sum")
    p = tmp_path / f"_seam_py_sum{SEAM}"
    p.write_text("-module(_seam_py_sum, [t/1])\nt(X) <- (X is ++sum([1, 2, 3]))\n")
    mod = _load_module("_seam_py_sum", str(p)).__dict__["$module"]
    x = Var()
    assert [walk(x) for _ in call("t", x, module=mod)] == [6]
