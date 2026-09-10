"""A predicate name that the same file also reads as a logic variable.

``todo/predicate-name-collides-with-unit-quantity-parser.md`` — reported as
``TypeError: 'clausal.logic.variables.AttVar' object is not callable`` at module
load, and diagnosed there as a collision with the SI unit/quantity grammar.  It
is not: the collision is with the *variable naming convention*.  ALL-CAPS and
leading-underscore identifiers are logic variables in Clausal, and a clause
head's functor position is the one place that rule is not applied — so ``P/2``
mints a class named ``P`` while every other occurrence of ``P`` is a fresh
``Var``.  The reported crash is the second clause head calling the ``Var`` that
the first clause's body walrus left in the module globals.

Reverse the two clauses and there is no crash at all; the body goal just
silently means something else (for arity 1, the ``VAR(Unit)`` quantity sugar,
which is where the unit grammar does enter — as a *symptom*).

The rule enforced is the INTERSECTION of "is a clause-head functor here" and
"is read as a logic variable here".  A var-shaped head that is never read as a
variable in its own file keeps working — that shorthand is used throughout this
repo's own test snippets — and the ``VAR(Unit)`` sugar is untouched.
"""

from __future__ import annotations

import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _write(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return str(path)


def _load(tmp_path, name, text):
    return _load_module(f"tests_vspn_{name}", _write(tmp_path, name, text))


# ── The reported crash ─────────────────────────────────────────────────────


class TestReportedCrash:
    """The exact repro from the todo, and the message it now gets."""

    def test_self_recursive_all_caps_predicate_is_a_syntax_error(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "recursive", """
                -module(m, [P(N, X)])
                P(N, X) <- (N > 0, M is N - 1, P(M, X))
                P(N, X) <- (X is N)
            """)
        assert "'AttVar' object is not callable" not in type(
            exc_info.value).__name__

    def test_the_message_names_the_predicate_and_both_sites(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "sites", """
                -module(m, [P(N, X)])
                P(N, X) <- (N > 0, M is N - 1, P(M, X))
                P(N, X) <- (X is N)
            """)
        message = str(exc_info.value)
        assert "'P'" in message
        assert "logic variable" in message
        # Both the declaration site and the variable read are attributed.
        assert "sites.clausal:1" in message
        assert "sites.clausal:2" in message
        # And the cryptic downstream failure is named so a search for it lands
        # here.
        assert "'AttVar' object is not callable" in message

    def test_the_message_suggests_a_non_variable_spelling(self, tmp_path):
        # ``foo``, not ``Foo``: since 2026-09-10 a capital initial is itself a
        # logic variable, so the old suggestion would have named another one.
        with pytest.raises(SyntaxError, match=r"e\.g\. foo"):
            _load(tmp_path, "suggest", """
                FOO(N, X) <- (N > 0, M is N - 1, FOO(M, X))
                FOO(N, X) <- (X is N)
            """)

    def test_no_module_declaration_needed_to_trigger_it(self, tmp_path):
        """The ``-module`` header is not part of the fault."""
        with pytest.raises(SyntaxError, match="also read as a logic variable"):
            _load(tmp_path, "nomodule", """
                P(N, X) <- (N > 0, M is N - 1, P(M, X))
                P(N, X) <- (X is N)
            """)

    def test_leading_underscore_predicate_name_says_underscore(self, tmp_path):
        with pytest.raises(SyntaxError, match="leading underscore"):
            _load(tmp_path, "underscore", """
                _p(N, X) <- (N > 0, M is N - 1, _p(M, X))
                _p(N, X) <- (X is N)
            """)


class TestSilentShapes:
    """The shapes that did NOT crash, and so were worse than the crash."""

    def test_arity_one_body_goal_reinterpreted_as_a_quantity(self, tmp_path):
        """``q(X) <- (FOO(X))`` used to load and then fail at *query* time with
        ``cannot build a Quantity from AttVar`` — the unit-grammar symptom the
        todo mistook for the cause."""
        with pytest.raises(SyntaxError, match="also read as a logic variable"):
            _load(tmp_path, "quantity", """
                -module(m, [q(X), FOO(X)])
                FOO(X) <- (X is 1)
                q(X) <- (FOO(X))
            """)

    def test_head_after_variable_read_in_a_different_clause(self, tmp_path):
        """Variable read first, head second — the ordering that crashes."""
        with pytest.raises(SyntaxError, match="also read as a logic variable"):
            _load(tmp_path, "varfirst", """
                p(FOO) <- (FOO > 0)
                FOO(X) <- (X is 1)
            """)

    def test_head_before_variable_read_in_a_different_clause(self, tmp_path):
        """Head first, variable read second — loaded silently, same defect."""
        with pytest.raises(SyntaxError, match="also read as a logic variable"):
            _load(tmp_path, "headfirst", """
                FOO(X) <- (X is 1)
                p(FOO) <- (FOO > 0)
            """)


# ── What must keep working ─────────────────────────────────────────────────


class TestNotNarrowed:
    """The check is an intersection; neither half alone may reject anything."""

    def test_var_shaped_head_never_read_as_a_variable_still_loads(self, tmp_path):
        """``LP(X, Y, OBJ)`` in tests/fixtures/clpq_examples.clausal is this
        shape, and so are a couple of dozen inline test snippets."""
        module = _load(tmp_path, "headonly", """
            -module(m, [LP(X, Y, OBJ)])
            LP(X, Y, OBJ) <- (X is 1, Y is 2, OBJ is 3)
        """)
        x, y, obj = Var(), Var(), Var()
        logic_module = module.__dict__["$module"]
        assert any(True for _ in call("LP", x, y, obj, module=logic_module))
        assert (deref(x), deref(y), deref(obj)) == (1, 2, 3)

    def test_var_unit_quantity_sugar_still_constructs(self, tmp_path):
        """``N(metre)`` is the documented ``VAR(Unit)`` sugar.  ``N`` is a
        variable, not a clause head, so the two sets never meet."""
        module = _load(tmp_path, "unitsugar", """
            -import_from(py.units, [metre])
            test <- (N == 5, eval_(N(metre), D), D == 5(metre))
        """)
        assert any(True for _ in call("test", module=module.__dict__["$module"]))

    def test_var_shaped_head_calling_a_lowercase_predicate_still_loads(
            self, tmp_path):
        module = _load(tmp_path, "callsdown", """
            twice(A, B) <- (B == A * 2)
            T(A, B) <- twice(A, B)
        """)
        b = Var()
        logic_module = module.__dict__["$module"]
        assert any(True for _ in call("T", 4, b, module=logic_module))
        assert deref(b) == 8

    def test_a_non_variable_name_may_be_recursive(self, tmp_path):
        module = _load(tmp_path, "titlecase", """
            countdown(N, X) <- (N > 0, M == N - 1, countdown(M, X))
            countdown(N, X) <- (N <= 0, X == N)
        """)
        x = Var()
        logic_module = module.__dict__["$module"]
        assert any(True for _ in call("countdown", 3, x, module=logic_module))
        assert deref(x) == 0


# ── The cross-module version of the same unreachability ────────────────────


class TestVarShapedImport:
    """``-import_from(m, [FOO])`` binds a name no call site can reach.

    ``visit_Name`` consults ``_is_logic_var_name`` before ``_import_remap``, so
    a var-shaped imported name is read as a variable and the remap never fires
    — the same reasoning that already rejects ``alias(twice, T)`` (A10-F017),
    applied to the direct form.  There is no head-only escape here: an imported
    name exists only to be called.
    """

    def test_direct_import_of_a_var_shaped_name_is_rejected(self, tmp_path):
        _load(tmp_path, "xlib", """
            -module(xlib, [FOO(X)])
            FOO(X) <- (X == 1)
        """)
        with pytest.raises(SyntaxError, match="is a logic-variable name"):
            _load(tmp_path, "xuse", """
                -import_from(tests_vspn_xlib, [FOO])
                q(X) <- FOO(X)
            """)

    def test_the_suggested_alias_repair_actually_works(self, tmp_path):
        """The message says ``alias(FOO, Foo)``; that must resolve and run."""
        _load(tmp_path, "xlib2", """
            -module(xlib2, [FOO(X)])
            FOO(X) <- (X == 1)
        """)
        module = _load(tmp_path, "xuse2", """
            -import_from(tests_vspn_xlib2, [alias(FOO, foo)])
            q(X) <- foo(X)
        """)
        x = Var()
        assert any(True for _ in call("q", x, module=module.__dict__["$module"]))
        assert deref(x) == 1
