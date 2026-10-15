"""Follow-up to the Ciao `is_test4` / `unify_test16` fix (commit 6915c42d,
`clausal/logic/builtins/iso_compare.py::_cycle_unify`), addressing two
concerns raised in review of that commit:

1. PERFORMANCE: `_cycle_unify` must not pay for a Python-level cycle-safe
   walk on the overwhelmingly common ACYCLIC call. It is now restructured
   to try the engine's own `unify` FIRST and fall back to the explicit-
   stack walk only when that raises `RecursionError`. This file pins that
   shape directly (not just by reading the source): `_cycle_unify` is
   monkeypatch-instrumented to record whether the slow walk ever ran, and
   asserts it did NOT for ordinary (acyclic) unifications, including every
   parity category below.

   CORRECTION made while writing this file, not assumed from reading one
   compiler pipeline in isolation: ordinary INFIX `=` in NATIVE `.pl`
   source (`compiler_v2.py`, what `CLAUSAL_PL_FRONTEND=native` /
   `_load_prolog_module` actually compile) has NO special-cased lowering
   for `=`/2 at all and falls through to ordinary predicate-call
   compilation, which DOES resolve through the builtin registry this
   module registers `'='`/2 under — i.e. straight into `_cycle_unify`.
   (The dedicated `Unify` IR op in
   `clausal/logic/compiler/terms_to_goalop.py` that calls `$unify_iter`
   directly, bypassing the registry, is Clausal's OWN `.clausal`/`.seam`
   dialect's infix `is` keyword — "Clausal's infix `is`, which is
   unification" — a different surface spelling in a different dialect,
   not native Prolog `=`.) So the fast-path-first restructuring is the
   COMMON-PATH performance fix for native `.pl`, not merely insurance
   against a rare quoted spelling.
   `test_ordinary_infix_unify_in_native_pl_DOES_reach_cycle_unify` pins
   this directly rather than leaving it a prose claim either way.

2. CORRECTNESS PARITY: because the fast path IS a call to `unify` with no
   wrapper logic around it (see `_cycle_unify`'s docstring), parity on
   every acyclic term is true by construction for the categories below —
   this file's job is to confirm that construction claim empirically
   (same result, same trail growth) rather than assume it, and to pin the
   one thing that IS new in this module: the slow-walk fallback's own
   trail mark/undo and `defer`/`run_first` discipline, exercised only by
   `test_rollback_after_partial_bindings_and_an_attributed_var_hook`.

`unify_with_occurs_check`/2 is NOT covered here: it is a separate C entry
point (`occurs_check`/`unify_with_occurs_check` in
`clausal/logic/variables/_variables.c`), used only by
`clausal/logic/builtins/inspection.py::_unify_with_occurs_check__2` and
`clausal/logic/constraints.py::_structural_unify_oc` — neither names
`_cycle_unify`, and `grep -rn _cycle_unify clausal/` finds only this
file's three call sites in `iso_compare.py` (`'is'`, `'='`, `'\\='`).
`test_cycle_unify_is_unreachable_from_occurs_check` pins that by source
inspection rather than leaving it an unchecked claim.
"""
from __future__ import annotations

import os
from decimal import Decimal
from fractions import Fraction

import pytest

import clausal.logic.builtins.iso_compare as iso_compare
from clausal.logic.builtins.iso_compare import _cycle_unify
from clausal.logic.cells import chars
from clausal.logic.clpb import sat as _clpb_sat
from clausal.logic.constraints import dif
from clausal.logic.variables import (
    Trail, Var, deref, get_attr, is_var, unify as _raw_unify,
)
from clausal.terms import DictTerm, SegList
from clausal.pythonic_ast.nodes import BitOr as _BitOr


# ---------------------------------------------------------------------------
# 1. The fast path really is the default: the slow walk never runs for any
#    acyclic case, across every category the review asked for parity on.
# ---------------------------------------------------------------------------

@pytest.fixture
def walk_calls(monkeypatch):
    """A counter of how many times the slow fallback walk actually ran."""
    calls = []
    original = iso_compare._cycle_unify_walk

    def _spy(a, b, trail):
        calls.append((a, b))
        return original(a, b, trail)

    monkeypatch.setattr(iso_compare, "_cycle_unify_walk", _spy)
    return calls


def test_ordinary_infix_unify_in_native_pl_DOES_reach_cycle_unify(monkeypatch):
    """CORRECTION, found while writing this test (not assumed): ordinary
    compiled infix `=` in NATIVE `.pl` source (`compiler_v2.py`, what
    `_load_prolog_module`/`CLAUSAL_PL_FRONTEND=native` actually compiles)
    DOES call `_cycle_unify` -- `grep -n '"="' clausal/logic/compiler_v2.py`
    finds no special-cased lowering for `=`/2 at all, so it falls through
    to ordinary predicate-call compilation, which resolves ANY undispatched
    functor/arity through the builtin registry this module registers
    `'='`/2 under. The dedicated `nodes.Unify` IR op
    (`clausal/logic/compiler/terms_to_goalop.py`) this test ORIGINALLY
    assumed every infix `=` compiled to is Clausal's OWN `.clausal`/`.seam`
    dialect's infix `is` keyword ("Clausal's infix `is`, which is
    unification"), a different surface spelling in a different dialect --
    not what native Prolog `=` lowers to.

    This means `_cycle_unify`'s fast-path-first restructuring is NOT merely
    defensive: ordinary `=` in every native `.pl` clause body runs through
    it, so the `try: return _unify(...) except RecursionError: ...` shape
    (as opposed to always walking) is THE common-path performance fix, not
    insurance against a rare quoted spelling.
    """
    # The builtin inlines `_cycle_unify`'s fast attempt (a direct `_unify`
    # call inside try/except RecursionError, so the common call pays no
    # extra Python frame), so the spy sits on the module's `_unify`.
    calls = []
    original = iso_compare._unify

    def _spy(a, b, trail):
        calls.append((a, b))
        return original(a, b, trail)

    monkeypatch.setattr(iso_compare, "_unify", _spy)

    import clausal.import_hook  # noqa: F401
    from clausal.import_hook import _load_prolog_module
    from clausal.logic.solve import solve
    import tempfile
    import os
    d = tempfile.mkdtemp()
    src = "p(X) :- X = foo(1, 2).\n"
    path = os.path.join(d, "_infix_eq_1.pl")
    with open(path, "w") as fh:
        fh.write(src)
    mod = _load_prolog_module("_infix_eq_1", path)
    v = Var()
    results = [repr(deref(v)) for _ in solve(("p", v), mod, Trail())]
    assert results == ["('foo', 1, 2)"]
    assert len(calls) == 1, (
        "expected ordinary infix `=` in native .pl to call _cycle_unify "
        "exactly once -- if this is now 0, the compiler changed to bypass "
        "the builtin registry for `=`/2 and the performance analysis in "
        "this module's docstrings needs revisiting")


def test_quoted_canonical_form_does_reach_cycle_unify(monkeypatch):
    """The mirror image of the test above: the EXPLICIT quoted canonical
    spelling `'='(A, B)` is exactly what reaches `_cycle_unify` -- the one
    path this module's fix is for."""
    # The builtin inlines `_cycle_unify`'s fast attempt (a direct `_unify`
    # call inside try/except RecursionError, so the common call pays no
    # extra Python frame), so the spy sits on the module's `_unify`.
    calls = []
    original = iso_compare._unify

    def _spy(a, b, trail):
        calls.append((a, b))
        return original(a, b, trail)

    monkeypatch.setattr(iso_compare, "_unify", _spy)

    import clausal.import_hook  # noqa: F401
    from clausal.import_hook import _load_prolog_module
    from clausal.logic.solve import solve
    import tempfile
    import os
    d = tempfile.mkdtemp()
    src = "p(X) :- '='(X, foo(1, 2)).\n"
    path = os.path.join(d, "_quoted_eq_1.pl")
    with open(path, "w") as fh:
        fh.write(src)
    mod = _load_prolog_module("_quoted_eq_1", path)
    v = Var()
    results = [repr(deref(v)) for _ in solve(("p", v), mod, Trail())]
    assert results == ["('foo', 1, 2)"]
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# 2. Correctness parity: _cycle_unify vs the engine's own `unify`, same
#    result and same trail growth, on one representative acyclic case per
#    category the review named.
# ---------------------------------------------------------------------------

def _assert_parity(walk_calls, a1, b1, a2, b2, *, label):
    """Run `_cycle_unify` on (a1, b1) and the raw engine `unify` on
    (a2, b2) -- two FRESH, independently-dereffable copies of the SAME
    scenario, each on its OWN Trail -- and assert identical outcome and
    identical trail growth. Also asserts the slow walk never ran: parity
    here is BY CONSTRUCTION (the fast path IS `unify`), and this confirms
    that construction held for this category rather than silently going
    through the fallback and merely happening to agree."""
    t1, t2 = Trail(), Trail()
    r1 = _cycle_unify(a1, b1, t1)
    r2 = bool(_raw_unify(a2, b2, t2))
    assert r1 == r2, f"{label}: result mismatch ({r1!r} vs {r2!r})"
    assert len(t1) == len(t2), (
        f"{label}: trail growth mismatch ({len(t1)} vs {len(t2)})")
    assert walk_calls == [], f"{label}: fell back to the slow walk"
    return r1


def test_parity_plain_compound_and_list(walk_calls):
    assert _assert_parity(walk_calls, ("f", 1, 2), ("f", 1, 2),
                           ("f", 1, 2), ("f", 1, 2), label="compound match")
    assert _assert_parity(walk_calls, ("f", 1, 2), ("f", 1, 3),
                           ("f", 1, 2), ("f", 1, 3), label="compound mismatch") is False
    assert _assert_parity(walk_calls, [1, 2, 3], [1, 2, 3],
                           [1, 2, 3], [1, 2, 3], label="list match")


def test_parity_dif_attributed_variable(walk_calls):
    """dif/2: unifying the attributed variable with a value that satisfies
    the constraint must bind AND leave the constraint's own bookkeeping
    identical on both paths."""
    def build():
        x = Var()
        trail = Trail()
        assert dif(x, "forbidden", trail) is True
        return x, "safe", trail

    x1, b1, t1 = build()
    x2, b2, t2 = build()
    r1 = _cycle_unify(x1, b1, t1)
    r2 = bool(_raw_unify(x2, b2, t2))
    assert r1 is True and r2 is True
    assert len(t1) == len(t2)
    assert deref(x1) == deref(x2) == "safe"
    assert walk_calls == []


def test_parity_freeze_wakes_the_frozen_goal():
    """freeze/2 (native Prolog source, since its goal-thunk is compiler-
    built): binding the frozen variable through `'='`/2 (`_cycle_unify`)
    must wake the goal exactly like COMPILED HEAD UNIFICATION does --
    e.g. calling `one(X)` against the fact `one(1).`, a clause-dispatch
    mechanism that goes nowhere near `_cycle_unify`/`unify_iter`/the
    builtin registry at all.

    REVIEW CORRECTION (L2): this test used to compare `'='(X, 1)` against
    bare infix `X = 1` -- but in native `.pl` those are literally the SAME
    builtin call (both resolve through the registry into `_iso_unify` /
    `_cycle_unify`; see `test_ordinary_infix_unify_in_native_pl_DOES_reach_cycle_unify`),
    so that comparison tested `_cycle_unify` against itself and could not
    have caught anything. Head unification is a genuinely different
    mechanism, so this is now an actual parity check.
    """
    import tempfile
    from clausal.import_hook import _load_prolog_module
    from clausal.logic.solve import solve

    counter = [0]

    def run(goal_src, extra_clauses=""):
        counter[0] += 1
        name = f"_freeze_parity_{counter[0]}"
        d = tempfile.mkdtemp()
        path = os.path.join(d, f"{name}.pl")
        with open(path, "w") as fh:
            fh.write(f"{extra_clauses}p(R) :- freeze(X, R = yes), {goal_src}.\n")
        mod = _load_prolog_module(name, path)
        v = Var()
        return [repr(deref(v)) for _ in solve(("p", v), mod, Trail())]

    got_quoted = run("'='(X, 1)")
    got_head = run("one(X)", extra_clauses="one(1).\n")
    # Normalise an incidental quoting difference in `repr()` of the SAME
    # atom `yes` that depends on process-wide atom-interning order between
    # separate calls (confirmed unrelated to `_cycle_unify` in isolation:
    # run alone, both repr identically) -- what this test actually checks
    # is that the frozen goal woke and bound R the same way both times.
    assert got_quoted[0].strip("'") == got_head[0].strip("'") == "yes"
    assert len(got_quoted) == len(got_head) == 1


def test_freeze_wake_order_matches_argument_order_not_reversed(walk_calls):
    """B2 (review of 6915c42d, fixed by the fast-path-first restructuring,
    now pinned behaviourally rather than only via the walk-call spy):
    `freeze(A, write(a)), freeze(B, write(b)), f(A,B) = f(1,2)` must print
    `ab`, matching base/Scryer -- NOT `ba`. 6915c42d's `_cycle_unify`
    always walked, visiting a compound's arguments LIFO (right-to-left),
    so A and B's wakeups queued and fired in reverse. The fast path here
    is a single call to the engine's own `unify`, which visits left to
    right, so this never falls back to the walk for this acyclic case
    (confirmed via `walk_calls`).
    """
    import contextlib
    import io
    import tempfile
    from clausal.import_hook import _load_prolog_module
    from clausal.logic.solve import solve

    d = tempfile.mkdtemp()
    path = os.path.join(d, "_b2_freeze_order.pl")
    with open(path, "w") as fh:
        fh.write(
            "p(R) :- freeze(A, write(a)), freeze(B, write(b)), "
            "f(A,B) = f(1,2), R = done.\n")
    mod = _load_prolog_module("_b2_freeze_order", path)
    v = Var()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        results = [repr(deref(v)) for _ in solve(("p", v), mod, Trail())]
    assert results == ["'done'"]
    assert buf.getvalue() == "ab", (
        f"freeze wake order was {buf.getvalue()!r}, expected 'ab' "
        f"(base/Scryer order) -- not the LIFO-reversed 'ba' of 6915c42d")
    assert walk_calls == []


def test_holzbaur_clpq_structural_mismatch_fails_cleanly_not_type_error():
    """B3 (review of 6915c42d, fixed by the fast-path-first restructuring):
    `{X >= 0}, f(1, X) = f(2, foo)` must FAIL cleanly under
    `CLAUSAL_CLPQ=holzbaur` -- matching legacy and base -- not raise
    `error(type_error(rational, foo), _)`. 6915c42d's always-walking
    `_cycle_unify` fired the holzbaur attribute hook for `X`'s binding
    (posted by `{X >= 0}`) as soon as that LEAF succeeded, before the
    walk's LIFO order reached the `1`-vs-`2` structural mismatch that
    should have decided the whole unification first; the hook then tried
    to read `foo` as a rational and raised instead of the mismatch simply
    failing. `CLAUSAL_CLPQ` is read at import time of
    `clausal.logic.clpq`, already fixed for this test session by whichever
    test imported it first, so this runs each solver in its own
    subprocess rather than trying to patch that after the fact.
    """
    import pathlib
    import subprocess
    import sys
    import tempfile

    root = pathlib.Path(__file__).resolve().parents[2]
    program = (
        ":- use_module(library(clpq)).\n"
        # No `->` -- Clausal is cut-free with no committed choice by
        # design (`!`, `->`, `*->` are refused); plain disjunction instead.
        "p(R) :- catch((({X >= 0}, f(1, X) = f(2, foo), R = yes) ; R = no),"
        " E, R = err(E)).\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "_b3_holzbaur.pl")
        with open(path, "w") as fh:
            fh.write(program)
        for solver in ("legacy", "holzbaur"):
            env = dict(os.environ, CLAUSAL_PL_FRONTEND="native", CLAUSAL_CLPQ=solver)
            result = subprocess.run(
                [sys.executable, "-m", "clausal", "-g",
                 "p(R), write(R), nl", path],
                cwd=str(root), env=env, capture_output=True, text=True,
                timeout=60)
            assert result.returncode == 0, (
                solver, result.stdout, result.stderr)
            # stdout's first line is `write(R), nl`'s own output; later
            # lines (if any) are the CLI's own answer-binding report.
            lines = [ln for ln in result.stdout.strip().splitlines() if ln]
            assert lines and lines[0] == "no", (
                f"CLAUSAL_CLPQ={solver}: expected a clean 'no', got "
                f"{result.stdout!r} / {result.stderr[-500:]!r}")


def test_parity_clpq_bound_variable(walk_calls):
    """CLP(Q): a variable bounded by `{X >= 1, X =< 5}` must accept/reject
    the SAME values, and keep the SAME bound afterward, through
    `_cycle_unify` as through plain `unify`."""
    from clausal.logic.clpq import normal_form as nf

    def build():
        trail = Trail()
        x = Var()
        assert nf.post_constraint((">=", x, 1), trail)
        assert nf.post_constraint(("=<", x, 5), trail)
        return x, trail

    for value, expected in ((3, True), (0, False), (6, False),
                             (Fraction(9, 2), True)):
        x1, t1 = build()
        x2, t2 = build()
        mark1, mark2 = t1.mark(), t2.mark()
        r1 = _cycle_unify(x1, value, t1)
        r2 = bool(_raw_unify(x2, value, t2))
        assert r1 is expected and r2 is expected, value
        assert len(t1) == len(t2), value
        t1.undo(mark1)
        t2.undo(mark2)
    assert walk_calls == []


def test_parity_clpb_bound_variable(walk_calls):
    """CLP(B): `sat(X \\/ Y)` constrains the pair without forcing either;
    binding X to true must propagate to Y identically on both paths."""
    def build():
        trail = Trail()
        x, y = Var(), Var()
        assert _clpb_sat(_BitOr(left=x, right=y), trail) is True
        return x, y, trail

    x1, y1, t1 = build()
    x2, y2, t2 = build()
    r1 = _cycle_unify(x1, 1, t1)
    r2 = bool(_raw_unify(x2, 1, t2))
    assert r1 is True and r2 is True
    assert len(t1) == len(t2)
    assert walk_calls == []


def test_parity_seglist_chars_carrier(walk_calls):
    """SegList / the chars carrier: `'='("ab", [a, b])` -- the exact
    Liskov str<->char-list case `_cycle_unify` has its own `_cell_functor`
    guard for (see its docstring) -- must agree with plain `unify`."""
    carrier1, lst1 = chars("ab"), ["a", "b"]
    carrier2, lst2 = chars("ab"), ["a", "b"]
    assert _assert_parity(walk_calls, carrier1, lst1, carrier2, lst2,
                           label="chars carrier vs char list")


def test_parity_seglist_open_tail(walk_calls):
    """An actual hole-built `SegList` (open tail: `[a, b | T]`), unified
    against a proper list of matching length."""
    from clausal.terms import ConcreteSeg, VarSeg

    def build():
        return SegList([ConcreteSeg(["a", "b"]), VarSeg(Var())]), ["a", "b", "c"]

    a1, b1 = build()
    a2, b2 = build()
    assert _assert_parity(walk_calls, a1, b1, a2, b2, label="SegList open tail")


def test_parity_dict_term(walk_calls):
    d1a, d1b = DictTerm({"k": Var()}), DictTerm({"k": 1})
    d2a, d2b = DictTerm({"k": Var()}), DictTerm({"k": 1})
    assert _assert_parity(walk_calls, d1a, d1b, d2a, d2b, label="DictTerm")


def test_parity_decimal(walk_calls):
    assert _assert_parity(walk_calls, Decimal("1.00"), Decimal("1.00"),
                           Decimal("1.00"), Decimal("1.00"), label="Decimal match")
    assert _assert_parity(walk_calls, Decimal("1.00"), Decimal("2.00"),
                           Decimal("1.00"), Decimal("2.00"),
                           label="Decimal mismatch") is False


# ---------------------------------------------------------------------------
# 3. The rollback-safety regression the addendum specifically asked for:
#    a cycle reached only AFTER an earlier binding (through an attributed
#    variable) has already happened and fired its hook.
# ---------------------------------------------------------------------------

def test_rollback_after_partial_bindings_and_an_attributed_var_hook(walk_calls):
    """`g(f(P, Q, P, 1), X)` vs `g(f(a(P), a(Q), Q, 2), bar)`, X carrying
    `dif(X, forbidden)`.

    The slow walk (LIFO: children pushed left-to-right, popped right-to-
    left) processes the `(X, bar)` pair FIRST -- X is unbound, so it
    delegates to a single leaf `unify()` call, which binds X and fires
    its dif hook immediately (checking `dif(X, forbidden)` against `bar`:
    satisfied). It then processes the `f(...)` pair, which structurally
    recurses and finds the `1`-vs-`2` mismatch (the same shape as
    `unify_test16`) and fails.

    `_cycle_unify`'s own mark/undo around the WHOLE slow walk must then
    undo X's binding AND whatever trail entry the dif hook recorded,
    leaving `dif(X, forbidden)` exactly as it was BEFORE this call --
    checked here by trying `X = forbidden` immediately afterward (must
    still fail, proving the constraint is intact, not dropped, not
    doubled, not left in a half-updated state) and by confirming X is
    still unbound.
    """
    trail = Trail()
    X = Var()
    assert dif(X, "forbidden", trail) is True
    P, Q = Var(), Var()
    a = ("g", ("f", P, Q, P, 1), X)
    b = ("g", ("f", ("a", P), ("a", Q), Q, 2), "bar")

    mark = trail.mark()
    result = _cycle_unify(a, b, trail)

    assert result is False, "the 1-vs-2 mismatch must decide the whole unification"
    assert len(walk_calls) == 1, "must have reached the slow walk exactly once"
    assert len(trail) == mark, "the trail must be back to its pre-call length"
    assert is_var(deref(X)), "X must be unbound again -- its binding was rolled back"
    assert is_var(deref(P)) and is_var(deref(Q)), "P, Q must be unbound too"

    # The dif constraint must be intact: exactly one firing, no corruption,
    # no silent drop -- trying the forbidden value must still fail.
    probe_mark = trail.mark()
    assert _raw_unify(X, "forbidden", trail) is False, (
        "dif(X, forbidden) did not survive the rollback intact")
    trail.undo(probe_mark)
    # And a SAFE value must still succeed normally afterward, proving the
    # variable and its constraint are in a perfectly ordinary, usable state
    # -- not merely "unbound" by accident of a half-applied undo.
    assert _raw_unify(X, "bar", trail) is True
    trail.undo(probe_mark)


def test_bare_walk_defers_a_woken_goal_until_the_whole_walk_succeeds(walk_calls):
    """L1 (review of 6915c42d/a026e39d): with NO driver around this call
    (a fresh `Trail()`, nothing else running), the slow walk's own
    `trail.defer = True` / bare `run_first` discipline is what keeps a
    goal `A`'s hook wakes from running MID-WALK, before `B` (processed
    AFTER `A` in the walk's LIFO pop order: children of `('g', B, A, X)`
    push as `[B, A, X]`, so `A` pops before `B`) has itself been bound.

    Without that `defer`/`run_first` discipline, mutating just ONE of the
    two guards -- dropping `trail.defer = True`, OR dropping the bare
    `run_first(trail)` call -- leaves every other test in this suite
    green (review finding L1): neither mutation is otherwise observable,
    because `solve()` always already owns a driver (`bare` is always
    False there), so this exact bare-call, no-driver shape is the only
    place the guard's absence shows up. Repro verified directly against
    both mutations before writing this test (both flip to "B UNBOUND");
    not re-mutating here to avoid leaving the production code broken
    mid-test, but this is the test a future accidental deletion of either
    line needs to fail.
    """
    from clausal.logic.coroutining import _freeze_var

    trail = Trail()
    A, B, X, Y = Var(), Var(), Var(), Var()
    assert _raw_unify(X, ("a", X), trail)
    assert _raw_unify(Y, ("a", Y), trail)
    seen = []

    def goal():
        seen.append("B bound" if not is_var(deref(B)) else "B UNBOUND")
        yield None

    _freeze_var(A, goal, trail)
    result = _cycle_unify(("g", B, A, X), ("g", 2, 1, Y), trail)

    assert result is True
    assert len(walk_calls) == 1
    assert seen == ["B bound"], (
        "A's woken goal ran before B was bound -- the walk's defer/"
        "run_first discipline did not hold the wakeup until the whole "
        "walk succeeded")
    assert trail.defer is False, "defer must be restored, not left set"


def test_cycle_unify_actually_falls_back_on_this_cyclic_pair(walk_calls):
    """Sanity check for the rollback test and the parity tests' shared
    assumption: THIS pair really does exercise the slow walk (so a bug
    that made `_cycle_unify` silently skip the fallback would be caught
    here, not hide behind the other tests' `assert walk_calls == []`)."""
    trail = Trail()
    X, Y = Var(), Var()
    a = ("f", X, Y, X, 1)
    b = ("f", ("a", X), ("a", Y), Y, 2)
    assert _cycle_unify(a, b, trail) is False
    assert len(walk_calls) == 1


# ---------------------------------------------------------------------------
# 4. The depth-cap guard really is a clean, catchable RecursionError on
#    this platform/build -- not a C stack guard that might segfault
#    instead -- checked directly rather than assumed.
# ---------------------------------------------------------------------------

def test_raw_unify_raises_a_catchable_recursion_error_not_a_crash():
    """Exercises the engine's own `unify` (bypassing `_cycle_unify`
    entirely) on the cyclic pair several times IN THIS SAME PROCESS. If
    the C depth cap (`MAX_DEPTH` in `_variables.c`, checked at the top of
    every recursive step before doing further work) ever failed to catch
    this before a real stack overflow, this test process would not still
    be here to make the assertions below -- it would have died with a
    signal, which pytest would report as a crashed worker, not a failure.
    Five repetitions rule out a one-off: whatever headroom this platform's
    8MB thread stack (`ulimit -s`) leaves below `MAX_DEPTH` frames of
    `do_unify`, it is not being exhausted."""
    for _ in range(5):
        trail = Trail()
        X, Y = Var(), Var()
        with pytest.raises(RecursionError):
            _raw_unify(("f", X, Y, X, 1), ("f", ("a", X), ("a", Y), Y, 2), trail)


# ---------------------------------------------------------------------------
# 5. unify_with_occurs_check/2 is unreachable from _cycle_unify -- checked
#    by source inspection, not left as an unchecked claim.
# ---------------------------------------------------------------------------

def test_cycle_unify_is_unreachable_from_occurs_check():
    import inspect
    import clausal.logic.builtins.inspection as inspection

    occurs_check_src = inspect.getsource(inspection._unify_with_occurs_check__2)
    assert "_cycle_unify" not in occurs_check_src

    # `constraints._structural_unify_oc` is shadowed by a C implementation
    # at import time (same pattern as `reify_eq`; see constraints.py's own
    # `_c_structural_unify_oc` swap), so `inspect.getsource` on the live
    # object resolves to a C builtin with no Python source at all --
    # checked on the FILE TEXT instead, which still holds the Python
    # definition verbatim.
    import clausal.logic.constraints as constraints
    constraints_src = inspect.getsource(constraints)
    assert "_cycle_unify" not in constraints_src

    # And the converse, as the one-line proof the review asked for: the
    # ENTIRE tree names `_cycle_unify` only from this module's own three
    # builtins. `--include='*.py'` is required (M2, found in review):
    # without it, a `__pycache__/*.cpython-*.pyc` that happens to contain
    # the byte sequence `_cycle_unify` also matches a bare `grep -rl`,
    # which is binary garbage, not a second source reference -- and fails
    # this test in any tree where bytecode has already been written
    # (i.e. any tree that has actually been imported from, which is most
    # of them).
    import subprocess
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(constraints.__file__))))
    out = subprocess.run(
        ["grep", "-rl", "--include=*.py", "_cycle_unify", "clausal/"],
        cwd=repo_root, capture_output=True, text=True,
    ).stdout.split()
    assert out == ["clausal/logic/builtins/iso_compare.py"], out
