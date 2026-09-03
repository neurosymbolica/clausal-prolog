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
    str-functor cells bind, mismatched functor/tag/arity fails, and the
    higher-order slot-0-Var case binds the functor itself.
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
    is_cell,
    make_cell,
    make_tuple_cell,
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

    def test_make_cell_var_functor(self):
        # nv
        v = Var()
        c = make_cell(v, 1, 2)
        assert c == (v, 1, 2)
        assert c[0] is v

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

    def test_make_cell_rejects_bound_var_is_still_accepted(self):
        # nv — is_var derefs first; a Var that IS bound derefs to its
        # binding, so a "Var" that resolves to e.g. a str is accepted (it
        # derefs to a legal slot-0 shape via the str branch's own check on
        # the bound value)... but a Var bound to an int does NOT satisfy
        # is_var (derefs to an int) and is not itself str/TUPLE_TAG, so it
        # is correctly rejected. Documents is_var's deref-first contract
        # rather than asserting new behavior.
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        assert is_var(v) is False  # bound to a non-var: no longer "a Var"
        with pytest.raises(TypeError):
            make_cell(v, 1, 2)

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

    def test_is_cell_true_for_var_functor(self):
        # nv
        assert is_cell((Var(), 1, 2)) is True

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

    def test_known_ambiguity_plain_str_tuple_is_a_cell_by_shape(self):
        # nv — documented, accepted ambiguity: a plain tuple that happens
        # to start with a str is indistinguishable from a cell by is_cell
        # alone. Not a bug; see cells.py's module docstring.
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

    def test_higher_order_slot0_var_binds_to_other_cells_functor(self):
        # nv — unify((F, 1), ("f", 1)) binds F="f". The higher-order case:
        # a cell whose functor slot is itself an unbound Var unifies
        # element-wise (slot 0 included) against a same-shape cell, which
        # binds the Var to the concrete functor string.
        f = Var()
        trail = Trail()
        c1 = make_cell(f, 1)
        c2 = make_cell("f", 1)
        assert unify(c1, c2, trail) is True
        assert deref(f) == "f"

    def test_higher_order_slot0_var_mismatched_arity_fails(self):
        # nv — the Var-functor slot doesn't rescue an arity mismatch; tuple
        # unify checks length before/independently of binding slot 0.
        f = Var()
        trail = Trail()
        assert unify(make_cell(f, 1), make_cell("f", 1, 2), trail) is False
        assert is_var(f)  # nothing bound on failure

    def test_mismatched_args_fail_after_functor_matches(self):
        # nv — same functor, mismatched trailing arg
        trail = Trail()
        assert unify(make_cell("f", 1, 2), make_cell("f", 1, 3), trail) is False


# ── Phase 3 deferral: str functor vs char-list cons-rule interaction ─────────


class TestConsRuleBoundaryDeferral:
    """Documents the boundary between a cell's str functor and the engine's
    str~char-list cons-rule unification (``do_unify``'s
    ``PyUnicode_Check(t1) && PyList_Check(t2)`` branch in
    ``_variables.c``), per the Phase 2 bridge plan's BRIDGE-ENTRY RULINGS:
    "the str~char-list cons-rule interaction is DEFERRED to Phase 3 — Task
    1 ships a guard test documenting the boundary instead."

    A str-functor cell's slot 0 is a bare ``str`` element inside a tuple
    being unified element-wise; it is unified against whatever occupies
    the peer cell's slot 0 (another str, by construction — see the
    slot-0 ruling). It NEVER meets the list-shaped char-list unification
    path, because that path only fires when one side of a *direct* unify
    call is a ``str`` and the other a ``list`` — and a cell's slot 0 is
    never unified against a bare list directly by anything built in this
    task's corpus (only against another cell's slot 0, i.e. another str /
    TUPLE_TAG / Var). This test exists to PIN that absence for the shapes
    Task 1 constructs, not to prove it is impossible in general — a future
    stage could hand-construct ``(["p", "o", "i", "n", "t"], 1)`` and unify
    it against a str-functor cell, and Phase 3 is where that gets a real
    ruling.
    """

    def test_str_functor_cell_slot0_never_meets_a_charlist_in_this_corpus(self):
        # nv — a str-functor cell unified against a same-shape cell: slot 0
        # unifies str-vs-str (ordinary equality-fallback unify), never
        # str-vs-list.
        trail = Trail()
        assert unify(make_cell("point", 1, 2), make_cell("point", 1, 2), trail) is True

    def test_str_vs_list_charlist_unification_is_a_different_call_shape(self):
        # nv — documents what the deferred interaction WOULD look like if a
        # cell's functor string were ever unified bare against a list: the
        # engine's str~char-list rule fires for a *direct* str/list unify
        # call, independent of cells entirely. This is existing, unrelated
        # behavior (not part of this task's corpus) shown here only so the
        # boundary this task defers is concrete rather than hypothetical.
        trail = Trail()
        assert unify("ab", ["a", "b"], trail) is True
