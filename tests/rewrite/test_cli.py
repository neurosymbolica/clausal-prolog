"""``clausal-rewrite`` on the command line -- the same contract as ``clausal-fmt``.

Anything that rewrites source in place has to be runnable in check mode from a
hook or a pipeline without writing anything, and has to say what it would do.
The exit codes are therefore the formatter's: 0 clean or written, 1 would
change under ``--check``/``--diff``, 2 something went wrong and nothing was
written.
"""

import subprocess
import sys


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "clausal.rewrite.cli", *args],
        capture_output=True,
        text=True,
    )


FOLDABLE = "r(K, S) <- (m(K, M), S is unknown(M))\n"
FOLDED = "r(K, unknown(M)) <- (\n    m(K, M)\n)\n"


def test_rewrites_in_place(tmp_path):
    path = tmp_path / "a.clausal"
    path.write_text(FOLDABLE)
    result = _run(str(path))
    assert result.returncode == 0, result.stderr
    assert path.read_text() == FOLDED


def test_check_reports_would_change_without_writing(tmp_path):
    path = tmp_path / "a.clausal"
    path.write_text(FOLDABLE)
    result = _run("--check", str(path))
    assert result.returncode == 1
    assert path.read_text() == FOLDABLE
    assert "a.clausal" in result.stdout


def test_check_passes_on_a_stable_file(tmp_path):
    path = tmp_path / "a.clausal"
    path.write_text("p(X) <- (\n    m(X)\n)\n")
    result = _run("--check", str(path))
    assert result.returncode == 0, result.stdout + result.stderr


def test_diff_prints_a_unified_diff(tmp_path):
    path = tmp_path / "a.clausal"
    path.write_text("p(X) <- (X is 5)\n")
    result = _run("--diff", str(path))
    assert result.returncode == 1
    assert "-p(X) <- (X is 5)" in result.stdout
    assert "+p(5)," in result.stdout
    assert path.read_text() == "p(X) <- (X is 5)\n"


def test_named_rules_select_a_subset(tmp_path):
    path = tmp_path / "a.clausal"
    path.write_text(FOLDABLE)
    assert _run("--rules", "head_fold", str(path)).returncode == 0
    assert path.read_text() == FOLDED


def test_unknown_rule_name_errors(tmp_path):
    path = tmp_path / "a.clausal"
    path.write_text(FOLDABLE)
    result = _run("--rules", "no_such_rule", str(path))
    assert result.returncode == 2
    assert "no_such_rule" in result.stderr
    assert path.read_text() == FOLDABLE


def test_a_broken_file_is_reported_and_left_alone(tmp_path):
    path = tmp_path / "broken.clausal"
    path.write_text("p(X <- (m(X))\n")
    result = _run(str(path))
    assert result.returncode == 2
    assert "broken.clausal" in result.stderr
    assert path.read_text() == "p(X <- (m(X))\n"


def test_recurses_into_directories(tmp_path):
    (tmp_path / "sub").mkdir()
    path = tmp_path / "sub" / "a.clausal"
    path.write_text(FOLDABLE)
    (tmp_path / "sub" / "notes.py").write_text("x  =  1\n")
    assert _run(str(tmp_path)).returncode == 0
    assert path.read_text() == FOLDED
    assert (tmp_path / "sub" / "notes.py").read_text() == "x  =  1\n"


def test_test_assets_are_not_shipped_rules(tmp_path):
    """The default rule set is what the tool ships, not what sits in the dir.

    A deliberately-broken control rule lives beside the real ones so the
    battery can prove the legality checks matter.  It must never be picked up
    by a bare ``clausal-rewrite``.
    """
    from clausal.rewrite.cli import default_rule_names

    assert "head_fold" in default_rule_names()
    assert not [name for name in default_rule_names() if name.startswith("_")]


# ── ``.seam`` is an alias extension for ``.clausal`` ─────────────────────────


def test_seam_file_is_rewritten(tmp_path):
    path = tmp_path / "a.seam"
    path.write_text(FOLDABLE)
    assert _run("--check", str(path)).returncode == 1
    assert "a.seam" in _run("--check", str(path)).stdout
    result = _run(str(path))
    assert result.returncode == 0, result.stderr
    assert path.read_text() == FOLDED


def test_seam_files_are_found_under_a_directory(tmp_path):
    (tmp_path / "sub").mkdir()
    path = tmp_path / "sub" / "b.seam"
    path.write_text(FOLDABLE)
    (tmp_path / "sub" / "notes.txt").write_text(FOLDABLE)
    result = _run(str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert path.read_text() == FOLDED
    assert (tmp_path / "sub" / "notes.txt").read_text() == FOLDABLE
