"""Tests for ``clausal.logic.cells`` — Phase 2 bridge Task 1.

Spec: ``.superpowers/sdd/2026-09-03-phase2-bridge/task-1-brief.md`` and the
Global Constraints / BRIDGE-ENTRY RULINGS sections of
``docs/superpowers/plans/2026-09-03-phase2-bridge.md``.

Three groups:

  - ``TestCellPrimitives`` — ``make_cell``/``make_tuple_cell``/``is_cell``/
    ``cell_functor``/``cell_args``/``cell_arity``, including the slot-0
    ruling enforcement (``make_cell`` rejects int/class/None functors) and
    the BRIDGE-ENTRY RULING that ``is_cell`` does NOT require an interned
    str (equality, not identity, is the semantics — ``make_cell`` interns
    only as a convenience).
  - ``TestCellUnificationBoundary`` — guard tests proving cells unify
    through the REAL ``unify`` from ``clausal.logic.variables`` (the
    existing C tuple branch), not a reimplementation: same-shape
    str-functor cells bind, mismatched functor/tag/arity fails. P3-2 Task
    5 (§1b): the former higher-order slot-0-Var case (a cell's functor
    slot binding via ordinary element-wise tuple unify) is retained here
    ONLY as a raw-tuple-unify property — ``make_cell`` itself now rejects
    a Var functor, and the resulting tuple, once built by hand, is no
    longer recognized as a cell by anything (see
    ``test_higher_order_slot0_var_unifies_but_is_no_longer_recognized_as_a_cell``).
  - ``TestConsRuleBoundaryDeferral`` — documents (does not fix) the
    Phase-3-deferred interaction between a str functor and the engine's
    str~char-list cons-rule unification path.
"""

from __future__ import annotations

import sys

import pytest

from clausal.logic.cells import (
    TUPLE_TAG,
    cell_args,
    cell_arity,
    cell_functor,
    clear_intern_table,
    intern_cell,
    is_cell,
    is_intern_enabled,
    make_cell,
    make_tuple_cell,
    set_intern_enabled,
)
from clausal.logic.builtins._helpers import (
    _arity,
    _functor_name,
    _is_compound,
)
from clausal.logic.variables import Trail, Var, deref, is_var, unify


# ── make_cell / make_tuple_cell / is_cell / accessors ────────────────────────


class TestCellPrimitives:
    def test_make_cell_builds_a_plain_tuple(self):
        # nv
        c = make_cell("point", 1, 2)
        assert type(c) is tuple
        assert c == ("point", 1, 2)

    def test_make_cell_zero_arity(self):
        # nv
        c = make_cell("atom")
        assert c == ("atom",)

    def test_make_cell_interns_str_functor(self):
        # nv — convenience only, see BRIDGE-ENTRY RULING test below for the
        # "does not REQUIRE interning" half of the ruling.
        built = "".join(["p", "o", "i", "n", "t"])  # a fresh, non-interned str
        c = make_cell(built, 1, 2)
        assert cell_functor(c) is sys.intern("point")

    def test_make_cell_tuple_tag_functor(self):
        # nv
        c = make_cell(TUPLE_TAG, 1, 2, 3)
        assert c == (tuple, 1, 2, 3)
        assert c == make_tuple_cell(1, 2, 3)

    def test_make_cell_rejects_unbound_var_functor(self):
        # INVERTED (P3-2 Task 5, §1b): the bridge's higher-order slot-0-Var
        # functor is DEPRECATED — it caused the bridge's one Critical
        # (recognition vanished the instant the functor bound), imposed a
        # deref on every recognition, and permitted category instability.
        # ``make_cell`` now rejects a Var functor same as any other invalid
        # one. (Formerly ``test_make_cell_var_functor``, asserting
        # ``make_cell(v, 1, 2) == (v, 1, 2)``.)
        v = Var()
        with pytest.raises(TypeError):
            make_cell(v, 1, 2)

    def test_make_cell_rejects_int_functor(self):
        # nv — slot-0 ruling enforcement
        with pytest.raises(TypeError):
            make_cell(42, 1, 2)

    def test_make_cell_rejects_none_functor(self):
        # nv
        with pytest.raises(TypeError):
            make_cell(None, 1, 2)

    def test_make_cell_rejects_arbitrary_class_functor(self):
        # nv — a class OTHER than `tuple` itself is not a valid tag
        class NotTuple:
            pass

        with pytest.raises(TypeError):
            make_cell(NotTuple, 1, 2)

    def test_make_cell_rejects_float_functor(self):
        # nv
        with pytest.raises(TypeError):
            make_cell(3.14)

    def test_make_cell_rejects_bound_var_functor_regardless_of_binding(self):
        # INVERTED (P3-2 Task 5, §1b): ``make_cell`` no longer derefs or
        # special-cases a Var functor at all — a Var is rejected whether
        # unbound OR bound, and regardless of what it is bound to (even a
        # value that would itself be a legal slot-0 shape, e.g. a str).
        # (Formerly ``test_make_cell_rejects_bound_var_is_still_accepted``,
        # which documented ``is_var``'s deref-first contract for a
        # bound-to-int Var; that contract is no longer relevant here since
        # make_cell never calls ``is_var`` on the functor any more.)
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        assert is_var(v) is False  # bound to a non-var: no longer "a Var"
        with pytest.raises(TypeError):
            make_cell(v, 1, 2)

        # Even a Var bound to a LEGAL slot-0 shape (a str) is still
        # rejected: make_cell inspects the functor object itself, never
        # its walked-to value.
        f = Var()
        unify(f, "point", trail)
        with pytest.raises(TypeError):
            make_cell(f, 1, 2)

    def test_make_tuple_cell(self):
        # nv
        c = make_tuple_cell(1, "a", None)
        assert c == (tuple, 1, "a", None)
        assert is_cell(c)

    def test_is_cell_true_for_str_functor(self):
        # nv
        assert is_cell(("point", 1, 2)) is True
        assert is_cell(("atom",)) is True

    def test_is_cell_true_for_tuple_tag(self):
        # nv
        assert is_cell((tuple, 1, 2)) is True

    def test_is_cell_true_for_zero_arity_tuple_tag(self):
        # nv — review finding #3: (tuple,) alone (len == 1, the "len >= 1"
        # boundary) is still a legal (if empty) tuple-DATA cell.
        assert is_cell((tuple,)) is True

    def test_is_cell_false_for_var_functor(self):
        # INVERTED (P3-2 Task 5, §1b): a Var-functor tuple is no longer
        # cell-shaped at all — it falls through to plain-tuple handling
        # everywhere, unbound or bound, same as any other non-str,
        # non-``tuple`` slot-0 tag. (Formerly
        # ``test_is_cell_true_for_var_functor``, asserting ``True``.)
        assert is_cell((Var(), 1, 2)) is False
        bound = Var()
        unify(bound, "point", Trail())
        assert is_cell((bound, 1, 2)) is False

    def test_is_cell_false_for_empty_tuple(self):
        # nv — len >= 1 required
        assert is_cell(()) is False

    def test_is_cell_false_for_int_slot0(self):
        # nv — the disambiguator this bridge stage relies on: a plain data
        # tuple like (1, 2) is NOT a cell.
        assert is_cell((1, 2)) is False

    def test_is_cell_false_for_non_tuple(self):
        # nv
        assert is_cell(["point", 1, 2]) is False
        assert is_cell("point") is False
        assert is_cell(None) is False
        assert is_cell(42) is False

    def test_is_cell_false_for_tuple_subclass(self):
        # nv — deliberately excluded: type(x) is tuple, not isinstance.
        class MyTuple(tuple):
            pass

        mt = MyTuple(("point", 1, 2))
        assert type(mt) is not tuple
        assert is_cell(mt) is False

    def test_bridge_entry_ruling_is_cell_does_not_require_interned_str(self):
        # nv — BRIDGE-ENTRY RULING: is_cell does NOT require sys.intern'd
        # functors; equality is the semantics. Build a str slot-0 through a
        # path that produces a fresh (non-interned) string object and
        # confirm is_cell still answers True, and that a cell built by hand
        # (bypassing make_cell entirely, so no interning ever happens)
        # still passes is_cell.
        fresh = "".join(["p", "o", "i", "n", "t"])  # not interned
        raw_cell = (fresh, 1, 2)  # NOT built via make_cell
        assert is_cell(raw_cell) is True
        assert cell_functor(raw_cell) == "point"

    def test_cell_functor_args_arity(self):
        # nv
        c = make_cell("point", 1, 2, 3)
        assert cell_functor(c) == "point"
        assert cell_args(c) == (1, 2, 3)
        assert cell_arity(c) == 3

    def test_cell_functor_args_arity_zero_arity(self):
        # nv
        c = make_cell("atom")
        assert cell_functor(c) == "atom"
        assert cell_args(c) == ()
        assert cell_arity(c) == 0

    def test_the_discipline_plain_str_tuple_is_a_cell_by_shape(self):
        # RE-WORDED (P3-2 Task 5, §1b), same assertion: what was
        # documented as an accepted "known ambiguity" (a plain tuple that
        # happens to start with a str is indistinguishable from a cell by
        # is_cell alone) is now THE DISCIPLINE per the slot-0 narrowing —
        # every runtime tuple whose slot 0 is a str IS a cell, full stop.
        # See cells.py's module docstring. (Formerly
        # ``test_known_ambiguity_plain_str_tuple_is_a_cell_by_shape``.)
        plain_user_tuple = ("hello", 1)
        assert is_cell(plain_user_tuple) is True


# ── Unification through the REAL engine unify (existing C tuple branch) ──────


class TestCellUnificationBoundary:
    """Guard tests: cells unify through ``clausal.logic.variables.unify``,
    the actual C-accelerated unifier, not a reimplementation. This proves
    the Global Constraints claim ("cells ride the EXISTING C tuple
    branches") rather than merely asserting it.
    """

    def test_same_shape_str_functor_cells_unify_and_bind_var(self):
        # nv — unify(("f", X), ("f", 1)) binds X
        x = Var()
        trail = Trail()
        c1 = make_cell("f", x)
        c2 = make_cell("f", 1)
        assert unify(c1, c2, trail) is True
        assert deref(x) == 1

    def test_different_functor_cells_fail(self):
        # nv — ("f", 1) vs ("g", 1) fails
        trail = Trail()
        assert unify(make_cell("f", 1), make_cell("g", 1), trail) is False

    def test_tuple_tag_cell_vs_str_functor_cell_fails(self):
        # nv — (tuple, 1) vs ("f",) fails: different arity AND different
        # slot-0 identity, either of which alone would fail it; this pins
        # the combined case explicitly named in the task brief.
        trail = Trail()
        assert unify(make_tuple_cell(1), make_cell("f"), trail) is False

    def test_tuple_tag_cell_same_shape_unifies(self):
        # nv — sanity: two TUPLE_TAG cells of the same shape DO unify
        # (proves the failure above is about mismatch, not TUPLE_TAG itself
        # being unify-hostile).
        x = Var()
        trail = Trail()
        assert unify(make_tuple_cell(x, 2), make_tuple_cell(1, 2), trail) is True
        assert deref(x) == 1

    def test_higher_order_slot0_var_unifies_but_is_no_longer_recognized_as_a_cell(self):
        # INVERTED (P3-2 Task 5, §1b): the bridge's higher-order cell
        # (a Var-functor slot that unify binds element-wise, same as any
        # other tuple slot) is DEPRECATED. ``make_cell`` no longer builds
        # one at all (see ``TestCellPrimitives::
        # test_make_cell_rejects_unbound_var_functor``), so this test now
        # builds the raw tuple directly, bypassing ``make_cell``, to prove
        # the underlying property this test always cared about first: raw
        # tuple unify (the existing C tuple branch) does not care whether
        # slot 0 is a legal cell tag — it unifies element-wise regardless,
        # binding the Var to the peer's functor string exactly as before.
        #
        # What INVERTS is the recognition half. Formerly (review fix,
        # finding #1): the cell must NOT vanish from the recognition
        # surface once its functor slot resolves, because every accessor
        # dereferenced slot 0. Now there is no such promise to keep — a
        # slot-0-Var tuple is never a cell, bound or not, because
        # recognition reads slot 0 RAW (no deref, anywhere, per §1b) — so
        # c1 falls through to plain-tuple handling both before AND after
        # the bind, uniformly.
        f = Var()
        trail = Trail()
        c1 = (f, 1)  # NOT built via make_cell -- see above
        c2 = make_cell("f", 1)
        assert unify(c1, c2, trail) is True
        assert deref(f) == "f"
        # c1's tuple slot 0 is still the (now-bound) Var object -- every
        # recognition path reads it RAW and answers "not a cell" both
        # before and after the bind.
        assert is_cell(c1) is False
        assert _functor_name(c1) is None
        assert _is_compound(c1) is False
        assert _arity(c1) is None

    def test_higher_order_slot0_var_functor_no_longer_constructible(self):
        # INVERTED (P3-2 Task 5, §1b): the arity-mismatch scenario this
        # test used to probe (``unify((F, 1), ("f", 1, 2))`` failing on
        # length before slot 0 matters) required building a higher-order
        # cell via ``make_cell`` — no longer possible, since ``make_cell``
        # rejects a Var functor outright regardless of the intended arity.
        # (Formerly ``test_higher_order_slot0_var_mismatched_arity_fails``.)
        f = Var()
        with pytest.raises(TypeError):
            make_cell(f, 1)
        assert is_var(f)  # nothing bound; make_cell raised before any unify

    def test_mismatched_args_fail_after_functor_matches(self):
        # nv — same functor, mismatched trailing arg
        trail = Trail()
        assert unify(make_cell("f", 1, 2), make_cell("f", 1, 3), trail) is False


# ── Phase 3 Task 5: str functor vs char-list cons-rule interaction — RETIRED ──


class TestConsRuleBoundaryDeferral:
    """Documents the (former) boundary between a cell's str functor and the
    engine's str~char-list cons-rule unification, per the Phase 2 bridge
    plan's BRIDGE-ENTRY RULINGS: "the str~char-list cons-rule interaction is
    DEFERRED to Phase 3 — Task 1 ships a guard test documenting the boundary
    instead."

    RESOLVED by P3-1 Task 5 (§1b): the cons rule itself is retired —
    ``do_unify``'s ``PyUnicode_Check(t1) && PyList_Check(t2)`` /
    ``PyList_Check(t1) && PyUnicode_Check(t2)`` branches in ``_variables.c``
    are deleted. A bare str no longer unifies with a char list in EITHER
    direction, cell-adjacent or not, so the deferred question this class
    posed ("what happens when a cell's str functor meets the char-list
    rule") no longer has a live answer to defer: there is no char-list rule
    left to meet. Both tests below are inverted to pin the retirement
    directly (class kept, name kept, for the historical cross-reference from
    the Phase 2 bridge plan).

    A str-functor cell's slot 0 is a bare ``str`` element inside a tuple
    being unified element-wise; it is unified against whatever occupies
    the peer cell's slot 0 (another str, by construction — see the
    slot-0 ruling). It never meets a list directly in this task's corpus
    (only against another cell's slot 0, i.e. another str / TUPLE_TAG /
    Var) — that fact is pinned below same as before; it is simply no
    longer load-bearing now that the cross-type rule is gone.
    """

    def test_str_functor_cell_slot0_never_meets_a_charlist_in_this_corpus(self):
        # nv — a str-functor cell unified against a same-shape cell: slot 0
        # unifies str-vs-str (ordinary equality-fallback unify), never
        # str-vs-list.
        trail = Trail()
        assert unify(make_cell("point", 1, 2), make_cell("point", 1, 2), trail) is True

    def test_str_vs_list_charlist_unification_is_retired(self):
        # nv — P3-1 Task 5 (§1b): the cons rule is retired. A direct
        # str/list unify call — independent of cells entirely — now FAILS;
        # lists unify with lists, strs unify with strs by equality only.
        # (Formerly ``test_str_vs_list_charlist_unification_is_a_different_
        # call_shape``, asserting ``unify("ab", ["a","b"], trail) is True``.)
        trail = Trail()
        assert unify("ab", ["a", "b"], trail) is False


# ── intern_cell / interning table (Task 4) ────────────────────────────────


class TestInternCell:
    """``intern_cell`` -- selective ground-cell interning, Task 4 of the
    Phase 2 bridge plan. Fixtures clear the module-level table before and
    after each test so tests never see each other's entries."""

    @pytest.fixture(autouse=True)
    def _clean_intern_table(self):
        clear_intern_table()
        yield
        clear_intern_table()

    def test_two_equal_ground_cells_intern_to_the_same_object(self):
        # nv -- the headline property: structurally-equal ground cells
        # collapse to ONE object after interning, even though they started
        # as two distinct tuple objects.
        c1 = make_cell("point", 1, 2)
        c2 = make_cell("point", 1, 2)
        assert c1 is not c2  # distinct objects going in
        i1 = intern_cell(c1)
        i2 = intern_cell(c2)
        assert i1 == c1 == c2
        assert i1 is i2

    def test_second_intern_returns_the_first_cells_object(self):
        # nv -- the FIRST cell interned with a given ground shape becomes
        # canonical; a later structurally-equal cell collapses onto it, not
        # the other way around.
        c1 = make_cell("point", 1, 2)
        i1 = intern_cell(c1)
        assert i1 is c1
        c2 = make_cell("point", 1, 2)
        i2 = intern_cell(c2)
        assert i2 is c1
        assert i2 is not c2

    def test_non_cell_passes_through_unchanged_and_untouched(self):
        # nv -- a non-cell object (stand-in for a class term instance) and
        # a plain scalar both skip interning entirely: object identity
        # preserved, table untouched.
        obj = object()
        assert intern_cell(obj) is obj
        assert intern_cell(5) == 5

    def test_non_ground_cell_returned_unchanged(self):
        # nv -- a Var anywhere in the cell's argument slots disqualifies it
        # from interning: returned object-identical to what was passed in,
        # never cached.
        X = Var()
        c = make_cell("point", X, 2)
        result = intern_cell(c)
        assert result is c

    def test_var_functor_tuple_is_not_a_cell_so_never_reaches_the_intern_walk(self):
        # INVERTED (P3-2 Task 5, §1b): the higher-order cell case this test
        # used to probe (an unbound Var in the functor slot disqualifying
        # interning via the groundness walk) can no longer be built through
        # ``make_cell`` at all. Built raw instead: the point now is that
        # ``intern_cell`` short-circuits on ``is_cell(c)`` BEFORE the
        # groundness walk (``_try_intern``) ever runs — a Var-functor tuple
        # is not a cell, so it "never reaches ``intern_cell``'s [real, table
        # touching] work" the same way a plain scalar or class term
        # instance never does (see
        # ``test_non_cell_passes_through_unchanged_and_untouched`` above).
        # (Formerly ``test_non_ground_functor_slot_returned_unchanged``.)
        F = Var()
        c = (F, 1, 2)  # NOT built via make_cell -- see above
        assert is_cell(c) is False
        result = intern_cell(c)
        assert result is c

    def test_a_cell_that_becomes_ground_after_binding_is_interned(self):
        # nv -- groundness is checked on the CURRENT (dereferenced) state,
        # not frozen at construction time: bind X, then intern.
        trail = Trail()
        X = Var()
        c = make_cell("point", X, 2)
        assert unify(X, 1, trail) is True
        result = intern_cell(c)
        assert result == ("point", 1, 2)
        # A second, independently-built cell with the same resolved shape
        # collapses onto it.
        c2 = make_cell("point", 1, 2)
        result2 = intern_cell(c2)
        assert result2 is result

    def test_nested_ground_cells_intern_bottom_up(self):
        # nv -- a cons-chain shape (struct_tabling's Nats/2 answers): the
        # inner cell gets interned as PART OF interning the outer cell
        # (bottom-up), and a SEPARATELY built, structurally-equal inner
        # cell interns to that exact same nested object -- proving the
        # sharing reaches inside nested structure, not just top-level cells.
        inner = make_cell("cons", 2, "nil")
        outer = make_cell("cons", 1, inner)
        interned_outer = intern_cell(outer)
        assert cell_args(interned_outer)[1] == inner

        inner_dup = make_cell("cons", 2, "nil")
        assert inner_dup is not inner  # started as distinct objects
        interned_inner_dup = intern_cell(inner_dup)

        # The inner cell nested inside the (already-interned) outer answer
        # is the SAME object as interning inner_dup directly.
        assert cell_args(interned_outer)[1] is interned_inner_dup

    def test_interning_does_not_mutate_the_cell_passed_in(self):
        # nv -- intern_cell returns a value; it never mutates its argument
        # (tuples are immutable anyway, but pin that the ORIGINAL first
        # cell is what ends up canonical, unmodified).
        c = make_cell("point", 1, 2)
        before = tuple(c)
        intern_cell(c)
        assert tuple(c) == before

    def test_unhashable_ground_argument_falls_back_without_raising(self):
        # nv -- a ground (no Var) but unhashable argument (a list): the
        # try/except TypeError guard returns a value equal to the input
        # rather than raising or caching a bogus entry.
        c = make_cell("bag", [1, 2, 3])
        result = intern_cell(c)
        assert result == c
        # Not cached: a second structurally-equal cell with the same
        # unhashable content also just falls back, and is not the SAME
        # object as the first (nothing was ever stored for it).
        c2 = make_cell("bag", [1, 2, 3])
        result2 = intern_cell(c2)
        assert result2 == c2
        assert result2 is not result

    def test_clear_intern_table_resets_identity(self):
        # nv -- after clear_intern_table(), a previously-canonical cell no
        # longer wins: the NEXT cell interned becomes the new canonical
        # object.
        c1 = make_cell("point", 1, 2)
        i1 = intern_cell(c1)
        assert i1 is c1
        clear_intern_table()
        c2 = make_cell("point", 1, 2)
        i2 = intern_cell(c2)
        assert i2 is c2
        assert i2 is not c1

    def test_moderate_depth_chain_interns_with_identity_and_completes_fast(self):
        # nv -- Task 4 review fix: a committed regression guard at a
        # MODERATE depth (~100, not the task report's n=1500) so a future
        # big-O regression in _try_intern's iterative walk is caught by the
        # ordinary suite without needing a slow, large-n run. Builds TWO
        # independently-constructed but structurally-equal 100-deep ground
        # cons-chains directly via make_cell (no tabling involved -- this
        # pins intern_cell's own contract, not the tabling integration) and
        # interns each.
        import time

        depth = 100

        def build_chain():
            node = "nil"
            for i in range(depth, 0, -1):
                node = make_cell("cons", i, node)
            return node

        chain1 = build_chain()
        chain2 = build_chain()
        assert chain1 is not chain2  # distinct objects going in
        assert chain1 == chain2      # same shape

        start = time.perf_counter()
        i1 = intern_cell(chain1)
        i2 = intern_cell(chain2)
        elapsed = time.perf_counter() - start

        assert i1 is chain1  # first cell interned becomes canonical
        assert i2 is i1      # second, structurally-equal chain collapses onto it
        # Generous bound -- this is a regression GUARD against a big-O
        # blowup (the task report documents O(depth^2)-per-call/O(depth^3)
        # total cost at n=1500 for the current groundness-first,
        # value-keyed implementation), not a tight performance assertion:
        # depth=100 should complete in well under a second on any
        # reasonable machine.
        assert elapsed < 2.0, (
            f"interning two 100-deep chains took {elapsed:.3f}s (>2.0s) -- "
            f"possible big-O regression in _try_intern's walk"
        )


class TestInternEnabledSwitch:
    """The module-level toggle gating the tabling freeze-boundary hook.
    Default OFF; only Task 4's tests/benchmark ever flip it."""

    def test_default_is_disabled(self):
        # nv -- this pins the DEFAULT-PATH INVARIANT at the switch itself:
        # a fresh process never has interning enabled unless something
        # explicitly turns it on.
        assert is_intern_enabled() is False

    def test_set_and_unset(self):
        assert is_intern_enabled() is False
        try:
            set_intern_enabled(True)
            assert is_intern_enabled() is True
        finally:
            set_intern_enabled(False)
        assert is_intern_enabled() is False
