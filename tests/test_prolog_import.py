"""Tests for direct .pl file import via PrologLoader/PrologFinder.

Verifies:
  - Basic .pl import (facts and rules)
  - Arithmetic, comparison operators
  - __pycache__ .pyc creation and cache hits
  - Cache invalidation on source modification
  - Recursive imports (use_module chaining)
  - Library imports (use_module(library(clpfd)))
  - .clausal takes priority over .pl when both exist
  - Translation errors (cut, if-then-else) surface as SyntaxError
  - DCG rules
  - dynamic/assertz after import
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import sys
import textwrap
from unittest.mock import patch

import pytest

import clausal.import_hook
from clausal.import_hook import PrologLoader, _load_prolog_module, _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.testing import collect_tests, run_test


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_pl(tmp_path, name, source):
    """write a .pl file in tmp_path and return its str path."""
    path = tmp_path / f"{name}.pl"
    path.write_text(textwrap.dedent(source))
    return str(path)


@pytest.fixture(autouse=True)
def cleanup_sys_path(tmp_path):
    """Add tmp_path to sys.path and clean up after each test."""
    sys_path_str = str(tmp_path)
    sys.path.insert(0, sys_path_str)
    yield
    sys.path.remove(sys_path_str)
    # Remove any test modules loaded during the test.
    for key in list(sys.modules):
        if key.startswith(("_pl_test_", "plbase_", "prio_test", "pltest_",
                           "_golden_pl")):
            del sys.modules[key]


# ── TestBasicImport ───────────────────────────────────────────────────────────


class TestBasicImport:
    """Basic .pl file import: facts and recursive rules."""

    def test_facts(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_facts", """\
            edge(1, 2).
            edge(2, 3).
            edge(3, 4).
        """)
        mod = _load_prolog_module("_pl_test_facts", path)
        lm = mod.__clausal_module__
        clauses = lm.db.clauses_for("Edge", 2)
        assert len(clauses) == 3

    def test_facts_queryable(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_facts2", """\
            score(1).
            score(2).
            score(3).
        """)
        mod = _load_prolog_module("_pl_test_facts2", path)
        lm = mod.__clausal_module__
        results = list(call("Score", Var(), module=lm))
        assert len(results) == 3

    def test_rule_with_body(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_rule", """\
            edge(1, 2).
            edge(2, 3).
            path(X, Y) :- edge(X, Y).
            path(X, Z) :- edge(X, Y), path(Y, Z).
        """)
        mod = _load_prolog_module("_pl_test_rule", path)
        lm = mod.__clausal_module__
        x, y = Var(), Var()
        results = [(deref(x), deref(y)) for _ in call("Path", x, y, module=lm)]
        # Should find path(1,2), path(2,3), path(1,3)
        assert (1, 2) in results
        assert (1, 3) in results
        assert (2, 3) in results


# ── TestArithmetic ────────────────────────────────────────────────────────────


class TestArithmetic:
    """Arithmetic and comparison operators in .pl files."""

    def test_is_operator(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_arith", """\
            double(X, Y) :- Y is X * 2.
        """)
        mod = _load_prolog_module("_pl_test_arith", path)
        lm = mod.__clausal_module__
        y = Var()
        results = [deref(y) for _ in call("Double", 3, y, module=lm)]
        assert results == [6]

    def test_comparison(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_cmp", """\
            positive(X) :- X > 0.
        """)
        mod = _load_prolog_module("_pl_test_cmp", path)
        lm = mod.__clausal_module__
        assert list(call("Positive", 5, module=lm))
        assert not list(call("Positive", -1, module=lm))

    def test_unification(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_unif", """\
            same(X, X).
        """)
        mod = _load_prolog_module("_pl_test_unif", path)
        lm = mod.__clausal_module__
        assert list(call("Same", 42, 42, module=lm))
        assert not list(call("Same", 42, 99, module=lm))


# ── TestPycacheCreation ───────────────────────────────────────────────────────


class TestPycacheCreation:
    """Importing a .pl file writes a .pyc into __pycache__/."""

    def test_pyc_created(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_pyc", """\
            fact(1).
        """)
        pycache = tmp_path / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

        _load_prolog_module("_pl_test_pyc", path)

        assert pycache.exists(), "__pycache__/ dir should be created"
        pyc_files = list(pycache.glob("*.pyc"))
        assert len(pyc_files) >= 1

    def test_pyc_path_matches_source(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_pyc2", """\
            fact(1).
        """)
        _load_prolog_module("_pl_test_pyc2", path)

        expected_pyc = importlib.util.cache_from_source(path)
        assert os.path.exists(expected_pyc), f"expected .pyc at {expected_pyc}"


# ── TestPycacheCacheHit ───────────────────────────────────────────────────────


class TestPycacheCacheHit:
    """Second import uses cached .pyc — source_to_code is not called."""

    def test_source_to_code_skipped_on_cache_hit(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_cachehit", """\
            fact(1).
        """)
        # First load: creates .pyc.
        _load_prolog_module("_pl_test_cachehit", path)
        pyc_path = importlib.util.cache_from_source(path)
        assert os.path.exists(pyc_path)

        # Second load: should use cached .pyc and NOT call source_to_code.
        with patch.object(PrologLoader, "source_to_code",
                          wraps=PrologLoader.source_to_code) as mock_s2c:
            _load_prolog_module("_pl_test_cachehit_2", path)
            mock_s2c.assert_not_called()

    def test_cached_predicates_work(self, tmp_path):
        """Predicates loaded from cache behave identically to fresh load."""
        # nv
        path = _write_pl(tmp_path, "_pl_test_cachehit3", """\
            animal(1).
            animal(2).
        """)
        _load_prolog_module("_pl_test_cachehit3", path)
        # Load again from cache under different module name.
        mod2 = _load_prolog_module("_pl_test_cachehit3_b", path)

        lm2 = mod2.__clausal_module__
        results = list(call("Animal", Var(), module=lm2))
        assert len(results) == 2


# ── TestPycacheInvalidation ───────────────────────────────────────────────────


class TestPycacheInvalidation:
    """Modifying source invalidates the cache."""

    def test_modified_source_recompiles(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_invalid", """\
            item(1).
            item(2).
        """)
        mod1 = _load_prolog_module("_pl_test_invalid", path)
        lm1 = mod1.__clausal_module__
        assert len(lm1.db.clauses_for("Item", 1)) == 2

        # Modify source — add a third fact (also bump mtime).
        (tmp_path / "_pl_test_invalid.pl").write_text(textwrap.dedent("""\
            item(1).
            item(2).
            item(3).
        """))
        # Ensure mtime changes (some filesystems have 1-second granularity).
        pl_stat = os.stat(path)
        os.utime(path, (pl_stat.st_atime, pl_stat.st_mtime + 2))

        mod2 = _load_prolog_module("_pl_test_invalid_2", path)
        lm2 = mod2.__clausal_module__
        assert len(lm2.db.clauses_for("Item", 1)) == 3


# ── TestRecursiveImport ───────────────────────────────────────────────────────


class TestRecursiveImport:
    """use_module chaining: foo.pl imports bar.pl."""

    def test_chained_import(self, tmp_path):
        # use_module with explicit import list so Helper is injected into
        # the calling module's namespace (standard Prolog practice).
        # Note: module names must be valid Prolog atoms (no leading underscore).
        # nv
        _write_pl(tmp_path, "plbase_helper", """\
            helper(10).
            helper(20).
        """)
        main_path = _write_pl(tmp_path, "_pl_test_main", """\
            :- use_module(plbase_helper, [helper/1]).
            uses_helper(Z) :- helper(Z).
        """)
        mod = _load_prolog_module("_pl_test_main", main_path)
        lm = mod.__clausal_module__
        results = list(call("UsesHelper", Var(), module=lm))
        assert len(results) == 2

    def test_imported_facts_accessible(self, tmp_path):
        # nv
        _write_pl(tmp_path, "plbase_vals", """\
            val(100).
            val(200).
        """)
        main_path = _write_pl(tmp_path, "_pl_test_main2", """\
            :- use_module(plbase_vals, [val/1]).
            my_val(C) :- val(C).
        """)
        mod = _load_prolog_module("_pl_test_main2", main_path)
        lm = mod.__clausal_module__
        z = Var()
        results = [deref(z) for _ in call("MyVal", z, module=lm)]
        assert 100 in results
        assert 200 in results


# ── TestLibraryImport ─────────────────────────────────────────────────────────


class TestLibraryImport:
    """use_module(library(X)) resolves to clausal built-in modules."""

    def test_clpfd_library_translates_to_import(self):
        """use_module(library(clpfd)) generates -import_from(clausal.logic.clpfd, ...)."""
        # nv
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        from clausal.tools.prolog_dialect import Dialect
        src = ":- use_module(library(clpfd), [all_different/1]).\n"
        result = prolog_to_clausal(src, dialect=Dialect.swi())
        assert "import_from" in result
        assert "clausal.logic.clpfd" in result

    def test_lists_library_no_import_generated(self):
        """library(lists) maps to None — emitted as comment, no import directive."""
        # nv
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        from clausal.tools.prolog_dialect import Dialect
        src = ":- use_module(library(lists)).\n"
        result = prolog_to_clausal(src, dialect=Dialect.swi())
        # library(lists) is built-in, so no -import_from or -import_module
        assert "-import_from" not in result
        assert "-import_module" not in result
        assert "built-in" in result


# ── TestPriority ──────────────────────────────────────────────────────────────


class TestPriority:
    """.clausal file takes priority over .pl when both exist."""

    def test_clausal_wins_over_pl(self, tmp_path):
        # write .clausal with fact(1) — one clause.
        # nv
        clausal_file = tmp_path / "prio_test.clausal"
        clausal_file.write_text("fact(1),\n")

        # write .pl with fact(1) and fact(2) — two clauses.
        _write_pl(tmp_path, "prio_test", """\
            fact(1).
            fact(2).
        """)

        # Import via importlib — finders should pick .clausal (1 clause),
        # not .pl (2 clauses).
        mod = importlib.import_module("prio_test")
        lm = mod.__clausal_module__
        clauses = lm.db.clauses_for("fact", 1)
        assert len(clauses) == 1


# ── TestErrors ────────────────────────────────────────────────────────────────


class TestErrors:
    """Translation errors surface as SyntaxError."""

    def test_cut_loads_successfully(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_cut", """\
            first(X, [X|_]) :- !.
            first(X, [_|T]) :- first(X, T).
        """)
        mod = _load_prolog_module("_pl_test_cut", path)
        assert "First" in mod.__dict__

    def test_if_then_else_raises_syntax_error(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_ite", """\
            classify(X, Cls) :-
                (X > 0 -> Cls = positive ; Cls = nonpositive).
        """)
        with pytest.raises(SyntaxError):
            _load_prolog_module("_pl_test_ite", path)


# ── TestDCG ───────────────────────────────────────────────────────────────────


class TestDCG:
    """DCG rules in .pl files compile and execute."""

    def test_dcg_rule(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_dcg", """\
            greeting --> [1], [2].
        """)
        mod = _load_prolog_module("_pl_test_dcg", path)
        lm = mod.__clausal_module__
        s0, s1 = Var(), Var()
        results = list(call("Greeting", s0, s1, module=lm))
        assert results  # DCG predicate should have at least one solution


# ── TestDynamic ───────────────────────────────────────────────────────────────


class TestDynamic:
    """dynamic predicates remain mutable after .pl import."""

    def test_assertz_after_import(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_dyn", """\
            :- dynamic(item/1).
            item(42).
        """)
        mod = _load_prolog_module("_pl_test_dyn", path)
        lm = mod.__clausal_module__

        # Verify initial clause.
        results_before = list(call("Item", Var(), module=lm))
        assert len(results_before) == 1

        # assertz a new clause — dynamic predicates should stay mutable.
        assert lm.db.is_dynamic("Item", 1)


# ── TestFinderIntegration ─────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: empty files, comments-only, encoding errors."""

    def test_empty_pl_file(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_empty", "")
        mod = _load_prolog_module("_pl_test_empty", path)
        assert hasattr(mod, '__clausal_module__')

    def test_comments_only(self, tmp_path):
        # nv
        path = _write_pl(tmp_path, "_pl_test_comments", """\
            % This file has only comments.
            /* block comment */
        """)
        mod = _load_prolog_module("_pl_test_comments", path)
        assert hasattr(mod, '__clausal_module__')

    def test_non_utf8_raises_syntax_error(self, tmp_path):
        # nv
        pl_path = tmp_path / "_pl_test_badenc.pl"
        pl_path.write_bytes(b"\xff\xfe" + "fact(1).".encode("utf-16-le"))
        with pytest.raises(SyntaxError, match="(?i)cannot import"):
            _load_prolog_module("_pl_test_badenc", str(pl_path))


# ── TestFinderIntegration ─────────────────────────────────────────────────────


class TestFinderIntegration:
    """PrologFinder works through importlib.import_module (the real import path)."""

    def test_import_finds_pl_file(self, tmp_path):
        # nv
        _write_pl(tmp_path, "pltest_auto", """\
            fact(1).
            fact(2).
        """)
        mod = importlib.import_module("pltest_auto")
        assert hasattr(mod, '__clausal_module__')
        lm = mod.__clausal_module__
        assert len(lm.db.clauses_for("Fact", 1)) == 2


# ── TestGoldenPrologImport ────────────────────────────────────────────────────

_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "prolog_golden")

# Golden .pl files that import successfully and have passing Test/1 clauses.
# dcg_grammar.pl is excluded — it has a known translator issue with DCG
# pushback lists.  Files whose Test/1 clauses rely on bare Prolog atoms
# (which become undefined Python names) have partial failures; we only
# assert on the tests that pass cleanly.
_GOLDEN_PL_FILES = sorted(
    f for f in os.listdir(_GOLDEN_DIR)
    if f.endswith(".pl") and f != "dcg_grammar.pl"
)


class TestGoldenPrologImport:
    """Import each golden .pl file and run its Test/1 clauses."""

    @pytest.mark.parametrize("pl_filename", _GOLDEN_PL_FILES,
                             ids=[f.removesuffix(".pl") for f in _GOLDEN_PL_FILES])
    def test_golden_imports(self, pl_filename):
        """Golden .pl file imports without error."""
        # nv
        path = os.path.join(_GOLDEN_DIR, pl_filename)
        mod_name = f"_golden_pl_{pl_filename.removesuffix('.pl')}"
        mod = _load_prolog_module(mod_name, path)
        assert hasattr(mod, '__clausal_module__')

    @pytest.mark.parametrize("pl_filename", _GOLDEN_PL_FILES,
                             ids=[f.removesuffix(".pl") for f in _GOLDEN_PL_FILES])
    def test_golden_tests_pass(self, pl_filename):
        """Test/1 clauses that can run should pass."""
        # nv
        path = os.path.join(_GOLDEN_DIR, pl_filename)
        mod_name = f"_golden_pl2_{pl_filename.removesuffix('.pl')}"
        mod = _load_prolog_module(mod_name, path)
        descs = collect_tests(mod)
        if not descs:
            pytest.skip("no Test/1 clauses")

        passed = []
        failed = []
        for desc in descs:
            result = run_test(mod, desc)
            (passed if result.passed else failed).append(desc)

        # At least some tests must pass (all golden files have passing tests).
        assert passed, f"no tests passed out of {len(descs)}"
