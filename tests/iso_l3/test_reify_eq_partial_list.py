"""library(reif)'s =/3 over a PARTIAL list (``[a|L]``, the seam's
``[a, *L]``): the reified equality answers as Scryer's reif.pl does --
``T = true`` with the unifier when the terms unify, then ``T = false`` with
``dif`` -- and definitely when the terms decide it.

The C ``reify_eq`` (and ``dif``) probe a unification and undo it.  A partial
list is a ``SegList``, whose ``__unify__`` advances a cached split
generator on every call with the same (target, trail); the probe consumed
the one split, so the real unification that followed failed and
``'='([a, b], [a|L], T)`` answered only ``T = false``.  The occurs-checked
structural unifier now reads a partial list itself.

Expected rows are Scryer's (scryer-prolog with library(reif), 2026-10-01).
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from clausal.logic.variables import is_var

PL = """\
:- use_module(library(reif)).
p1(T, L) :- '='([a, b], [a|L], T).
p2(T, L) :- '='([a|L], [a, b], T).
p3(T, L, M) :- '='([a|L], [a|M], T).
p4(T, L, M) :- '='([a|L], [b|M], T).
p5(T, L) :- '='([[a|L]], [[a, b]], T).
p6(T, L) :- '='([a, b], [a, c|L], T).
p7(T, L) :- '='([a|L], foo, T).
p8(T, L) :- '='("ab", [a|L], T).
p9(T, L) :- '='([a|L], [a|L], T).
p10(T, L) :- '='([a, b|L], [a], T).
d1(L) :- '='([a, b], [a|L], false), L = [b].
d2(L) :- '='([a, b], [a|L], false), L = [c].
"""

SEAM = """\
-private([a, b, c, foo])
p1(T, L) <- '='([a, b], [a, *L], T)
p2(T, L) <- '='([a, *L], [a, b], T)
p3(T, L, M) <- '='([a, *L], [a, *M], T)
p4(T, L, M) <- '='([a, *L], [b, *M], T)
p5(T, L) <- '='([[a, *L]], [[a, b]], T)
p6(T, L) <- '='([a, b], [a, c, *L], T)
p7(T, L) <- '='([a, *L], foo, T)
p9(T, L) <- '='([a, *L], [a, *L], T)
p10(T, L) <- '='([a, b, *L], [a], T)
d1(L) <- ('='([a, b], [a, *L], False), L is [b])
d2(L) <- ('='([a, b], [a, *L], False), L is [c])
"""

_ = "_"
SCRYER = {
    # name, arity: rows (T first); "_" an unbound variable
    ("p1", 2): [(True, ["b"]), (False, _)],      # partial vs proper
    ("p2", 2): [(True, ["b"]), (False, _)],      # proper vs partial
    ("p3", 3): [(True, "L", "L"), (False, _, _)],  # partial vs partial
    ("p4", 3): [(False, _, _)],                  # decided: a \\= b
    ("p5", 2): [(True, ["b"]), (False, _)],      # nested partial list
    ("p6", 2): [(False, _)],                     # decided: b \\= c
    ("p7", 2): [(False, _)],                     # partial vs a non-list
    ("p9", 2): [(True, _)],                      # identical
    ("p10", 2): [(False, _)],                    # decided: too long
}


def _rows(rows):
    def one(v):
        return "_" if is_var(v) else v
    return [tuple(one(v) for v in (r if isinstance(r, tuple) else (r,)))
            for r in rows]


def _check(mod, ans):
    for (name, arity), want in SCRYER.items():
        got = ans(mod, name, arity)
        if name == "p3":
            # T = true binds L = M (one variable); T = false leaves two.
            (t1, l1, m1), (t2, l2, m2) = got
            assert (t1, t2) == (True, False), (name, got)
            assert is_var(l1) and l1 is m1, (name, got)
            assert is_var(l2) and is_var(m2) and l2 is not m2, (name, got)
            continue
        assert _rows(got) == want, (name, got)
    # T = false carries dif(L, [b]): L = [b] is refused, L = [c] is not.
    assert ans(mod, "d1") == []
    assert ans(mod, "d2") == [["c"]]


def test_reified_equality_reads_a_partial_list_pl(native, ans):
    mod = native.load("reqpl_pl", PL)
    _check(mod, ans)
    # Strings: "ab" is a char list (Scryer: T = true, L = "b"; T = false).
    got = ans(mod, "p8", 2)
    assert [t for t, _l in got] == [True, False]
    from clausal.logic.cells import chars, is_chars
    l_true = got[0][1]
    assert l_true == ["b"] or (is_chars(l_true) and l_true == chars("b"))
    assert is_var(got[1][1])


def test_reified_equality_reads_a_star_list_seam(native, ans):
    mod = native.load("reqpl_seam", SEAM, suffix=".seam", frontend=None)
    _check(mod, ans)


# ── the Python twin answers the same as the C reify_eq / dif ──

_TWIN = r"""
import sys
if sys.argv[1] == "py":
    sys.modules["clausal.logic._constraints_dif"] = None
import clausal.logic.constraints as C
assert C._USE_C_DIF is (sys.argv[1] == "c")
from clausal.logic.reif import eq__3
from clausal.logic.variables import Var, Trail, unify, deref, walk, is_var
from clausal.logic.cells import chars
from clausal.terms import SegList, ConcreteSeg, VarSeg

def P(*els, tail=None):
    tail = Var() if tail is None else tail
    return SegList([ConcreteSeg(list(els)), VarSeg(tail)])

def show(v):
    v = walk(deref(v))
    return "_" if is_var(v) else repr(v)

def run(x, y, probe=None):
    tr, t, out = Trail(), Var(), []
    for _ in eq__3(x, y, t, tr, None):
        row = [deref(t)]
        if probe is not None:
            var, val = probe
            m = tr.mark(); row.append(unify(var, val, tr)); tr.undo(m)
            row.append(show(var))
        out.append(row)
    return out

L = Var(); print(run(["a", "b"], P("a", tail=L), (L, ["b"])))
L = Var(); print(run(["a", "b"], P("a", tail=L), (L, ["c"])))
L = Var(); print(run(P("a", tail=L), ["a", "b"], (L, ["b"])))
L, M = Var(), Var(); print(run(P("a", tail=L), P("a", tail=M), (L, M)))
print(run(P("a"), P("b")))
L = Var(); print(run([P("a", tail=L)], [["a", "b"]], (L, ["b"])))
print(run(["a", "b"], P("a", "c")))
print(run(P("a"), "foo"))
L = Var(); print(run(chars("ab"), P("a", tail=L), (L, ["b"])))
L = Var(); print(run(P("a", tail=L), P("a", tail=L)))
print(run(P("a", "b"), ["a"]))
L = Var(); print(run(P("a", tail=L), P("a", "b", tail=L)))   # occurs check
t = Trail(); L = Var(); print(C.dif(["a", "b"], P("a", tail=L), t),
                              unify(L, ["b"], t))
"""


def test_the_python_twin_agrees_with_c():
    out = {}
    for impl in ("c", "py"):
        r = subprocess.run([sys.executable, "-c", _TWIN, impl],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        out[impl] = r.stdout
    assert out["c"] == out["py"]
    assert out["c"].splitlines() == [
        # [T, unify(probe var, probe value) under that answer, the var]
        "[[True, True, \"['b']\"], [False, False, '_']]",   # dif(L, [b])
        "[[True, False, \"['b']\"], [False, True, '_']]",   # L = [c] ok
        "[[True, True, \"['b']\"], [False, False, '_']]",
        "[[True, True, '_'], [False, False, '_']]",          # L = M; dif
        "[[False]]",
        "[[True, True, \"['b']\"], [False, False, '_']]",   # nested
        "[[False]]",
        "[[False]]",                                         # vs foo
        "[[True, True, \"('$chars', 'b')\"], [False, False, '_']]",
        "[[True]]",
        "[[False]]",
        "[[False]]",          # occurs-checked: L = [b|L] has no answer
        "True False",
    ]
