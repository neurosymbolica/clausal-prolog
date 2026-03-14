"""Tests for .clausal module files: meta-predicates, higher-order, lambdas.

These tests validate that predicates defined in .clausal files using
meta-predicates (find_all, bag_of, set_of, for_all), higher-order list
builtins (map_list, include, exclude, foldl), and lambdas (arrow syntax,
variable capture, conjunction bodies) work correctly end-to-end through
the import hook and compiled dispatch.
"""

from __future__ import annotations

import os

import pytest

from clausal.logic.database import Module
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var, Trail, deref

import clausal.import_hook
from clausal.import_hook import _load_module


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_clausal_module(filename: str) -> Module:
    """Load a .clausal file from tests/clausal_modules/ and return its LogicModule."""
    path = os.path.join(os.path.dirname(__file__), "clausal_modules", filename)
    name = f"_test_cm_{filename.replace('.', '_')}"
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _call_collect(functor: str, *args, mod: Module) -> list:
    """Call functor with args, collect deref'd value of last Var arg."""
    var = args[-1]
    return [_deref_walk(var) for _ in call(functor, *args, module=mod)]


def _call_succeeds(functor: str, *args, mod: Module) -> int:
    """Call functor with args, return number of solutions."""
    return len(list(call(functor, *args, module=mod)))


# ══════════════════════════════════════════════════════════════════════════════
# Meta-predicates (meta.clausal)
# ══════════════════════════════════════════════════════════════════════════════


class TestMetaSquares:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_squares_basic(self):
        r = Var()
        assert _call_collect("Squares", [1, 2, 3], r, mod=self.mod) == [[1, 4, 9]]

    def test_squares_empty(self):
        r = Var()
        assert _call_collect("Squares", [], r, mod=self.mod) == [[]]

    def test_squares_single(self):
        r = Var()
        assert _call_collect("Squares", [5], r, mod=self.mod) == [[25]]

    def test_squares_negative(self):
        r = Var()
        assert _call_collect("Squares", [-2, 3], r, mod=self.mod) == [[4, 9]]


class TestMetaPositives:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_positives_mixed(self):
        r = Var()
        assert _call_collect("Positives", [-1, 2, -3, 4], r, mod=self.mod) == [[2, 4]]

    def test_positives_all_negative(self):
        r = Var()
        assert _call_collect("Positives", [-1, -2, -3], r, mod=self.mod) == [[]]

    def test_positives_all_positive(self):
        r = Var()
        assert _call_collect("Positives", [1, 2, 3], r, mod=self.mod) == [[1, 2, 3]]

    def test_positives_with_zero(self):
        r = Var()
        assert _call_collect("Positives", [0, 1, -1], r, mod=self.mod) == [[1]]


class TestMetaUniqueMembers:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_unique_dedup(self):
        r = Var()
        assert _call_collect("UniqueMembers", [1, 2, 1, 3, 2], r, mod=self.mod) == [[1, 2, 3]]

    def test_unique_already_unique(self):
        r = Var()
        assert _call_collect("UniqueMembers", [5, 10, 15], r, mod=self.mod) == [[5, 10, 15]]

    def test_unique_single(self):
        r = Var()
        assert _call_collect("UniqueMembers", [7, 7, 7], r, mod=self.mod) == [[7]]


class TestMetaAllPositive:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_all_positive_succeeds(self):
        assert _call_succeeds("AllPositive", [1, 2, 3], mod=self.mod) == 1

    def test_all_positive_fails(self):
        assert _call_succeeds("AllPositive", [1, -2, 3], mod=self.mod) == 0

    def test_all_positive_empty(self):
        # for_all with no solutions is vacuously true
        assert _call_succeeds("AllPositive", [], mod=self.mod) == 1


class TestMetaSumSquares:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_sum_squares(self):
        r = Var()
        assert _call_collect("SumSquares", [1, 2, 3], r, mod=self.mod) == [14]

    def test_sum_squares_empty(self):
        r = Var()
        assert _call_collect("SumSquares", [], r, mod=self.mod) == [0]


class TestMetaEvens:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_evens(self):
        r = Var()
        assert _call_collect("Evens", [1, 2, 3, 4, 5, 6], r, mod=self.mod) == [[2, 4, 6]]

    def test_evens_none(self):
        r = Var()
        assert _call_collect("Evens", [1, 3, 5], r, mod=self.mod) == [[]]


class TestMetaCountSolutions:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_count(self):
        r = Var()
        assert _call_collect("CountSolutions", [10, 20, 30], r, mod=self.mod) == [3]

    def test_count_empty(self):
        r = Var()
        assert _call_collect("CountSolutions", [], r, mod=self.mod) == [0]


class TestMetaPairs:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_pairs_cartesian(self):
        r = Var()
        results = _call_collect("Pairs", ["a", "b"], [1, 2], r, mod=self.mod)
        assert results == [[["a", 1], ["a", 2], ["b", 1], ["b", 2]]]

    def test_pairs_empty_first(self):
        r = Var()
        assert _call_collect("Pairs", [], [1, 2], r, mod=self.mod) == [[]]

    def test_pairs_empty_second(self):
        r = Var()
        assert _call_collect("Pairs", ["a"], [], r, mod=self.mod) == [[]]


class TestMetaAllMembers:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_all_members_subset(self):
        assert _call_succeeds("AllMembers", [1, 2], [1, 2, 3], mod=self.mod) == 1

    def test_all_members_not_subset(self):
        assert _call_succeeds("AllMembers", [1, 4], [1, 2, 3], mod=self.mod) == 0

    def test_all_members_empty_sub(self):
        assert _call_succeeds("AllMembers", [], [1, 2, 3], mod=self.mod) == 1


class TestMetaBagPositives:
    def setup_method(self):
        self.mod = _load_clausal_module("meta.clausal")

    def test_bag_positives(self):
        r = Var()
        assert _call_collect("BagPositives", [-1, 2, -3, 4], r, mod=self.mod) == [[2, 4]]

    def test_bag_positives_fails_on_none(self):
        r = Var()
        # bag_of fails when no solutions
        assert _call_collect("BagPositives", [-1, -2, -3], r, mod=self.mod) == []


# ══════════════════════════════════════════════════════════════════════════════
# Higher-order list predicates (higher_order.clausal)
# ══════════════════════════════════════════════════════════════════════════════


class TestHigherOrderDoubles:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_doubles(self):
        r = Var()
        assert _call_collect("Doubles", [1, 2, 3], r, mod=self.mod) == [[2, 4, 6]]

    def test_doubles_empty(self):
        r = Var()
        assert _call_collect("Doubles", [], r, mod=self.mod) == [[]]

    def test_doubles_negative(self):
        r = Var()
        assert _call_collect("Doubles", [-1, 0, 5], r, mod=self.mod) == [[-2, 0, 10]]


class TestHigherOrderAllPositive:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_all_positive_pass(self):
        assert _call_succeeds("AllPositive", [1, 2, 3], mod=self.mod) == 1

    def test_all_positive_fail(self):
        assert _call_succeeds("AllPositive", [1, -2, 3], mod=self.mod) == 0

    def test_all_positive_empty(self):
        assert _call_succeeds("AllPositive", [], mod=self.mod) == 1


class TestHigherOrderKeepPositive:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_keep_positive(self):
        r = Var()
        assert _call_collect("KeepPositive", [1, -2, 3, -4], r, mod=self.mod) == [[1, 3]]

    def test_keep_positive_none(self):
        r = Var()
        assert _call_collect("KeepPositive", [-1, -2], r, mod=self.mod) == [[]]

    def test_keep_positive_all(self):
        r = Var()
        assert _call_collect("KeepPositive", [5, 10], r, mod=self.mod) == [[5, 10]]


class TestHigherOrderRemoveNegative:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_remove_negative(self):
        r = Var()
        assert _call_collect("RemoveNegative", [1, -2, 3, -4], r, mod=self.mod) == [[1, 3]]

    def test_remove_negative_none(self):
        r = Var()
        assert _call_collect("RemoveNegative", [1, 2, 3], r, mod=self.mod) == [[1, 2, 3]]


class TestHigherOrderSumListFold:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_sum(self):
        r = Var()
        assert _call_collect("SumListFold", [1, 2, 3], r, mod=self.mod) == [6]

    def test_sum_empty(self):
        r = Var()
        assert _call_collect("SumListFold", [], r, mod=self.mod) == [0]

    def test_sum_single(self):
        r = Var()
        assert _call_collect("SumListFold", [42], r, mod=self.mod) == [42]


class TestHigherOrderProductList:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_product(self):
        r = Var()
        assert _call_collect("ProductList", [2, 3, 4], r, mod=self.mod) == [24]

    def test_product_empty(self):
        r = Var()
        assert _call_collect("ProductList", [], r, mod=self.mod) == [1]

    def test_product_with_zero(self):
        r = Var()
        assert _call_collect("ProductList", [5, 0, 3], r, mod=self.mod) == [0]


class TestHigherOrderSquares:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_squares(self):
        r = Var()
        assert _call_collect("Squares", [1, 2, 3, 4], r, mod=self.mod) == [[1, 4, 9, 16]]


class TestHigherOrderKeepEven:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_keep_even(self):
        r = Var()
        assert _call_collect("KeepEven", [1, 2, 3, 4, 5, 6], r, mod=self.mod) == [[2, 4, 6]]

    def test_keep_even_none(self):
        r = Var()
        assert _call_collect("KeepEven", [1, 3, 5], r, mod=self.mod) == [[]]


class TestHigherOrderRemoveEven:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_remove_even(self):
        r = Var()
        assert _call_collect("RemoveEven", [1, 2, 3, 4, 5], r, mod=self.mod) == [[1, 3, 5]]


class TestHigherOrderNegateList:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_negate(self):
        r = Var()
        assert _call_collect("NegateList", [1, -2, 3], r, mod=self.mod) == [[-1, 2, -3]]

    def test_negate_empty(self):
        r = Var()
        assert _call_collect("NegateList", [], r, mod=self.mod) == [[]]


class TestHigherOrderCountFold:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_count(self):
        r = Var()
        assert _call_collect("CountFold", [10, 20, 30, 40], r, mod=self.mod) == [4]

    def test_count_empty(self):
        r = Var()
        assert _call_collect("CountFold", [], r, mod=self.mod) == [0]


class TestHigherOrderMaxFold:
    def setup_method(self):
        self.mod = _load_clausal_module("higher_order.clausal")

    def test_max_fold(self):
        r = Var()
        assert _call_collect("MaxFold", [3, 7, 2, 9, 1], 0, r, mod=self.mod) == [9]

    def test_max_fold_single(self):
        r = Var()
        assert _call_collect("MaxFold", [5], 0, r, mod=self.mod) == [5]

    def test_max_fold_init_wins(self):
        r = Var()
        assert _call_collect("MaxFold", [1, 2], 100, r, mod=self.mod) == [100]


# ══════════════════════════════════════════════════════════════════════════════
# Lambdas (lambdas.clausal)
# ══════════════════════════════════════════════════════════════════════════════


class TestLambdaApplyVal:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_apply_val(self):
        r = Var()
        assert _call_collect("ApplyVal", r, 42, mod=self.mod) == [42]

    def test_apply_val_string(self):
        r = Var()
        assert _call_collect("ApplyVal", r, "hello", mod=self.mod) == ["hello"]


class TestLambdaAddOne:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_add_one(self):
        r = Var()
        assert _call_collect("AddOne", 5, r, mod=self.mod) == [6]

    def test_add_one_negative(self):
        r = Var()
        assert _call_collect("AddOne", -1, r, mod=self.mod) == [0]


class TestLambdaAddZ:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_add_z(self):
        r = Var()
        assert _call_collect("AddZ", 3, 10, r, mod=self.mod) == [13]

    def test_add_z_zero(self):
        r = Var()
        assert _call_collect("AddZ", 0, 7, r, mod=self.mod) == [7]


class TestLambdaDoubleVal:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_double_val(self):
        r = Var()
        assert _call_collect("DoubleVal", 5, r, mod=self.mod) == [10]


class TestLambdaZeroArg:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_zero_arg(self):
        r = Var()
        assert _call_collect("ZeroArg", r, mod=self.mod) == [42]


class TestLambdaTransform:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_transform(self):
        """Transform(5, Y): T := 5 + 1 = 6, Y := 6 * 2 = 12"""
        r = Var()
        assert _call_collect("Transform", 5, r, mod=self.mod) == [12]

    def test_transform_zero(self):
        """Transform(0, Y): T := 0 + 1 = 1, Y := 1 * 2 = 2"""
        r = Var()
        assert _call_collect("Transform", 0, r, mod=self.mod) == [2]


class TestLambdaCaptureTwo:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_capture_two(self):
        """CaptureTwo(10, 20, 5, R): R := 5 + 10 + 20 = 35"""
        r = Var()
        assert _call_collect("CaptureTwo", 10, 20, 5, r, mod=self.mod) == [35]


class TestLambdaApplyPred:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_apply_pred(self):
        """ApplyPred(3, Y): Helper(3, Y) → Y := 3 * 10 = 30"""
        r = Var()
        assert _call_collect("ApplyPred", 3, r, mod=self.mod) == [30]


class TestLambdaAllColors:
    def setup_method(self):
        self.mod = _load_clausal_module("lambdas.clausal")

    def test_all_colors(self):
        r = Var()
        results = _call_collect("AllColors", r, mod=self.mod)
        assert results == [["red", "green", "blue"]]


# ══════════════════════════════════════════════════════════════════════════════
# Term inspection builtins (term_inspection.clausal) — V2-13
# ══════════════════════════════════════════════════════════════════════════════


class TestTermInspectionCopyFresh:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_copy_ground_term(self):
        from clausal.terms import Compound
        term = Compound("foo", (1, 2))
        r = Var()
        result = _call_collect("CopyFresh", term, r, mod=self.mod)
        assert len(result) == 1
        assert result[0] == Compound("foo", (1, 2))

    def test_copy_returns_fresh_copy(self):
        from clausal.terms import Compound
        from clausal.logic.variables import is_var
        x = Var()
        term = Compound("f", (x,))
        r = Var()
        result = _call_collect("CopyFresh", term, r, mod=self.mod)
        assert len(result) == 1
        c = result[0]
        assert isinstance(c, Compound)
        assert is_var(c.args[0])
        assert c.args[0] is not x

    def test_copy_atom(self):
        r = Var()
        result = _call_collect("CopyFresh", "hello", r, mod=self.mod)
        assert result == ["hello"]

    def test_copy_integer(self):
        r = Var()
        result = _call_collect("CopyFresh", 42, r, mod=self.mod)
        assert result == [42]

    def test_copy_list(self):
        r = Var()
        result = _call_collect("CopyFresh", [1, 2, 3], r, mod=self.mod)
        assert result == [[1, 2, 3]]


class TestTermInspectionHasNoVars:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_ground_term_no_vars(self):
        from clausal.terms import Compound
        assert _call_succeeds("HasNoVars", Compound("f", (1, 2)), mod=self.mod) == 1

    def test_ground_atom(self):
        assert _call_succeeds("HasNoVars", "hello", mod=self.mod) == 1

    def test_term_with_var_fails(self):
        from clausal.terms import Compound
        term = Compound("f", (Var(),))
        assert _call_succeeds("HasNoVars", term, mod=self.mod) == 0

    def test_ground_list(self):
        assert _call_succeeds("HasNoVars", [1, 2, 3], mod=self.mod) == 1

    def test_list_with_var_fails(self):
        assert _call_succeeds("HasNoVars", [1, Var(), 3], mod=self.mod) == 0


class TestTermInspectionCountVars:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_no_vars(self):
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("CountVars", Compound("f", (1, 2)), r, mod=self.mod)
        assert result == [0]

    def test_one_var(self):
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("CountVars", Compound("f", (Var(),)), r, mod=self.mod)
        assert result == [1]

    def test_two_vars(self):
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("CountVars", Compound("f", (Var(), Var())), r, mod=self.mod)
        assert result == [2]

    def test_repeated_var_counts_once(self):
        from clausal.terms import Compound
        x = Var()
        r = Var()
        result = _call_collect("CountVars", Compound("f", (x, x)), r, mod=self.mod)
        assert result == [1]

    def test_list_vars(self):
        r = Var()
        result = _call_collect("CountVars", [Var(), Var(), Var()], r, mod=self.mod)
        assert result == [3]


class TestTermInspectionNumberAndCount:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_no_vars(self):
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("NumberAndCount", Compound("f", (1, 2)), 0, r, mod=self.mod)
        assert result == [0]

    def test_one_var(self):
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("NumberAndCount", Compound("f", (Var(),)), 0, r, mod=self.mod)
        assert result == [1]

    def test_start_offset(self):
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("NumberAndCount", Compound("f", (Var(), Var())), 5, r, mod=self.mod)
        assert result == [7]

    def test_two_vars_consecutive(self):
        r = Var()
        result = _call_collect("NumberAndCount", [Var(), Var()], 0, r, mod=self.mod)
        assert result == [2]


class TestTermInspectionCopyShared:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_sharing_preserved(self):
        """f(X, X) copied: the two args in copy should be the same fresh Var."""
        from clausal.terms import Compound
        from clausal.logic.variables import is_var
        x = Var()
        term = Compound("f", (x, x))
        a, b = Var(), Var()
        shared = []
        for _ in call("CopyShared", term, a, b, module=self.mod):
            shared.append((deref(a), deref(b)))
        assert len(shared) == 1
        av, bv = shared[0]
        assert is_var(av) and is_var(bv)
        assert av is bv

    def test_sharing_independent_from_original(self):
        """Fresh vars in copy are distinct from original Var."""
        from clausal.terms import Compound
        from clausal.logic.variables import is_var
        x = Var()
        term = Compound("f", (x, x))
        a, b = Var(), Var()
        captured = []
        for _ in call("CopyShared", term, a, b, module=self.mod):
            captured.append(deref(a))
        assert len(captured) == 1
        assert captured[0] is not x


class TestTermInspectionVarList:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_empty_list(self):
        r = Var()
        result = _call_collect("VarList", [], r, mod=self.mod)
        assert result == [[]]

    def test_list_no_vars(self):
        r = Var()
        result = _call_collect("VarList", [1, 2, 3], r, mod=self.mod)
        assert result == [[]]

    def test_list_with_vars(self):
        from clausal.logic.variables import is_var
        x, y = Var(), Var()
        r = Var()
        results = []
        for _ in call("VarList", [1, x, 2, y], r, module=self.mod):
            vs = _deref_walk(r)
            results.append(vs)
        assert len(results) == 1
        assert len(results[0]) == 2
        assert all(is_var(v) for v in results[0])
