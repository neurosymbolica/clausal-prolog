"""Standard order of terms — the ordering behind sort/2, msort/2, setof/3 and
the ``*_by`` higher-order builtins.

The defect these tests pin down (todo/msort-orders-compound-integer-args-as-
strings.md): terms that Python cannot compare with ``<`` fell back to a
``(type name, repr)`` sort key, so a compound's *integer* arguments were
ordered by their decimal rendering — ``"15" < "2" < "9"``.  ``msort`` did not
raise; it returned a well-formed list in a confidently wrong order.

The fix is a real standard order key (``_standard_order_key``) shared by every
sort site, so a compound's arguments get exactly the comparison bare values
already get.
"""

from __future__ import annotations

import datetime as dt
from fractions import Fraction

import pytest

from clausal.logic.builtins._helpers import _standard_order_key
from clausal.logic.builtins.lists import _sort__2, _msort__2
from clausal.logic.compiler.globals_env import _set_of_sort_dedup
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, DictTerm, KWTerm, SetTerm


# ── Helpers ──────────────────────────────────────────────────────────────

def _run_list_builtin(fn, in_list):
    """Drive a deterministic (lst, out) list builtin; return the one output."""
    trail = Trail()
    out = Var()
    results = []
    for _cont, val in fn(None, "proceed", "fail", None, in_list, out, trail):
        if val is DONE:
            break
        results.append([deref(x) for x in deref(out)])
    assert len(results) == 1, f"expected one solution, got {results!r}"
    return results[0]


def _key_sorted(items):
    """Sort by the shared standard-order key alone (no ``sorted()`` fast path)."""
    return sorted(items, key=_standard_order_key)


def _c(f, *args):
    return Compound(f, tuple(args))


# ── The reported defect ──────────────────────────────────────────────────

class TestCompoundIntegerArguments:
    """A compound's integer arguments compare numerically, not as strings."""

    def test_msort_one_arg_compounds(self):
        got = _run_list_builtin(
            _msort__2, [_c("score", 15), _c("score", 2), _c("score", 9)])
        assert got == [_c("score", 2), _c("score", 9), _c("score", 15)]

    def test_msort_two_arg_compounds(self):
        got = _run_list_builtin(
            _msort__2, [_c("pt", 1, 15), _c("pt", 1, 2), _c("pt", 1, 9)])
        assert got == [_c("pt", 1, 2), _c("pt", 1, 9), _c("pt", 1, 15)]

    def test_msort_three_arg_compounds(self):
        a, b, c = _c("d", 2026, 1, 15), _c("d", 2026, 1, 2), _c("d", 2026, 1, 9)
        assert _run_list_builtin(_msort__2, [a, b, c]) == [b, c, a]

    def test_order_is_input_independent(self):
        """Two different input orders must produce the SAME correct output.

        The old repr order was also input-independent — it was just wrong.
        """
        a, b, c = _c("d", 2026, 1, 15), _c("d", 2026, 1, 2), _c("d", 2026, 1, 9)
        assert (_run_list_builtin(_msort__2, [a, b, c])
                == _run_list_builtin(_msort__2, [c, a, b])
                == [b, c, a])

    def test_kwterm_integer_fields(self):
        k15 = KWTerm("pt", x=1, y=15)
        k2 = KWTerm("pt", x=1, y=2)
        k9 = KWTerm("pt", x=1, y=9)
        assert _run_list_builtin(_msort__2, [k15, k2, k9]) == [k2, k9, k15]

    def test_dataclass_term_instance(self):
        """A declared term (dataclass-shaped instance) orders by its fields."""
        import dataclasses

        @dataclasses.dataclass(frozen=True)
        class money:
            amount: int

        got = _run_list_builtin(_msort__2, [money(15), money(2), money(9)])
        assert got == [money(2), money(9), money(15)]

    def test_sort_dedups_and_orders_compounds(self):
        got = _run_list_builtin(
            _sort__2, [_c("s", 15), _c("s", 2), _c("s", 15), _c("s", 9)])
        assert got == [_c("s", 2), _c("s", 9), _c("s", 15)]

    def test_sort_keeps_distinct_terms(self):
        """Regression guard from the todo: the terms are NOT equal."""
        got = _run_list_builtin(
            _sort__2, [_c("d", 2026, 1, 15), _c("d", 2026, 1, 2), _c("d", 2026, 1, 9)])
        assert len(got) == 3

    def test_setof_ordering_matches(self):
        a, b, c = _c("d", 2026, 1, 15), _c("d", 2026, 1, 2), _c("d", 2026, 1, 9)
        assert _set_of_sort_dedup([a, b, c, a]) == [b, c, a]

    def test_nested_compound_arguments(self):
        a, b = _c("w", _c("v", 15)), _c("w", _c("v", 9))
        assert _key_sorted([a, b]) == [b, a]

    def test_list_argument_inside_compound(self):
        a, b = _c("w", [2026, 1, 15]), _c("w", [2026, 1, 9])
        assert _key_sorted([a, b]) == [b, a]

    def test_float_and_int_arguments_compare_numerically(self):
        assert _key_sorted([_c("s", 10), _c("s", 2.5)]) == [_c("s", 2.5), _c("s", 10)]

    def test_fraction_argument(self):
        a, b = _c("s", Fraction(1, 2)), _c("s", Fraction(1, 3))
        assert _key_sorted([a, b]) == [b, a]


# ── Standard order across term kinds ─────────────────────────────────────

class TestStandardOrderShape:
    def test_compounds_order_by_arity_then_name_then_args(self):
        f1, g1, f2 = _c("f", 1), _c("g", 1), _c("f", 1, 1)
        assert _key_sorted([f2, g1, f1]) == [f1, g1, f2]

    def test_numbers_before_atoms_before_compounds(self):
        n, s, cmp_ = 3, "abc", _c("f", 1)
        assert _key_sorted([cmp_, s, n]) == [n, s, cmp_]

    def test_unbound_vars_sort_first(self):
        v = Var()
        assert _key_sorted([_c("f", 1), 3, v])[0] is v

    def test_bound_var_uses_its_value(self):
        """A bound Var is keyed by what it is bound to, not as a variable."""
        v, t = Var(), Trail()
        from clausal.logic.variables import unify
        unify(v, _c("s", 2), t)
        ordered = [deref(x) for x in _key_sorted([_c("s", 15), v])]
        assert ordered == [_c("s", 2), _c("s", 15)]

    def test_key_is_total_over_mixed_junk(self):
        """Every pair of keys must be comparable — no TypeError may escape."""
        items = [
            Var(), 1, 2.5, Fraction(1, 3), "atom", b"bytes", [1, 2], (1, 2),
            _c("f", 1), KWTerm("f", a=1), {"k": 1}, DictTerm({"k": 1}),
            SetTerm([1, 2]), dt.date(2020, 1, 1), None, object(),
        ]
        keys = [_standard_order_key(x) for x in items]
        for a in keys:
            for b in keys:
                a < b  # must not raise
        assert len(_key_sorted(items)) == len(items)

    def test_structural_containers_order_numerically(self):
        assert _key_sorted([[15], [2], [9]]) == [[2], [9], [15]]
        assert (_key_sorted([DictTerm({"k": 15}), DictTerm({"k": 2})])
                == [DictTerm({"k": 2}), DictTerm({"k": 15})])

    def test_repeated_calls_are_stable(self):
        items = [_c("f", 15), _c("f", 2), _c("f", 9)]
        assert _key_sorted(items) == _key_sorted(list(reversed(items)))


# ── Paths that were already correct must stay correct ────────────────────

class TestNoRegression:
    def test_bare_integers(self):
        assert _run_list_builtin(_msort__2, [15, 2, 9]) == [2, 9, 15]

    def test_lists_of_integers(self):
        got = _run_list_builtin(
            _msort__2, [[2026, 1, 15], [2026, 1, 2], [2026, 1, 9]])
        assert got == [[2026, 1, 2], [2026, 1, 9], [2026, 1, 15]]

    def test_strings(self):
        assert _run_list_builtin(_msort__2, ["c", "b", "a"]) == ["a", "b", "c"]

    def test_dates(self):
        a, b, c = dt.date(2021, 1, 1), dt.date(2019, 5, 5), dt.date(2020, 3, 3)
        assert _run_list_builtin(_msort__2, [a, b, c]) == [b, c, a]

    def test_duplicates_preserved_by_msort(self):
        got = _run_list_builtin(_msort__2, [_c("s", 2), _c("s", 2)])
        assert got == [_c("s", 2), _c("s", 2)]


# ── End to end, through the query path the todo reported it from ─────────

def _load_inline_clausal(name: str, source: str):
    """Write *source* to a temp .clausal file and load it as *name*.

    Kept out of ``tests/fixtures/`` (mirroring ``test_atom_diagnostics.py``)
    so pytest's ``.clausal`` collector does not also try to run it.
    """
    import os
    import tempfile
    from clausal.import_hook import _load_module

    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def test_msort_of_domain_local_compounds_end_to_end():
    """The todo's own repro: a module-declared ``pt/2`` sorted by ``msort/2``.

    ``msort`` never raised here — it returned ``[pt(1,15), pt(1,2), pt(1,9)]``,
    a well-formed list in decimal-string order.
    """
    mod = _load_inline_clausal(
        "_standard_order_msort_probe",
        "-module(_standard_order_msort_probe, [pt(A, B), two_arg(S)])\n"
        "\n"
        "two_arg(SORTED) <- msort([pt(1, 15), pt(1, 2), pt(1, 9)], SORTED)\n",
    )
    S = Var()
    got = [deref(S) for _ in mod.two_arg(S)]
    assert got == [[mod.pt(1, 2), mod.pt(1, 9), mod.pt(1, 15)]]
