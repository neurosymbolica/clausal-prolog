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
    """The emitted program with comments removed.

    The discarded unit is deliberately ECHOED in a /* unit */ note, so
    "the unit is gone" has to be asserted against the CODE, not the text --
    otherwise the annotation would make these tests fail while the program is
    perfectly correct.
    """
    out = re.sub(r"/\*.*?\*/", "", out, flags=re.S)
    return "\n".join(l for l in out.splitlines() if not l.lstrip().startswith("%"))


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
    # the magnitude survives as a variable (renamed by the usual singleton
    # mapping -- DEPOSIT occurs once, so it emits as _Deposit)
    assert "eposit" in out
    assert "(" not in out.split("X == ")[1].split("\n")[0]  # no VARIABLE functor


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

def test_discarded_unit_is_noted_above_the_clause():
    """The reader can still see what Clausal treated each value as."""
    out = _tr("p(X) <- ( X == 5000(euro) + 3000(euro) )")
    assert "units discarded on export" in out
    assert "%   unit discarded: 5000(euro) -> 5000" in out
    assert "%   unit discarded: 3000(euro) -> 3000" in out
    # and the note is ABOVE the clause it describes
    assert out.index("units discarded") < out.index("p(X) :-")


def test_variable_magnitude_is_noted_too():
    out = _tr("p(X) <- ( X == DEPOSIT(baht) )")
    assert "%   unit discarded: DEPOSIT(baht) -> DEPOSIT" in out


def test_notes_are_LINE_comments_never_block_comments():
    """ISO portability: `%` is the comment form to rely on, and a `%` cannot
    sit inline because it would swallow the rest of the clause -- which is why
    the note goes above rather than beside the value."""
    out = _tr("p(X) <- ( X == 5000(euro) + 3000(euro) )")
    assert "/*" not in out and "*/" not in out
    for line in out.splitlines():
        if "unit discarded" in line:
            assert line.lstrip().startswith("%")


def test_note_is_per_clause_not_per_file():
    """Two clauses, two notes -- a reader should not have to guess which
    clause a file-level summary was about."""
    out = _tr("p(X) <- ( X == 5000(euro) )\nq(Y) <- ( Y == 7(baht) )",
              decl="p(X), q(Y)")
    assert out.count("units discarded on export") == 2


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
    assert "unit discarded: -3(s) -> -3" in out or "unit discarded: 3(s) -> 3" in out


def test_float_magnitude_lowers():
    out = _tr("p(X) <- ( X == 9.8(newton) )", strict=True)
    assert "9.8" in _code(out) and "newton" not in _code(out)
