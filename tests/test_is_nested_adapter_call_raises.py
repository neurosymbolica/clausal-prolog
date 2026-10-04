"""A qualified predicate ADAPTER in an ARITHMETIC position raises.

T4 (08bfbef8) made ``X is mod.pred(Args)`` raise ``type_error(evaluable,
'mod.pred'/N)`` when a whole side of ``is`` IS the qualified adapter call.
Ruled 2026-10-04 (D11): the same holds when the call is NESTED in an
arithmetic position, and for the arithmetic comparisons.

The arithmetic positions of a side (``terms_to_ast.arithmetic_adapter_call``):

- the side itself;
- the operands of an evaluable operator node -- ``+ - * / // % **`` and
  unary ``-`` (``exact_arith.node_keys``);
- the arguments of an unqualified call to an ISO evaluable function --
  ``abs/1``, ``max/2``, ``sqrt/1`` ... (``exact_arith.EVALUABLE``);

recursively.  The walk stops at anything else, which keeps building its term:
a list, a tuple, a data or goal compound ``f(...)``, a qualified Python call's
arguments, a ``++`` escape.

The goals whose sides are walked: ``is`` (both sides), the comparisons ``==
!= < <= > >=``, in a clause body (compiled), as the test of ``if_/3``
(reified), and built as a goal term then run by ``call/1`` (the check runs
where the term is built).  ``eval_/2``, the quoted ISO forms (``'is'``,
``'=:='``, ``'<'`` ...) and the CLP set goal ``{...}`` evaluate their
argument at run time and already raised the same ``type_error``; they are
pinned here so every arithmetic route agrees.
"""

from __future__ import annotations

import pytest

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-implicit_functors
-import_module(py.re)
-import_module(math)
-import_module(fractions)

# ── is: nested in an arithmetic position (raise) ──
is_add(X) <- (X is 1 + py.re.match("a", "abc"))
is_add_left(X) <- (py.re.match("a", "abc") + 1 is X)
is_neg(X) <- (X is -py.re.match("a", "abc"))
is_deep(X) <- (X is (1 + 2) * (3 - py.re.match("a", "abc")))
is_div(X) <- (X is 1 / py.re.match("a", "abc"))
is_pow(X) <- (X is 2 ** py.re.match("a", "abc"))
is_abs(X) <- (X is abs(py.re.match("a", "abc")))
is_max(X) <- (X is max(1, 2 + py.re.match("a", "abc")))
is_term(X) <- (G is (X is 1 + py.re.match("a", "abc")), call(G))
is_if(X) <- if_(X is 1 + py.re.match("a", "abc"), True, True)
is_call_arg(X) <- call(X is 1 + py.re.match("a", "abc"))

# ── is: not an arithmetic position (build, unchanged) ──
in_list(X) <- (X is [py.re.match("a", "abc")])
in_list_sum(X) <- (X is [1 + py.re.match("a", "abc")])
in_tuple(X) <- (X is (1, py.re.match("a", "abc")))
in_data(X) <- (X is wrap(py.re.match("a", "abc")))
in_data_sum(X) <- (X is 1 + wrap(py.re.match("a", "abc")))
py_call_sum(X) <- (X is 1 + math.sqrt(16))
py_class_sum(X) <- (X is 1 + fractions.Fraction(1, 2))

# ── comparisons (raise) ──
lt_side() <- (1 < py.re.match("a", "abc"))
lt_nested() <- (1 < 1 + py.re.match("a", "abc"))
le_nested() <- (1 <= abs(py.re.match("a", "abc")))
gt_nested() <- (1 + py.re.match("a", "abc") > 1)
ge_nested() <- (1 >= 1 + py.re.match("a", "abc"))
eq_nested(X) <- (X == 1 + py.re.match("a", "abc"))
ne_side() <- (1 != py.re.match("a", "abc"))
ne_nested() <- (1 != 1 + py.re.match("a", "abc"))
lt_term() <- (G is (1 < 1 + py.re.match("a", "abc")), call(G))
lt_if() <- if_(1 < 1 + py.re.match("a", "abc"), True, True)

# ── comparisons: not an arithmetic position (unchanged) ──
lt_data() <- (1 < wrap(py.re.match("a", "abc")))

# ── already raised at run time (pinned) ──
via_eval(X) <- eval_(1 + py.re.match("a", "abc"), X)
via_iso_is(X) <- 'is'(X, 1 + py.re.match("a", "abc"))
via_iso_eq() <- '=:='(1, 1 + py.re.match("a", "abc"))
via_iso_lt() <- '<'(1, 1 + py.re.match("a", "abc"))
via_set(X) <- {X == 1 + py.re.match("a", "abc")}

# ── a Python callable still computes ──
cmp_py() <- (1 < 1 + math.sqrt(16))
"""

ADAPTER = ("/", "py.re.match", 2)


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("is_nested") / f"is_nested_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("is_nested_probe", str(src)).__dict__["$module"]


_ZERO = {"lt_side", "lt_nested", "le_nested", "gt_nested", "ge_nested",
         "ne_side", "ne_nested", "lt_term", "lt_if", "lt_data", "via_iso_eq",
         "via_iso_lt", "cmp_py"}


def _answers(module, name):
    args = [Var() for _ in range(0 if name in _ZERO else 1)]
    return [[_deref_walk(a) for a in args]
            for _ in call(name, *args, module=module)]


def _raised(module, name):
    with pytest.raises(LogicException) as info:
        _answers(module, name)
    return info.value.term


@pytest.mark.parametrize("name", [
    "is_add", "is_add_left", "is_neg", "is_deep", "is_div", "is_pow",
    "is_abs", "is_max", "is_term", "is_if", "is_call_arg",
])
def test_nested_in_is_raises(module, name):
    assert _raised(module, name) == (
        "error", ("type_error", "evaluable", ADAPTER), ("/", "is", 2))


@pytest.mark.parametrize("name,op", [
    ("lt_side", "<"), ("lt_nested", "<"), ("le_nested", "<="),
    ("gt_nested", ">"), ("ge_nested", ">="), ("eq_nested", "=="),
    ("ne_side", "!="), ("ne_nested", "!="), ("lt_term", "<"),
    ("lt_if", "<"),
])
def test_in_a_comparison_raises_with_its_own_context(module, name, op):
    assert _raised(module, name) == (
        "error", ("type_error", "evaluable", ADAPTER), ("/", op, 2))


@pytest.mark.parametrize("name,context", [
    ("via_eval", "eval_"), ("via_iso_is", "is"), ("via_iso_eq", "is"),
    ("via_iso_lt", "is"), ("via_set", "=="),
])
def test_run_time_evaluators_agree(module, name, context):
    assert _raised(module, name) == (
        "error", ("type_error", "evaluable", ADAPTER), ("/", context, 2))


_CELL = ("py.re.match", ("$chars", "a"), ("$chars", "abc"))


def test_a_list_or_tuple_keeps_building(module):
    assert _answers(module, "in_list") == [[[_CELL]]]
    [[got]] = _answers(module, "in_list_sum")
    assert got[0].right == _CELL                  # [1 + cell]: a list element
    [[got]] = _answers(module, "in_tuple")
    assert _CELL in tuple(got)


def test_a_data_compound_keeps_building(module):
    assert _answers(module, "in_data") == [[("wrap", _CELL)]]
    [[got]] = _answers(module, "in_data_sum")
    assert got.right == ("wrap", _CELL)


def test_a_python_callable_in_an_arithmetic_position_still_computes(module):
    [[got]] = _answers(module, "py_call_sum")
    assert (got.left, got.right) == (1, 4.0)
    from fractions import Fraction
    [[got]] = _answers(module, "py_class_sum")
    assert got.right == Fraction(1, 2)
    assert _answers(module, "cmp_py") == [[]]


def test_a_comparison_over_a_data_compound_is_not_this_check(module):
    # wrap/1 is the outermost non-evaluable: whatever the comparison says
    # about it, it is not the adapter's type_error.
    try:
        _answers(module, "lt_data")
    except LogicException as e:
        assert e.term[1] != ("type_error", "evaluable", ADAPTER)



# ── Clausal Prolog: unchanged, ISO ──

_CP = """:- module(is_nested_cp, [k/1, c/0]).
k(X) :- X is 1 + lists:length([a], _).
c :- 1 < 1 + lists:length([a], _).
:- end_module(is_nested_cp).
"""


def test_clausal_prolog_is_unchanged(tmp_path):
    # Clausal Prolog writes a qualified goal M:G, never m.p(...), and its
    # is/2 and comparisons evaluate as ISO does: M:G in an arithmetic
    # position is the non-evaluable (:)/2 -- and a Python adapter is not
    # reachable from it at all (the dialect gate).
    from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
    src = tmp_path / f"is_nested_cp{CLAUSAL_PROLOG_SUFFIXES[0]}"
    src.write_text(_CP, encoding="utf-8")
    mod = _load_module("is_nested_cp", str(src))
    for name, args in (("k", [Var()]), ("c", [])):
        with pytest.raises(LogicException) as info:
            list(call(name, *args, module=mod))
        assert info.value.term[1] == ("type_error", "evaluable", ("/", ":", 2))
