"""`constant(c) / <unit>` folds to c's magnitude IN that unit.

A declaration stores the BASE magnitude, so a use site asking for a constant in
a named unit has to convert back out. Before this, the constant folded and the
DIVISOR survived:

    CENTS =:= 1550.00/usd_cent.

A unit atom is not an evaluable functor, so BOTH reference engines answer
`type_error(evaluable, usd_cent/0)` — the derived predicate could never have
answered. Dozens of single-goal downstream clauses were this exact shape,
measured 2026-09-13.
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
    test above while silently deleting division from downstream code.
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


# ── the same defect over a NON-constant left operand ──────────────────────────
#
# `constant(c) / unit` was only half of it. A use site that asks for a RUNTIME
# value in a named unit — `CENTS == A / eur_cent` — has the identical problem
# and the fold above declines it, because it requires the left to be a Call.
# Measured 2026-09-19 over the emitted AST: 13 of 18 downstream `/`-bearing
# `#=` goals are this shape.
#
# It matters more since the 2026-09-18 ruling: the goal now emits `#=`, and
# clpz answers `domain_error(clpz_expression, eur_cent)` for the atom. It was
# equally dead before — `=:=` raises on it too — so this is a pre-existing
# defect, not a regression.

VAR_SRC = """-module(m, [c/2])

c(CENTS, A) <- (CENTS == {expr})
"""


def _emit_var(expr):
    return clausal_source_to_prolog(VAR_SRC.format(expr=expr))


def test_a_variable_asked_for_in_a_scaled_unit_folds_to_multiplication():
    """`A / eur_cent` is `A * 100` — exact, and no atom reaches arithmetic.

    Multiplication rather than division on purpose: the reciprocal of every
    scaled unit in downstream code is an exact integer, so this shape leaves clpz's
    exact-division limit ENTIRELY rather than landing inside it.
    """
    out = _emit_var("A / eur_cent")
    body = out[out.index("c(CENTS, A) :-"):]
    assert "A*100" in body.replace(" ", ""), out
    assert "eur_cent" not in body, out
    assert "/" not in body.split(":-")[1], out


def test_a_basis_point_divisor_folds_to_its_own_reciprocal():
    """Not every unit is 100 — a wrong factor is a wrong number in a legal program."""
    out = _emit_var("A / basis_point")
    body = out[out.index("c(CENTS, A) :-"):]
    assert "A*10000" in body.replace(" ", ""), out
    assert "basis_point" not in body, out


def test_a_base_unit_divisor_leaves_the_term_unchanged():
    """Factor 1 divides by nothing, so the term must not acquire a `* 1`."""
    out = _emit_var("A / euro")
    body = out[out.index("c(CENTS, A) :-"):]
    assert "euro" not in body, out
    assert "*" not in body, out


def test_a_compound_left_operand_folds_too():
    """The left need not be a bare variable — this is the HEADROOM_CENTS shape."""
    out = _emit_var("(A - 5) / eur_cent")
    body = out[out.index("c(CENTS, A) :-"):]
    assert "100" in body, out
    assert "eur_cent" not in body, out


def test_real_division_between_variables_stays_division():
    """The control. Without it every assertion above passes on a fold that
    swallowed ALL division, which is the catastrophic direction: `TOTAL/COUNT`
    is arithmetic and must survive untouched."""
    out = clausal_source_to_prolog(
        "-module(m, [c/3])\n\nc(AVG, T, C) <- (AVG == T / C)\n")
    body = out[out.index("c(AVG, T, C) :-"):]
    assert "T/C" in body.replace(" ", ""), out


def test_an_unresolvable_lowercase_divisor_stays_division():
    """A second control, for the refusal branch: a lowercase name the unit
    vocabulary does not hold is NOT a unit, and guessing a factor for it would
    put a wrong number in an exported legal program."""
    out = _emit_var("A / widget")
    body = out[out.index("c(CENTS, A) :-"):]
    assert "widget" in body, out
    assert "*" not in body, out


# ── a divisor that names NO unit is not a unit divisor ────────────────────────
#
# `_unit_factor([])` answers 1 by design — a compound of base units resolves to
# 1 because every leaf does. But a NUMERIC divisor also names no unit, so it
# reached that same answer and the division was folded away to nothing:
# `PCT * SUB / 10000` emitted `PCT * SUB`, silently, off by four orders of
# magnitude. Found 2026-09-19 while measuring the fold above; the constant path
# had shipped with the same hole.


def test_a_numeric_divisor_is_not_folded_away_variable_left():
    """`PCT * SUB / 10000` keeps its division. The bug this pins was SILENT —
    a wrong number in an exported legal program, with nothing raised."""
    out = clausal_source_to_prolog(
        "-module(m, [c/3])\n\nc(C, PCT, SUB) <- (C == PCT * SUB / 10000)\n")
    body = out[out.index("c(C, PCT, SUB) :-"):]
    assert "10000" in body, out
    assert "/" in body.split(":-")[1], out


def test_a_numeric_divisor_is_not_folded_away_constant_left():
    """The same hole on the pre-existing `constant(c) / <divisor>` path.

    1550.00 / 10000 is 0.155, not 1550 — the shipped exporter emitted 1550.
    """
    out = _emit("155000", "aud_cent", "constant(cap) / 10000")
    body = out[out.index("c(V) :-"):]
    assert "10000" in body, out
    assert "/" in body.split(":-")[1], out


def test_a_unit_quantity_divisor_folds_like_a_bare_unit():
    """`/ 1(euro)` is a unit conversion written as a Quantity literal.

    Three corpus sites spell the divisor this way. It used to fold only by
    ACCIDENT, through the empty-name-list hole closed above: the Call named no
    leaf, `_unit_factor([])` answered 1, and dividing by 1 happened to be the
    right answer. Closing the hole broke it, which is how the shape was found —
    so it is handled deliberately now, and pinned here.
    """
    out = _emit("155000", "aud_cent", "constant(cap) / 1(aud)")
    body = out[out.index("c(V) :-"):]
    assert "1550" in body, out
    assert "/" not in body.split(":-")[1], out


def test_a_scaled_quantity_divisor_stays_division():
    """The control that makes the test above safe: only a magnitude of ONE is a
    unit conversion. `/ 5(aud)` is a division by five dollars, and folding it
    away as though it named a unit would be off by a factor of five."""
    out = _emit("155000", "aud_cent", "constant(cap) / 5(aud)")
    body = out[out.index("c(V) :-"):]
    assert "/" in body.split(":-")[1], out
