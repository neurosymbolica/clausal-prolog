"""A date is the term ('date', Y, M, D); a Python datetime is not a term.

Ruled 2026-09-14/15: dates normalise with everything else. The corpus already
writes `date(Y, M, D)` and has a ratchet (`check_date_representation.py`)
enforcing it against `[Y, M, D]` lists, so this closes the *second*
representation rather than introducing the first.

Scope: the COMPILE route only -- `term_to_ast_expr` lowers a goal to Python AST,
and `_DATETIME_CTOR_FIELDS` let a Python date through it by emitting a
reconstruction call. `clausal.modules.py.datetime` is the declared Python-interop
surface (`py.` namespace, "real Python datetime objects" by design) and keeps
working through the RUNTIME route, where a value is bound to a Var and never
needs an AST form.
"""
import datetime
from decimal import Decimal

import pytest

from clausal.logic.compiler.terms_to_ast import term_to_ast_expr


def _lowers(value):
    try:
        term_to_ast_expr(value, {})
        return True
    except NotImplementedError:
        return False


def test_a_date_written_as_a_term_lowers():
    """The ruled representation is ordinary data: ints in a cell."""
    assert _lowers(("date", 2026, 9, 14)) is True


def test_a_python_date_does_NOT_lower():
    """The second representation, closed. It used to emit a reconstruction
    call -- `__import__('datetime').date(2026, 9, 14)` -- rebuilding the object
    at match time."""
    assert _lowers(datetime.date(2026, 9, 14)) is False


@pytest.mark.parametrize("value", [
    datetime.datetime(2026, 9, 14, 12, 0),
    datetime.time(12, 0),
    datetime.timedelta(days=3),
])
def test_the_rest_of_the_datetime_family_does_NOT_lower_either(value):
    assert _lowers(value) is False


def test_it_now_matches_how_every_other_python_object_is_treated():
    """Decimal and an opaque object were already refused; a date was the odd
    one out."""
    class Opaque:
        pass
    assert _lowers(Decimal("10.01")) is False
    assert _lowers(Opaque()) is False
    assert _lowers(datetime.date(2026, 9, 14)) is False


def test_the_two_date_representations_no_longer_BOTH_exist():
    """Measured before the change: unify(('date',2026,9,14),
    datetime.date(2026,9,14)) is False -- two shapes for one concept that do
    not unify with each other. Only one of them can reach a compiled goal now."""
    assert _lowers(("date", 2026, 9, 14)) is True
    assert _lowers(datetime.date(2026, 9, 14)) is False


def test_the_public_discriminator_separates_a_date_term_from_a_look_alike():
    """`cells.is_cell` cannot do this -- ('date', 2023, 6, 1) and a profile
    tuple ('alpha', 'beta') are both cells. The eval harness needs the
    distinction to avoid resolving `date` as an atom on a rulebase that never
    declared it, and must use the ENGINE's definition so the two cannot drift.
    """
    from clausal.logic.cells import is_cell
    from clausal.modules.py.datetime import date_term_to_python as P

    converts = [("date", 2023, 6, 1), ("timedelta", 3, 0, 0)]
    passes_through = [("alpha", "beta"), ("date", "x", "y"), ("alpha",),
                      ("cite", ("art52",)), 42]
    for v in converts:
        assert is_cell(v) is True
        assert P(v) is not v, f"{v!r} should convert"
    for v in passes_through:
        assert P(v) is v, f"{v!r} should pass through untouched"
