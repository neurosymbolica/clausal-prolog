"""Tests for V2-D — directives (-dynamic, -discontiguous, -table).

Verifies:
  - -dynamic(pred/arity) allows runtime assertz/retract
  - Non-dynamic predicates are locked after module load
  - -discontiguous(pred/arity) sets the discontiguous flag
  - -table(pred/arity) sets the tabled flag
  - Unknown directive raises SyntaxError
  - Malformed directive args raise SyntaxError
"""

from __future__ import annotations

import sys
import os
import ast

import pytest

import clausal.import_hook
from clausal.import_hook import _load_module
from clausal.logic.database import Database, Clause
from clausal.logic.predicate import PredicateMeta
from clausal.templating.term_rewriting import EmbedTransformer


# ── Fixture loading helper ────────────────────────────────────────────────────


def _load_fixture(filename: str, mod_name: str | None = None) -> object:
    path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
    name = mod_name or f"_test_directive_{filename.replace('.', '_')}"
    return _load_module(name, path)


# ── Database mark_dynamic / mark_discontiguous / mark_tabled ─────────────────


class TestDatabaseDirectiveMetadata:
    def test_mark_dynamic(self):
        db = Database()
        db.mark_dynamic("foo", 2)
        assert db.is_dynamic("foo", 2)

    def test_not_dynamic_by_default(self):
        db = Database()
        assert not db.is_dynamic("foo", 2)

    def test_mark_discontiguous(self):
        db = Database()
        db.mark_discontiguous("bar", 1)
        assert db.is_discontiguous("bar", 1)

    def test_not_discontiguous_by_default(self):
        db = Database()
        assert not db.is_discontiguous("bar", 1)

    def test_mark_tabled(self):
        db = Database()
        db.mark_tabled("fib", 2)
        assert db.is_tabled("fib", 2)

    def test_not_tabled_by_default(self):
        db = Database()
        assert not db.is_tabled("fib", 2)

    def test_multiple_dynamic(self):
        db = Database()
        db.mark_dynamic("foo", 2)
        db.mark_dynamic("bar", 3)
        assert db.is_dynamic("foo", 2)
        assert db.is_dynamic("bar", 3)
        assert not db.is_dynamic("baz", 1)


# ── Directive parsing in EmbedTransformer ────────────────────────────────────


def _transform_source(source: str) -> ast.Module:
    """Parse and transform source through EmbedTransformer."""
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        tree = ast.parse(source)
        return EmbedTransformer().visit(tree)


class TestDirectiveParsing:
    def test_dynamic_directive_generates_mark_dynamic_call(self):
        tree = _transform_source("-dynamic(foo/2)\n")
        # Should generate $module.db.mark_dynamic("foo", 2)
        code = ast.dump(tree)
        assert "mark_dynamic" in code

    def test_discontiguous_directive_generates_mark_call(self):
        tree = _transform_source("-discontiguous(bar/1)\n")
        code = ast.dump(tree)
        assert "mark_discontiguous" in code

    def test_table_directive_generates_mark_call(self):
        tree = _transform_source("-table(fib/2)\n")
        code = ast.dump(tree)
        assert "mark_tabled" in code

    def test_multiple_pred_arity_args(self):
        tree = _transform_source("-dynamic(foo/2, bar/3)\n")
        code = ast.dump(tree)
        # Should have two mark_dynamic calls
        assert code.count("mark_dynamic") == 2

    def test_unknown_directive_raises(self):
        with pytest.raises(SyntaxError, match="Unknown directive.*bogus"):
            _transform_source("-bogus(foo/2)\n")

    def test_malformed_arg_no_arity_raises(self):
        with pytest.raises(SyntaxError, match="Malformed argument"):
            _transform_source("-dynamic(foo)\n")

    def test_malformed_arg_string_arity_raises(self):
        with pytest.raises(SyntaxError, match="Malformed argument"):
            _transform_source('-dynamic(foo/"two")\n')

    def test_empty_args_raises(self):
        with pytest.raises(SyntaxError, match="requires at least one"):
            _transform_source("-dynamic()\n")


# ── Import-level: -dynamic allows runtime assertz ────────────────────────────


class TestDynamicImport:
    def test_dynamic_predicate_is_unlocked(self):
        mod = _load_fixture("dynamic_pred.clausal")
        color_cls = mod.__dict__["Color"]
        assert isinstance(color_cls, PredicateMeta)
        assert not color_cls._locked

    def test_dynamic_predicate_allows_runtime_assertz(self):
        mod = _load_fixture("dynamic_pred.clausal")
        color_cls = mod.__dict__["Color"]
        logic_mod = mod.__dict__["$module"]
        initial_count = len(logic_mod.db.clauses_for("Color", 2))
        color_cls._assertz(Clause(head=color_cls("fire", "red"), body=[]))
        assert len(color_cls._clauses) == initial_count + 1

    def test_static_predicate_is_locked(self):
        mod = _load_fixture("static_pred.clausal")
        fact_cls = mod.__dict__["Fact"]
        assert isinstance(fact_cls, PredicateMeta)
        assert fact_cls._locked

    def test_static_predicate_rejects_runtime_assertz(self):
        mod = _load_fixture("static_pred.clausal")
        fact_cls = mod.__dict__["Fact"]
        with pytest.raises(RuntimeError, match="locked"):
            fact_cls._assertz(Clause(head=fact_cls("c", 3), body=[]))

    def test_dynamic_flag_recorded_on_db(self):
        mod = _load_fixture("dynamic_pred.clausal")
        logic_mod = mod.__dict__["$module"]
        assert logic_mod.db.is_dynamic("Color", 2)

    def test_static_not_dynamic_on_db(self):
        mod = _load_fixture("static_pred.clausal")
        logic_mod = mod.__dict__["$module"]
        assert not logic_mod.db.is_dynamic("Fact", 2)
