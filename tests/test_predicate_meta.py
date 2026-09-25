"""Tests for clausal.logic.predicate — PredicateMeta metaclass (Phase 0)."""

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import is_cell, cell_functor, cell_args, cell_arity
from clausal.logic.predicate import PredicateMeta, _MISSING
from clausal.logic.database import Clause
from clausal.logic.variables import Var, is_var


# ── Test predicate classes ────────────────────────────────────────────────────


class fib(metaclass=PredicateMeta):
    _fields = ("n", "f")


class point(metaclass=PredicateMeta):
    _fields = ("x", "y", "z")


class atom(metaclass=PredicateMeta):
    _fields = ()


def _f(term, cls, name):
    """The value of the field *name* in a term cell built from *cls*.

    P2: constructing a predicate class yields a CELL -- a functor and
    POSITIONS -- so the term no longer carries its field names.  The class
    that DECLARED them still does, which is where a name is resolved."""
    return cell_args(term)[cls._fields.index(name)]


# ── Properties ────────────────────────────────────────────────────────────────


class TestProperties:
    def test_functor(self):
        # nv
        assert fib._functor == "fib"

    def test_arity(self):
        # nv
        assert fib._arity == 2

    def test_arity_zero(self):
        # nv
        assert atom._arity == 0

    def test_arity_three(self):
        # nv
        assert point._arity == 3


# ── Term construction ─────────────────────────────────────────────────────────


class TestTermConstruction:
    def test_full_kwargs(self):
        # nv
        t = fib(n=0, f=0)
        assert _f(t, fib, "n") == 0
        assert _f(t, fib, "f") == 0

    def test_partial_kwargs_are_refused(self):
        """Naming only SOME fields is refused (operator ruling 2026-09-25: no padding; it used to fill the rest with fresh Vars)."""
        # nv
        from clausal.logic.predicate import ClausalTermConstructionError
        with pytest.raises(ClausalTermConstructionError):
            fib(n=5)

    def test_no_args_are_refused(self):
        """A construction with no arguments against a fielded class is
        refused (operator ruling 2026-09-25: no padding; it used to fill the rest with fresh Vars)."""
        # nv
        from clausal.logic.predicate import ClausalTermConstructionError
        with pytest.raises(ClausalTermConstructionError):
            fib()

    def test_all_keywords_place_by_name(self):
        # nv
        t = fib(f=8, n=5)
        assert _f(t, fib, "n") == 5 and _f(t, fib, "f") == 8

    def test_positional_args(self):
        # nv
        t = fib(1, 2)
        assert _f(t, fib, "n") == 1
        assert _f(t, fib, "f") == 2

    def test_isinstance_works(self):
        """P2: a term is a CELL, so class membership is not what identifies
        it -- the functor is.  isinstance was the old spelling of this."""
        # nv
        t = fib(n=0, f=1)
        assert is_cell(t)
        assert cell_functor(t) == "fib"
        assert cell_arity(t) == 2

    def test_three_fields_partial_is_refused(self):
        """(operator ruling 2026-09-25: no padding; it used to fill the rest with fresh Vars)"""
        # nv
        from clausal.logic.predicate import ClausalTermConstructionError
        with pytest.raises(ClausalTermConstructionError):
            point(x=1)

    def test_none_is_not_missing(self):
        """Explicitly passing None should NOT be replaced with Var()."""
        # nv
        t = fib(n=None, f=5)
        assert _f(t, fib, "n") is None
        assert _f(t, fib, "f") == 5

    def test_zero_arity_returns_class(self):
        """Zero-arity __call__ returns the class itself — class IS the atom."""
        # nv
        assert atom() is atom


# ── __eq__ and __repr__ ──────────────────────────────────────────────────────


class TestEqRepr:
    def test_eq_same_values(self):
        # nv
        assert fib(n=1, f=1) == fib(n=1, f=1)

    def test_eq_different_values(self):
        # nv
        assert fib(n=1, f=1) != fib(n=1, f=2)

    def test_eq_different_types(self):
        # nv
        assert fib(n=1, f=2) != point(x=1, y=2, z=3)

    def test_repr(self):
        # nv
        t = fib(n=1, f=2)
        # P2: a cell's repr is the TUPLE's -- the field names moved to the
        # class that declares them, so they are not in the term's repr.
        assert repr(t) == repr(("fib", 1, 2))

    def test_repr_zero_arity(self):
        # atom() is atom (the class), so repr is the class name
        # nv
        assert repr(atom()) == "atom"


# ── __match_args__ ────────────────────────────────────────────────────────────


class TestPatternMatch:
    def test_match_args_set(self):
        # nv
        assert fib.__match_args__ == ("n", "f")

    def test_match_case(self):
        # nv
        t = fib(n=1, f=1)
        # P2: a cell matches as the SEQUENCE it is -- functor then arguments.
        match t:
            case ("fib", 1, f_val):
                assert f_val == 1
            case _:
                pytest.fail("Pattern match failed")


# ── Clause management ─────────────────────────────────────────────────────────


class pred_a(metaclass=PredicateMeta):
    _fields = ("x",)


class TestClauseManagement:
    def setup_method(self):
        pred_a._state_row().clauses = []
        pred_a._state_row().dispatch_fn = None
        pred_a._state_row().lazy_recompile = None
        pred_a._state_row().locked = False

    def test_assertz_appends(self):
        # nv
        c1 = Clause(head=pred_a(x=1), body=[])
        c2 = Clause(head=pred_a(x=2), body=[])
        pred_a._assertz(c1)
        pred_a._assertz(c2)
        assert pred_a._state_row().clauses == [c1, c2]

    def test_asserta_prepends(self):
        # nv
        c1 = Clause(head=pred_a(x=1), body=[])
        c2 = Clause(head=pred_a(x=2), body=[])
        pred_a._assertz(c1)
        pred_a._asserta(c2)
        assert pred_a._state_row().clauses == [c2, c1]

    def test_assertz_clears_dispatch(self):
        # nv
        with pred_a._mutate("test", "recompile"):   # the gate, P3-3 Task 3
            pred_a._state_row().dispatch_fn = lambda: None
        pred_a._assertz(Clause(head=pred_a(x=1), body=[]))
        assert pred_a._state_row().dispatch_fn is None

    def test_retract_removes_first_match(self):
        # nv
        h1 = pred_a(x=1)
        h2 = pred_a(x=2)
        pred_a._assertz(Clause(head=h1, body=[]))
        pred_a._assertz(Clause(head=h2, body=[]))
        assert pred_a._retract(h1) is True
        assert len(pred_a._state_row().clauses) == 1
        assert pred_a._state_row().clauses[0].head == h2

    def test_retract_nonexistent_returns_false(self):
        # nv
        pred_a._assertz(Clause(head=pred_a(x=1), body=[]))
        assert pred_a._retract(pred_a(x=99)) is False

    def test_retract_clears_dispatch(self):
        # nv
        h = pred_a(x=1)
        pred_a._assertz(Clause(head=h, body=[]))
        with pred_a._mutate("test", "recompile"):   # the gate, P3-3 Task 3
            pred_a._state_row().dispatch_fn = lambda: None
        pred_a._retract(h)
        assert pred_a._state_row().dispatch_fn is None


# ── Dispatch ──────────────────────────────────────────────────────────────────


class pred_b(metaclass=PredicateMeta):
    _fields = ("x",)


class TestDispatch:
    def setup_method(self):
        pred_b._state_row().clauses = []
        pred_b._state_row().dispatch_fn = None
        pred_b._state_row().lazy_recompile = None
        pred_b._state_row().locked = False

    def test_get_dispatch_returns_fn(self):
        # nv
        fn = lambda *a: iter([])
        with pred_b._mutate("test", "recompile"):   # the gate, P3-3 Task 3
            pred_b._state_row().dispatch_fn = fn
        assert pred_b._get_dispatch() is fn

    def test_get_dispatch_lazy_recompile(self):
        # nv
        fn = lambda *a: iter([])
        pred_b._state_row().lazy_recompile = lambda: fn
        result = pred_b._get_dispatch()
        assert result is fn
        assert pred_b._state_row().dispatch_fn is fn

    def test_get_dispatch_no_fn_raises(self):
        # nv
        with pytest.raises(NotImplementedError, match="no compiled dispatch"):
            pred_b._get_dispatch()

    def test_assertz_triggers_lazy_recompile(self):
        # nv
        calls = []

        def recompile():
            calls.append(1)
            return lambda *a: iter([])

        with pred_b._mutate("test", "recompile"):   # the gate, P3-3 Task 3
            pred_b._state_row().dispatch_fn = lambda *a: iter([])
        pred_b._state_row().lazy_recompile = recompile
        pred_b._assertz(Clause(head=pred_b(x=1), body=[]))
        assert pred_b._state_row().dispatch_fn is None
        pred_b._get_dispatch()
        assert len(calls) == 1


# ── Locking ───────────────────────────────────────────────────────────────────


class pred_locked(metaclass=PredicateMeta):
    _fields = ("x",)


class TestLocking:
    def setup_method(self):
        pred_locked._state_row().clauses = []
        pred_locked._state_row().dispatch_fn = None
        pred_locked._state_row().lazy_recompile = None
        pred_locked._state_row().locked = False

    def test_starts_unlocked(self):
        # nv
        assert pred_locked._state_row().locked is False

    def test_lock(self):
        # nv
        pred_locked._lock()
        assert pred_locked._state_row().locked is True

    def test_unlock(self):
        # nv
        pred_locked._lock()
        pred_locked._unlock()
        assert pred_locked._state_row().locked is False

    def test_locked_assertz_raises(self):
        # nv
        pred_locked._lock()
        with pytest.raises(RuntimeError, match="locked"):
            pred_locked._assertz(Clause(head=pred_locked(x=1), body=[]))

    def test_locked_asserta_raises(self):
        # nv
        pred_locked._lock()
        with pytest.raises(RuntimeError, match="locked"):
            pred_locked._asserta(Clause(head=pred_locked(x=1), body=[]))

    def test_locked_retract_raises(self):
        # nv
        pred_locked._lock()
        with pytest.raises(RuntimeError, match="locked"):
            pred_locked._retract(pred_locked(x=1))

    def test_unlocked_after_lock_allows_assertz(self):
        # nv
        pred_locked._lock()
        pred_locked._unlock()
        pred_locked._assertz(Clause(head=pred_locked(x=1), body=[]))
        assert len(pred_locked._state_row().clauses) == 1


# ── Isolation ─────────────────────────────────────────────────────────────────


class pred_x(metaclass=PredicateMeta):
    _fields = ("v",)


class pred_y(metaclass=PredicateMeta):
    _fields = ("v",)


class TestIsolation:
    def setup_method(self):
        pred_x._state_row().clauses = []
        pred_y._state_row().clauses = []
        pred_x._state_row().locked = False
        pred_y._state_row().locked = False

    def test_clauses_are_per_class(self):
        # nv
        pred_x._assertz(Clause(head=pred_x(v=1), body=[]))
        assert len(pred_x._state_row().clauses) == 1
        assert len(pred_y._state_row().clauses) == 0

    def test_locking_is_per_class(self):
        # nv
        pred_x._lock()
        assert pred_x._state_row().locked is True
        assert pred_y._state_row().locked is False


# ── Repr (class-level) ───────────────────────────────────────────────────────


class TestClassRepr:
    def test_repr_uncompiled(self):
        # nv
        r = repr(fib)
        assert "fib/2" in r
        assert "uncompiled" in r

    def test_repr_compiled(self):
        # nv
        with fib._mutate("test", "recompile"):      # the gate, P3-3 Task 3
            fib._state_row().dispatch_fn = lambda: None
        r = repr(fib)
        assert "compiled" in r
        fib._state_row().dispatch_fn = None

    def test_repr_locked(self):
        # nv
        fib._lock()
        r = repr(fib)
        assert "locked" in r
        fib._unlock()


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_predicate_is_a_class(self):
        # nv
        assert isinstance(fib, type)
        assert isinstance(fib, PredicateMeta)

    def test_fields_preserved(self):
        # nv
        assert fib._fields == ("n", "f")

    def test_slots(self):
        # nv
        assert fib.__slots__ == ("n", "f")

    def test_missing_sentinel_identity(self):
        # nv
        assert _MISSING is not None

    def test_hash_is_structural(self):
        """P2 INVERTS this pin, and means to.

        The old instance was mutable, so it was deliberately unhashable.
        A cell is an immutable tuple, which is the whole point of the
        representation -- Prolog compounds do not change -- so it hashes,
        and it hashes STRUCTURALLY: equal terms have equal hashes."""
        # nv
        assert hash(fib(n=1, f=1)) == hash(("fib", 1, 1))
        assert hash(fib(n=1, f=1)) == hash(fib(n=1, f=1))


# ── Dataclass compatibility ──────────────────────────────────────────────────


class TestTermHelpers:
    """is_term_instance / term_field_names work for PredicateMeta classes."""

    def test_is_term_instance_true(self):
        # nv
        assert is_cell(fib(n=1, f=2))

    def test_is_term_instance_class_false(self):
        # nv
        from clausal.logic.predicate import is_term_instance
        assert not is_term_instance(fib)

    def test_term_field_names(self):
        # nv
        # P2: the CLASS names the fields of a cell it built; the cell
        # itself carries positions.
        assert fib._fields == ("n", "f")
        assert cell_arity(fib(n=1, f=2)) == len(fib._fields)

    def test_term_field_names_on_class(self):
        # nv
        assert fib._fields == ("n", "f")

    def test_zero_arity_fields(self):
        # atom() is atom (the class); use _fields directly
        # nv
        assert atom._fields == ()
        assert atom()._fields == ()  # same object

    def test_not_dataclass(self):
        """PredicateMeta classes should NOT pass dataclasses.is_dataclass."""
        # nv
        import dataclasses
        assert not dataclasses.is_dataclass(fib)
        assert not dataclasses.is_dataclass(fib(n=1, f=2))


# ── Atom identity (zero-arity) ───────────────────────────────────────────────


class red(metaclass=PredicateMeta):
    _fields = ()


class blue(metaclass=PredicateMeta):
    _fields = ()


class TestAtomIdentity:
    def test_call_returns_class(self):
        # nv
        assert red() is red

    def test_different_atoms_not_identical(self):
        # nv
        assert red is not blue

    def test_atom_is_hashable(self):
        # nv
        assert hash(red) == hash(red())
        assert {red: 1}[red()] == 1

    def test_atom_in_set(self):
        # nv
        s = {red, blue}
        assert red() in s
        assert blue() in s

    def test_unify_same_atom(self):
        # nv
        from clausal.logic.variables import Trail, unify
        trail = Trail()
        assert unify(red, red, trail)

    def test_unify_different_atoms_fails(self):
        # nv
        from clausal.logic.variables import Trail, unify
        trail = Trail()
        assert not unify(red, blue, trail)

    def test_unify_var_with_atom(self):
        # nv
        from clausal.logic.variables import Trail, unify, deref
        trail = Trail()
        x = Var()
        assert unify(x, red, trail)
        assert deref(x) is red

    def test_is_zero_field_class_helper(self):
        # nv
        # Task 12 renamed the zero-field-CLASS test out of the ``is_atom``
        # stem it shared with ``atoms.is_atom``, the TERM test.
        from clausal.logic.predicate import is_zero_field_class
        assert is_zero_field_class(red)
        assert is_zero_field_class(blue)
        assert not is_zero_field_class(fib)   # has fields
        assert not is_zero_field_class("str")
        assert not is_zero_field_class(42)

    def test_non_zero_arity_unchanged(self):
        """Predicates with fields still create instances as before."""
        # nv
        t = fib(n=1, f=2)
        assert t is not fib
        assert is_cell(t) and cell_functor(t) == "fib"
        assert _f(t, fib, "n") == 1


# ── make_atom ─────────────────────────────────────────────────────────────────


class TestMakeAtom:
    """``make_atom(spelling)`` returns the ATOM for that spelling.

    THE FLIP (spec §6.1): ``make_atom`` is ``mint`` under its API-continuity
    name, so it hands back the arity-0 CELL -- INVERTING the P3-3 Task 7 pin
    that it returned a plain ``str`` (which itself inverted the zero-arity
    ``PredicateMeta`` it used to mint).  ``make_predicate(name, [])`` is
    still how a caller asks for a /0 PREDICATE class.
    """

    def test_returns_the_atom_cell(self):
        # nv
        from clausal.logic.predicate import make_atom
        a = make_atom("a")
        assert a == mint("a")
        assert type(a) is str
        assert not isinstance(a, PredicateMeta)

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

    def test_zero_arity_predicate_class_is_no_longer_made_from_python(self):
        """``make_atom``'s old behaviour moved to ``make_predicate(name, [])``
        at P3-3 Task 7; W4b-3 slice 6 retired ``make_predicate``.  A 0-arity
        PREDICATE is a row named by its handle; the ATOM is ``make_atom``."""
        # nv
        from clausal.logic.predicate import (  # KEEP_MP
            MakePredicateRetiredError, make_predicate)
        with pytest.raises(MakePredicateRetiredError):
            make_predicate("a", [])  # KEEP_MP
        from clausal.logic.predicate import make_atom
        assert make_atom("a") == mint("a")
