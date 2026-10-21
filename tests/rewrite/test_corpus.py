"""Every ``.clausal`` file in the repository, run through the rewriter.

The rule tests are written on snippets chosen to exercise one condition each,
which is the right shape for pinning a rule and the wrong shape for trusting
one.  This sweeps every seam file in the repository and asks six things of
each: comments are conserved (the formatter raises if not), the rewrite is
LOCALIZED -- every statement no rule fired on is bit-for-bit the same tree it
was, quote characters included -- a second pass changes nothing, no arrow
decayed into a comparison, the output is seam the front end reads, and every
text literal keeps its class and spelling (the multiset of ``(quote, value)``
is the same before and after: no shipped rule discards or respells a literal,
and the driver's own read-back check refuses a rewrite that would).

A failure here is a finding, not a fixture to skip: it means a rule fired where
it should have refused, or the splice lost a comment on source nobody wrote
with this tool in mind.
"""

import ast
import collections
import io
import tokenize

import pytest

from clausal.fmt.comments import arrow_candidates, arrow_nodes
from clausal.fmt.verify import ast_equivalent
from clausal.reflection import ReifyError, reify_source
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


def literal_census(text: str) -> collections.Counter:
    """How many times each ``(quote character, value)`` literal occurs.

    Counted from the token stream, where the quote character still exists;
    the VALUE rather than the token text, so a respelled escape or a
    collapsed triple quote is not a difference but ``'a'`` -> ``a`` (gone),
    ``'a'`` -> ``"a"`` (requoted) and ``'Foo'`` -> ``Foo`` (gone) are.
    """
    census: collections.Counter = collections.Counter()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.STRING:
            continue
        quote = token.string.lstrip("bBrRuU")[0]
        census[(quote, ast.literal_eval(token.string))] += 1
    return census


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
            assert ast_equivalent(
                ast.get_source_segment(source, original),
                ast.get_source_segment(result.text, rewritten),
            ), "a statement no rule fired on came back requoted"

    # Where a rule fired, the output is seam the front end reads (reification
    # is the loader's own transform, short of running anything) wherever the
    # input was -- two fixtures are deliberate load-error witnesses.  An
    # untouched file is the formatter's output, which tests/fmt holds to the
    # same tree.  And the file's literals are all still there, each with the
    # quote it had.
    if fired:
        try:
            reify_source(source)
        except ReifyError:
            pass
        else:
            reify_source(result.text)
    assert literal_census(result.text) == literal_census(source), (
        "a text literal changed class or spelling"
    )

    again = rewrite_source(result.text, shipped_rules)
    assert again.text == result.text, "the rewriter is not idempotent"
    assert again.fired == [], "a rule fired on its own output"

    assert _decayed(result.text) <= _decayed(source), "an arrow became a comparison"


def test_the_corpus_is_not_empty():
    assert len(CORPUS) > 100
