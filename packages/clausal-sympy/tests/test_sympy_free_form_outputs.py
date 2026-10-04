"""Free-form text sympy hands back is a STRING; names stay ATOMS.

Ruled 2026-10-04 (adapters are their own entry point, strings spec 9.4):
a printed representation -- ``sym_str/2``, ``latex/2``, ``pretty/2``,
``math_ml/2``, and ``sympy_term/2``'s ``str(expr)`` fallback for a SymPy
object with no term form -- is the string ``('$chars', s)``.  A symbol
name (``free_vars/2``) and an arity-0 constant (``pi``) stay atoms, and the
``++`` escape keeps "a Python str is an atom".
"""

from __future__ import annotations

import pytest

sp = pytest.importorskip("sympy", reason="sympy not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars, is_chars
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-import_from(sympy, [sym_str, latex, pretty, math_ml, free_vars, sym, sympy_term])

sym_str_out(S) <- sym_str(42, S)
latex_out(S) <- latex(42, S)
pretty_out(S) <- pretty(42, S)
math_ml_out(S) <- math_ml(42, S)
check_string() <- sym_str(42, "42")
check_atom() <- sym_str(42, '42')
free_vars_out(V) <- (sym('a', A), sym('b', B), free_vars(A + B, V))
pi_out(T) <- sympy_term(++__import__('sympy').pi, T)
fallback_out(T) <- sympy_term(++__import__('sympy').Eq(__import__('sympy').Symbol('a'), 1), T)
escape_out(S) <- (sym('x', X), E is ++(X + 1), S is ++str(E))
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("sympyfree") / f"sympy_free_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("sympy_free_probe", str(src)).__dict__["$module"]


def _answers(module, name, *args):
    out = Var()
    return [_deref_walk(out) for _ in call(name, *args, out, module=module)]


def _holds(module, name):
    return any(True for _ in call(name, module=module))


@pytest.mark.parametrize("name", ["sym_str_out", "latex_out", "pretty_out"])
def test_printed_form_is_a_string(module, name):
    assert _answers(module, name) == [chars("42")]


def test_math_ml_is_a_string(module):
    [got] = _answers(module, "math_ml_out")
    assert is_chars(got) and got == chars("<cn>42</cn>")


def test_check_mode_takes_the_string_not_the_atom(module):
    # as py.files and every other text-returning adapter: the result is the
    # string, and the atom of the same spelling is a different term
    assert _holds(module, "check_string")
    assert not _holds(module, "check_atom")


def test_term_fallback_is_a_string(module):
    assert _answers(module, "fallback_out") == [chars("Eq(a, 1)")]


def test_symbol_names_stay_atoms(module):
    [got] = _answers(module, "free_vars_out")
    assert got == ["a", "b"] and all(type(n) is str for n in got)


def test_constant_stays_an_atom(module):
    assert _answers(module, "pi_out") == ["pi"]


def test_escape_keeps_python_str_an_atom(module):
    [got] = _answers(module, "escape_out")
    assert type(got) is str and got == "x + 1"
