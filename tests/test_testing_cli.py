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
