"""Tests for ISO Prolog-compatible operators and quoted atom translation.

Tests that:
  - The ``prolog`` module provides ISO-compatible TruncDiv, TruncMod, Rem
  - The translator emits prolog.TruncDiv() for Prolog's ``//``
  - The translator quotes Prolog atoms as Python string literals
  - End-to-end: .pl files with ``//``, ``mod``, atoms import and execute
"""

from __future__ import annotations

import os
import sys
import textwrap

import pytest

from clausal.import_hook import _load_prolog_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.tools.prolog_to_clausal import prolog_to_clausal
from clausal.tools.prolog_dialect import Dialect


# ── Prolog module: ISO arithmetic ─────────────────────────────────────────


class TestPrologModule:
    """clausal.modules.prolog provides ISO-compatible arithmetic."""

    def test_trunc_div_positive(self):
        from clausal.modules.prolog import TruncDiv
        assert TruncDiv(7, 2) == 3

    def test_trunc_div_negative_dividend(self):
        from clausal.modules.prolog import TruncDiv
        # ISO: truncate toward zero -> -3, Python //: floor -> -4
        assert TruncDiv(-7, 2) == -3

    def test_trunc_div_negative_divisor(self):
        from clausal.modules.prolog import TruncDiv
        assert TruncDiv(7, -2) == -3

    def test_trunc_mod_positive(self):
        from clausal.modules.prolog import TruncMod
        assert TruncMod(7, 3) == 1

    def test_trunc_mod_negative_dividend(self):
        from clausal.modules.prolog import TruncMod
        # ISO: sign follows dividend -> -1, Python %: floor mod -> 2
        assert TruncMod(-7, 3) == -1

    def test_rem_positive(self):
        from clausal.modules.prolog import Rem
        assert Rem(7, 3) == 1

    def test_rem_negative(self):
        from clausal.modules.prolog import Rem
        assert Rem(-7, 3) == -1


# ── Translator: ISO operators ─────────────────────────────────────────────


class TestTranslatorISOOperators:
    """Prolog ``//``, ``mod``, ``rem`` are emitted as prolog.TruncDiv etc."""

    def test_integer_division_emits_prolog_qualified(self):
        src = "test :- X is 7 // 2."
        result = prolog_to_clausal(src)
        assert "prolog.TruncDiv" in result

    def test_mod_emits_prolog_qualified(self):
        src = "test :- X is 7 mod 3."
        result = prolog_to_clausal(src)
        assert "prolog.TruncMod" in result

    def test_rem_emits_prolog_qualified(self):
        src = "test :- X is 7 rem 3."
        result = prolog_to_clausal(src)
        assert "prolog.Rem" in result

    def test_auto_imports_prolog_module(self):
        src = "test :- X is 7 // 2."
        result = prolog_to_clausal(src)
        assert "-import_module(prolog)" in result

    def test_no_prolog_import_when_not_needed(self):
        src = "test :- X is 1 + 2."
        result = prolog_to_clausal(src)
        assert "prolog" not in result


# ── Translator: Atom quoting ──────────────────────────────────────────────


class TestTranslatorAtomQuoting:
    """Prolog atoms are emitted as quoted Python strings."""

    def test_atom_declared_via_private(self):
        """Prolog atoms generate a -private declaration."""
        src = "color(red). color(blue)."
        result = prolog_to_clausal(src)
        assert "-private(" in result
        assert "red" in result
        assert "blue" in result

    def test_atom_used_as_bare_name(self):
        """Atoms appear as bare names in clause bodies (not quoted)."""
        src = "color(red)."
        result = prolog_to_clausal(src)
        assert "Color(red)," in result
        assert "'red'" not in result

    def test_true_false_not_in_private(self):
        src = "val(true). val(false)."
        result = prolog_to_clausal(src)
        # true/false are Python builtins, not collected as data atoms
        if "-private(" in result:
            assert "true" not in result.split("-private(")[1].split(")")[0]

    def test_numbers_not_in_private(self):
        src = "val(42)."
        result = prolog_to_clausal(src)
        assert "-private(" not in result  # no atoms at all

    def test_functor_names_not_affected(self):
        """Functor names (PascalCase predicates) are not declared as atoms."""
        src = "foo_bar(1, 2)."
        result = prolog_to_clausal(src)
        assert "FooBar(1, 2)," in result


# ── End-to-end: .pl import with atoms and ISO operators ───────────────────


@pytest.fixture(autouse=True)
def cleanup_modules(tmp_path):
    sys_path_str = str(tmp_path)
    sys.path.insert(0, sys_path_str)
    yield
    sys.path.remove(sys_path_str)
    for key in list(sys.modules):
        if key.startswith("_plop_"):
            del sys.modules[key]


def _write_pl(tmp_path, name, source):
    path = tmp_path / f"{name}.pl"
    path.write_text(textwrap.dedent(source))
    return str(path)


class TestEndToEnd:
    """Import .pl files using atoms and ISO operators, query predicates."""

    def test_atoms_as_data(self, tmp_path):
        """Prolog atoms become zero-arity PredicateMeta classes when imported."""
        path = _write_pl(tmp_path, "_plop_atoms", """\
            color(red).
            color(green).
            color(blue).
        """)
        mod = _load_prolog_module("_plop_atoms", path)
        lm = mod.__clausal_module__
        v = Var()
        results = [deref(v) for _ in call("Color", v, module=lm)]
        # Atoms declared via -private are PredicateMeta instances, not strings.
        assert {type(r).__name__ for r in results} == {"PredicateMeta"}
        assert {str(r) for r in results} == {"red", "green", "blue"}

    def test_iso_truncate_div(self, tmp_path):
        """Prolog // uses ISO truncation-toward-zero semantics."""
        path = _write_pl(tmp_path, "_plop_div", """\
            trunc_div(X, Y, R) :- R is X // Y.
        """)
        mod = _load_prolog_module("_plop_div", path)
        lm = mod.__clausal_module__
        r = Var()
        # ISO: -7 // 2 = -3 (truncate toward zero)
        # Python: -7 // 2 = -4 (floor)
        results = [deref(r) for _ in call("TruncDiv", -7, 2, r, module=lm)]
        assert results == [-3]

    def test_iso_mod(self, tmp_path):
        """Prolog mod uses ISO sign-follows-dividend semantics."""
        path = _write_pl(tmp_path, "_plop_mod", """\
            my_mod(X, Y, R) :- R is X mod Y.
        """)
        mod = _load_prolog_module("_plop_mod", path)
        lm = mod.__clausal_module__
        r = Var()
        # ISO: -7 mod 3 = -1 (sign follows dividend)
        # Python: -7 % 3 = 2 (floor mod)
        results = [deref(r) for _ in call("MyMod", -7, 3, r, module=lm)]
        assert results == [-1]

    def test_mixed_atoms_and_arithmetic(self, tmp_path):
        """A .pl file that uses both atoms and arithmetic."""
        path = _write_pl(tmp_path, "_plop_mixed", """\
            classify(X, positive) :- X > 0.
            classify(0, zero).
            classify(X, negative) :- X < 0.
        """)
        mod = _load_prolog_module("_plop_mixed", path)
        lm = mod.__clausal_module__
        # Atoms are zero-arity PredicateMeta instances after -private declaration.
        assert hasattr(mod, 'positive')
        assert hasattr(mod, 'zero')
        assert hasattr(mod, 'negative')
        # Correct atom matches succeed.
        assert list(call("Classify", 5, mod.positive, module=lm))
        assert list(call("Classify", 0, mod.zero, module=lm))
        assert list(call("Classify", -3, mod.negative, module=lm))
