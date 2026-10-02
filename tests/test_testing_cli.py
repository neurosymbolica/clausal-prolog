"""CLI behaviour for ``python -m clausal.testing``.

Regression: a missing path (mistyped path / wrong cwd) and a file with no
``test(...)`` clauses both used to report ``[PASSED]`` with exit 0, masking
mistakes as green runs. See todo/testing-missing-file-reports-pass.md.  An
empty run now exits 5 by default (tests/test_testing_empty_scan_and_pl.py).
"""

from __future__ import annotations

from clausal.testing import main
from tests._suffix import SEAM


def test_missing_path_errors_nonzero(capsys, tmp_path):
    rc = main([str(tmp_path / f"does_not_exist{SEAM}")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no such file" in err


def test_non_clausal_file_errors(capsys, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    rc = main([str(p)])
    assert rc == 2
    assert "not a .clausal, .seam or .pl file" in capsys.readouterr().err


def test_testless_file_is_distinct_not_passed(capsys, tmp_path):
    p = tmp_path / f"notests{SEAM}"
    p.write_text("foo(1),\n")
    rc = main([str(p)])
    out = capsys.readouterr().out
    assert rc == 5  # EXIT_NO_TESTS: an empty run is not a green run
    assert "NO TESTS" in out
    assert "PASSED" not in out


def test_testless_file_strict_fails(capsys, tmp_path):
    p = tmp_path / f"notests{SEAM}"
    p.write_text("foo(1),\n")
    # Failing on an empty run is the default now; the flags stay accepted.
    assert main(["--strict", str(p)]) == 5
    assert main(["--fail-on-empty", str(p)]) == 5


def test_passing_file_still_passes(capsys, tmp_path):
    p = tmp_path / f"ok{SEAM}"
    p.write_text('-double_quotes(atom)\ntest("one is one") <- (1 == 1)\n')
    rc = main([str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 passed, 0 failed [PASSED]" in out


def test_failing_file_still_fails(capsys, tmp_path):
    p = tmp_path / f"bad{SEAM}"
    p.write_text('-double_quotes(atom)\ntest("one is two") <- (1 == 2)\n')
    rc = main([str(p)])
    assert rc == 1
    assert "[FAILED]" in capsys.readouterr().out


# ── test/1 is the predicate; Test/1 was its spelling ─────────────────────────
#
# Predicates are lowercase (docs/syntax.md), so the test-clause predicate is
# ``test/1``.  ``Test/1`` is TitleCase, which has no role in Clausal code:
# a file spelling it no longer loads — the TitleCase lint raises a located
# SyntaxError at the first ``Test(`` clause and names the rename.  These are
# the engine-side witnesses of that; the runner's own ``Test/1`` union
# (``collect_tests`` reads both spellings) stays until the removal in
# todo/remove-Test-1-spelling-union-after-migration-2026-09-10.md.

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
    '-double_quotes(atom)\ntest("zeta") <- (1 == 1)\n'
    'test("alpha") <- (2 == 2)\n'
    'test("mid") <- (3 == 3)\n'
)
UPPER = LOWER.replace("test(", "Test(")


def test_lowercase_only_file_runs_all_silently(tmp_path):
    """# nv"""
    p = tmp_path / f"lower{SEAM}"
    p.write_text(LOWER)
    mod, spelling = _load_recording(p)
    assert spelling == []
    # File order, not sorted: the canonical spelling keeps today's order rule.
    assert collect_tests(mod) == ["zeta", "alpha", "mid"]
    results = run_file(p)
    assert [(r.name, r.passed) for r in results.results] == [
        ("zeta", True), ("alpha", True), ("mid", True)]


def test_uppercase_file_does_not_load_and_names_the_rename(tmp_path):
    """# nv"""
    p = tmp_path / f"upper{SEAM}"
    p.write_text(UPPER)
    with pytest.raises(SyntaxError) as ei:
        load_clausal_module(p)
    message = str(ei.value)
    assert "`Test` is TitleCase" in message
    assert "Rename `Test` -> `test`" in message
    assert f"upper{SEAM}:2" in message  # the first offending site
    assert ei.value.lineno == 2


def test_uppercase_file_is_a_load_failure_for_the_runner(tmp_path):
    """``run_file`` reports the load error as the single ``<load>`` result
    and the CLI exits 1 — never a green run."""
    # nv
    p = tmp_path / f"upper{SEAM}"
    p.write_text(UPPER)
    results = run_file(p)
    assert [(r.name, r.passed) for r in results.results] == [("<load>", False)]
    assert isinstance(results.results[0].error, SyntaxError)
    assert main([str(p)]) == 1


def test_witness_fixture_on_the_old_spelling_does_not_load():
    """The checked-in witness (tests/fixtures/titlecase_test_spelling_witness.seam)."""
    # nv
    from pathlib import Path
    p = Path(__file__).parent / "fixtures" / "titlecase_test_spelling_witness.seam"
    with pytest.raises(SyntaxError) as ei:
        load_clausal_module(p)
    assert "Rename `Test` -> `test`" in str(ei.value)
    assert ei.value.lineno == 7
    assert [(r.name, r.passed) for r in run_file(p).results] == [("<load>", False)]


def test_mixed_file_fails_at_the_first_uppercase_clause(tmp_path):
    """A file part-way through a rename does not load either; the error
    locates the first ``Test(`` clause, not the file's first line."""
    # nv
    p = tmp_path / f"mixed{SEAM}"
    p.write_text(
        '-double_quotes(atom)\ntest("a") <- (1 == 1)\n'
        'Test("b") <- (1 == 1)\n'
        'test("c") <- (1 == 1)\n'
    )
    with pytest.raises(SyntaxError) as ei:
        load_clausal_module(p)
    assert f"mixed{SEAM}:3" in str(ei.value)
    assert ei.value.lineno == 3


def test_cli_messages_name_the_lowercase_predicate(capsys, tmp_path):
    """# nv"""
    p = tmp_path / f"notests{SEAM}"
    p.write_text("foo(1),\n")
    assert main([str(p)]) == 5
    out = capsys.readouterr().out
    assert "no test/1 clauses found" in out
    assert "Test(" not in out
    with pytest.raises(SystemExit):
        main(["--help"])
    help_text = capsys.readouterr().out
    assert "test/1" in help_text
    assert "Test(...)" not in help_text


# ── ``.seam`` is an alias extension for ``.clausal`` ─────────────────────────


def test_seam_file_is_run(capsys, tmp_path):
    p = tmp_path / "ok.seam"
    p.write_text('-double_quotes(atom)\ntest("one is one") <- (1 == 1)\n')
    rc = main([str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 passed, 0 failed [PASSED]" in out


def test_seam_files_are_discovered_under_a_directory(capsys, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.seam").write_text('-double_quotes(atom)\ntest("seam") <- (1 == 1)\n')
    (tmp_path / "sub" / f"b{SEAM}").write_text('-double_quotes(atom)\ntest("clausal") <- (1 == 1)\n')
    (tmp_path / "sub" / "c.txt").write_text('-double_quotes(atom)\ntest("txt") <- (1 == 1)\n')
    rc = main(["-v", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "a.seam::seam" in out
    assert f"b{SEAM}::clausal" in out
    assert "::txt" not in out                       # c.txt is not run...
    assert "c.txt  (unsupported suffix)" in out       # ...and is reported
    assert "2 passed, 0 failed [PASSED]" in out


def test_discover_clausal_files_orders_both_extensions_together(tmp_path):
    from clausal.testing import discover_clausal_files
    for name in ("b.seam", f"a{SEAM}", f"c{SEAM}", "d.txt"):
        (tmp_path / name).write_text("")
    found = [p.name for p in discover_clausal_files([tmp_path])]
    assert found == [f"a{SEAM}", "b.seam", f"c{SEAM}"]


def test_seam_load_module_name_drops_the_suffix(tmp_path):
    from clausal.testing import load_clausal_module
    p = tmp_path / "named.seam"
    p.write_text("foo(1),\n")
    mod = load_clausal_module(p)
    assert mod.__name__ == "_clausal_test_named"
