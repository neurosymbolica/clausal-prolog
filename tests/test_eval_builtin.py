"""Tests for the reserved ``eval_/2`` builtin — eager arithmetic evaluate-and-bind.

``eval_(EXPR, RESULT)`` evaluates EXPR with Python semantics and unifies the
result with RESULT.  It is the successor of the deprecated ``:=`` operator and
compiles to the same backend (``Evaluate`` node → ``ArithEval`` IR), so it is
eager (TRO-friendly, unit-aware, raises catchable Python exceptions) — unlike
``==``, which posts a deferred CLP constraint.
"""
import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


def _succeeds(mod, pred="Test"):
    return any(True for _ in call(pred, module=mod))


class TestEvalBuiltin:
    def test_eval_binds_fresh_var(self, tmp_path):
        # nv
        mod = _load(tmp_path, "eval_binds",
                    "Test <- (eval_(6 * 7, X), X == 42)\n")
        assert _succeeds(mod)

    def test_eval_bound_equal_succeeds(self, tmp_path):
        # nv
        mod = _load(tmp_path, "eval_bound_eq",
                    "Test <- eval_(1 + 2, 3)\n")
        assert _succeeds(mod)

    def test_eval_bound_unequal_fails(self, tmp_path):
        # nv
        mod = _load(tmp_path, "eval_bound_neq",
                    "Test <- eval_(1 + 2, 4)\n")
        assert not _succeeds(mod)

    def test_eval_zero_division_raises(self, tmp_path):
        """Python semantics: uncaught ZeroDivisionError propagates.

        Specifically ZeroDivisionError — not a predicate-resolution error —
        so this cannot pass while eval_/2 is unimplemented.
        """
        # nv
        mod = _load(tmp_path, "eval_zdiv_raw",
                    "Test <- eval_(1 // 0, _)\n")
        with pytest.raises(ZeroDivisionError):
            _succeeds(mod)

    def test_eval_zero_division_catchable(self, tmp_path):
        """Python semantics: ZeroDivisionError is interceptable by catch/3."""
        # nv
        mod = _load(tmp_path, "eval_zdiv",
                    'Test <- catch(eval_(1 // 0, _), _, 1 == 1)\n')
        assert _succeeds(mod)

    def test_eval_big_integer(self, tmp_path):
        # nv
        mod = _load(tmp_path, "eval_big",
                    "Test <- (eval_(10 ** 100, X), eval_(X + 1, Y), "
                    "Y == 10 ** 100 + 1)\n")
        assert _succeeds(mod)

    def test_eval_chained_dependency(self, tmp_path):
        """Eager left-to-right binding: later goals see earlier results."""
        # nv
        mod = _load(tmp_path, "eval_chain",
                    "Test <- (eval_(2 + 3, A), eval_(A * A, B), B == 25)\n")
        assert _succeeds(mod)

    def test_eval_units_division(self, tmp_path):
        """The case CLP ``==`` cannot do: Quantity / Quantity division."""
        # nv
        mod = _load(tmp_path, "eval_units",
                    "-import_from(py.units, [metre, second])\n"
                    "Test <- (eval_(20(metre), D), eval_(2(second), T), "
                    "eval_(D / T, V), ++(V.value) == 10.0)\n")
        assert _succeeds(mod)
