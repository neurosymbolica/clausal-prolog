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
from pathlib import Path

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.fmt import format_source
from clausal.fmt.comments import arrow_nodes
from clausal.fmt.verify import ast_equivalent

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
        for path in sorted(root.rglob("*.clausal")):
            if SKIP_DIRS.isdisjoint(path.parts):
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
    """The leading identifier of a code line, for a loose comparison."""
    match = re.match(r"[(]*\s*([A-Za-z_][\w.]*)", line)
    return match.group(1) if match else line[:12]


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
