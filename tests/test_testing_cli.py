"""CLI behaviour for ``python -m clausal.testing``.

Regression: a missing path (mistyped path / wrong cwd) and a file with no
``Test(...)`` clauses both used to report ``[PASSED]`` with exit 0, masking
mistakes as green runs. See todo/testing-missing-file-reports-pass.md.
"""

from __future__ import annotations

from clausal.testing import main


def test_missing_path_errors_nonzero(capsys, tmp_path):
    rc = main([str(tmp_path / "does_not_exist.clausal")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no such file" in err


def test_non_clausal_file_errors(capsys, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    rc = main([str(p)])
    assert rc == 2
    assert "not a .clausal file" in capsys.readouterr().err


def test_testless_file_is_distinct_not_passed(capsys, tmp_path):
    p = tmp_path / "notests.clausal"
    p.write_text("foo(1),\n")
    rc = main([str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NO TESTS" in out
    assert "PASSED" not in out


def test_testless_file_strict_fails(capsys, tmp_path):
    p = tmp_path / "notests.clausal"
    p.write_text("foo(1),\n")
    assert main(["--strict", str(p)]) == 1
    assert main(["--fail-on-empty", str(p)]) == 1


def test_passing_file_still_passes(capsys, tmp_path):
    p = tmp_path / "ok.clausal"
    p.write_text('Test("one is one") <- (1 == 1)\n')
    rc = main([str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 passed, 0 failed [PASSED]" in out


def test_failing_file_still_fails(capsys, tmp_path):
    p = tmp_path / "bad.clausal"
    p.write_text('Test("one is two") <- (1 == 2)\n')
    rc = main([str(p)])
    assert rc == 1
    assert "[FAILED]" in capsys.readouterr().out


# ── test/1 is the predicate; Test/1 is its deprecated spelling ───────────────
#
# Predicates are lowercase (docs/syntax.md), so the test-clause predicate is
# ``test/1``.  ``Test/1`` still runs but warns once per file at load time,
# the way ``If`` -> ``if_`` does.  A file may hold both spellings during a
# rename, and the runner reports the UNION in source order.

import warnings

import pytest

from clausal.templating.term_rewriting import ClausalDeprecatedSpellingWarning
from clausal.testing import collect_tests, load_clausal_module, run_file


def _spelling_warnings(caught):
    return [w for w in caught
            if issubclass(w.category, ClausalDeprecatedSpellingWarning)]


def _load_recording(path):
    """Load *path* and return (module, spelling warnings raised by the load)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = load_clausal_module(path)
    return mod, _spelling_warnings(caught)


LOWER = (
    'test("zeta") <- (1 == 1)\n'
    'test("alpha") <- (2 == 2)\n'
    'test("mid") <- (3 == 3)\n'
)
UPPER = LOWER.replace("test(", "Test(")


def test_lowercase_only_file_runs_all_silently(tmp_path):
    """# nv"""
    p = tmp_path / "lower.clausal"
    p.write_text(LOWER)
    mod, spelling = _load_recording(p)
    assert spelling == []
    # File order, not sorted: the canonical spelling keeps today's order rule.
    assert collect_tests(mod) == ["zeta", "alpha", "mid"]
    results = run_file(p)
    assert [(r.name, r.passed) for r in results.results] == [
        ("zeta", True), ("alpha", True), ("mid", True)]


def test_uppercase_only_file_runs_all_and_warns_once(tmp_path):
    """# nv"""
    p = tmp_path / "upper.clausal"
    p.write_text(UPPER)
    mod, spelling = _load_recording(p)
    assert len(spelling) == 1, [str(w.message) for w in spelling]
    message = str(spelling[0].message)
    assert "`Test` -> `test`" in message
    assert "test/1" in message
    assert "upper.clausal:1" in message  # the first offending site
    assert collect_tests(mod) == ["zeta", "alpha", "mid"]
    assert [(r.name, r.passed) for r in run_file(p).results] == [
        ("zeta", True), ("alpha", True), ("mid", True)]


def test_mixed_file_runs_the_union_in_source_order(tmp_path):
    """# nv"""
    p = tmp_path / "mixed.clausal"
    p.write_text(
        'test("a") <- (1 == 1)\n'
        'Test("b") <- (1 == 1)\n'
        'test("c") <- (1 == 1)\n'
        'Test("d") <- (1 == 2)\n'   # a failing legacy clause: FAIL, not error
        'test("e") <- (1 == 2)\n'   # a failing canonical clause
    )
    mod, spelling = _load_recording(p)
    assert len(spelling) == 1
    assert collect_tests(mod) == ["a", "b", "c", "d", "e"]
    results = run_file(p)
    assert [(r.name, r.passed, r.error) for r in results.results] == [
        ("a", True, None), ("b", True, None), ("c", True, None),
        ("d", False, None), ("e", False, None)]
    # Each failure was diagnosed against ITS OWN clause, whichever spelling.
    for r in results.results[3:]:
        assert r.diagnostic is not None
        assert not any("could not locate" in n for n in r.diagnostic.notes)
        assert r.line is not None


def test_cli_messages_name_the_lowercase_predicate(capsys, tmp_path):
    """# nv"""
    p = tmp_path / "notests.clausal"
    p.write_text("foo(1),\n")
    assert main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "no test/1 clauses found" in out
    assert "Test(" not in out
    with pytest.raises(SystemExit):
        main(["--help"])
    help_text = capsys.readouterr().out
    assert "test/1" in help_text
    assert "Test(...)" not in help_text


def test_same_description_under_both_spellings_warns(tmp_path):
    """# nv"""
    p = tmp_path / "dup.clausal"
    p.write_text(
        'test("same") <- (1 == 1)\n'
        'Test("same") <- (1 == 2)\n'
        'test("other") <- (1 == 1)\n'
    )
    mod, _spelling = _load_recording(p)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        names = collect_tests(mod)
    dups = [w for w in caught if "both test/1 and Test/1" in str(w.message)]
    assert len(dups) == 1, [str(w.message) for w in caught]
    message = str(dups[0].message)
    assert "dup.clausal" in message
    assert "'same'" in message
    assert "'other'" not in message
    assert names == ["same", "same", "other"]


# ── ``.seam`` is an alias extension for ``.clausal`` ─────────────────────────


def test_seam_file_is_run(capsys, tmp_path):
    p = tmp_path / "ok.seam"
    p.write_text('test("one is one") <- (1 == 1)\n')
    rc = main([str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 passed, 0 failed [PASSED]" in out


def test_seam_files_are_discovered_under_a_directory(capsys, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.seam").write_text('test("seam") <- (1 == 1)\n')
    (tmp_path / "sub" / "b.clausal").write_text('test("clausal") <- (1 == 1)\n')
    (tmp_path / "sub" / "c.txt").write_text('test("txt") <- (1 == 1)\n')
    rc = main(["-v", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "a.seam::seam" in out
    assert "b.clausal::clausal" in out
    assert "txt" not in out
    assert "2 passed, 0 failed [PASSED]" in out


def test_discover_clausal_files_orders_both_extensions_together(tmp_path):
    from clausal.testing import discover_clausal_files
    for name in ("b.seam", "a.clausal", "c.clausal", "d.txt"):
        (tmp_path / name).write_text("")
    found = [p.name for p in discover_clausal_files([tmp_path])]
    assert found == ["a.clausal", "b.seam", "c.clausal"]


def test_seam_load_module_name_drops_the_suffix(tmp_path):
    from clausal.testing import load_clausal_module
    p = tmp_path / "named.seam"
    p.write_text("foo(1),\n")
    mod = load_clausal_module(p)
    assert mod.__name__ == "_clausal_test_named"
