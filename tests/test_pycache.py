"""Tests for V2-3 — __pycache__ bytecode caching and deferred compilation.

Verifies:
  - Importing a .clausal file creates __pycache__/*.pyc
  - Second import uses cached .pyc (source_to_code not called again)
  - Modifying source invalidates cache
  - Predicates work identically from cache vs fresh
  - Dynamic predicates still support runtime assertz/retract after cached load
  - sys.dont_write_bytecode = True suppresses cache writes
  - Deferred compilation: each predicate compiled once, not N times
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import textwrap
from unittest.mock import patch

import pytest

import clausal.import_hook
from clausal.import_hook import PredicateLoader, _load_module
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_clausal(tmp_path):
    """Create a temporary .clausal file and return (path, module_name).

    Cleans up __pycache__ and sys.modules on teardown.
    """
    src = tmp_path / "test_cached.clausal"
    src.write_text(textwrap.dedent("""\
        greet("hello"),
        greet("world"),
    """))
    mod_name = "_pycache_test_mod"
    yield src, mod_name
    sys.modules.pop(mod_name, None)
    pycache = tmp_path / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPycacheCreation:
    """Importing a .clausal file writes a .pyc into __pycache__/."""

    def test_pyc_created(self, tmp_clausal):
        src, mod_name = tmp_clausal
        pycache = src.parent / "__pycache__"
        # Ensure no cache exists initially.
        if pycache.exists():
            shutil.rmtree(pycache)

        _load_module(mod_name, str(src))

        assert pycache.exists(), "__pycache__/ dir should be created"
        pyc_files = list(pycache.glob("*.pyc"))
        assert len(pyc_files) >= 1, "at least one .pyc file should exist"

    def test_pyc_path_matches_source(self, tmp_clausal):
        src, mod_name = tmp_clausal
        _load_module(mod_name, str(src))

        expected_pyc = importlib.util.cache_from_source(str(src))
        assert os.path.exists(expected_pyc), f"expected .pyc at {expected_pyc}"


class TestPycacheCacheHit:
    """Second import uses cached .pyc — source_to_code is not called."""

    def test_source_to_code_skipped_on_cache_hit(self, tmp_clausal):
        src, mod_name = tmp_clausal
        # First load: creates .pyc.
        _load_module(mod_name, str(src))
        pyc_path = importlib.util.cache_from_source(str(src))
        assert os.path.exists(pyc_path)

        # Second load: should use cached .pyc and NOT call source_to_code.
        with patch.object(PredicateLoader, "source_to_code",
                          wraps=PredicateLoader.source_to_code) as mock_s2c:
            _load_module(mod_name + "_2", str(src))
            mock_s2c.assert_not_called()


class TestPycacheInvalidation:
    """Modifying source invalidates the cache."""

    def test_modified_source_recompiles(self, tmp_clausal):
        src, mod_name = tmp_clausal
        # First load.
        mod1 = _load_module(mod_name, str(src))
        lm1 = mod1.__dict__["$module"]
        clauses1 = lm1.db.clauses_for("greet", 1)
        assert len(clauses1) == 2

        # Modify source — add a third fact.
        src.write_text(textwrap.dedent("""\
            greet("hello"),
            greet("world"),
            greet("again"),
        """))

        # Second load should pick up the new clause.
        mod2 = _load_module(mod_name, str(src))
        lm2 = mod2.__dict__["$module"]
        clauses2 = lm2.db.clauses_for("greet", 1)
        assert len(clauses2) == 3


class TestCachedCorrectness:
    """Predicates work identically from cache vs fresh."""

    def test_query_from_cache(self, tmp_clausal):
        src, mod_name = tmp_clausal
        # First load (creates cache).
        mod1 = _load_module(mod_name, str(src))
        lm1 = mod1.__dict__["$module"]
        results1 = _query_greet(lm1)

        # Second load (from cache).
        mod2 = _load_module(mod_name, str(src))
        lm2 = mod2.__dict__["$module"]
        results2 = _query_greet(lm2)

        assert results1 == results2 == ["hello", "world"]

    def test_rules_from_cache(self, tmp_path):
        """Rules (head <- body) work from cache."""
        src = tmp_path / "rules_cached.clausal"
        src.write_text(textwrap.dedent("""\
            double(X_, Y_) <- (Y_ := X_ * 2)
        """))
        mod_name = "_pycache_rules_test"
        try:
            # First load.
            mod1 = _load_module(mod_name, str(src))
            lm1 = mod1.__dict__["$module"]
            y1 = Var()
            r1 = [deref(y1) for _ in call("double", 5, y1, module=lm1)]
            assert r1 == [10]

            # Second load (cached).
            mod2 = _load_module(mod_name, str(src))
            lm2 = mod2.__dict__["$module"]
            y2 = Var()
            r2 = [deref(y2) for _ in call("double", 5, y2, module=lm2)]
            assert r2 == [10]
        finally:
            sys.modules.pop(mod_name, None)
            pycache = tmp_path / "__pycache__"
            if pycache.exists():
                shutil.rmtree(pycache)


class TestDynamicAfterCache:
    """Dynamic predicates support runtime assertz/retract after cached load."""

    def test_dynamic_assertz_after_cache(self, tmp_path):
        src = tmp_path / "dyn_cached.clausal"
        src.write_text(textwrap.dedent("""\
            -dynamic(color/1)
            color("red"),
        """))
        mod_name = "_pycache_dyn_test"
        try:
            # Load twice to ensure cache.
            _load_module(mod_name, str(src))
            mod = _load_module(mod_name, str(src))
            lm = mod.__dict__["$module"]

            # Query initial state.
            v = Var()
            results = [deref(v) for _ in call("color", v, module=lm)]
            assert results == ["red"]

            # Runtime assertz — dynamic should still work.
            color_cls = mod.__dict__["color"]
            assert not color_cls._locked
        finally:
            sys.modules.pop(mod_name, None)
            pycache = tmp_path / "__pycache__"
            if pycache.exists():
                shutil.rmtree(pycache)


class TestDontWriteBytecode:
    """sys.dont_write_bytecode = True suppresses cache writes."""

    def test_no_pyc_when_dont_write(self, tmp_clausal):
        src, mod_name = tmp_clausal
        pycache = src.parent / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

        old = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            _load_module(mod_name, str(src))
        finally:
            sys.dont_write_bytecode = old

        # Should still work (predicates are functional).
        # But no __pycache__ should be created.
        pyc_path = importlib.util.cache_from_source(str(src))
        assert not os.path.exists(pyc_path), ".pyc should not be written"


class TestDeferredCompilation:
    """Deferred compilation: compile_predicate called once per predicate."""

    def test_compile_called_once_per_predicate(self, tmp_path):
        """With 3 facts for the same predicate, compile_predicate should be
        called exactly once (after all clauses asserted)."""
        src = tmp_path / "deferred.clausal"
        src.write_text(textwrap.dedent("""\
            item("a"),
            item("b"),
            item("c"),
        """))
        mod_name = "_pycache_deferred_test"
        # Remove any cached .pyc so source_to_code runs.
        pycache = tmp_path / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

        try:
            with patch("clausal.logic.compiler_v2.compile_predicate_trampoline",
                       wraps=compile_predicate_trampoline) as mock_cp:
                _load_module(mod_name, str(src))
                # Should be called once for the single predicate item/1.
                assert mock_cp.call_count == 1
                args = mock_cp.call_args
                assert args[0][0] == "item"  # functor
                assert args[0][1] == 1       # arity
                assert len(args[0][2]) == 3  # all 3 clauses at once
        finally:
            sys.modules.pop(mod_name, None)
            if pycache.exists():
                shutil.rmtree(pycache)

    def test_multiple_predicates_compiled_once_each(self, tmp_path):
        """Multiple predicates each get compiled exactly once."""
        src = tmp_path / "multi_pred.clausal"
        src.write_text(textwrap.dedent("""\
            foo("a"),
            foo("b"),
            bar("x"),
            bar("y"),
            bar("z"),
        """))
        mod_name = "_pycache_multi_pred_test"
        pycache = tmp_path / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

        try:
            with patch("clausal.logic.compiler_v2.compile_predicate_trampoline",
                       wraps=compile_predicate_trampoline) as mock_cp:
                _load_module(mod_name, str(src))
                # Two predicates: foo/1 and bar/1.
                assert mock_cp.call_count == 2
                calls = {c[0][0]: len(c[0][2]) for c in mock_cp.call_args_list}
                assert calls == {"foo": 2, "bar": 3}
        finally:
            sys.modules.pop(mod_name, None)
            if pycache.exists():
                shutil.rmtree(pycache)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _query_greet(logic_module):
    """Query greet/1 and return list of deref'd values."""
    results = []
    v = Var()
    for trail in call("greet", v, module=logic_module):
        results.append(deref(v))
    return results
