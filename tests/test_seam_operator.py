"""The ``--`` seam: Python-hosted code in a ``.clausal`` file speaks TERMS.

``++expr`` escapes to Python; ``--term`` escapes back to Clausal.  Inside
``--`` the term grammar is the host module's: declared bare names are atoms,
ALL-CAPS / leading-underscore names are logic variables, quoted literals
follow the module's ``-double_quotes`` mode, and a Python value enters only
through ``++``.  The result is the RUNTIME term — a cell — built at the
point of execution, never a rewriter node.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from tests._suffix import SEAM


def _load_inline(name: str, source: str):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}{SEAM}")
        with open(path, "w") as fh:
            fh.write(source)
        return _load_module(name, path)


class TestSeamBuildsCells:
    def test_a_declared_functor_with_atom_and_string_args_is_the_cell(self):
        mod = _load_inline("_seam_cell", (
            "-module(_seam_cell, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "-private([good])\n"
            "def build():\n"
            "    return --verdict(good, \"baz\")\n"
        ))
        assert mod.build() == ("verdict", "good", ("$chars", "baz"))   # stage 1: the chars CARRIER

    def test_under_atom_mode_a_double_quoted_literal_is_the_atom(self):
        mod = _load_inline("_seam_atom_mode", (
            "-module(_seam_atom_mode, [verdict(A, B)])\n"
            "-double_quotes(atom)\n"
            "-private([good])\n"
            "def build():\n"
            "    return --verdict(good, \"baz\")\n"
        ))
        assert mod.build() == ("verdict", "good", "baz")

    def test_a_single_quoted_literal_is_an_atom_in_chars_mode(self):
        mod = _load_inline("_seam_sq", (
            "-module(_seam_sq, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --verdict('sq', \"dq\")\n"
        ))
        assert mod.build() == ("verdict", "sq", ("$chars", "dq"))

    def test_a_titlecase_name_is_an_atom_not_a_variable(self):
        mod = _load_inline("_seam_title", (
            "-module(_seam_title, [verdict(A, B), foo])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --verdict(foo, 1)\n"
        ))
        assert mod.build() == ("verdict", "foo", 1)

    def test_the_built_term_unifies_with_the_engine_s_own(self):
        from clausal.logic.solve import call
        mod = _load_inline("_seam_unify", (
            "-module(_seam_unify, [verdict(A, B), fact(X)])\n"
            "-double_quotes(chars)\n"
            "-private([good])\n"
            "fact(verdict(good, \"baz\"))\n"
            "def build():\n"
            "    return --verdict(good, \"baz\")\n"
        ))
        lm = mod.__dict__["$module"]
        assert list(call("fact", mod.build(), module=lm)) != []


class TestVariablesAndEscapes:
    def test_a_logic_variable_is_fresh_and_shared_within_one_expression(self):
        from clausal.logic.variables import is_var
        mod = _load_inline("_seam_var", (
            "-module(_seam_var, [pair(A, B)])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --pair(X, [X, _y])\n"
        ))
        t1, t2 = mod.build(), mod.build()
        assert t1[0] == "pair" and is_var(t1[1]) and t1[1] is t1[2][0]
        assert is_var(t1[2][1]) and t1[2][1] is not t1[1]
        assert t1[1] is not t2[1]

    def test_a_python_value_enters_through_plus_plus_and_is_evaluated_now(self):
        mod = _load_inline("_seam_pp", (
            "-module(_seam_pp, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "def build(status, n):\n"
            "    return --verdict(++status, ++(n + 1))\n"
        ))
        assert mod.build("ok", 41) == ("verdict", "ok", 42)

    def test_seams_nest_to_any_depth(self):
        mod = _load_inline("_seam_nest", (
            "-module(_seam_nest, [outer(A, B), inner(A)])\n"
            "-double_quotes(chars)\n"
            "-private([done])\n"
            "def build(xs):\n"
            "    return --outer(++[--inner(++x) for x in xs], done)\n"
        ))
        assert mod.build([1, 2]) == ("outer", [("inner", 1), ("inner", 2)], "done")

    def test_keyword_construction_in_a_seam_is_refused(self):
        """A seam operand is a CLAUSAL subtree, so the keyword refusal reaches
        it: ``--verdict(B=2, A=1)`` used to place by name and build
        ``("verdict", 1, 2)``.  The positional seam construction it placed
        INTO is unchanged and covered by the tests around this one."""
        with pytest.raises(SyntaxError, match="keyword arguments"):
            _load_inline("_seam_kw", (
                "-module(_seam_kw, [verdict(A, B)])\n"
                "-double_quotes(chars)\n"
                "def build():\n"
                "    return --verdict(B=2, A=1)\n"
            ))


class TestHostModuleRulesApply:
    def test_an_undeclared_functor_is_refused_loudly(self):
        mod = _load_inline("_seam_undeclared", (
            "-module(_seam_undeclared, [])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --nosuch(1)\n"
        ))
        with pytest.raises(NameError, match="nosuch"):
            mod.build()

    def test_implicit_functors_opens_construction_at_the_written_arity(self):
        mod = _load_inline("_seam_owa", (
            "-module(_seam_owa, [])\n"
            "-double_quotes(chars)\n"
            "-implicit_functors\n"
            "def build():\n"
            "    return --nosuch(1, 2, 3)\n"
        ))
        assert mod.build() == ("nosuch", 1, 2, 3)

    def test_a_double_quoted_literal_with_no_explicit_mode_is_a_string(self):
        # The default is chars (2026-09-26): a seam literal in a module that
        # declares no mode is a STRING, and the "no mode declared" warning
        # that used to fire here is retired -- there is nothing left to warn
        # about.
        import warnings
        from clausal.lint_warnings import ClausalLintWarning
        from clausal.logic.atoms import mint
        from clausal.logic.cells import chars
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            mod = _load_inline("_seam_warn", (
                "-module(_seam_warn, [verdict(A, B), tag(A)])\n"
                "-private([good])\n"
                "def build():\n"
                "    return --verdict(good, \"baz\")\n"
                "def build_atom():\n"
                "    return --tag('baz')\n"
            ))
        assert [w for w in caught if isinstance(w.message, ClausalLintWarning)] == []
        assert mod.build() == ("verdict", "good", chars("baz"))
        assert mod.build_atom() == ("tag", mint("baz"))   # '...' stays an atom


class TestNoClassInstances:
    def test_a_predicate_functor_builds_a_goal_cell_not_an_instance(self):
        from clausal.logic.solve import call
        mod = _load_inline("_seam_pred", (
            "-module(_seam_pred, [fact(X)])\n"
            "-double_quotes(chars)\n"
            "fact(1)\n"
            "def goal():\n"
            "    return --fact(1)\n"
        ))
        g = mod.goal()
        assert g == ("fact", 1) and type(g) is tuple
        assert list(call("call", g, module=mod.__dict__["$module"])) != []


class TestTermForms:
    def test_a_zero_argument_call_is_not_a_term(self):
        mod = _load_inline("_seam_arity0", (
            "-module(_seam_arity0, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --verdict()\n"
        ))
        with pytest.raises(SyntaxError, match="not a term"):
            mod.build()

    def test_ground_arithmetic_is_a_value_as_in_a_clause_body(self):
        mod = _load_inline("_seam_arith", (
            "-module(_seam_arith, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --verdict(1 + 2, 10 * 4)\n"
        ))
        assert mod.build() == ("verdict", 3, 40)

    def test_arithmetic_over_atoms_is_not_evaluable(self):
        mod = _load_inline("_seam_arith_atoms", (
            "-module(_seam_arith_atoms, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "-private([x, y])\n"
            "def build():\n"
            "    return --verdict(x + y, 0)\n"
        ))
        with pytest.raises(TypeError, match="evaluable"):
            mod.build()

    def test_arithmetic_over_an_unbound_variable_is_refused(self):
        mod = _load_inline("_seam_arith_var", (
            "-module(_seam_arith_var, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --verdict(X + 1, X)\n"
        ))
        with pytest.raises(SyntaxError, match="unbound variable"):
            mod.build()

    def test_a_module_level_seam_is_an_ordinary_python_value(self):
        mod = _load_inline("_seam_toplevel", (
            "-module(_seam_toplevel, [verdict(A, B)])\n"
            "-double_quotes(chars)\n"
            "-private([good])\n"
            "GOLD = --verdict(good, \"x\")\n"
        ))
        assert mod.GOLD == ("verdict", "good", ("$chars", "x"))


class TestImportedVocabulary:
    """An oracle names the vocabulary its DOMAIN declares and imports; it
    declares none of it itself.  Imported atoms and functors must resolve
    inside ``--`` exactly as they do outside it."""

    def _load_tree(self, tmp_path, monkeypatch, files: dict):
        import sys
        for rel, src in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(src)
        monkeypatch.syspath_prepend(str(tmp_path))
        import clausal.import_hook  # noqa: F401 — installs the hook
        for name in list(sys.modules):
            if name.startswith("seamprobe"):
                del sys.modules[name]
        import importlib
        return importlib.import_module("seamprobe.host")

    def test_an_imported_atom_resolves_inside_the_seam(self, tmp_path, monkeypatch):
        host = self._load_tree(tmp_path, monkeypatch, {
            "seamprobe/__init__.py": "",
            f"seamprobe/lib{SEAM}": (
                "-module(lib, [verdict(STATUS, IDS), dummy(X), ok, bad])\n"
                "dummy(ok),\n"),
            f"seamprobe/host{SEAM}": (
                "-module(host, [])\n"
                "-double_quotes(chars)\n"
                "-import_from(seamprobe.lib, [verdict, ok])\n"
                "def outside():\n"
                "    return ok\n"
                "def inside():\n"
                "    return --verdict(ok, \"text\")\n"),
        })
        assert host.outside() == "ok"
        assert host.inside() == ("verdict", "ok", ("$chars", "text"))
