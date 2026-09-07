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

from clausal.logic.builtins._helpers import (
    _ORD_ATOM, _ORD_COMPOUND, _standard_order_key,
)
from clausal.logic.builtins.lists import _sort__2, _msort__2
from clausal.logic.compiler.globals_env import _set_of_sort_dedup
from clausal.logic.solve import solve
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, DictTerm, KWTerm, SetTerm
from clausal.logic.atoms import char_atom, is_atom, mint, spelling


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


# ── P3-1 Task 4: standard-order collapse (atom key shape) ────────────────

class TestAtomKeyCollapse:
    """``_standard_order_key``'s atom branch after the collapse.

    THE FLIP (spec §6.5): the ATOM is the arity-0 cell and keys
    ``(_ORD_ATOM, spelling)``; a ``str`` is a STRING and keys in the
    SEQUENCE band as the char list it denotes.  That INVERTS the P3-1
    "a str IS the atom, one key shape" reading below it -- what is still
    true, and what this class is really about, is that a zero-arity
    ``PredicateMeta`` class atom keys IDENTICALLY to the atom of the same
    spelling, not merely adjacently.  (``make_predicate(name, [])`` still
    legitimately produces that class: it is a general-purpose test/infra
    helper and the shape a bare 0-arity PREDICATE declared with call
    syntax -- ``-module(m, [p()])`` -- mints for real.)
    """

    def test_atom_key_shape_has_no_discriminator(self):
        assert _standard_order_key(mint("work")) == (_ORD_ATOM, "work")

    def test_string_keys_in_the_sequence_band_as_its_char_list(self):
        assert _standard_order_key("work") == _standard_order_key(
            [char_atom(c) for c in "work"]
        )
        assert _standard_order_key("work")[0] != _ORD_ATOM

    def test_class_atom_key_matches_same_spelled_atom_key(self):
        from clausal.logic.predicate import make_predicate

        atom_cls = make_predicate("work", [])
        assert _standard_order_key(atom_cls) == _standard_order_key(mint("work"))
        assert _standard_order_key(atom_cls) == (_ORD_ATOM, "work")

    def test_same_spelled_atom_and_class_atom_sort_adjacent_equal(self):
        from clausal.logic.predicate import make_predicate

        atom_cls = make_predicate("work", [])
        # Neither is ordered strictly before the other by the key.
        ordered = _key_sorted([mint("work"), atom_cls])
        assert {_standard_order_key(x) for x in ordered} == {(_ORD_ATOM, "work")}

    def test_mixed_atoms_strings_numbers_compounds_key_shape(self):
        """A representative mixed list: each rank keeps its own key shape."""
        items = [_c("f", 1), "zeta", "alpha", 3, Var(), 1.5]
        ordered = _key_sorted(items)
        ranks = [_standard_order_key(x)[0] for x in ordered]
        # Var < Number < Atom < ... < Compound, and stable within a rank.
        assert ranks == sorted(ranks)
        assert ordered[-1] == _c("f", 1)


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
    # P3-2 Task 2 (THE FLIP, R6): ``pt`` is a data functor, so the sorted
    # answers are cells.  The ORDER is what this test is about and it is
    # unchanged.
    assert got == [[("pt", 1, 2), ("pt", 1, 9), ("pt", 1, 15)]]


# ── P3-3 Task 3: cells in standard order — atoms in the atom band ────────


class TestCellStandardOrder:
    """A cell atom (arity 0, spec §5.1) keys IDENTICALLY to its str spelling
    (§6.5) -- a str atom and a cell atom are one atom in the order.  A cell
    of arity > 0 keys in the compound band, arity first (ISO 7.2.1), never
    as a sequence.
    """

    def test_cell_atom_keys_in_atom_band(self):
        assert _standard_order_key(("bar",)) == (_ORD_ATOM, "bar")
        assert _standard_order_key(("bar",)) == _standard_order_key(mint("bar"))

    def test_cell_keys_in_compound_band_arity_first(self):
        k = _standard_order_key(("f", 1, 2))
        assert k[0] == _ORD_COMPOUND and k[1] == 2 and k[2] == (0, "f")
        assert _standard_order_key(("f", 1, 2)) < _standard_order_key(("a", 1, 2, 3))
        assert _standard_order_key(("f", 1, 2)) > _standard_order_key([1, 2, 3])
        assert _standard_order_key(("f", 1)) != _standard_order_key(["f", 1])

    def test_msort_orders_number_atom_list_cell(self):   # §13 row 16 (Stage A form)
        # A cell goal requires a module (``_module_for_moduleless_solve``
        # raises ``existence_error`` for a moduleless cell goal) -- same
        # convention as ``tests/test_cell_goals.py``/``test_atoms_as_cells.py``:
        # a trivial loaded module supplies the module context; only the
        # ``msort`` builtin is exercised.  ``deref`` runs INSIDE the
        # ``solve`` iteration (as ``test_cell_goals.py`` does), not after
        # ``list()`` has exhausted the generator -- ``solve`` undoes its
        # trail bindings once the generator is exhausted, same as any other
        # backtracking choice point.
        mod = _load_inline_clausal("_standard_order_cell_msort_probe", "z0,\n")
        lm = mod.__dict__["$module"]
        out = Var()
        answers = [deref(out)
                   for _ in solve(("msort", [("f", "x"), [1], ("b",), 1], out), lm)]
        assert len(answers) == 1
        assert answers[0] == [1, ("b",), [1], ("f", "x")]


# ── sort/2's dedup is linear, not quadratic ──────────────────────────────

class TestSortDedupCost:
    """``sort/2`` deduped by scanning a LIST of standard-order keys, which is
    O(n^2) tuple comparisons.  The keys are hashable in every band but
    ``_ORD_OTHER``, so the seen-set is a set and only the unhashable keys
    (``_OpaqueOrder``) pay the scan."""

    def test_many_distinct_strings_sort_in_linear_time(self):
        """The bound has to be able to FAIL: at 2000 elements the old list
        scan cost 0.13 s, which no generous bound separates from the 0.004 s
        the set costs.  At 20000 the quadratic scan alone is ~11.8 s against
        0.045 s, so a 2 s bound is 5x under the old cost and 40x over the
        new one — discriminating and still loose enough not to flake."""
        # nv
        import time

        items = [f"s{i:06d}" for i in range(20000)]
        start = time.perf_counter()
        got = _run_list_builtin(_sort__2, list(items))
        elapsed = time.perf_counter() - start
        assert got == sorted(items)
        assert elapsed < 2.0, f"sort/2 over {len(items)} strings took {elapsed:.2f}s"

    def test_unhashable_keys_still_dedup(self):
        """A ``date`` keys through ``_OpaqueOrder``, which has ``__eq__`` and
        no ``__hash__`` — the list fallback must still remove the duplicate."""
        # nv
        import datetime

        d1, d2 = datetime.date(2026, 1, 2), datetime.date(2026, 1, 15)
        got = _run_list_builtin(_sort__2, [d2, d1, d2, d1])
        assert got == [d1, d2]

    def test_mixed_hashable_and_unhashable_keys_dedup_independently(self):
        # nv
        import datetime

        d = datetime.date(2026, 1, 2)
        got = _run_list_builtin(_sort__2, [3, d, 3, "ab", d, "ab"])
        assert len(got) == 3
        assert 3 in got and d in got and "ab" in got

    def test_a_string_and_its_char_list_are_one_term(self):
        """The property the dedup exists for (spec §6.5) survives the set."""
        # nv
        got = _run_list_builtin(
            _sort__2, ["ab", [char_atom("a"), char_atom("b")], "ab"])
        assert len(got) == 1
