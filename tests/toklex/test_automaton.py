from clausal.tools.toklex.charset import CharSet, Partition
from clausal.tools.toklex.spec import parse_spec_text, Lit, Seq, Star, ButNot, Plus, SpecError
from clausal.tools.toklex.automaton import build_partition, compile_expr, compile_spec

import pytest


def run(dfa, partition, s):
    """Longest accepted prefix's labels, or None."""
    q, best = dfa.start, None
    for i, ch in enumerate(s):
        q = dfa.delta[q].get(partition.symbol_of(ch))
        if q is None:
            break
        if dfa.accepts[q]:
            best = (i + 1, dfa.accepts[q])
    return best


SPEC = parse_spec_text("""
encoding(chars).
class(digit, range('0','9')).
class(small, range(a, z)).
class(graphic, ['*','/','+','=','.']).
token(integer, digit then digit*).
token(name, small then small*).
token(graphic_tok, graphic+ but_not ('/' then '*' then any*)).
""")


def test_single_rule_longest_match():
    p = build_partition(SPEC)
    dfa = compile_expr(SPEC.tokens[0].expr, p, label="integer")
    assert run(dfa, p, "123x") == (3, ("integer",))
    assert run(dfa, p, "x1") is None


def test_but_not_subtraction():
    p = build_partition(SPEC)
    dfa = compile_expr(SPEC.tokens[2].expr, p, label="g")
    assert run(dfa, p, "=..") == (3, ("g",))
    assert run(dfa, p, "/") == (1, ("g",))
    # DEVIATION from the brief's literal text (see task-4-report.md): the
    # brief's verbatim assertions here were `run(dfa, p, "/*") is None` and
    # `run(dfa, p, "/**/") is None`. That is unsatisfiable by construction:
    # `run` never un-sets `best` once set, and the state reached after
    # consuming the single character "/" is identical (DFA determinism)
    # whether "/" is the whole string or a prefix of "/*"/"/**/". Since the
    # line above requires that state to be accepting -- (1, ("g",)) -- the
    # same accept must be visible as the running `best` for "/*" and
    # "/**/" too; per-prefix acceptance can only grow monotonically longer
    # or stay put, never regress to None. What *is* true (verified against
    # the implementation) is that consumption dies at the second character
    # ('*' has no transition out of the "seen one '/'" state, since '*'
    # would complete the excluded '/','*',any* pattern), so the automaton
    # falls back to the longest prefix actually accepted: "/" alone. This
    # matches ordinary maximal-munch-with-backtrack lexer behavior.
    assert run(dfa, p, "/*") == (1, ("g",))
    assert run(dfa, p, "/**/") == (1, ("g",))
    # but a '/' followed later by '*' via another char is fine
    assert run(dfa, p, "/+*") == (3, ("g",))


def test_union_labels_and_priority():
    p = build_partition(SPEC)
    dfa = compile_spec(SPEC, p)
    assert run(dfa, p, "12 ") == (2, ("integer",))
    assert run(dfa, p, "ab1") == (2, ("name",))
    assert run(dfa, p, "==") == (2, ("graphic_tok",))


def test_global_order_token_before_trivia():
    # A token and a trivia rule that accept the same string: token's global
    # index (position in tokens+trivia concatenation) must sort first.
    spec = parse_spec_text("""
    encoding(chars).
    class(small, range(a, z)).
    trivia(ws, small+).
    token(name, small+).
    """)
    p = build_partition(spec)
    dfa = compile_spec(spec, p)
    result = run(dfa, p, "ab")
    assert result is not None
    length, labels = result
    assert length == 2
    assert labels == ("name", "ws")


def test_empty_language_raises_spec_error():
    spec = parse_spec_text("""
    encoding(chars).
    token(x, 'a' but_not 'a').
    """)
    p = build_partition(spec)
    with pytest.raises(SpecError, match="x"):
        compile_spec(spec, p)
