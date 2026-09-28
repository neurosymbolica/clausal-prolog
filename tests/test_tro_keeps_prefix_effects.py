"""Regression: a tail-recursive clause must not lose the effects of its prefix.

Tail-recursion optimisation (TRO) restarts the predicate's body in place of
the recursive call.  It used to undo the clause's trail segment before the
restart, keeping only a top-level ``deref`` snapshot of the tail arguments.
Everything else the prefix did was silently discarded:

- a dif/2 constraint posted on a caller variable by ``K is not H``
  (the explicit ``dif(K, H)`` spelling escaped only because a call to dif/2
  is not on TRO's deterministic-prefix list);
- a CLP constraint on a caller variable (``K != 3``, ``K > 3``);
- a plain binding of a caller variable (``K is foo``);
- a binding reachable from inside a compound tail argument
  (``X is H, p(f(X, A), T)``).

TRO now takes the in-place restart only when ``Trail.commit_fresh`` confirms
every trail entry of the activation is on a variable created within it, and
otherwise makes the ordinary call.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call
from clausal.logic.variables import AttVar, Trail, Var, deref, put_attr, unify


_SOURCE = """\
-private([a, b, c, d, g, go, p1, p2, p3, p4, p5, s1, s2, s3, foo, tro_absent, f(X, Y), h(X)])

# `is not` and dif/2 over a list, the reported shape
ka(_, []),
ka(K, [H, *T]) <- (K is not H, ka(K, T))
kb(_, []),
kb(K, [H, *T]) <- (dif(K, H), kb(K, T))
ra(L, V, R) <- findall(1, (ka(K, L), K is V), R)
rb(L, V, R) <- findall(1, (kb(K, L), K is V), R)
nr(R) <- findall(1, (K is not a, K is a), R)

# the same, first-argument indexed (the p1..p5 clauses push the predicate over
# the index threshold).  Behavioural rows only: as of 2026-09-29 the lifted
# bucket clauses are compiled WITHOUT a TRO tail, so these do not exercise
# signal-mode TRO -- that path shares ``_compile_tro_tail`` with loop mode.
kx(go, _, []),
kx(go, K, [H, *T]) <- (K is not H, kx(go, K, T))
kx(p1, _, _),
kx(p2, _, _),
kx(p3, _, _),
kx(p4, _, _),
kx(p5, _, _),
rx(L, V, R) <- findall(1, (kx(go, K, L), K is V), R)

# ... and single-clause buckets
ky(s1, K, [H, *T]) <- (K is not H, ky(s2, K, T))
ky(s2, K, [H, *T]) <- (K is not H, ky(s3, K, T))
ky(s3, _, []),
ky(p1, _, _),
ky(p2, _, _),
ky(p3, _, _),
ky(p4, _, _),
ry(L, V, R) <- findall(1, (ky(s1, K, L), K is V), R)

# first element that differs from all before it: body-bind and head-bind
c1(X, [H, *_]) <- (X is H)
c1(X, [H, *T]) <- (X is not H, c1(X, T))
d1(X, [H, *_]) <- (X is H)
d1(X, [H, *T]) <- (dif(X, H), d1(X, T))
c2(X, [X, *_]),
c2(X, [H, *T]) <- (X is not H, c2(X, T))
d2(X, [X, *_]),
d2(X, [H, *T]) <- (dif(X, H), d2(X, T))

# other prefix effects on a caller variable
pb(_, []),
pb(K, [_, *T]) <- (K is foo, pb(K, T))
pc(_, []),
pc(K, [_, *T]) <- (K != 3, pc(K, T))
pg(_, []),
pg(K, [_, *T]) <- (K > 3, pg(K, T))

# a binding reachable only from inside a compound tail argument
sc(A, [], A),
sc(A, [H, *T], R) <- (X is H, sc(f(X, A), T, R))
sd(A, [], A),
sd(_, [_, *T], R) <- (X is h(Y), Y is a, sd(X, T, R))

# the safe shape TRO exists for: every effect is on a clause-local variable
len2(N, [], N),
len2(N0, [_, *T], N) <- (eval_(N0 + 1, N1), len2(N1, T, N))
walk([]),
walk([H, *T]) <- (H is not tro_absent, walk(T))
"""


@pytest.fixture(scope="module")
def mod():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "tro_prefix_effects.seam")
        with open(path, "w") as f:
            f.write(_SOURCE)
        yield _load_module("_tro_prefix_effects", path)


def _all(mod, name, *args, out_first=False):
    """Every answer for the output argument (last, or first if *out_first*)."""
    lm = mod.__dict__["$module"]
    out = Var()
    full = (out, *args) if out_first else (*args, out)
    return [_deref_walk(out) for _ in call(name, *full, module=lm)]


def _findall_one(mod, name, *args):
    (r,) = _all(mod, name, *args)
    return r


def _funcdef_sources(mod, name, arity):
    """Every generated function body reachable from the predicate row."""
    row = mod.__dict__["$module"].db.row(name, arity)
    assert row is not None
    seen, out = set(), []

    def visit(fn):
        if fn is None or id(fn) in seen:
            return
        seen.add(id(fn))
        code = getattr(fn, "__code__", None)
        if code is not None:
            out.append(code)
        for cell in getattr(fn, "__closure__", None) or ():
            try:
                visit(cell.cell_contents)
            except ValueError:
                pass
        for v in (getattr(fn, "__globals__", None) or {}).values():
            if callable(v) and getattr(v, "__name__", "").startswith(name + "__"):
                visit(v)

    visit(row.dispatch_fn)
    for idx in (getattr(row, "index_plans", None) or {}).values():
        for w in idx.values():
            visit(w)
    return out


def _uses_commit_fresh(mod, name, arity):
    def names(code):
        yield from code.co_names
        for c in code.co_consts:
            if hasattr(c, "co_names"):
                yield from names(c)
    return any("commit_fresh" in set(names(c))
               for c in _funcdef_sources(mod, name, arity))


class TestTroIsActive:
    """Guard against a vacuous pass: these predicates must compile with TRO."""

    @pytest.mark.parametrize("name,arity", [
        ("ka", 2), ("c1", 2), ("c2", 2), ("pb", 2), ("sc", 3),
        ("len2", 3), ("walk", 1),
    ])
    def test_tro_tail_emitted(self, mod, name, arity):
        assert _uses_commit_fresh(mod, name, arity), (
            f"{name}/{arity} did not compile a TRO tail")


class TestIsNotSurvivesTheRecursion:
    @pytest.mark.parametrize("pred", ["ra", "rb", "rx", "ry"])
    @pytest.mark.parametrize("lst,val,want", [
        (["a"], "a", []),                     # depth 1
        (["a", "b"], "a", []),                # depth 2, excluded early
        (["a", "b"], "b", []),                # depth 2, excluded last
        (["a", "b"], "c", [1]),
        (["a", "b", "c"], "a", []),           # depth 3
        (["a", "b", "c"], "c", []),
        (["a", "b", "c"], "d", [1]),          # not excluded: still succeeds
        ([], "a", [1]),
    ])
    def test_constraint_kept(self, mod, pred, lst, val, want):
        if pred == "ry" and len(lst) != 2:
            pytest.skip("ky/3 walks exactly two elements")
        assert _findall_one(mod, pred, lst, val) == want

    def test_non_recursive(self, mod):
        assert _findall_one(mod, "nr") == []


class TestFirstDistinct:
    @pytest.mark.parametrize("pred", ["c1", "d1", "c2", "d2"])
    def test_a_b_a(self, mod, pred):
        assert _all(mod, pred, ["a", "b", "a"], out_first=True) == ["a", "b"]

    @pytest.mark.parametrize("pred", ["c1", "d1", "c2", "d2"])
    def test_a_a(self, mod, pred):
        assert _all(mod, pred, ["a", "a"], out_first=True) == ["a"]

    @pytest.mark.parametrize("pred", ["c1", "c2"])
    def test_ground_first_argument(self, mod, pred):
        lm = mod.__dict__["$module"]
        assert len(list(call(pred, "a", ["a", "b", "a"], module=lm))) == 1
        assert len(list(call(pred, "b", ["a", "b", "a"], module=lm))) == 1


class TestOtherPrefixEffects:
    def test_binding_of_a_caller_variable(self, mod):
        k = Var()
        lm = mod.__dict__["$module"]
        got = [deref(k) for _ in call("pb", k, ["a", "b"], module=lm)]
        assert got == ["foo"]

    @pytest.mark.parametrize("pred,val", [("pc", 3), ("pg", 1)])
    def test_clp_constraint_on_a_caller_variable(self, mod, pred, val):
        lm = mod.__dict__["$module"]
        k = Var()
        n = 0
        for _ in call(pred, k, ["a", "b"], module=lm):
            t = Trail()
            if unify(k, val, t):
                n += 1
            t.reset()
        assert n == 0

    def test_binding_inside_a_compound_tail_argument(self, mod):
        assert _all(mod, "sc", "g", ["a", "b"]) == [("f", "b", ("f", "a", "g"))]

    def test_binding_made_after_the_tail_argument_was_built(self, mod):
        assert _all(mod, "sd", "g", ["a", "b"]) == [("h", "a")]


class TestSafeShapesStillLoop:
    def test_accumulator(self, mod):
        assert _all(mod, "len2", 0, list(range(2000))) == [2000]

    def test_is_not_on_ground_elements(self, mod):
        lm = mod.__dict__["$module"]
        assert len(list(call("walk", list(range(2000)), module=lm))) == 1


class TestTrailCommitFresh:
    def test_fresh_binding_is_committed_and_kept(self):
        t = Trail()
        mark, floor = t.mark(), t.var_floor()
        v = Var()
        assert unify(v, 1, t)
        assert t.commit_fresh(mark, floor) is True
        assert t.mark() == mark
        assert deref(v) == 1
        t.reset()
        assert deref(v) == 1   # no longer on the trail: never undone

    def test_older_binding_is_refused_and_left_undoable(self):
        t = Trail()
        old = Var()
        mark, floor = t.mark(), t.var_floor()
        fresh = Var()
        assert unify(fresh, 2, t)
        assert unify(old, 1, t)
        assert t.commit_fresh(mark, floor) is False
        assert t.mark() == mark + 2
        t.undo(mark)
        assert isinstance(deref(old), Var) and isinstance(deref(fresh), Var)

    def test_attribute_on_an_older_attvar_is_refused(self):
        t = Trail()
        av = AttVar()
        mark, floor = t.mark(), t.var_floor()
        put_attr(av, "k", 1, t)
        assert t.commit_fresh(mark, floor) is False
        t.undo(mark)

    def test_attribute_on_a_fresh_attvar_is_committed(self):
        t = Trail()
        mark, floor = t.mark(), t.var_floor()
        av = AttVar()
        put_attr(av, "k", 1, t)
        assert t.commit_fresh(mark, floor) is True
        assert t.mark() == mark

    def test_undo_callback_is_refused(self):
        t = Trail()
        mark, floor = t.mark(), t.var_floor()
        t.record(lambda: None)
        assert t.commit_fresh(mark, floor) is False
        assert t.mark() == mark + 1
        t.undo(mark)

    def test_nothing_recorded(self):
        t = Trail()
        assert t.commit_fresh(t.mark(), t.var_floor()) is True
