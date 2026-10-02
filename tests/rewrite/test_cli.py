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
from tests._suffix import SEAM


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "clausal.rewrite.cli", *args],
        capture_output=True,
        text=True,
    )


FOLDABLE = "r(K, S) <- (m(K, M), S is unknown(M))\n"
FOLDED = "r(K, unknown(M)) <- (\n    m(K, M)\n)\n"


def test_rewrites_in_place(tmp_path):
    path = tmp_path / f"a{SEAM}"
    path.write_text(FOLDABLE)
    result = _run(str(path))
    assert result.returncode == 0, result.stderr
    assert path.read_text() == FOLDED


def test_check_reports_would_change_without_writing(tmp_path):
    path = tmp_path / f"a{SEAM}"
    path.write_text(FOLDABLE)
    result = _run("--check", str(path))
    assert result.returncode == 1
    assert path.read_text() == FOLDABLE
    assert f"a{SEAM}" in result.stdout


def test_check_passes_on_a_stable_file(tmp_path):
    path = tmp_path / f"a{SEAM}"
    path.write_text("p(X) <- (\n    m(X)\n)\n")
    result = _run("--check", str(path))
    assert result.returncode == 0, result.stdout + result.stderr


def test_diff_prints_a_unified_diff(tmp_path):
    path = tmp_path / f"a{SEAM}"
    path.write_text("p(X) <- (X is 5)\n")
    result = _run("--diff", str(path))
    assert result.returncode == 1
    assert "-p(X) <- (X is 5)" in result.stdout
    assert "+p(5)," in result.stdout
    assert path.read_text() == "p(X) <- (X is 5)\n"


def test_named_rules_select_a_subset(tmp_path):
    path = tmp_path / f"a{SEAM}"
    path.write_text(FOLDABLE)
    assert _run("--rules", "head_fold", str(path)).returncode == 0
    assert path.read_text() == FOLDED


def test_unknown_rule_name_errors(tmp_path):
    path = tmp_path / f"a{SEAM}"
    path.write_text(FOLDABLE)
    result = _run("--rules", "no_such_rule", str(path))
    assert result.returncode == 2
    assert "no_such_rule" in result.stderr
    assert path.read_text() == FOLDABLE


def test_a_broken_file_is_reported_and_left_alone(tmp_path):
    path = tmp_path / f"broken{SEAM}"
    path.write_text("p(X <- (m(X))\n")
    result = _run(str(path))
    assert result.returncode == 2
    assert f"broken{SEAM}" in result.stderr
    assert path.read_text() == "p(X <- (m(X))\n"


def test_recurses_into_directories(tmp_path):
    (tmp_path / "sub").mkdir()
    path = tmp_path / "sub" / f"a{SEAM}"
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


def test_a_real_seam_rule_loads_and_fires(tmp_path, monkeypatch):
    """The half that resolution alone does not prove.

    The three tests above pin DISCOVERY: a `.seam` name is listed and turned
    into a path.  That a `.seam` file then LOADS is a separate claim, owned by
    `_load_module`, and a stub containing a comment would satisfy the first
    while telling us nothing about the second.  So copy a real shipped rule
    under the other spelling and drive it through `rewrite_source`, asserting
    it fires on source it is known to rewrite.
    """
    from clausal.rewrite import cli
    from clausal.rewrite.driver import rewrite_source

    rules = tmp_path / "rules"
    rules.mkdir()
    body = cli.rule_path("head_fold")
    assert body is not None, "the shipped head_fold rule vanished"
    (rules / "head_fold.seam").write_text(body.read_text())
    monkeypatch.setattr(cli, "RULES_DIR", rules)

    resolved = cli.rule_paths(["head_fold"])
    assert resolved == [rules / "head_fold.seam"]

    result = rewrite_source("r(K, S) <- (m(K, M), S is unknown(M))\n", resolved)
    assert result.text == "r(K, unknown(M)) <- (\n    m(K, M)\n)\n"
    assert len(result.fired) == 1


@pytest.mark.parametrize("name", [
    "../../etc/passwd", "sub/head_fold", "..", ".", "",
])
def test_a_rule_name_is_a_stem_not_a_path(name, monkeypatch, tmp_path):
    """`load_rules` EXECUTES what `rule_path` returns, so a name carrying
    separators must not reach outside the rules directory.  Pre-existing
    exposure; `rule_path` is now the one place a name becomes a path, so it
    is the one place to refuse."""
    from clausal.rewrite import cli

    rules = tmp_path / "rules"
    (rules / "sub").mkdir(parents=True)
    (rules / "sub" / f"head_fold{SEAM}").write_text("# reachable by traversal\n")
    monkeypatch.setattr(cli, "RULES_DIR", rules)

    assert cli.rule_path(name) is None
    with pytest.raises(cli.UnknownRule):
        cli.rule_paths([name])


def test_no_rewrite_site_spells_the_suffix_itself():
    """The exit check for the whole class, not just the sites fixed once.

    `clausal/_suffixes.py` says every place that recognises a predicate module
    by its extension consults its tuples rather than spelling the suffix
    itself.  The behavioural tests above cannot enforce that: the shipped
    rules carry the first suffix today, so a site that hardcodes it behaves
    identically until the rename and only then fails — precisely too late to
    learn about it.  So assert the property on the SOURCE.

    Read through `ast` rather than line by line: a first version scanned raw
    lines and flagged the neighbouring docstring that QUOTES the removed
    shape in order to explain it.  Prose about a defect is not the defect, so
    docstrings are excluded and every other string constant is inspected,
    f-strings included.

    Scope is stated rather than implied: the CLI and this suite's fixtures,
    being the two files that turn a rule NAME into a path.
    """
    import ast
    import pathlib

    from clausal._suffixes import CLAUSAL_SUFFIXES
    from clausal.rewrite import cli

    root = pathlib.Path(__file__).resolve().parents[2]
    watched = [
        root / "clausal" / "rewrite" / "cli.py",
        pathlib.Path(__file__).resolve().parent / "conftest.py",
    ]

    def _docstring_nodes(tree):
        out = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
        return out

    def _offenders(path):
        tree = ast.parse(path.read_text())
        docstrings = _docstring_nodes(tree)
        hits = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings:
                    continue
                if not any(sfx in node.value for sfx in CLAUSAL_SUFFIXES):
                    continue
                # Prose mentions a suffix inside a sentence; a path or a glob
                # is one whitespace-free token (`".clausal"`, `"*.clausal"`,
                # and the literal part of `f"{name}.clausal"`).  Help text
                # and messages that NAME the suffixes are not sites.
                if any(ch.isspace() for ch in node.value):
                    continue
                hits.append(f"{path.name}:{node.lineno}: {node.value!r}")
        return hits

    # Positive control: the check DOES catch both removed shapes, so an empty
    # result means "clean" rather than "the check stopped looking".
    control = pathlib.Path(__file__).parent / "_suffix_check_control.py"
    control.write_text(
        'D = None\n'
        'def f(name):\n'
        '    """A docstring naming .clausal must NOT be flagged."""\n'
        '    a = D / f"{name}.clausal"\n'
        '    b = D.glob("*.clausal")\n'
        '    return a, b\n')
    try:
        caught = _offenders(control)
        assert len(caught) == 2, f"control should catch 2 sites, caught {caught}"
    finally:
        control.unlink()

    offenders = [hit for path in watched for hit in _offenders(path)]
    assert not offenders, (
        "a rule path is built from a hardcoded suffix; use "
        "clausal.rewrite.cli.rule_path / CLAUSAL_SUFFIXES:\n  "
        + "\n  ".join(offenders))

    # And the property the check exists to protect, stated directly.
    assert cli.rule_path("head_fold") is not None
