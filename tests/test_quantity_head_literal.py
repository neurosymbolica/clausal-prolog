"""Regression tests: a `value(unit)` quantity in a clause HEAD must match.

Bug (2026-07-30): a units/currency amount in a clause head argument compiles
to a PyThunk (deferred lambda). PyThunk was not recognized by the structural
head-arg normalizer, so it fell through to the opaque-head-literal capture
(A02-F003) and the clause guarded against the thunk object itself — which no
runtime value ever unifies with, so the clause silently never fired. The same
amount in a body goal worked, masking the problem.
See todo/quantity-head-literal-compiles-to-a-pythunk-that-never-matches.md.
"""

import os

import pytest

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.modules.py.units import Metre
from clausal.terms import Quantity


@pytest.fixture(scope="module")
def mod():
    fixture = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "quantity_head_literal.clausal"
    )
    return _load_module("quantity_head_literal_mod", fixture).__dict__["$module"]


def _collect(name, out_vars, *args, module):
    snapshots = []
    for _ in call(name, *args, module=module):
        snapshots.append(tuple(deref(v) for v in out_vars))
    return snapshots


def _atom_names(snapshots):
    return [tuple(getattr(a, "__name__", a) for a in snap) for snap in snapshots]


class TestQuantityHeadLiteral:
    def test_input_mode_single_clause(self, mod):
        N = Var()
        assert _atom_names(_collect("Chk", [N], N, module=mod)) == [(mint("short_"),)]

    def test_output_mode_binds_quantity(self, mod):
        A = Var()
        sols = _collect("Amt", [A], A, module=mod)
        assert len(sols) == 1
        (q,) = sols[0]
        assert isinstance(q, Quantity)
        assert q == Quantity(5, {Metre: 1})

    def test_input_mode_selects_among_clauses(self, mod):
        N = Var()
        assert _atom_names(_collect("Pick", [N], N, module=mod)) == [(mint("long_"),)]

    def test_output_mode_enumerates_all_clauses(self, mod):
        A, N = Var(), Var()
        sols = _collect("Sel", [A, N], A, N, module=mod)
        quantities = [q for q, _ in sols]
        assert quantities == [
            Quantity(2, {Metre: 1}),
            Quantity(5, {Metre: 1}),
            Quantity(50, {Metre: 1}),
        ]

    def test_quantity_nested_in_head_list(self, mod):
        N = Var()
        assert _atom_names(_collect("ChkPack", [N], N, module=mod)) == [(mint("packed_"),)]


class TestOtherPyThunkHeadLiterals:
    """The hoist is keyed on the PyThunk type, so the currency spelling and
    the other thunk producers (f-strings, ++() escapes) take the same path."""

    def test_currency_head_literal(self, mod):
        N = Var()
        assert _atom_names(_collect("ChkPrice", [N], N, module=mod)) == [(mint("pricey_"),)]

    def test_fstring_head_literal(self, mod):
        N = Var()
        assert _atom_names(_collect("ChkTag", [N], N, module=mod)) == [(mint("tagged_"),)]

    def test_python_escape_head_literal(self, mod):
        N = Var()
        assert _atom_names(_collect("ChkEsc", [N], N, module=mod)) == [(mint("escd_"),)]


class TestQuantityClauseInIndexedPredicate:
    """The quantity clause keys as _INDEX_VAR and is merged into every
    argument-index bucket; the bucket compiler must not re-lift its hoisted
    Unify(Var, PyThunk) into the head (see _lift_clause_at_pos)."""

    def test_scalar_bucket_query_still_works(self, mod):
        N = Var()
        assert _atom_names(_collect("PickMix", [N], N, module=mod)) == [(mint("two_"),)]

    def test_quantity_clause_matches_alongside_indexed_clauses(self, mod):
        N = Var()
        assert _atom_names(_collect("PickQty", [N], N, module=mod)) == [(mint("qty_"),)]

    def test_output_mode_enumerates_mixed_clauses(self, mod):
        K, N = Var(), Var()
        names = _atom_names(_collect("Mix", [N], K, N, module=mod))
        assert names == [(mint("one_"),), (mint("two_"),), (mint("three_"),),
                         (mint("qty_"),)]
