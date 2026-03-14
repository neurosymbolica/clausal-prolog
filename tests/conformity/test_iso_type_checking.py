"""ISO Prolog conformity: type-checking predicates.

ISO §8.3 — var/1, nonvar/1, atom/1, integer/1, float/1, number/1,
           compound/1, callable/1.

Clausal equivalents:
  var/1, nonvar/1, atom/1, integer/1, float_/1, number/1,
  compound/1, callable/1, string/1, is_list/1, ground/1.

Differences from ISO:
  - atom/1: in ISO, atoms include symbols like 'foo' and [].
    In clausal, atom/1 tests for Python str.  [] is a list, not an atom.
  - float/1 is spelled float_/1 (avoids shadowing Python builtin).
  - string/1 is an alias for atom/1 (Python str = Prolog atom).
  - bool is excluded from integer/1 and number/1 (Python bool is int subclass,
    but logically distinct).
  - No atomic/1 — use number/1 or atom/1 separately.
  - Prolog's callable/1 includes atoms; clausal's callable/1 includes strings.
"""

from __future__ import annotations

import pytest
from clausal.logic.database import Module
from clausal.logic.solve import call, once
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, KWTerm


def _succeeds(functor, arg, mod=None):
    """True if builtin(arg) has at least one solution."""
    if mod is None:
        mod = Module("test")
    return once(
        __import__("clausal.terms", fromlist=["Call", "LoadName"]).Call(
            func=__import__("clausal.terms", fromlist=["LoadName"]).LoadName(name=functor),
            args=[arg], kwargs=[],
        ),
        mod,
    ) is not None


def succeeds(functor, arg):
    mod = Module("test")
    trail = Trail()
    results = list(call(functor, arg, module=mod, trail=trail))
    return len(results) > 0


def fails(functor, arg):
    return not succeeds(functor, arg)


# ── var/1, nonvar/1 ──────────────────────────────────────────────────────────
# ISO §8.3.1 / §8.3.2


class TestVar:
    def test_unbound_var_succeeds(self):
        assert succeeds("IsVar", Var())

    def test_bound_var_fails(self):
        """A Var that has been unified with a value is no longer var."""
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, 42, t)
        assert fails("IsVar", v)

    def test_integer_fails(self):
        assert fails("IsVar", 42)

    def test_atom_fails(self):
        assert fails("IsVar", "hello")

    def test_compound_fails(self):
        assert fails("IsVar", Compound("f", (1, 2)))


class TestNonvar:
    def test_integer_succeeds(self):
        assert succeeds("IsBound", 42)

    def test_atom_succeeds(self):
        assert succeeds("IsBound", "hello")

    def test_unbound_var_fails(self):
        assert fails("IsBound", Var())

    def test_bound_var_succeeds(self):
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, 42, t)
        assert succeeds("IsBound", v)

    def test_compound_succeeds(self):
        assert succeeds("IsBound", Compound("f", (1,)))

    def test_list_succeeds(self):
        assert succeeds("IsBound", [1, 2])


# ── atom/1 ────────────────────────────────────────────────────────────────────
# ISO §8.3.3
# In ISO: atom(X) succeeds for atoms (symbol tokens).
# In clausal: atom/1 tests for Python str.


class TestAtom:
    def test_string_succeeds(self):
        """ISO: atom(atom) succeeds.  Clausal: atom("atom") succeeds."""
        assert succeeds("IsStr", "atom")

    def test_empty_string_succeeds(self):
        """ISO: atom('') succeeds."""
        assert succeeds("IsStr", "")

    def test_integer_fails(self):
        """ISO: atom(1) fails."""
        assert fails("IsStr", 1)

    def test_float_fails(self):
        assert fails("IsStr", 1.0)

    def test_var_fails(self):
        """ISO: atom(X) fails when X unbound."""
        assert fails("IsStr", Var())

    def test_compound_fails(self):
        """ISO: atom(f(x)) fails."""
        assert fails("IsStr", Compound("f", ("x",)))

    def test_list_fails(self):
        """ISO: atom([]) succeeds ([] is an atom).
        DIFFERS: clausal atom([]) fails — [] is a list, not a string."""
        assert fails("IsStr", [])

    def test_bool_fails(self):
        """Python bool is not treated as atom in clausal."""
        assert fails("IsStr", True)


# ── integer/1, number/1, float_/1 ────────────────────────────────────────────
# ISO §8.3.4 / §8.3.5 / §8.3.6


class TestInteger:
    def test_positive_int(self):
        """ISO: integer(1) succeeds."""
        assert succeeds("IsInt", 1)

    def test_zero(self):
        assert succeeds("IsInt", 0)

    def test_negative_int(self):
        """ISO test 56: integer(- 1) succeeds.
        In clausal, -1 is a Python int literal."""
        assert succeeds("IsInt", -1)

    def test_large_int(self):
        """Python supports arbitrary-precision integers."""
        assert succeeds("IsInt", 10**100)

    def test_float_fails(self):
        """ISO: integer(1.0) fails."""
        assert fails("IsInt", 1.0)

    def test_atom_fails(self):
        assert fails("IsInt", "1")

    def test_var_fails(self):
        assert fails("IsInt", Var())

    def test_bool_fails(self):
        """DIFFERS from Python: True/False are int subclass but not integer/1."""
        assert fails("IsInt", True)
        assert fails("IsInt", False)

    def test_hex_literal(self):
        """ISO test 175 (partial): 0x1 = 1.  Python 0x1 is an int."""
        assert succeeds("IsInt", 0x1)

    def test_octal_literal(self):
        """ISO test 175 (partial): 0o1 = 1."""
        assert succeeds("IsInt", 0o1)

    def test_binary_literal(self):
        """ISO test 175 (partial): 0b1 = 1."""
        assert succeeds("IsInt", 0b1)


class TestFloat:
    def test_float_succeeds(self):
        """ISO: float(1.0) succeeds."""
        assert succeeds("IsFloat", 1.0)

    def test_zero_float(self):
        assert succeeds("IsFloat", 0.0)

    def test_negative_float(self):
        assert succeeds("IsFloat", -1.5)

    def test_scientific(self):
        """Python 1e9 is a float."""
        assert succeeds("IsFloat", 1e9)

    def test_int_fails(self):
        """ISO: float(1) fails."""
        assert fails("IsFloat", 1)

    def test_atom_fails(self):
        assert fails("IsFloat", "1.0")

    def test_var_fails(self):
        assert fails("IsFloat", Var())


class TestNumber:
    def test_int_succeeds(self):
        assert succeeds("IsNumber", 42)

    def test_float_succeeds(self):
        assert succeeds("IsNumber", 3.14)

    def test_negative_int(self):
        assert succeeds("IsNumber", -1)

    def test_atom_fails(self):
        assert fails("IsNumber", "42")

    def test_var_fails(self):
        assert fails("IsNumber", Var())

    def test_bool_fails(self):
        """DIFFERS: bool excluded from number/1."""
        assert fails("IsNumber", True)

    def test_complex_fails(self):
        """Python complex not treated as number."""
        assert fails("IsNumber", 1+2j)


# ── compound/1 ────────────────────────────────────────────────────────────────
# ISO §8.3.7


class TestCompound:
    def test_compound_succeeds(self):
        """ISO: compound(f(a)) succeeds."""
        assert succeeds("IsCompound", Compound("f", ("a",)))

    def test_arity2_succeeds(self):
        assert succeeds("IsCompound", Compound("g", (1, 2)))

    def test_kwterm_succeeds(self):
        assert succeeds("IsCompound", KWTerm("point", x=1, y=2))

    def test_atom_fails(self):
        """ISO: compound(a) fails (atom, not compound)."""
        assert fails("IsCompound", "a")

    def test_int_fails(self):
        assert fails("IsCompound", 42)

    def test_var_fails(self):
        assert fails("IsCompound", Var())

    def test_list_fails(self):
        """ISO: compound([a]) succeeds (it's ./2).
        DIFFERS: clausal lists are Python lists, not compound."""
        assert fails("IsCompound", [1, 2])

    def test_arity0_compound_is_compound(self):
        """DIFFERS from ISO: Prolog's compound(a) fails for arity-0.
        In clausal, Compound("f", ()) is still a compound term because the
        Compound object itself has structure (functor, args fields)."""
        assert succeeds("IsCompound", Compound("f", ()))


# ── callable/1 ────────────────────────────────────────────────────────────────
# ISO §8.3.8


class TestCallable:
    def test_atom_succeeds(self):
        """ISO: callable(a) succeeds."""
        assert succeeds("IsCallable", "hello")

    def test_compound_succeeds(self):
        """ISO: callable(f(x)) succeeds."""
        assert succeeds("IsCallable", Compound("f", ("x",)))

    def test_integer_fails(self):
        """ISO: callable(1) fails."""
        assert fails("IsCallable", 1)

    def test_var_fails(self):
        assert fails("IsCallable", Var())


# ── is_list/1 (non-ISO, common extension) ────────────────────────────────────


class TestIsList:
    def test_list_succeeds(self):
        assert succeeds("IsList", [1, 2, 3])

    def test_empty_list(self):
        assert succeeds("IsList", [])

    def test_nested_list(self):
        assert succeeds("IsList", [[1], [2]])

    def test_atom_fails(self):
        assert fails("IsList", "hello")

    def test_int_fails(self):
        assert fails("IsList", 42)

    def test_var_fails(self):
        assert fails("IsList", Var())


# ── ground/1 (non-ISO, common extension) ─────────────────────────────────────


class TestGround:
    def test_integer_ground(self):
        assert succeeds("IsGround", 42)

    def test_atom_ground(self):
        assert succeeds("IsGround", "abc")

    def test_list_of_ground(self):
        assert succeeds("IsGround", [1, 2, 3])

    def test_var_not_ground(self):
        assert fails("IsGround", Var())

    def test_compound_with_var_not_ground(self):
        assert fails("IsGround", Compound("f", (Var(),)))

    def test_list_with_var_not_ground(self):
        assert fails("IsGround", [1, Var(), 3])

    def test_empty_list_ground(self):
        assert succeeds("IsGround", [])

    def test_nested_ground(self):
        assert succeeds("IsGround", [[1, 2], [3, 4]])


# ── string/1 (non-ISO, clausal-specific) ─────────────────────────────────────


class TestString:
    def test_string_succeeds(self):
        assert succeeds("IsStr", "hello")

    def test_empty_string(self):
        assert succeeds("IsStr", "")

    def test_int_fails(self):
        assert fails("IsStr", 42)

    def test_var_fails(self):
        assert fails("IsStr", Var())
