import pytest
from clausal.tools.toklex.spec import parse_spec_text
from clausal.tools.toklex.annotate import annotate, UnboundedBackupError, dump_term

NUM = """
encoding(chars).
class(digit, range('0','9')).
class(layout, [' ']).
def(exp, 'e' then ('+' | '-')? then digit then digit*).
token(integer, digit then digit*).
token(float_num, digit then digit* then '.' then digit then digit* then exp?).
trivia(ws, layout then layout*).
"""


def test_extend_sets_drive_emission():
    lx = annotate(parse_spec_text(NUM))
    p = lx.partition
    # after '1' the state accepts integer; '.' extends (float path), ' ' does not
    q = lx.dfa.delta[lx.dfa.start][p.symbol_of("1")]
    assert lx.dfa.accepts[q] == ("integer",)
    assert p.symbol_of(".") in lx.extend[q]
    assert p.symbol_of(" ") not in lx.extend[q]


def test_backup_bound_is_two():
    lx = annotate(parse_spec_text(NUM))
    # worst case: '1.2e+' then non-digit -> emit float '1.2', return 'e+'
    assert lx.max_backup == 2


def test_unbounded_backup_rejected():
    bad = """
    encoding(chars).
    class(a_, [a]). class(b_, [b]).
    token(short, a_).
    token(long, a_ then b_ then b_ then (b_ then b_)* then a_).
    """
    with pytest.raises(UnboundedBackupError):
        annotate(parse_spec_text(bad))


def test_follow_and_kind_maps():
    spec = parse_spec_text(NUM + "token(end, '.' followed_by (layout | eof)).")
    lx = annotate(spec)
    syms, eof_ok = lx.follow["end"]
    assert eof_ok and lx.partition.symbol_of(" ") in syms
    assert lx.kind["ws"] == "trivia" and lx.kind["integer"] == "token"


def test_dump_is_prolog_readable():
    from clausal.tools.prolog_parser import parse_term
    lx = annotate(parse_spec_text(NUM))
    term = parse_term(dump_term(lx).rstrip(". \n"))  # parses as a term
    assert term is not None


def test_follow_unconstrained_representation():
    # 'integer' has no `followed_by` constraint -- per the Lexer docstring's
    # chosen representation, unconstrained rules are simply absent from the
    # follow map (Task 6's driver treats a missing key as unconstrained-pass).
    lx = annotate(parse_spec_text(NUM))
    assert "integer" not in lx.follow
    assert "float_num" not in lx.follow
