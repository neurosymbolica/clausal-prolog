"""Lowering the ISO canonical form `'op'(A, B)` to Prolog `A op B`.

Spec: docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md §3.2

The engine registers these names (landed d4f4c486) but the translator refused
every one of them with "unsupported call target", so a site migrated to a
canonical form became UNEXPORTABLE — turning a G3 red (exports, then fails in
Scryer) into a G1 red (does not export at all). Migration would have made the
export strictly worse while looking like progress in the source.

Note `'@<'` has NO infix alternative: `X @< Y` is not valid Python, so the
quoted form is the only spelling that can exist in Clausal source.
"""
import pytest

from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    UntranslatableConstructError,
)

INFIX_ROWS = [
    ("'@<'(X, Y)",    "X @< Y"),
    ("'@>'(X, Y)",    "X @> Y"),
    ("'@=<'(X, Y)",   "X @=< Y"),
    ("'@>='(X, Y)",   "X @>= Y"),
    ("'=:='(X, Y)",   "X =:= Y"),
    ("'=\\\\='(X, Y)", "X =\\= Y"),
    ("'<'(X, Y)",     "X < Y"),
    ("'>'(X, Y)",     "X > Y"),
    ("'=<'(X, Y)",    "X =< Y"),
    ("'>='(X, Y)",    "X >= Y"),
    ("'=='(X, Y)",    "X == Y"),
    ("'\\\\=='(X, Y)", "X \\== Y"),
    ("'is'(X, Y)",    "X is Y"),
    ("'='(X, Y)",     "X = Y"),
    ("'\\\\='(X, Y)",  "X \\= Y"),
    ("'=..'(X, Y)",   "X =.. Y"),
]


@pytest.mark.parametrize("body,expected", INFIX_ROWS)
def test_canonical_form_lowers_to_infix(body, expected):
    out = clausal_source_to_prolog(f"p(X, Y) <- ({body})\n", strict=True)
    assert expected in out, out


def test_canonical_form_of_a_non_operator_stays_a_compound():
    """`compare/3` has no operator entry, so it emits as an ordinary
    compound rather than being forced into infix."""
    out = clausal_source_to_prolog("p(O, X, Y) <- ('compare'(O, X, Y))\n",
                                   strict=True)
    assert "compare(O, X, Y)" in out, out


def test_a_quoted_ordinary_atom_is_a_functor_too():
    """The canonical form is general — it is how ANY atom is written as a
    functor, not a special case for operators."""
    out = clausal_source_to_prolog("p(X) <- ('foo'(X))\n", strict=True)
    assert "foo(X)" in out, out


def test_strict_mode_no_longer_refuses_canonical_forms():
    """The regression this whole change exists to prevent: strict=True used
    to raise `unsupported call target` for every one of these."""
    src = "".join(f"p{i}(X, Y) <- ({b})\n" for i, (b, _) in enumerate(INFIX_ROWS))
    clausal_source_to_prolog(src, strict=True)   # must not raise


def test_clpfd_canonical_forms_are_still_refused():
    """`'#='` and friends are CLP(FD) constraints with no ISO meaning. They
    must NOT be silently lowered to something that looks like arithmetic —
    failing loudly is correct until a dialect that has clpz is targeted."""
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("p(X, Y) <- ('#='(X, Y))\n", strict=True)
