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
        assert succeeds("var", Var())

    def test_bound_var_fails(self):
        """A Var that has been unified with a value is no longer var."""
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, 42, t)
        assert fails("var", v)

    def test_integer_fails(self):
        assert fails("var", 42)

    def test_atom_fails(self):
        assert fails("var", "hello")

    def test_compound_fails(self):
        assert fails("var", Compound("f", (1, 2)))


class TestNonvar:
    def test_integer_succeeds(self):
        assert succeeds("nonvar", 42)

    def test_atom_succeeds(self):
        assert succeeds("nonvar", "hello")

    def test_unbound_var_fails(self):
        assert fails("nonvar", Var())

    def test_bound_var_succeeds(self):
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, 42, t)
        assert succeeds("nonvar", v)

    def test_compound_succeeds(self):
        assert succeeds("nonvar", Compound("f", (1,)))

    def test_list_succeeds(self):
        assert succeeds("nonvar", [1, 2])


# ── atom/1 ────────────────────────────────────────────────────────────────────
# ISO §8.3.3
# In ISO: atom(X) succeeds for atoms (symbol tokens).
# In clausal: atom/1 tests for Python str.


class TestAtom:
    def test_string_succeeds(self):
        """ISO: atom(atom) succeeds.  Clausal: atom("atom") succeeds."""
        assert succeeds("atom", "atom")

    def test_empty_string_succeeds(self):
        """ISO: atom('') succeeds."""
        assert succeeds("atom", "")

    def test_integer_fails(self):
        """ISO: atom(1) fails."""
        assert fails("atom", 1)

    def test_float_fails(self):
        assert fails("atom", 1.0)

    def test_var_fails(self):
        """ISO: atom(X) fails when X unbound."""
        assert fails("atom", Var())

    def test_compound_fails(self):
        """ISO: atom(f(x)) fails."""
        assert fails("atom", Compound("f", ("x",)))

    def test_list_fails(self):
        """ISO: atom([]) succeeds ([] is an atom).
        DIFFERS: clausal atom([]) fails — [] is a list, not a string."""
        assert fails("atom", [])

    def test_bool_fails(self):
        """Python bool is not treated as atom in clausal."""
        assert fails("atom", True)


# ── integer/1, number/1, float_/1 ────────────────────────────────────────────
# ISO §8.3.4 / §8.3.5 / §8.3.6


class TestInteger:
    def test_positive_int(self):
        """ISO: integer(1) succeeds."""
        assert succeeds("integer", 1)

    def test_zero(self):
        assert succeeds("integer", 0)

    def test_negative_int(self):
        """ISO test 56: integer(- 1) succeeds.
        In clausal, -1 is a Python int literal."""
        assert succeeds("integer", -1)

    def test_large_int(self):
        """Python supports arbitrary-precision integers."""
        assert succeeds("integer", 10**100)

    def test_float_fails(self):
        """ISO: integer(1.0) fails."""
        assert fails("integer", 1.0)

    def test_atom_fails(self):
        assert fails("integer", "1")

    def test_var_fails(self):
        assert fails("integer", Var())

    def test_bool_fails(self):
        """DIFFERS from Python: True/False are int subclass but not integer/1."""
        assert fails("integer", True)
        assert fails("integer", False)

    def test_hex_literal(self):
        """ISO test 175 (partial): 0x1 = 1.  Python 0x1 is an int."""
        assert succeeds("integer", 0x1)

    def test_octal_literal(self):
        """ISO test 175 (partial): 0o1 = 1."""
        assert succeeds("integer", 0o1)

    def test_binary_literal(self):
        """ISO test 175 (partial): 0b1 = 1."""
        assert succeeds("integer", 0b1)


class TestFloat:
    def test_float_succeeds(self):
        """ISO: float(1.0) succeeds."""
        assert succeeds("float_", 1.0)

    def test_zero_float(self):
        assert succeeds("float_", 0.0)

    def test_negative_float(self):
        assert succeeds("float_", -1.5)

    def test_scientific(self):
        """Python 1e9 is a float."""
        assert succeeds("float_", 1e9)

    def test_int_fails(self):
        """ISO: float(1) fails."""
        assert fails("float_", 1)

    def test_atom_fails(self):
        assert fails("float_", "1.0")

    def test_var_fails(self):
        assert fails("float_", Var())


class TestNumber:
    def test_int_succeeds(self):
        assert succeeds("number", 42)

    def test_float_succeeds(self):
        assert succeeds("number", 3.14)

    def test_negative_int(self):
        assert succeeds("number", -1)

    def test_atom_fails(self):
        assert fails("number", "42")

    def test_var_fails(self):
        assert fails("number", Var())

    def test_bool_fails(self):
        """DIFFERS: bool excluded from number/1."""
        assert fails("number", True)

    def test_complex_fails(self):
        """Python complex not treated as number."""
        assert fails("number", 1+2j)


# ── compound/1 ────────────────────────────────────────────────────────────────
# ISO §8.3.7


class TestCompound:
    def test_compound_succeeds(self):
        """ISO: compound(f(a)) succeeds."""
        assert succeeds("compound", Compound("f", ("a",)))

    def test_arity2_succeeds(self):
        assert succeeds("compound", Compound("g", (1, 2)))

    def test_kwterm_succeeds(self):
        assert succeeds("compound", KWTerm("point", x=1, y=2))

    def test_atom_fails(self):
        """ISO: compound(a) fails (atom, not compound)."""
        assert fails("compound", "a")

    def test_int_fails(self):
        assert fails("compound", 42)

    def test_var_fails(self):
        assert fails("compound", Var())

    def test_list_fails(self):
        """ISO: compound([a]) succeeds (it's ./2).
        DIFFERS: clausal lists are Python lists, not compound."""
        assert fails("compound", [1, 2])

    def test_arity0_compound_is_compound(self):
        """DIFFERS from ISO: Prolog's compound(a) fails for arity-0.
        In clausal, Compound("f", ()) is still a compound term because the
        Compound object itself has structure (functor, args fields)."""
        assert succeeds("compound", Compound("f", ()))


# ── callable/1 ────────────────────────────────────────────────────────────────
# ISO §8.3.8


class TestCallable:
    def test_atom_succeeds(self):
        """ISO: callable(a) succeeds."""
        assert succeeds("callable", "hello")

    def test_compound_succeeds(self):
        """ISO: callable(f(x)) succeeds."""
        assert succeeds("callable", Compound("f", ("x",)))

    def test_integer_fails(self):
        """ISO: callable(1) fails."""
        assert fails("callable", 1)

    def test_var_fails(self):
        assert fails("callable", Var())


# ── is_list/1 (non-ISO, common extension) ────────────────────────────────────


class TestIsList:
    def test_list_succeeds(self):
        assert succeeds("is_list", [1, 2, 3])

    def test_empty_list(self):
        assert succeeds("is_list", [])

    def test_nested_list(self):
        assert succeeds("is_list", [[1], [2]])

    def test_atom_fails(self):
        assert fails("is_list", "hello")

    def test_int_fails(self):
        assert fails("is_list", 42)

    def test_var_fails(self):
        assert fails("is_list", Var())


# ── ground/1 (non-ISO, common extension) ─────────────────────────────────────


class TestGround:
    def test_integer_ground(self):
        assert succeeds("ground", 42)

    def test_atom_ground(self):
        assert succeeds("ground", "abc")

    def test_list_of_ground(self):
        assert succeeds("ground", [1, 2, 3])

    def test_var_not_ground(self):
        assert fails("ground", Var())

    def test_compound_with_var_not_ground(self):
        assert fails("ground", Compound("f", (Var(),)))

    def test_list_with_var_not_ground(self):
        assert fails("ground", [1, Var(), 3])

    def test_empty_list_ground(self):
        assert succeeds("ground", [])

    def test_nested_ground(self):
        assert succeeds("ground", [[1, 2], [3, 4]])


# ── string/1 (non-ISO, clausal-specific) ─────────────────────────────────────


class TestString:
    def test_string_succeeds(self):
        assert succeeds("string", "hello")

    def test_empty_string(self):
        assert succeeds("string", "")

    def test_int_fails(self):
        assert fails("string", 42)

    def test_var_fails(self):
        assert fails("string", Var())
