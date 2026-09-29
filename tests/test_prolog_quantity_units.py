"""Quantity literals lower to their magnitude; the unit is discarded.

A quantity is a value with a unit, represented at the Python level -- not a
term. ISO Prolog cannot represent one: a number may not be a functor, and
evaluable functors are a closed set, so even a term-shaped money value could
not be used with is/2 (Scryer: `type_error(evaluable, euro/1)` even when +/3
is defined as a predicate). Teaching ISO about units would mean a quantity
class plus hand-rolled arithmetic at every site that might touch one, losing
CLP(Z) and every other facility defined over ordinary numbers.

So the export drops the unit and keeps the magnitude. THE TRANSLATION IS LOSSY
BY DESIGN; dimensional analysis stays in the Clausal runtime, where it works.
"""
import re

import pytest

from clausal.tools.clausal_to_prolog import (
    UntranslatableConstructError, clausal_source_to_prolog,
)

MOD = """-module(m, [{decl}])
-double_quotes(chars)
{imports}
{body}
"""


def _tr(body, decl="p(X)", imports="", **kw):
    return clausal_source_to_prolog(
        MOD.format(decl=decl, imports=imports, body=body), **kw)


def _code(out):
    """The emitted program with ALL comments removed — whole-line and trailing.

    The discarded unit is deliberately echoed in a trailing `% Clausal units:`
    note, so "the unit is gone from the program" has to be asserted against the
    CODE. Stripping only whole comment LINES is not enough now that the notes
    ride on code lines; that gap made twelve of these tests fail for the wrong
    reason when the format changed.
    """
    lines = []
    for line in out.splitlines():
        if line.lstrip().startswith("%"):
            continue
        lines.append(line.split("%", 1)[0].rstrip())
    return "\n".join(lines)


def test_literal_quantity_keeps_magnitude_drops_unit():
    out = _tr("p(X) <- ( X == 5000(euro) )")
    assert "5000" in out
    assert "euro" not in _code(out)


def test_quantity_inside_arithmetic_stays_arithmetic():
    """The whole point of dropping the unit: ordinary ISO arithmetic survives."""
    out = _tr("p(X) <- ( X == 5000(euro) + 3000(euro) )")
    assert "5000 + 3000" in out
    assert "euro" not in _code(out)


def test_variable_magnitude_quantity():
    """`DEPOSIT(baht)` -- a variable amount -- lowers to the bare variable.

    Without this the head would be a Python Name call and would emit a term
    with a VARIABLE functor, which is not valid Prolog.
    """
    out = _tr("p(X) <- ( X == DEPOSIT(baht) )", decl="p(X)")
    assert "baht" not in _code(out)
    # The magnitude survives as a variable. DEPOSIT occurs once, so the
    # singleton pass underscore-prefixes it; the NAME is unchanged (it used
    # to be titlecased to _Deposit as well, which is why this asserted the
    # case-free substring "eposit").
    assert "_DEPOSIT" in out
    # no VARIABLE functor in the CODE (the note legitimately says "(baht)")
    # The goal line carries no VARIABLE functor -- `_DEPOSIT(baht)` would be
    # one. Read from the argument list of the emitted `#=`, not from an
    # `X == ` prefix: the 2026-09-18 ruling made an unquoted `==` emit
    # `#=(X, _DEPOSIT)`, so the old split found nothing and raised IndexError
    # rather than failing on the property under test.
    goal = [l for l in _code(out).splitlines() if "#=(X," in l][0]
    assert "(" not in goal.split("#=(X,")[1], goal


def test_zero_quantity_is_not_mistaken_for_something_else():
    out = _tr("p(X) <- ( X == 0(euro) )")
    assert "euro" not in _code(out) and "0" in out


def test_float_magnitude():
    out = _tr("p(X) <- ( X == 2.5(euro) )")
    assert "euro" not in _code(out) and "2.5" in out


def test_strict_mode_does_not_raise_on_a_quantity():
    """A quantity LOWERS; it is not an untranslatable construct.

    Regression pin: quantities used to fall through to the unsupported-call-
    target branch, which made strict mode refuse the whole file.
    """
    out = _tr("p(X) <- ( X == 5000(euro) )", strict=True)
    assert "euro" not in _code(out)


def test_unit_only_import_is_dropped():
    """The import naming a unit goes too -- it would not resolve on export."""
    out = _tr("p(X) <- ( X == 5000(euro) )",
              imports="-import_from(european_union, [euro])")
    assert "use_module('european_union'" not in out
    # `euro` survives ONLY inside the comment that explains the drop -- the
    # emitted program itself must not mention it
    assert "euro" not in _code(out)
    assert "skipped" in out and "units are discarded" in out


def test_ordinary_predicate_call_is_untouched():
    """NEGATIVE CONTROL: a real one-argument call must NOT be treated as a
    quantity just because it has a single atom argument."""
    out = _tr("p(X) <- ( X == successor(zero) )")
    assert "successor(zero)" in out


def test_uppercase_argument_is_not_a_unit():
    """A unit is a lowercase atom. `5000(THING)` is not a quantity."""
    with pytest.raises(UntranslatableConstructError):
        _tr("p(X) <- ( X == 5000(THING) )", strict=True)


def test_two_argument_call_on_a_number_is_still_unsupported():
    """Only the arity-1 quantity shape is lowered; anything else still refuses,
    so this change cannot silently swallow a genuinely bad construct."""
    with pytest.raises(UntranslatableConstructError):
        _tr("p(X) <- ( X == 5000(euro, baht) )", strict=True)


# --- the unit is VISIBLE in the output, though not semantic -------------------

def test_discarded_units_ride_a_TRAILING_comment_on_their_own_line():
    """One comment per LINE, listing that line's values and units.

    Trailing, not above: a `%` runs to end of line, which is harmless once the
    line's code is complete, and it costs NO EXTRA LINES. Downstream, this
    took the note overhead from 78 added lines (9.7% of output) to 16 (2.3%),
    and the 16 are the one-per-file header.
    """
    out = _tr("p(X) <- ( X == 5000(euro) + 3000(euro) )")
    # `#=(X, ...)` since the 2026-09-18 ruling. The property under test is the
    # TRAILING note, which is unchanged -- only the goal's spelling moved.
    assert "#=(X, 5000 + 3000).  % Clausal units: 5000 (euro), 3000 (euro)" in out, out


def test_variable_magnitude_is_noted_too():
    out = _tr("p(X) <- ( X == DEPOSIT(baht) )")
    assert "% Clausal units: _DEPOSIT (baht)" in out


def test_negative_magnitude_keeps_its_sign_in_the_note():
    out = _tr("p(X) <- ( X == -3(second) )")
    assert "% Clausal units: -3 (second)" in out


def test_header_says_it_once_per_file():
    out = _tr("p(X) <- ( X == 5000(euro) )\nq(Y) <- ( Y == 7(baht) )",
              decl="p(X), q(Y)")
    assert out.count(
        "% Clausal to Prolog translation has removed units from some numbers."
    ) == 1
    assert out.startswith("% Clausal to Prolog translation has removed units")
    # ...but each line still carries its own note
    assert out.count("% Clausal units:") == 2


def test_no_header_when_nothing_was_discarded():
    """NEGATIVE CONTROL: a file that loses no unit must not carry the caveat."""
    out = _tr("p(X) <- ( X == 42 )")
    assert "Clausal to Prolog translation has removed units" not in out
    assert "% Clausal units:" not in out


def test_notes_are_LINE_comments_never_block_comments():
    """ISO portability: `%` is the comment form to rely on."""
    out = _tr("p(X) <- ( X == 5000(euro) + 3000(euro) )")
    assert "/*" not in out and "*/" not in out


def test_internal_marker_never_reaches_the_output():
    """The unit rides an internal sentinel between emit_term and the line
    rewrite. If it ever leaked it would be a U+0001 in a .pl file, which no
    reader would diagnose — so pin it, on every shape at once."""
    out = _tr("p(X) <- ( X == 5000(euro) + DEPOSIT(baht) - 2.5(m) )")
    assert "\x01" not in out


def test_a_line_with_no_units_gets_no_comment():
    out = _tr("p(X) <- ( X == 5000(euro) )\nq(Y) <- ( Y == 42 )",
              decl="p(X), q(Y)")
    # `#=(Y,` since the 2026-09-18 ruling; the older spellings are kept so
    # this selector says what the goal line has ever looked like.
    q_line = [l for l in out.splitlines()
              if "#=(Y," in l or "Y ==" in l or "Y =:=" in l][0]
    assert "%" not in q_line

# --- the SAFETY property, not just the detail --------------------------------

def test_mixed_units_in_one_expression_are_refused():
    """THE point of the guard. `5000(euro) + 3000(baht)` is a UnitsMismatch in
    Clausal; discarding units would export it as `5000 + 3000` and yield 8000 —
    a dimensional ERROR silently becoming a WRONG ANSWER in a program that runs
    clean under Scryer."""
    with pytest.raises(UntranslatableConstructError) as e:
        _tr("p(X) <- ( X == 5000(euro) + 3000(baht) )", strict=True)
    assert "mixed units" in str(e.value)


def test_same_unit_arithmetic_is_accepted():
    """NEGATIVE CONTROL for the guard: it must not fire on valid input."""
    out = _tr("p(X) <- ( X == 5000(euro) + 3000(euro) )", strict=True)
    assert "5000 + 3000" in out


def test_subtraction_is_guarded_too():
    with pytest.raises(UntranslatableConstructError):
        _tr("p(X) <- ( X == 5000(euro) - 3000(baht) )", strict=True)


# --- documented surface forms that fail SAFE ---------------------------------

@pytest.mark.parametrize("expr", ["5(m/s)", "10(m**2)"])
def test_compound_unit_expression_refused_with_a_real_diagnosis(expr):
    """docs/units.md's other syntactic style. Refused, never mis-lowered — and
    the message must NAME the shape, or a reader hunts for a bug in a number."""
    with pytest.raises(UntranslatableConstructError) as e:
        _tr(f"p(X) <- ( X == {expr} )", strict=True)
    assert "compound unit expression" in str(e.value)


def test_negative_magnitude_lowers():
    """`-3(s)` is USub wrapping the Call, so the quantity still lowers."""
    out = _tr("p(X) <- ( X == -3(s) )", strict=True)
    assert "-3" in _code(out)
    assert "% Clausal units: -3 (s)" in out


def test_float_magnitude_lowers():
    out = _tr("p(X) <- ( X == 9.8(newton) )", strict=True)
    assert "9.8" in _code(out) and "newton" not in _code(out)


# --- the guard's KNOWN LIMIT, pinned so nobody mistakes it for a real check ---

@pytest.mark.parametrize("expr", [
    "5000(euro) + 3000(baht) * 2",
    "5000(euro) + 3000(baht) / 2",
    "5000(euro) * 1 + 3000(baht) * 2",
])
def test_mixed_units_NESTED_under_another_operator_are_NOT_caught(expr):
    """DOCUMENTS A LIMIT, NOT A FEATURE.

    _check_unit_mixing reads the DIRECT operands of a +/- node, so a unit
    nested under `*` or `/` is invisible to it and this mixed-unit expression
    translates. Catching it would need the unit of each operand SUBTREE — real
    dimension inference — which is out of scope precisely because `*` and `/`
    legitimately combine different units (m/s), so a blanket "units must agree"
    rule would reject valid input.

    The guard is the cheap syntactic half of a PRECONDITION: the export is
    sound only for dimensionally valid sources. Clausal's runtime is the
    complete check. If this test ever starts failing because someone taught the
    guard to descend, that is an improvement — delete the test and say so.
    """
    out = _tr(f"p(X) <- ( X == {expr} )", strict=True)
    assert "euro" not in _code(out) and "baht" not in _code(out)


def test_the_guard_still_catches_the_direct_case():
    """Companion to the limit above: the case it DOES catch, so the pair reads
    as a boundary rather than as a broken guard."""
    with pytest.raises(UntranslatableConstructError):
        _tr("p(X) <- ( X == 5000(euro) + 3000(baht) )", strict=True)
