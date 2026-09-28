"""ISO Prolog conformity: type-checking — Python-only cases.

Ground-literal behavior tests have moved to
``tests/conformity/iso_type_checking.clausal``.

What stays here:

- Tests that pass a cell or ``KWTerm(...)`` as the argument —
  these cannot be constructed at clausal surface syntax (``f(x)`` in an
  argument position would resolve as a predicate call, not a term).
- Tests involving ``bool`` (True/False) and ``complex`` literals, which
  intentionally differ from Python's is-a relationships (``bool`` is-a
  ``int``; clausal excludes bool from ``integer/1``/``number/1``).
- Tests asserting on post-unification state of a ``Var``.
- Tests passing a negative integer literal: ``-1`` is parsed as
  ``Negate(1)`` at clausal surface, so ``integer(-1)`` in .clausal would
  test structural compound, not Python ``int``.
"""

from __future__ import annotations

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.database import Module
from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, unify
from clausal.terms import KWTerm


def _succeeds(functor, arg):
    mod = Module("test")
    trail = Trail()
    return len(list(call(functor, arg, module=mod, trail=trail))) > 0


def _fails(functor, arg):
    return not _succeeds(functor, arg)


# ── var/nonvar post-binding state ───────────────────────────────────────────


class TestVarPostBinding:
    def test_bound_var_not_var(self):
        v = Var()
        unify(v, 42, Trail())
        assert _fails("var", v)

    def test_bound_var_is_nonvar(self):
        v = Var()
        unify(v, 42, Trail())
        assert _succeeds("nonvar", v)


# ── Compound (cell) / KWTerm arguments ─────────────────────────────────────────────


class TestCompoundArgs:
    def test_var_fails_compound(self):
        assert _fails("var", ("f", 1, 2))

    def test_nonvar_succeeds_compound(self):
        assert _succeeds("nonvar", ("f", 1))

    def test_atom_fails_for_compound(self):
        assert _fails("is_str", ("f", "x"))

    def test_compound_succeeds(self):
        assert _succeeds("compound", ("f", "a"))

    def test_compound_arity2(self):
        assert _succeeds("compound", ("g", 1, 2))

    @pytest.mark.compound_retirement_slice9
    def test_compound_kwterm(self):
        assert _succeeds("compound", KWTerm("point", x=1, y=2))

    def test_compound_atom_fails(self):
        assert _fails("compound", mint("a"))

    def test_compound_int_fails(self):
        assert _fails("compound", 42)

    def test_compound_var_fails(self):
        assert _fails("compound", Var())

    def test_compound_list_succeeds(self):
        """Task 15 item 2 (ISO alignment, 2026-09-07): a non-empty list is
        the ``'.'/2`` compound, as ISO 7.1.6 has it and as Scryer answers —
        and so is a STRING, which is the list of its characters.  The empty
        list is the atom ``'[]'`` and is not compound."""
        assert _succeeds("compound", [1, 2])
        assert _succeeds("compound", chars("a"))
        assert _fails("compound", [])
        assert _fails("compound", chars(""))

    def test_callable_compound(self):
        assert _succeeds("callable_", ("f", "x"))

    def test_ground_compound_with_var(self):
        assert _fails("ground", ("f", Var()))


# ── bool / complex edge cases (Python-level literals) ──────────────────────


class TestBoolComplex:
    def test_bool_not_integer(self):
        """DIFFERS from Python: True/False are int subclass but fail integer/1."""
        assert _fails("integer", True)
        assert _fails("integer", False)

    def test_bool_not_number(self):
        assert _fails("number", True)

    def test_bool_not_atom(self):
        assert _fails("is_str", True)

    def test_complex_not_number(self):
        assert _fails("number", 1 + 2j)


# ── negative integer literal (parsed as Negate(1) at clausal surface) ─────


class TestNegativeIntegerLiteral:
    def test_negative_integer(self):
        assert _succeeds("integer", -1)

    def test_negative_number(self):
        assert _succeeds("number", -1)

    def test_negative_float(self):
        assert _succeeds("float_", -1.5)
