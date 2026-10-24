"""The engine's own `unify` unifies rational trees (2026-10-24).

Until 2026-10-15 the C `do_unify` (``clausal/logic/variables/_variables.c``)
raised a raw ``RecursionError: unify: term nesting too deep`` on a cyclic
pair -- the Ciao `iso_tests` `unify_test16` pair, ``'='(f(X, Y, X, 1),
f(a(X), a(Y), Y, 2))``, builds ``X = a(X)`` and ``Y = a(Y)`` and then equates
the two cyclic terms.  From then until 2026-10-24, three builtins (`'='`/2,
`'\\='`/2, `is`/2) caught that error and re-walked the pair in Python
(`_cycle_unify`), while a clause head, `member/2`, `==`/2's trial unify and
every other unification still raised
(todo/done/l3-cyclic-unify-fix-covers-only-eq-neq-is-2026-10-15.md).

Now `do_unify` itself switches, past a depth of 1000, to `unify_rational`:
an explicit-stack walk with a memo of the compound pairs in hand, which
terminates on a cycle with Scryer's answer and never raises for depth.  The
tests here exercise the ENGINE's `unify` directly -- the pair-memo
semantics, the trail discipline the C wrapper (`do_unify_and_wake`) keeps
around a failed or deep unification, and the threshold itself.  The
`.pl`-level rows are in tests/iso/test_cyclic_terms_scryer.py.
"""
from __future__ import annotations

import pytest

from clausal.logic.constraints import dif
from clausal.logic.variables import (
    Trail, Var, deref, is_var, unify, unify_with_occurs_check,
)


def _cyclic(functor, *more):
    """``X = functor(X, *more)``: the Var and its cell."""
    x = Var()
    assert unify(x, (functor, x, *more), Trail())
    return x


# ---------------------------------------------------------------------------
# 1. A cyclic pair terminates with Scryer's answer, through the raw unify.
# ---------------------------------------------------------------------------

def test_the_ciao_pair_fails_cleanly_through_the_raw_unify():
    """`unify_test16`: the third argument equates two cyclic terms, the
    fourth (1 against 2) decides.  Five times in one process: a depth cap
    that segfaulted instead of returning would not get here."""
    for _ in range(5):
        trail = Trail()
        X, Y = Var(), Var()
        assert unify(("f", X, Y, X, 1), ("f", ("a", X), ("a", Y), Y, 2), trail) is False
        assert len(trail) == 0, "a failed unification leaves no binding"
        assert is_var(deref(X)) and is_var(deref(Y))


@pytest.mark.parametrize("build_b,expected", [
    (lambda: _cyclic("f"), True),                       # f(Y) = f(f(f(...)))
    (lambda: (lambda y: (unify(y, ("f", ("f", y)), Trail()), y)[1])(Var()), True),  # Y = f(f(Y))
    (lambda: _cyclic("g"), False),                      # Y = g(Y)
    (lambda: ("f", "a"), False),                        # the finite f(a)
])
def test_two_cyclic_terms_unify_exactly_when_they_are_one_rational_tree(build_b, expected):
    X = _cyclic("f")
    Y = build_b()
    assert unify(X, Y, Trail()) is expected


def test_the_pair_memo_does_not_hide_a_later_argument():
    """``X = f(X, a), Y = f(Y, b)``: the first argument pair is the pair in
    hand (assumed), the second decides: fails.  And ``X = f(a, X), Y =
    f(a, Y)`` succeeds."""
    X, Y = _cyclic("f", "a"), _cyclic("f", "b")
    assert unify(X, Y, Trail()) is False
    P, Q = Var(), Var()
    assert unify(P, ("f", "a", P), Trail()) and unify(Q, ("f", "a", Q), Trail())
    assert unify(P, Q, Trail()) is True


def test_a_cycle_through_a_list_terminates():
    X, Y = Var(), Var()
    assert unify(X, ["a", X], Trail())
    assert unify(Y, ["a", ["a", Y]], Trail())
    assert unify(X, Y, Trail()) is True
    Z = Var()
    assert unify(Z, ["b", Z], Trail())
    assert unify(X, Z, Trail()) is False


def test_unify_with_occurs_check_on_two_cyclic_terms_terminates():
    """Scryer: ``X = f(X), Y = f(Y), unify_with_occurs_check(X, Y)`` succeeds
    -- nothing is bound, so there is nothing for the check to refuse."""
    X, Y = _cyclic("f"), _cyclic("f")
    assert unify_with_occurs_check(X, Y, Trail()) is True


# ---------------------------------------------------------------------------
# 2. The trail discipline around a failed cyclic unification is the C
#    wrapper's own: every binding undone, an attributed variable's hook
#    state intact, no woken goal run early.
# ---------------------------------------------------------------------------

def test_rollback_after_partial_bindings_and_an_attributed_var_hook():
    """`g(f(P, Q, P, 1), X)` against `g(f(a(P), a(Q), Q, 2), bar)`, X
    carrying `dif(X, forbidden)`: the `f` pair fails on 1 against 2 after
    P and Q were bound into cycles; the whole unification is undone, and
    `dif(X, forbidden)` must still hold afterwards."""
    trail = Trail()
    X = Var()
    assert dif(X, "forbidden", trail) is True
    P, Q = Var(), Var()
    a = ("g", ("f", P, Q, P, 1), X)
    b = ("g", ("f", ("a", P), ("a", Q), Q, 2), "bar")

    mark = trail.mark()
    assert unify(a, b, trail) is False
    assert len(trail) == mark
    assert is_var(deref(X)) and is_var(deref(P)) and is_var(deref(Q))

    probe = trail.mark()
    assert unify(X, "forbidden", trail) is False, "dif(X, forbidden) did not survive"
    trail.undo(probe)
    assert unify(X, "bar", trail) is True
    trail.undo(probe)


def test_a_bare_unify_wakes_a_frozen_goal_after_the_whole_structure_is_bound():
    """With no driver around the call, `do_unify_and_wake` binds the whole
    structure before any hook fires: A's frozen goal sees B bound, whatever
    the walk's own order of visiting them."""
    from clausal.logic.coroutining import _freeze_var

    trail = Trail()
    A, B, X, Y = Var(), Var(), Var(), Var()
    assert unify(X, ("a", X), trail)
    assert unify(Y, ("a", Y), trail)
    seen = []

    def goal():
        seen.append("B bound" if not is_var(deref(B)) else "B UNBOUND")
        yield None

    _freeze_var(A, goal, trail)
    assert unify(("g", B, A, X), ("g", 2, 1, Y), trail) is True
    assert seen == ["B bound"]
    assert trail.defer is False


# ---------------------------------------------------------------------------
# 3. Deep acyclic terms cross the threshold and come out right either way.
# ---------------------------------------------------------------------------

def _nested(n, leaf):
    t = leaf
    for _ in range(n):
        t = ("f", t)
    return t


@pytest.mark.parametrize("depth", [999, 1001, 5000])
def test_deep_acyclic_terms_unify_and_bind_through_the_threshold(depth):
    V = Var()
    trail = Trail()
    assert unify(_nested(depth, V), _nested(depth, "a"), trail) is True
    assert deref(V) == "a"
    trail.undo(0)
    assert is_var(deref(V))
    # A mismatch at the bottom fails and undoes the binding made on the way.
    W = Var()
    assert unify(("g", W, _nested(depth, "a")), ("g", 1, _nested(depth, "b")), trail) is False
    assert is_var(deref(W)) and len(trail) == 0


def test_a_deep_list_of_lists_unifies():
    t1, t2 = ["x"], ["x"]
    for _ in range(3000):
        t1, t2 = [t1], [t2]
    assert unify(t1, t2, Trail()) is True
    t2[0][0][0] = ["y"]
    assert unify(t1, t2, Trail()) is False


def test_the_threshold_is_the_documented_one():
    """`UNIFY_DEEP` is 1000 in the C source; this engine's `.pl` `=`/2 is a
    direct call to the engine's `unify`, with no Python fallback left."""
    import inspect
    import re
    import clausal.logic.builtins.iso_compare as iso_compare
    from pathlib import Path
    import clausal.logic.variables as variables

    c = Path(variables.__file__).with_name("_variables.c").read_text()
    assert re.search(r"^#define UNIFY_DEEP 1000$", c, re.M)
    assert "_cycle_unify" not in inspect.getsource(iso_compare)
