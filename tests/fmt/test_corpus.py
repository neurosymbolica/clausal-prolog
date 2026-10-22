"""Sweep real ``.clausal`` source through the formatter.

The unit tests pin the style rules on hand-written snippets, which is the wrong
shape of evidence for a formatter: what it has to survive is source nobody
wrote with it in mind.  So this sweeps every ``.clausal`` file in the repository
-- fixtures, examples, package test data, the standard library -- and requires
four things of each: the tree is unchanged, no comment was lost (the formatter
raises if one was), every comment still anchors the code it anchored, and every
arrow is still spelled as an arrow.  A second pass must change nothing.

Point ``CLAUSAL_FMT_CORPUS`` at a directory to sweep source living outside this
repository as well.
"""

import ast
import os
import re
import sys
from pathlib import Path

import pytest

from clausal.fmt import format_source
from clausal.fmt.comments import arrow_nodes
from clausal.fmt.verify import ast_equivalent
from tests._suffix import SEAM, seam_glob

REPO = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", "build", "dist", ".claude", "__pycache__", "node_modules"}


def _corpus_roots() -> list[Path]:
    roots = [REPO]
    external = os.environ.get("CLAUSAL_FMT_CORPUS")
    if external:
        roots.extend(Path(part) for part in external.split(os.pathsep) if part)
    return [root for root in roots if root.is_dir()]


def _clausal_files() -> list[Path]:
    found: list[Path] = []
    for root in _corpus_roots():
        for path in seam_glob(root, recursive=True):
            # Relative to the ROOT that produced it, never the absolute path:
            # a checkout may itself live under a directory named like one of
            # the skips — a git worktree under `.claude/`, say — and filtering
            # the absolute parts then discards EVERY file and empties the
            # corpus silently.  The only thing that notices is
            # ``test_the_corpus_is_not_empty``, and a guard that fails in both
            # arms of a before/after diff cancels out of the failure-name set
            # and reads as agreement.  Measured: 430 files present, 0 selected.
            if SKIP_DIRS.isdisjoint(path.relative_to(root).parts):
                found.append(path)
    return found


CORPUS = _clausal_files()


def _ids(paths: list[Path]) -> list[str]:
    return [str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path) for path in paths]


@pytest.mark.parametrize("path", CORPUS, ids=_ids(CORPUS))
def test_fmt_is_ast_equivalent_conserving_and_idempotent(path):
    source = path.read_text()
    try:
        ast.parse(source)
    except SyntaxError:
        pytest.skip("fixture is deliberately unparsable")
    formatted = format_source(source)  # conservation asserted inside
    assert ast_equivalent(source, formatted), "the formatter changed the code"
    assert format_source(formatted) == formatted, "the formatter is not idempotent"


@pytest.mark.parametrize("path", CORPUS, ids=_ids(CORPUS))
def test_fmt_keeps_the_compiled_module(path):
    """The formatted file compiles to the SAME program as the original.

    ``ast_equivalent`` compares the Python tree plus the quote character of
    each string literal; this asks the seam compiler itself, which is what
    the quote character (atom vs string, ISO 6.3.3) and the arrow spacing
    actually mean to.  Each file is run through ``transform_seam_source``
    before and after formatting -- parsed and transformed, never executed --
    and the two generated modules must match once their source positions
    are stripped.  This is what caught a quoted functor ``'if_'(...)`` being
    written as the string ``"if_"(...)`` (todo/done/fmt-requotes-a-quoted-
    atom-head-as-a-string-2026-10-20.md); roughly 25 ms per file.
    """
    import warnings

    from clausal.import_hook import transform_seam_source

    source = path.read_text()
    try:
        ast.parse(source)
    except SyntaxError:
        pytest.skip("fixture is deliberately unparsable")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            before = _compiled_shape(transform_seam_source(source, str(path))[0])
        except SyntaxError:
            pytest.skip("fixture is deliberately uncompilable")
        after = _compiled_shape(
            transform_seam_source(format_source(source), str(path))[0]
        )
    assert before == after, "the formatter changed the compiled program"


class _StripPositions(ast.NodeTransformer):
    """Drop the source positions the generated module carries as data:
    ``SourcePosition(...)`` calls, ``position=`` / ``_position=`` tuples,
    and the line number of an ``$unterminated_fact_error`` call."""

    def visit_Call(self, node):
        self.generic_visit(node)
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name == "SourcePosition":
            return ast.Name(id="POSITION", ctx=ast.Load())
        if name == "$unterminated_fact_error" and len(node.args) >= 2:
            node.args[1] = ast.Name(id="LINE", ctx=ast.Load())
        node.keywords = [
            k for k in node.keywords
            if not (k.arg in ("position", "_position") and isinstance(k.value, ast.Tuple))
        ]
        return node


def _compiled_shape(tree: ast.Module) -> str:
    return ast.dump(_StripPositions().visit(tree), include_attributes=False)


def _anchors(text: str) -> dict[str, str]:
    """Each standalone comment mapped to the first code line below it.

    Comments that appear more than once in a file -- separator rules, repeated
    notes -- are dropped: there is no way to tell which copy is which, so they
    can neither confirm nor deny a move.
    """
    lines = text.splitlines()
    anchors: dict[str, str] = {}
    repeated = set()
    for index, line in enumerate(lines):
        comment = line.strip()
        if not comment.startswith("#"):
            continue
        if comment in anchors:
            repeated.add(comment)
        below = ""
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if stripped and not stripped.startswith("#"):
                below = stripped
                break
        anchors[comment] = below
    return {c: below for c, below in anchors.items() if c not in repeated}


def _head(line: str) -> str:
    """The leading identifier of a code line, for a loose comparison.

    A directive's leading ``-`` is skipped with any opening parentheses, so
    ``-dynamic(sp/1)`` and the formatter's ``-dynamic(sp / 1)`` both head as
    ``-dynamic``.  Without that the match failed on the ``-`` and fell back to
    the first twelve raw characters, which compared operator spacing inside the
    directive rather than which code the comment sits above.
    """
    match = re.match(r"[(]*\s*(-?)\s*([A-Za-z_][\w.]*)", line)
    return match.group(1) + match.group(2) if match else line[:12]


def test_head_reads_a_directive_by_its_name_not_its_spacing():
    assert _head("-dynamic(sp/1)") == _head("-dynamic(sp / 1)") == "-dynamic"
    assert _head("-dynamic(sp/1)") != _head("-module(m, [sp/1])")
    assert _head("-dynamic(sp/1)") != _head("dynamic(sp)")
    assert _head("sp(X) <- (") == "sp"


# Seam fixtures spelled `.seam` joined the corpus when its glob moved to every
# seam suffix (tests/_suffix.seam_glob).  One of them shows a formatter defect
# the `.clausal`-only glob never reached: a comment inside a one-line
# `-private([...])` list drifts.  Known, not hidden: the xfail names it.
_KNOWN_ANCHOR_DRIFT = {
    "rulebase_s1_twin.seam":
        "fmt: a comment inside -private([...]) changes anchor "
        "(exposed when the corpus glob took in .seam fixtures)",
}


@pytest.mark.parametrize("path", CORPUS, ids=_ids(CORPUS))
def test_comments_keep_pointing_at_the_same_code(path):
    """Conservation is not enough: a comment must still anchor where it did.

    Every comment survives by construction, so this asks the question that
    survival does not answer -- whether it still sits above the same code.  It
    is what catches a comment written inside a construct the formatter renders
    on one line, which has nowhere to sit and would otherwise drift onto
    whatever came next.
    """
    source = path.read_text()
    try:
        ast.parse(source)
    except SyntaxError:
        pytest.skip("fixture is deliberately unparsable")
    if path.name in _KNOWN_ANCHOR_DRIFT:
        pytest.xfail(_KNOWN_ANCHOR_DRIFT[path.name])
    before = _anchors(source)
    after = _anchors(format_source(source))
    for comment, below in before.items():
        assert comment in after, f"{comment} is no longer on a line of its own"
        assert _head(below) == _head(after[comment]), f"{comment} changed anchor"


@pytest.mark.parametrize("path", CORPUS, ids=_ids(CORPUS))
def test_every_arrow_is_still_an_arrow(path):
    """AST equivalence cannot see this one: ``<-`` and ``< -`` are one tree.

    A clause arrow, and any lambda arrow inside a goal, is an arrow only
    because of how it is spelled.  So the sweep counts them the way the loader
    does -- by adjacency -- on the way in and on the way out.
    """
    source = path.read_text()
    try:
        ast.parse(source)
    except SyntaxError:
        pytest.skip("fixture is deliberately unparsable")
    formatted = format_source(source)
    assert len(_arrows(formatted)) == len(_arrows(source)), "an arrow changed meaning"


def _arrows(text: str) -> set:
    return arrow_nodes(ast.parse(text), text)


def test_the_corpus_is_not_empty():
    # A sweep that silently found nothing would pass forever.
    assert len(CORPUS) > 100


# ─── The skip filter is ROOT-RELATIVE, not absolute ─────────────────────────

def test_a_root_living_under_a_skip_name_still_yields_its_files(tmp_path, monkeypatch):
    """A checkout may itself live under a directory named like one of the
    skips — a git worktree under `.claude/`, for instance.

    Filtering the ABSOLUTE path's parts then discards every file and the
    corpus goes silently empty: measured at 430 files present and 0 selected.
    The only test that notices is ``test_the_corpus_is_not_empty``, and a
    guard that fails in BOTH arms of a before/after comparison cancels out of
    the failure-name set and reads as agreement — which is how 1914 corpus
    cases went unmeasured on both sides of a landing.
    """
    root = tmp_path / ".claude" / "worktrees" / "wt"
    root.mkdir(parents=True)
    (root / f"a{SEAM}").write_text("p(1),\n")
    monkeypatch.setenv("CLAUSAL_FMT_CORPUS", str(root))
    this_module = sys.modules[__name__]
    monkeypatch.setattr(this_module, "REPO", tmp_path / "nonexistent")

    found = this_module._clausal_files()
    assert [p.name for p in found] == [f"a{SEAM}"]


def test_a_skip_directory_INSIDE_the_root_is_still_skipped(tmp_path, monkeypatch):
    """The negative half: making the filter root-relative must not stop it
    filtering.  Without this, deleting the check entirely would pass the test
    above."""
    root = tmp_path / "tree"
    (root / "build").mkdir(parents=True)
    (root / f"keep{SEAM}").write_text("p(1),\n")
    (root / "build" / f"generated{SEAM}").write_text("p(2),\n")
    monkeypatch.setenv("CLAUSAL_FMT_CORPUS", str(root))
    this_module = sys.modules[__name__]
    monkeypatch.setattr(this_module, "REPO", tmp_path / "nonexistent")

    found = this_module._clausal_files()
    assert [p.name for p in found] == [f"keep{SEAM}"]
