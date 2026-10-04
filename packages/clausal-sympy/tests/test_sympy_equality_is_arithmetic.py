"""``==`` in a goal is arithmetic (CLP), not symbolic equality.

The package docs (docs/sympy.md, "Symbolic equality") say exactly this:
``R == <expr>`` with ``R`` bound to a SymPy result raises
``domain_error(clpz_expression, ...)``; a numeric result collapses to a
plain Python number, so ``R == 0`` still works with ``==``; and
``sym_equal/2`` is the symbolic comparison.  These tests pin all three
(ruled 2026-10-04: no engine change)."""

from __future__ import annotations

import pytest

pytest.importorskip("sympy", reason="sympy not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


SRC = """\
-import_from(sympy, [expand, simplify, sym_equal])
eq_symbolic() <- (expand((X + 1)**2, R), R == X**2 + 2*X + 1)
eq_symbolic_caught(K) <- catch(
    (expand((X + 1)**2, R), R == X**2 + 2*X + 1),
    error(domain_error(K, _), _), True)
eq_numeric() <- (simplify(X - X, R), R == 0)
sym_equal_holds() <- (expand((X + 1)**2, R), sym_equal(R, X**2 + 2*X + 1))
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("sympy_eq") / f"sympy_eq_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    mod = _load_module("sympy_eq_probe", str(src))
    return mod.__dict__["$module"]


def test_double_equals_on_a_sympy_result_raises_domain_error(module):
    with pytest.raises(LogicException) as info:
        list(call("eq_symbolic", module=module))
    term = info.value.term
    assert term[0] == "error"
    assert term[1][0] == "domain_error"
    assert term[1][1] == "clpz_expression"


def test_the_domain_error_is_catchable(module):
    k = Var()
    got = [deref(k) for _ in call("eq_symbolic_caught", k, module=module)]
    assert got == ["clpz_expression"]


def test_a_numeric_result_still_compares_with_double_equals(module):
    assert len(list(call("eq_numeric", module=module))) == 1


def test_sym_equal_is_the_symbolic_spelling(module):
    assert len(list(call("sym_equal_holds", module=module))) == 1
