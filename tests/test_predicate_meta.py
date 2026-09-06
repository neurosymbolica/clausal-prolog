"""Tests for clausal.logic.predicate — PredicateMeta metaclass (Phase 0)."""

import pytest

from clausal.logic.atoms import char_atom, mint
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
        assert t.n == 0
        assert t.f == 0

    def test_partial_kwargs_fills_var(self):
        # nv
        t = fib(n=5)
        assert t.n == 5
        assert is_var(t.f)

    def test_no_args_all_vars(self):
        # nv
        t = fib()
        assert is_var(t.n)
        assert is_var(t.f)

    def test_each_call_fresh_vars(self):
        # nv
        t1 = fib()
        t2 = fib()
        assert t1.n is not t2.n
        assert t1.f is not t2.f

    def test_positional_args(self):
        # nv
        t = fib(1, 2)
        assert t.n == 1
        assert t.f == 2

    def test_isinstance_works(self):
        """fib is a class, so isinstance works (unlike singleton pattern)."""
        # nv
        t = fib(n=0, f=1)
        assert isinstance(t, fib)

    def test_three_fields_partial(self):
        # nv
        t = point(x=1)
        assert t.x == 1
        assert is_var(t.y)
        assert is_var(t.z)

    def test_none_is_not_missing(self):
        """Explicitly passing None should NOT be replaced with Var()."""
        # nv
        t = fib(n=None, f=5)
        assert t.n is None
        assert t.f == 5

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
        assert repr(t) == "fib(n=1, f=2)"

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
        match t:
            case fib(n=1, f=f_val):
                assert f_val == 1
            case _:
                pytest.fail("Pattern match failed")


# ── Clause management ─────────────────────────────────────────────────────────


class pred_a(metaclass=PredicateMeta):
    _fields = ("x",)


class TestClauseManagement:
    def setup_method(self):
        pred_a._clauses = []
        pred_a._dispatch_fn = None
        pred_a._lazy_recompile = None
        pred_a._locked = False

    def test_assertz_appends(self):
        # nv
        c1 = Clause(head=pred_a(x=1), body=[])
        c2 = Clause(head=pred_a(x=2), body=[])
        pred_a._assertz(c1)
        pred_a._assertz(c2)
        assert pred_a._clauses == [c1, c2]

    def test_asserta_prepends(self):
        # nv
        c1 = Clause(head=pred_a(x=1), body=[])
        c2 = Clause(head=pred_a(x=2), body=[])
        pred_a._assertz(c1)
        pred_a._asserta(c2)
        assert pred_a._clauses == [c2, c1]

    def test_assertz_clears_dispatch(self):
        # nv
        with pred_a._mutate("test", "recompile"):   # the gate, P3-3 Task 3
            pred_a._dispatch_fn = lambda: None
        pred_a._assertz(Clause(head=pred_a(x=1), body=[]))
        assert pred_a._dispatch_fn is None

    def test_retract_removes_first_match(self):
        # nv
        h1 = pred_a(x=1)
        h2 = pred_a(x=2)
        pred_a._assertz(Clause(head=h1, body=[]))
        pred_a._assertz(Clause(head=h2, body=[]))
        assert pred_a._retract(h1) is True
        assert len(pred_a._clauses) == 1
        assert pred_a._clauses[0].head == h2

    def test_retract_nonexistent_returns_false(self):
        # nv
        pred_a._assertz(Clause(head=pred_a(x=1), body=[]))
        assert pred_a._retract(pred_a(x=99)) is False

    def test_retract_clears_dispatch(self):
        # nv
        h = pred_a(x=1)
        pred_a._assertz(Clause(head=h, body=[]))
        with pred_a._mutate("test", "recompile"):   # the gate, P3-3 Task 3
            pred_a._dispatch_fn = lambda: None
        pred_a._retract(h)
        assert pred_a._dispatch_fn is None


# ── Dispatch ──────────────────────────────────────────────────────────────────


class pred_b(metaclass=PredicateMeta):
    _fields = ("x",)


class TestDispatch:
    def setup_method(self):
        pred_b._clauses = []
        pred_b._dispatch_fn = None
        pred_b._lazy_recompile = None
        pred_b._locked = False

    def test_get_dispatch_returns_fn(self):
        # nv
        fn = lambda *a: iter([])
        with pred_b._mutate("test", "recompile"):   # the gate, P3-3 Task 3
            pred_b._dispatch_fn = fn
        assert pred_b._get_dispatch() is fn

    def test_get_dispatch_lazy_recompile(self):
        # nv
        fn = lambda *a: iter([])
        pred_b._lazy_recompile = lambda: fn
        result = pred_b._get_dispatch()
        assert result is fn
        assert pred_b._dispatch_fn is fn

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
            pred_b._dispatch_fn = lambda *a: iter([])
        pred_b._lazy_recompile = recompile
        pred_b._assertz(Clause(head=pred_b(x=1), body=[]))
        assert pred_b._dispatch_fn is None
        pred_b._get_dispatch()
        assert len(calls) == 1


# ── Locking ───────────────────────────────────────────────────────────────────


class pred_locked(metaclass=PredicateMeta):
    _fields = ("x",)


class TestLocking:
    def setup_method(self):
        pred_locked._clauses = []
        pred_locked._dispatch_fn = None
        pred_locked._lazy_recompile = None
        pred_locked._locked = False

    def test_starts_unlocked(self):
        # nv
        assert pred_locked._locked is False

    def test_lock(self):
        # nv
        pred_locked._lock()
        assert pred_locked._locked is True

    def test_unlock(self):
        # nv
        pred_locked._lock()
        pred_locked._unlock()
        assert pred_locked._locked is False

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
        assert len(pred_locked._clauses) == 1


# ── Isolation ─────────────────────────────────────────────────────────────────


class pred_x(metaclass=PredicateMeta):
    _fields = ("v",)


class pred_y(metaclass=PredicateMeta):
    _fields = ("v",)


class TestIsolation:
    def setup_method(self):
        pred_x._clauses = []
        pred_y._clauses = []
        pred_x._locked = False
        pred_y._locked = False

    def test_clauses_are_per_class(self):
        # nv
        pred_x._assertz(Clause(head=pred_x(v=1), body=[]))
        assert len(pred_x._clauses) == 1
        assert len(pred_y._clauses) == 0

    def test_locking_is_per_class(self):
        # nv
        pred_x._lock()
        assert pred_x._locked is True
        assert pred_y._locked is False


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
            fib._dispatch_fn = lambda: None
        r = repr(fib)
        assert "compiled" in r
        fib._dispatch_fn = None

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

    def test_hash_disabled(self):
        """Mutable terms should not be hashable by default."""
        # nv
        with pytest.raises(TypeError):
            hash(fib(n=1, f=1))


# ── Dataclass compatibility ──────────────────────────────────────────────────


class TestTermHelpers:
    """is_term_instance / term_field_names work for PredicateMeta classes."""

    def test_is_term_instance_true(self):
        # nv
        from clausal.logic.predicate import is_term_instance
        assert is_term_instance(fib(n=1, f=2))

    def test_is_term_instance_class_false(self):
        # nv
        from clausal.logic.predicate import is_term_instance
        assert not is_term_instance(fib)

    def test_term_field_names(self):
        # nv
        from clausal.logic.predicate import term_field_names
        assert term_field_names(fib(n=1, f=2)) == ("n", "f")

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

    def test_is_atom_helper(self):
        # nv
        from clausal.logic.predicate import is_atom
        assert is_atom(red)
        assert is_atom(blue)
        assert not is_atom(fib)   # has fields
        assert not is_atom("str")
        assert not is_atom(42)

    def test_non_zero_arity_unchanged(self):
        """Predicates with fields still create instances as before."""
        # nv
        t = fib(n=1, f=2)
        assert t is not fib
        assert isinstance(t, fib)
        assert t.n == 1


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
        assert type(a) is tuple and len(a) == 1 and type(a[0]) is str
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

    def test_zero_arity_predicate_class_comes_from_make_predicate(self):
        """The behaviour ``make_atom`` used to provide, at its new address."""
        # nv
        from clausal.logic.predicate import make_predicate
        a = make_predicate("a", [])
        assert isinstance(a, PredicateMeta)
        assert a._fields == ()
        assert a._arity == 0
        assert a() == a
