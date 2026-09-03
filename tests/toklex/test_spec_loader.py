import pytest
from clausal.tools.toklex.spec import (
    parse_spec_text, SpecError, Lit, Seq, Alt, Star, Plus, Opt, ButNot,
)

MINI = """
encoding(chars).
class(digit, range('0', '9')).
class(small, range(a, z)).
class(nl, ['\\n']).
def(udigits, digit then (digit | '_')*).
token(integer, udigits).
token(name_atom, small then (small | digit)*).
token(end, '.' followed_by (nl | eof)).
token(weird, small+ but_not ('/' then '*' then any*)).
trivia(line_comment, '%' then (any - nl)*).
trivia(block_comment, '/' then '*' then body('*' then '/')) nest self.
token(quoted, q_ then (any - q_)* then q_) value quoted_atom_val.
class(q_, ['''']).
"""


def test_loads_and_shapes():
    spec = parse_spec_text(MINI)
    assert spec.encoding == "chars"
    assert set(spec.classes) >= {"digit", "small", "nl", "q_"}
    names = [t.name for t in spec.tokens]
    assert names == ["integer", "name_atom", "end", "weird", "quoted"]
    integer = spec.tokens[0]
    # def-inlining: udigits became Seq(Lit(digit), Star(Alt(Lit(digit), Lit('_'))))
    assert isinstance(integer.expr, Seq) and isinstance(integer.expr.parts[1], Star)
    end = spec.tokens[2]
    assert end.follow is not None and end.follow_eof is True
    assert end.follow.contains("\n") and not end.follow.contains("x")
    weird = spec.tokens[3]
    assert isinstance(weird.expr, ButNot) and isinstance(weird.expr.a, Plus)
    assert spec.tokens[4].builder == "quoted_atom_val"
    assert spec.tokens[1].builder is None


def test_trivia_and_nest():
    spec = parse_spec_text(MINI)
    line, block = spec.trivia
    assert line.nest_close is None
    assert block.nest_close is not None            # ('*','/') close expr
    assert isinstance(block.expr, Seq)              # open expr: '/' then '*'
    assert len(block.expr.parts) == 2


def test_priorities_are_declaration_order():
    spec = parse_spec_text(MINI)
    assert [t.prio for t in spec.tokens] == [0, 1, 2, 3, 4]


def test_unknown_class_reference_raises():
    with pytest.raises(SpecError):
        parse_spec_text("token(x, nosuchclass).")


def test_def_cycle_raises():
    with pytest.raises(SpecError):
        parse_spec_text("def(a, b then 'x'). def(b, a). token(t, a).")


def test_multichar_literal_raises():
    with pytest.raises(SpecError):
        parse_spec_text("token(x, 'ab').")


# ── Extra SpecError coverage (controller-specified, beyond the brief) ──


def test_duplicate_class_raises():
    with pytest.raises(SpecError):
        parse_spec_text(
            "class(digit, range('0', '9')). class(digit, range('0', '1'))."
        )


def test_duplicate_def_raises():
    with pytest.raises(SpecError):
        parse_spec_text("def(a, 'x'). def(a, 'y').")


def test_duplicate_token_raises():
    with pytest.raises(SpecError):
        parse_spec_text("token(t, 'x'). token(t, 'y').")


def test_duplicate_trivia_raises():
    with pytest.raises(SpecError):
        parse_spec_text("trivia(t, 'x'). trivia(t, 'y').")


def test_stray_body_in_non_nest_trivia_raises():
    with pytest.raises(SpecError):
        parse_spec_text("trivia(c, '%' then body('*')).")


def test_body_outside_trivia_raises():
    with pytest.raises(SpecError):
        parse_spec_text("token(t, 'a' then body('*')).")


def test_nest_trivia_missing_body_raises():
    with pytest.raises(SpecError):
        parse_spec_text("trivia(c, '/' then '*') nest self.")


def test_bad_encoding_raises():
    with pytest.raises(SpecError):
        parse_spec_text("encoding(latin1).")


def test_default_encoding_is_chars():
    spec = parse_spec_text("token(t, 'x').")
    assert spec.encoding == "chars"


def test_unknown_declaration_functor_raises():
    with pytest.raises(SpecError):
        parse_spec_text("bogus(t, 'x').")


def test_fragment_declaration_accepted():
    spec = parse_spec_text("fragment(f, 'x', gives v). token(t, 'x').")
    assert len(spec.fragments) == 1
    assert spec.fragments[0].name == "f"
