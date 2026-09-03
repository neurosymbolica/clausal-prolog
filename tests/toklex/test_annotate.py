from clausal.tools.toklex.spec import parse_spec_text
from clausal.tools.toklex.annotate import annotate, dump_term

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


def test_cycle_becomes_commit_region():
    # Same crafted spec as before (Task 8 fix round: annotate() no longer
    # rejects this -- it DERIVES a commit region instead of raising).
    # `long` = a_ b_ b_ (b_ b_)* a_, sharing its `a_ b_ b_` prefix with
    # `short` = a_. After the `short` accept (state 1, just "a"), 'b'
    # leads to state 2 then state 3 -- both non-accepting but still
    # boundedly reachable (the mandatory "bb" of `long`'s prefix, exactly
    # one path each, no cycle yet). From state 3, a further 'b' enters
    # the (b_ then b_)* loop body (states 5<->6): this pair genuinely
    # cycles (arbitrarily many more "bb" pairs before `long`'s trailing
    # a_ can close it), so 5 and 6 are the commit region.
    bad = """
    encoding(chars).
    class(a_, [a]). class(b_, [b]).
    token(short, a_).
    token(long, a_ then b_ then b_ then (b_ then b_)* then a_).
    """
    lx = annotate(parse_spec_text(bad))

    # annotate() succeeds (no UnboundedBackupError) and finds a nonempty
    # commit region.
    assert lx.commit

    # Hand-computed by tracing the DFA (see automaton dump in the Task 8
    # fix-round report): pending = {2, 3, 5, 6} (non-accepting states
    # reachable from the `short` accept without crossing another accept);
    # 5 and 6 form a 2-cycle (5 --b--> 6 --b--> 5) and nothing else is
    # reachable from that cycle within `pending`, so commit == {5, 6}
    # exactly. The remaining eligible states {2, 3} are a 2-long acyclic
    # chain (2 --b--> 3, then 3's only pending-eligible edge, on 'a',
    # leaves eligible into the `long` accept) hanging off the `short`
    # accept, giving max_backup == 2: worst case, the scanner commits to
    # "short" + up to 2 extra chars ("bb") before either finding `long`'s
    # accept or spilling into the unbounded commit region.
    assert lx.commit == frozenset({5, 6})
    assert lx.max_backup == 2


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
