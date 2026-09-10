"""``clausal-rewrite`` on the command line -- the same contract as ``clausal-fmt``.

Anything that rewrites source in place has to be runnable in check mode from a
hook or a pipeline without writing anything, and has to say what it would do.
The exit codes are therefore the formatter's: 0 clean or written, 1 would
change under ``--check``/``--diff``, 2 something went wrong and nothing was
written.
"""

import subprocess
import sys

import pytest


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


# ─── `.seam` rule files are found, because the suffixes are aliases ──────────
#
# `clausal/_suffixes.py` says every place that recognises a predicate module by
# its extension consults its tuples rather than spelling ".clausal" itself.
# Two sites here did not: `default_rule_names` globbed "*.clausal" and
# `rule_paths` built `f"{name}.clausal"`.  Renaming the shipped rules to
# `.seam` — which the extension ruling requires — would therefore have emptied
# the rule set SILENTLY: `--rules head_fold` answering "unknown rule class:
# head_fold (available: )" and a bare run applying nothing while still
# reporting success, because a rewrite run that fires no rule is a legal
# outcome.

def test_a_seam_rule_file_is_listed_and_resolvable(tmp_path, monkeypatch):
    """Plant one of each spelling and require both to be found."""
    from clausal.rewrite import cli

    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "in_clausal.clausal").write_text("# a rule\n")
    (rules / "in_seam.seam").write_text("# a rule\n")
    (rules / "_hidden.seam").write_text("# excluded, leading underscore\n")
    monkeypatch.setattr(cli, "RULES_DIR", rules)

    assert cli.default_rule_names() == ["in_clausal", "in_seam"]
    assert cli.rule_path("in_seam") == rules / "in_seam.seam"
    assert cli.rule_path("in_clausal") == rules / "in_clausal.clausal"
    assert cli.rule_paths(["in_seam", "in_clausal"]) == [
        rules / "in_seam.seam", rules / "in_clausal.clausal"]


def test_an_unknown_rule_is_still_refused_by_name(tmp_path, monkeypatch):
    """The negative half: widening the suffixes must not make everything
    resolve.  Without this, a `rule_path` that returned a path it had not
    checked would pass the test above."""
    from clausal.rewrite import cli

    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "real.seam").write_text("# a rule\n")
    monkeypatch.setattr(cli, "RULES_DIR", rules)

    assert cli.rule_path("no_such_rule") is None
    with pytest.raises(cli.UnknownRule) as ei:
        cli.rule_paths(["no_such_rule"])
    assert "no_such_rule" in str(ei.value)
    # ...and the message offers what IS available, including the .seam one.
    assert "real" in str(ei.value)


def test_the_twin_resolves_in_finder_priority_order(tmp_path, monkeypatch):
    """A directory holding both spellings of one stem resolves the way an
    import of that stem would — `.clausal` first — rather than by whatever
    order the filesystem hands back.  A stale twin winning silently is the
    documented hazard of the rename, so the tie-break is pinned, not left to
    `glob`."""
    from clausal._suffixes import CLAUSAL_SUFFIXES
    from clausal.rewrite import cli

    assert CLAUSAL_SUFFIXES[0] == ".clausal", "priority order changed"
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "twin.clausal").write_text("# the winner\n")
    (rules / "twin.seam").write_text("# the stale twin\n")
    monkeypatch.setattr(cli, "RULES_DIR", rules)

    assert cli.default_rule_names() == ["twin"]          # listed once
    assert cli.rule_path("twin") == rules / "twin.clausal"
