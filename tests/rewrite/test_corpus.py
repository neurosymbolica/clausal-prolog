"""Every ``.clausal`` file in the repository, run through the rewriter.

The rule tests are written on snippets chosen to exercise one condition each,
which is the right shape for pinning a rule and the wrong shape for trusting
one.  This sweeps the real corpus and asks four things of each file: comments
are conserved (the formatter raises if not), the rewrite is LOCALIZED -- every
statement no rule fired on is bit-for-bit the same tree it was -- a second pass
changes nothing, and no arrow decayed into a comparison.

A failure here is a finding, not a fixture to skip: it means a rule fired where
it should have refused, or the splice lost a comment on source nobody wrote
with this tool in mind.
"""

import ast

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.fmt.comments import arrow_candidates, arrow_nodes
from clausal.rewrite.driver import rewrite_source
from tests.fmt.test_corpus import CORPUS, _ids


def _position(statement):
    return (
        statement.lineno,
        statement.col_offset,
        statement.end_lineno,
        statement.end_col_offset,
    )


def _decayed(text: str) -> int:
    """Arrow-shaped nodes this text does NOT spell as arrows.

    An arrow that lost its spacing shows up here as an increase: the node is
    still shaped like an arrow and no longer reads as one.  Counting the
    arrows themselves would not work, since a clause folded to a fact
    legitimately has one fewer.
    """
    tree = ast.parse(text)
    return len(arrow_candidates(tree)) - len(arrow_nodes(tree, text))


@pytest.mark.parametrize("path", CORPUS, ids=_ids(CORPUS))
def test_rewrite_is_conserving_localized_idempotent_and_arrow_safe(path, shipped_rules):
    source = path.read_text()
    try:
        before = ast.parse(source).body
    except SyntaxError:
        pytest.skip("fixture is deliberately unparsable")

    result = rewrite_source(source, shipped_rules)  # conservation asserted inside

    after = ast.parse(result.text).body
    assert len(before) == len(after), "the rewrite added or removed a statement"
    fired = {position for position, _rule in result.fired}
    for original, rewritten in zip(before, after):
        if _position(original) not in fired:
            assert ast.dump(original) == ast.dump(rewritten), (
                "a statement no rule fired on came back changed"
            )

    again = rewrite_source(result.text, shipped_rules)
    assert again.text == result.text, "the rewriter is not idempotent"
    assert again.fired == [], "a rule fired on its own output"

    assert _decayed(result.text) <= _decayed(source), "an arrow became a comparison"


def test_the_corpus_is_not_empty():
    assert len(CORPUS) > 100
