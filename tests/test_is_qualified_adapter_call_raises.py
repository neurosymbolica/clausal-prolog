"""``X is mod.pred(Args)`` where ``mod.pred`` is a PREDICATE adapter.

Ruled 2026-10-04: a qualified predicate adapter (a ``ModulePredicate``, a
non-callable ``_get_dispatch`` object) on either side of ``is`` raises the
ISO ``type_error(evaluable, 'mod.pred'/N)`` -- the term ``eval_`` and
``'is'`` already gave for the same cell.  It used to bind the compound
``('mod.pred', Args)`` silently.  Python callables that compute a value
(``math.sqrt``, a class) are unaffected, and so is the bare / imported
spelling that builds a goal cell for ``call/1`` (``G is match(P, S)``).

Covered: the compiled ``is`` goal (both sides, in a conjunction, under
``catch/3``), ``is`` built as a goal TERM and run by ``call/1``, the
compiled ``eval_`` and quoted ``'is'`` (which raised already: pinned so
the three agree).
"""

from __future__ import annotations

import pytest

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-import_module(py.re)
-import_module(math)
-import_module(fractions)
-import_from(py.re, [match])
-import_module(py.os)

rhs(X) <- (X is py.re.match("a", "abc"))
lhs(X) <- (py.re.match("a", "abc") is X)
conj(X) <- (Y is 1, X is py.re.match("a", [Y]))
caught(E) <- catch((_ is py.re.match("a", "abc")), error(E, _), True)
as_term(X) <- (G is (X is py.re.match("a", "abc")), call(G))
via_eval(X) <- eval_(py.re.match("a", "abc"), X)
via_iso_is(X) <- 'is'(X, py.re.match("a", "abc"))

not_imported(X) <- (X is py.os.platform(1))

py_function(X) <- (X is math.sqrt(16))
py_class(X) <- (X is fractions.Fraction(1, 2))
py_function_as_term(X) <- (G is (X is math.sqrt(4)), call(G))
imported_goal_cell(G) <- (G is match("a", "abc"))
imported_goal_runs() <- (G is match("a", "abc"), call(G))
"""

# The functor is the one the cell would have carried: the bare leaf, since
# this module also imports match/2 (as eval_ and 'is' name it).
ERR = ("type_error", "evaluable", ("/", "match", 2))


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("is_adapter") / f"is_adapter_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("is_adapter_probe", str(src)).__dict__["$module"]


def _answers(module, name):
    x = Var()
    return [_deref_walk(x) for _ in call(name, x, module=module)]


def _raised(module, name):
    with pytest.raises(LogicException) as info:
        _answers(module, name)
    return info.value.term


@pytest.mark.parametrize("name", ["rhs", "lhs", "as_term"])
def test_a_qualified_adapter_in_is_raises_type_error_evaluable(module, name):
    assert _raised(module, name) == ("error", ERR, ("/", "is", 2))


def test_in_a_conjunction_with_its_own_arity(module):
    assert _raised(module, "conj")[1] == ERR


def test_a_qualified_adapter_not_imported_keeps_its_dotted_name(module):
    assert _raised(module, "not_imported")[1] == (
        "type_error", "evaluable", ("/", "py.os.platform", 1))


def test_the_error_is_catchable(module):
    assert _answers(module, "caught") == [ERR]


@pytest.mark.parametrize("name,context", [
    ("via_eval", ("/", "eval_", 2)),
    ("via_iso_is", ("/", "is", 2)),
])
def test_eval_and_iso_is_raise_the_same_term(module, name, context):
    assert _raised(module, name) == ("error", ERR, context)


def test_a_python_function_still_computes(module):
    assert _answers(module, "py_function") == [4.0]
    assert _answers(module, "py_function_as_term") == [2.0]


def test_a_python_class_still_constructs(module):
    from fractions import Fraction
    assert _answers(module, "py_class") == [Fraction(1, 2)]


def test_the_imported_spelling_still_builds_a_goal_cell(module):
    [g] = _answers(module, "imported_goal_cell")
    assert g[0] == "match" and len(g) == 3
    assert len(list(call("imported_goal_runs", module=module))) == 1
