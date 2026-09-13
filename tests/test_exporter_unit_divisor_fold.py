"""`constant(c) / <unit>` folds to c's magnitude IN that unit.

A declaration stores the BASE magnitude, so a use site asking for a constant in
a named unit has to convert back out. Before this, the constant folded and the
DIVISOR survived:

    CENTS =:= 1550.00/usd_cent.

A unit atom is not an evaluable functor, so BOTH reference engines answer
`type_error(evaluable, usd_cent/0)` — the derived predicate could never have
answered. 65 single-goal corpus clauses were this exact shape, measured
2026-09-13, across 18 domains.
"""
import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

SRC = """-module(m, [c/1])
-import_from(australia, [aud])
-constant_number_units(cap, {declared}, {unit})

c(V) <- (V == {expr})
"""


def _emit(declared, unit, expr):
    return clausal_source_to_prolog(SRC.format(declared=declared, unit=unit, expr=expr))


def test_a_constant_asked_for_in_its_declared_scaled_unit_folds_exactly():
    """155000 aud_cent is 1550.00 aud stored; asked back in cents it is 155000 —
    an exact INTEGER, not 155000.0, and with no divisor left."""
    out = _emit("155000", "aud_cent", "constant(cap) / aud_cent")
    body = out[out.index("c(V) :-"):]
    assert "155000" in body, out
    # The DECLARATION legitimately carries its unit (that is option 3); the
    # CLAUSE must not — a surviving divisor is the defect.
    assert "aud_cent" not in body, out
    assert "155000.0" not in body, out                    # and it did not become a float


def test_a_base_unit_constant_asked_in_its_base_unit_is_unchanged():
    out = _emit("155000", "aud", "constant(cap) / aud")
    assert "155000" in out and "155000.0" not in out


def test_division_by_something_that_is_not_a_unit_stays_division():
    """THE NEGATIVE CONTROL, and the half that can rot.

    `/` between a constant and an ordinary term is real arithmetic and must
    survive as real arithmetic. A fold that swallowed every `/` would pass every
    test above while silently deleting division from the corpus.
    """
    out = _emit("155000", "aud", "constant(cap) / COUNT")
    body = out.split("%")[0]
    assert "/" in body, out
    assert "COUNT" in body.upper(), out


def test_an_unresolvable_unit_divisor_is_left_alone_rather_than_guessed():
    """A divisor the unit vocabulary does not hold is not treated as a unit.
    Refusing here would break arithmetic that has always been legal."""
    out = _emit("155000", "aud", "constant(cap) / not_a_unit_at_all")
    assert "not_a_unit_at_all" in out


@pytest.mark.parametrize("declared,unit,asked,expected", [
    ("155000", "aud_cent", "aud_cent", "155000"),
    ("250000", "usd_cent", "usd_cent", "250000"),
    ("300",    "basis_point", "basis_point", "300"),
])
def test_the_round_trip_is_exact_for_each_scaled_unit(declared, unit, asked, expected):
    """Declared -> base at collection, base -> declared at the use site. The two
    halves are separate helpers and must compose back to the original number."""
    out = _emit(declared, unit, f"constant(cap) / {asked}")
    assert expected in out, out
    assert f"{expected}.0" not in out
