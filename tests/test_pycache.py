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

from clausal.logic.atoms import mint
import clausal.import_hook
from clausal.import_hook import PredicateLoader, _load_module
from clausal.logic.compiler import compile_predicate_trampoline
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
        -double_quotes(atom)
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
        # nv
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
        # nv
        src, mod_name = tmp_clausal
        _load_module(mod_name, str(src))

        expected_pyc = importlib.util.cache_from_source(str(src))
        assert os.path.exists(expected_pyc), f"expected .pyc at {expected_pyc}"


class TestPycacheCacheHit:
    """Second import uses cached .pyc — source_to_code is not called."""

    def test_source_to_code_skipped_on_cache_hit(self, tmp_clausal):
        # nv
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
        # nv
        src, mod_name = tmp_clausal
        # First load.
        mod1 = _load_module(mod_name, str(src))
        lm1 = mod1.__dict__["$module"]
        clauses1 = lm1.db.clauses_for("greet", 1)
        assert len(clauses1) == 2

        # Modify source — add a third fact.
        src.write_text(textwrap.dedent("""\
            -double_quotes(atom)
            greet("hello"),
            greet("world"),
            greet("again"),
        """))

        # Second load should pick up the new clause.
        mod2 = _load_module(mod_name, str(src))
        lm2 = mod2.__dict__["$module"]
        clauses2 = lm2.db.clauses_for("greet", 1)
        assert len(clauses2) == 3

    def test_same_size_same_second_edit_recompiles(self, tmp_path):
        """A same-size edit within the same integer second must recompile.

        Truncating mtime to whole seconds (``int(st.st_mtime)``) let the stale
        .pyc be served for this window — the mutation-testing false-green bug.
        With nanosecond mtime the cache is correctly invalidated. Both source
        versions have identical byte length (``val(1)`` / ``val(2)``) so size —
        which is also in the cache key — cannot mask the difference; the mtimes
        are pinned so both loads fall in the same integer second.
        """
        # nv
        src = tmp_path / "same_size.clausal"
        mod_name = "_pycache_same_size_test"
        pycache = tmp_path / "__pycache__"
        try:
            # First version + first load (creates .pyc).
            src.write_text("val(1),\n")
            base_ns = 1_600_000_000_000_000_000  # arbitrary fixed nanosecond time
            os.utime(src, ns=(base_ns, base_ns))
            mod1 = _load_module(mod_name, str(src))
            lm1 = mod1.__dict__["$module"]
            v1 = Var()
            r1 = [deref(v1) for _ in call("val", v1, module=lm1)]
            assert r1 == [1]

            # Edit to a same-size source within the SAME integer second
            # (advance only nanoseconds, keeping whole-second value identical).
            src.write_text("val(2),\n")
            edit_ns = base_ns + 250_000_000  # +0.25s → same integer second
            assert int(edit_ns / 1e9) == int(base_ns / 1e9)
            os.utime(src, ns=(edit_ns, edit_ns))
            assert src.stat().st_size == len("val(1),\n")  # sizes equal

            # Second load must recompile and see the new fact.
            sys.modules.pop(mod_name, None)
            mod2 = _load_module(mod_name, str(src))
            lm2 = mod2.__dict__["$module"]
            v2 = Var()
            r2 = [deref(v2) for _ in call("val", v2, module=lm2)]
            assert r2 == [2], "stale .pyc served for same-size same-second edit"
        finally:
            sys.modules.pop(mod_name, None)
            if pycache.exists():
                shutil.rmtree(pycache)


class TestCachedCorrectness:
    """Predicates work identically from cache vs fresh."""

    def test_query_from_cache(self, tmp_clausal):
        # nv
        src, mod_name = tmp_clausal
        # First load (creates cache).
        mod1 = _load_module(mod_name, str(src))
        lm1 = mod1.__dict__["$module"]
        results1 = _query_greet(lm1)

        # Second load (from cache).
        mod2 = _load_module(mod_name, str(src))
        lm2 = mod2.__dict__["$module"]
        results2 = _query_greet(lm2)

        assert results1 == results2 == [mint("hello"), mint("world")]

    def test_rules_from_cache(self, tmp_path):
        """Rules (head <- body) work from cache."""
        # nv
        src = tmp_path / "rules_cached.clausal"
        src.write_text(textwrap.dedent("""\
            double(_x, _y) <- (_y == _x * 2)
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
        # nv
        src = tmp_path / "dyn_cached.clausal"
        src.write_text(textwrap.dedent("""\
            -double_quotes(atom)
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
            assert results == [mint("red")]

            # Runtime assertz — dynamic should still work.
            color_row = lm.db.row("color", 1)
            assert color_row is not None and color_row.clauses
            assert not color_row.locked
        finally:
            sys.modules.pop(mod_name, None)
            pycache = tmp_path / "__pycache__"
            if pycache.exists():
                shutil.rmtree(pycache)


class TestDontWriteBytecode:
    """sys.dont_write_bytecode = True suppresses cache writes."""

    def test_no_pyc_when_dont_write(self, tmp_clausal):
        # nv
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
        # nv
        src = tmp_path / "deferred.clausal"
        src.write_text(textwrap.dedent("""\
            -double_quotes(atom)
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
        # nv
        src = tmp_path / "multi_pred.clausal"
        src.write_text(textwrap.dedent("""\
            -double_quotes(atom)
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


class TestEngineFingerprintInvalidation:
    """An ENGINE change invalidates cached bytecode, not just a source change.

    A ``.clausal`` file is compiled by the engine's transformer and the result
    cached as ordinary bytecode, validated against the source's mtime and
    size. Nothing about the source changes when the compiler does -- so before
    the fingerprint, upgrading the engine left every unchanged file running
    the compilation whatever engine last saw it produced. Silently: stale
    bytecode loads perfectly well, which is why a load census cannot detect
    this and why it went 55 transformer commits unnoticed.

    ``CLAUSAL_BYTECODE_TAG`` was always the intended lever (it is XORed into
    the mtime importlib validates against, so a bump invalidates everything
    with no clearing step). It is hand-maintained, and nothing turned it. The
    fingerprint turns it automatically.
    """

    def test_the_effective_tag_includes_the_fingerprint(self):
        from clausal import import_hook as ih
        assert ih._effective_bytecode_tag() != ih.CLAUSAL_BYTECODE_TAG, (
            "the manual tag alone would mean nothing had been derived")
        assert ih._effective_bytecode_tag() == (
            ih.CLAUSAL_BYTECODE_TAG ^ ih._compilation_fingerprint())

    def test_the_fingerprint_is_lazy_and_memoised(self):
        """It costs ~10ms, so a process that never compiles Clausal source
        must not pay it, and one that compiles a thousand files pays once."""
        from clausal import import_hook as ih
        first = ih._compilation_fingerprint()
        assert ih._FINGERPRINT_CACHE == first
        assert ih._compilation_fingerprint() is first

    def test_it_tracks_content_of_compilation_sources(self, tmp_path, monkeypatch):
        """Content, not mtimes: ``git checkout`` rewrites mtimes without
        changing content, and discarding every user's cache on a branch
        switch would be a cost blamed on something else."""
        from clausal import import_hook as ih
        pkg = tmp_path / "enginelike"
        (pkg / "templating").mkdir(parents=True)
        source = pkg / "templating" / "term_rewriting.py"
        source.write_text("EMIT = 1\n")

        monkeypatch.setattr(ih, "_COMPILATION_ROOTS", ("templating",))
        monkeypatch.setattr(ih, "_COMPILATION_FILES", ())
        monkeypatch.setattr(ih, "__file__", str(pkg / "import_hook.py"))

        monkeypatch.setattr(ih, "_FINGERPRINT_CACHE", None)
        before = ih._compilation_fingerprint()

        # Same content, new mtime: the fingerprint must NOT move.
        os.utime(source, (0, 0))
        monkeypatch.setattr(ih, "_FINGERPRINT_CACHE", None)
        assert ih._compilation_fingerprint() == before, "mtime must not count"

        # Changed content: it must.
        source.write_text("EMIT = 2\n")
        monkeypatch.setattr(ih, "_FINGERPRINT_CACHE", None)
        assert ih._compilation_fingerprint() != before

    def test_it_ignores_engine_files_that_do_not_decide_emitted_code(
            self, tmp_path, monkeypatch):
        """The negative control. Every file in the roots invalidates every
        user's cache when it changes, so the set is narrow on purpose -- a
        runtime-only module must not be in it."""
        from clausal import import_hook as ih
        pkg = tmp_path / "enginelike"
        (pkg / "templating").mkdir(parents=True)
        (pkg / "templating" / "t.py").write_text("EMIT = 1\n")
        runtime_only = pkg / "solve.py"
        runtime_only.write_text("def solve(): pass\n")

        monkeypatch.setattr(ih, "_COMPILATION_ROOTS", ("templating",))
        monkeypatch.setattr(ih, "_COMPILATION_FILES", ())
        monkeypatch.setattr(ih, "__file__", str(pkg / "import_hook.py"))
        monkeypatch.setattr(ih, "_FINGERPRINT_CACHE", None)
        before = ih._compilation_fingerprint()

        runtime_only.write_text("def solve(): return 42\n")
        monkeypatch.setattr(ih, "_FINGERPRINT_CACHE", None)
        assert ih._compilation_fingerprint() == before, (
            "a runtime-only change must not discard everyone's bytecode; "
            "the manual tag is the lever for that case")

    def test_it_degrades_to_the_manual_tag_when_sources_are_unreadable(
            self, tmp_path, monkeypatch):
        """Degrading to the hand tag is the safe direction -- it is exactly
        the behaviour that existed before the fingerprint."""
        from clausal import import_hook as ih
        monkeypatch.setattr(ih, "_COMPILATION_ROOTS", ("does_not_exist",))
        monkeypatch.setattr(ih, "_COMPILATION_FILES", ("also/missing.py",))
        monkeypatch.setattr(ih, "__file__", str(tmp_path / "import_hook.py"))
        monkeypatch.setattr(ih, "_FINGERPRINT_CACHE", None)
        assert ih._compilation_fingerprint() == 0
        assert ih._effective_bytecode_tag() == ih.CLAUSAL_BYTECODE_TAG

    def test_a_changed_fingerprint_recompiles_a_warm_cache(self, tmp_clausal):
        """End to end, and the assertion the whole mechanism exists for."""
        from clausal import import_hook as ih
        src, mod_name = tmp_clausal
        _load_module(mod_name + "_warm", str(src))          # writes the .pyc

        with patch.object(ih.PredicateLoader, "source_to_code",
                          autospec=True,
                          side_effect=ih.PredicateLoader.source_to_code) as spy:
            _load_module(mod_name + "_hit", str(src))
            assert spy.call_count == 0, "unchanged engine: cache hit expected"

            original = ih._FINGERPRINT_CACHE
            try:
                ih._FINGERPRINT_CACHE = (original or 0) ^ 0xABCD1234
                _load_module(mod_name + "_miss", str(src))
                assert spy.call_count == 1, (
                    "a changed compiler must recompile, not reuse")
            finally:
                ih._FINGERPRINT_CACHE = original
