"""The ``PredicateMeta`` metaclass is DELETED (W4b-3 slice 7, 2026-09-26).

This file tested the metaclass itself -- construction, ``__eq__``/``__repr__``,
``__match_args__``, per-class clause storage, dispatch, locking, isolation --
and those tests were retired with the class (a predicate is a Database row,
named by a handle).  What stays here:

* the POSITIVE CONTROL that the class is gone: it is not importable from
  ``clausal.logic.predicate`` nor exported by ``clausal``;
* ``make_predicate`` is still a stub that raises ``MakePredicateRetiredError``
  (public API with a documented error; removing the name is a separate
  decision), and the error is still exported;
* ``make_atom``, the atom constructor, which lived beside the class.
"""

import pytest

import clausal
from clausal.logic import predicate as predicate_mod
from clausal.logic.atoms import mint
from clausal.logic.variables import Var


class TestTheClassIsGone:
    def test_predicate_meta_is_not_importable(self):
        with pytest.raises(ImportError):
            from clausal.logic.predicate import PredicateMeta  # noqa: F401
        assert not hasattr(predicate_mod, "PredicateMeta")
        assert "PredicateMeta" not in predicate_mod.__all__
        assert not hasattr(clausal, "PredicateMeta")
        assert "PredicateMeta" not in clausal.__all__

    def test_make_predicate_is_a_stub_that_raises(self):
        from clausal import MakePredicateRetiredError, make_predicate
        with pytest.raises(MakePredicateRetiredError) as info:
            make_predicate("a", [])
        assert isinstance(info.value, TypeError)
        assert "retired" in str(info.value)

    def test_the_c_extension_has_no_predicate_class_slot(self):
        """W4b-3 slice 8: the extension's ``PredicateMeta`` slot, its
        ``_register_predicate_meta`` entry point and the class-only ``is_atom``
        are gone, and so is the Python placeholder that fed the slot.  The
        term helpers work with no Python-side registration: module init sets
        up what they read.  (A stale ``.so`` still has the entry point -- this
        is also the check that the rebuilt extension is the one imported.)"""
        import dataclasses
        from clausal.logic.variables import _variables as C
        assert not hasattr(C, "_register_predicate_meta")
        assert not hasattr(C, "is_atom")
        assert not hasattr(predicate_mod, "_NoPredicateClasses")
        assert predicate_mod.is_term_instance is C.is_term_instance
        assert predicate_mod.is_zero_field_class(int) is False

        @dataclasses.dataclass
        class pt:
            x: int
            y: int

        assert C.is_term_instance(pt(1, 2)) is True
        assert C.is_term_instance(("pt", 1, 2)) is False
        assert C.is_term_instance(pt) is False
        assert C.term_field_names(pt(1, 2)) == ("x", "y")


class TestMakeAtom:
    """``make_atom(spelling)`` returns the ATOM for that spelling -- the
    ``str`` itself (STAGE 2); equality is the semantics (spec §5.2)."""

    def test_returns_the_atom(self):
        # nv
        from clausal.logic.predicate import make_atom
        a = make_atom("a")
        assert a == mint("a")
        assert type(a) is str

    def test_repeated_calls_agree(self):
        """Same spelling, same atom — EQUALITY, never identity (spec §5.2)."""
        # nv
        from clausal.logic.predicate import make_atom
        assert make_atom("a") == make_atom("a")

    def test_hashable(self):
        # nv
        from clausal.logic.predicate import make_atom
        a = make_atom("a")
        d = {a: 42}
        assert d[mint("a")] == 42

    def test_unify(self):
        # nv
        from clausal.logic.predicate import make_atom
        from clausal.logic.variables import Trail, unify, deref
        a = make_atom("a")
        b = make_atom("b")
        trail = Trail()
        x = Var()
        assert unify(x, a, trail)
        assert deref(x) == mint("a")
        assert not unify(a, b, trail)
