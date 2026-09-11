"""Minor currency units — `cent` as a scaled unit of its base currency.

The operator's ruling, 2026-09-11: a declaration must name the currency AND
the scale where the ENGINE can see both, instead of encoding them in the
parameter's identifier where only a human can read them:

    -constant_number_units(sga_monthly, 155000, cent)

A minor unit is an ORDINARY scaled unit — `Quantity(Decimal('0.01'), dollar)`,
the same shape as `kilometre = Quantity(1000, {metre: 1})` — so it works in a
declaration, in value position and in arithmetic, with no special case
anywhere. Two properties make it safe for money and are tested here:

  * the factor is DERIVED from the currency's ISO scale, so it cannot drift
    from it, and
  * it is a `Decimal`, never a binary float, so `155000 cent` is exactly
    `Decimal('1550.00')`.

`constant_number_units/3` still reports the DECLARED pair (`155000, cent`),
which is what lets a gate check that a parameter's unit matches the unit its
NAME claims. See docs/currency.md.
"""
import textwrap
from decimal import Decimal

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import Quantity


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tcmu_{name}", str(path))


def _one(module, goal, arity):
    """The single solution of `goal`, as a tuple of `arity` dereferenced args."""
    vs = [Var() for _ in range(arity)]
    rows = [tuple(deref(v) for v in vs) for _ in
            call(goal, *vs, module=module.__dict__["$module"])]
    assert len(rows) == 1, f"{goal} had {len(rows)} solutions, expected 1"
    return rows[0]


# ── the units themselves ──────────────────────────────────────────────────────

def test_cent_is_a_scaled_unit_of_the_dollar():
    from clausal.modules.countries.united_states import cent, dollar
    assert isinstance(cent, Quantity)
    assert cent.dims == {dollar: 1}, "a cent is a dollar amount, not a dimension"


def test_the_minor_factor_is_decimal_never_float():
    """The constraint money exists to keep. A float factor is what puts money
    in binary floating point; `gram = Quantity(1e-3, {kilogram: 1})` is why
    `7 gram` is 0.007 and not exact."""
    from clausal.modules.countries.united_states import cent
    from clausal.modules.countries.european_union import cent as eur_cent
    assert isinstance(cent.value, Decimal)
    assert isinstance(eur_cent.value, Decimal)


def test_the_factor_is_derived_from_the_currency_scale():
    """Not a hand-written 0.01 — derived, so it cannot disagree with the
    scale the rest of the currency machinery rounds and formats to."""
    from clausal.modules.countries._currency import _make_minor_unit
    from clausal.modules.countries.bahrain import dinar   # ISO scale 3
    from clausal.modules.countries.united_states import dollar   # scale 2
    assert _make_minor_unit(dollar).value == Decimal("0.01")
    assert _make_minor_unit(dinar).value == Decimal("0.001"), (
        "a thousandths currency gets thousandths, from its own scale")


def test_a_currency_with_no_minor_unit_is_refused():
    """16 currencies are ISO scale 0 (yen, won): there is no minor unit to
    name, and inventing one at scale 0 would make `1 minor` == `1 yen`."""
    from clausal.modules.countries._currency import _make_minor_unit
    from clausal.modules.countries.japan import yen
    with pytest.raises(ValueError, match="no minor unit"):
        _make_minor_unit(yen)


def test_each_currencys_cent_is_its_own():
    """`cent` is jurisdiction-scoped exactly as `dinar` already is."""
    from clausal.modules.countries.united_states import cent as usd_cent, dollar
    from clausal.modules.countries.european_union import cent as eur_cent, euro
    assert usd_cent.dims == {dollar: 1}
    assert eur_cent.dims == {euro: 1}


# ── declaring a constant in minor units ───────────────────────────────────────

def test_a_minor_unit_declaration_stores_the_base_currency_amount(tmp_path):
    """One representation: after declaration it IS a dollar amount, which is
    what makes it addable to dollars with no conversion logic."""
    m = _load(tmp_path, "store", """
        -import_from(united_states, [dollar, cent])
        -constant_number_units(mu_sga_monthly, 155000, cent)
    """)
    from clausal.modules.countries.united_states import dollar
    assert m.mu_sga_monthly.value == Decimal("1550.00")
    assert isinstance(m.mu_sga_monthly.value, Decimal)
    assert m.mu_sga_monthly.dims == {dollar: 1}


def test_the_declared_minor_pair_is_what_slash_3_reports(tmp_path):
    """The recoverability the operator asked for: a statutory "155000 cents"
    reads back as 155000 cents, not as 1550 dollars."""
    m = _load(tmp_path, "declared", """
        -module(declared, [look/2, mu_fee])
        -import_from(european_union, [euro, cent])
        -constant_number_units(mu_fee, 5000, cent)

        look(N, U) <- constant_number_units(mu_fee, N, U)
    """)
    assert _one(m, "look", 2) == (5000, ("cent",))


def test_a_minor_amount_adds_to_a_major_amount(tmp_path):
    """The operator's stated requirement: "euro numbers must be addable to
    eur_cents"."""
    m = _load(tmp_path, "add", """
        -module(add, [total/1])
        -import_from(european_union, [euro, cent])

        total(T) <- (eval_(5000 (cent), A), eval_(10.00 (euro), B),
                     eval_(A + B, T))
    """)
    (total,) = _one(m, "total", 1)
    assert total.value == Decimal("60.00")


def test_a_minor_unit_works_in_value_position(tmp_path):
    """An ordinary scaled unit, so the annotation sugar takes it too — the
    corpus has values duplicated as bare literals beside their parameter."""
    m = _load(tmp_path, "sugar", """
        -module(sugar, [fee/1])
        -import_from(united_states, [dollar, cent])

        fee(F) <- eval_(155000 (cent), F)
    """)
    (fee,) = _one(m, "fee", 1)
    assert fee.value == Decimal("1550.00")


def test_the_qualified_form_names_the_currency(tmp_path):
    """Two currencies in one file: bare-import one, qualify the other —
    the rule that already governs `dinar`."""
    m = _load(tmp_path, "qual", """
        -module(qual, [eu/1, us/1])
        -import_from(united_states, [dollar, cent])
        -import_module(european_union)

        eu(A) <- eval_(5000 (european_union.cent), A)
        us(A) <- eval_(5000 (cent), A)
    """)
    from clausal.modules.countries.european_union import euro
    from clausal.modules.countries.united_states import dollar
    (eu,) = _one(m, "eu", 1)
    (us,) = _one(m, "us", 1)
    assert eu.value == Decimal("50.00") and eu.dims == {euro: 1}
    assert us.value == Decimal("50.00") and us.dims == {dollar: 1}


def test_minor_units_of_different_currencies_do_not_add(tmp_path):
    """The negative control: the dimension safety is inherited unchanged, so
    a cent of one currency is still not a cent of another."""
    from clausal.terms import UnitsMismatch
    m = _load(tmp_path, "mismatch", """
        -module(mismatch, [bad/1])
        -import_from(united_states, [dollar, cent])
        -import_module(european_union)

        bad(X) <- (eval_(100 (cent), A), eval_(100 (european_union.cent), B),
                   eval_(A + B, X))
    """)
    with pytest.raises(UnitsMismatch):
        _one(m, "bad", 1)


# ── the magnitude recorded for constant_number_units/3 ────────────────────────

def test_a_decimal_magnitude_is_recorded_as_a_decimal(tmp_path):
    """The fidelity channel must not be the one place money goes binary.

    `_literal_number` reads the raw AST value, so `19.99` was recorded as a
    Python float even though the constant's VALUE is `Decimal('19.99')`.
    """
    m = _load(tmp_path, "exact", """
        -module(exact, [look/2, mu_odd_fee])
        -import_from(european_union, [euro])
        -constant_number_units(mu_odd_fee, 19.99, euro)

        look(N, U) <- constant_number_units(mu_odd_fee, N, U)
    """)
    number, units = _one(m, "look", 2)
    assert isinstance(number, Decimal), f"recorded as {type(number).__name__}"
    assert number == Decimal("19.99")
    assert units == ("euro",)


def test_an_integer_magnitude_stays_an_integer(tmp_path):
    """Only the inexact kind changes. An int is already exact, and turning
    every declared count into a Decimal would change what /3 answers for
    every united constant in the corpus."""
    m = _load(tmp_path, "int", """
        -module(int, [look/2, mu_cap])
        -import_from(european_union, [euro])
        -constant_number_units(mu_cap, 5000, euro)

        look(N, U) <- constant_number_units(mu_cap, N, U)
    """)
    number, _ = _one(m, "look", 2)
    assert isinstance(number, int) and number == 5000


def test_a_non_currency_float_magnitude_is_untouched(tmp_path):
    """The negative control for the fix above: a duration is not money, and
    `1.5 hour` has no exactness claim to keep."""
    m = _load(tmp_path, "hours", """
        -module(hours, [look/2, mu_window])
        -import_from(py.units, [hour])
        -constant_number_units(mu_window, 1.5, hour)

        look(N, U) <- constant_number_units(mu_window, N, U)
    """)
    number, units = _one(m, "look", 2)
    assert isinstance(number, float) and number == 1.5
    assert units == ("hour",)


# ── the Prolog exporter: a known divergence, pinned not endorsed ──────────────

def test_the_exporter_folds_a_minor_unit_to_its_declared_magnitude():
    """CHARACTERISATION, not an endorsement — this behaviour is wrong for money.

    `clausal_to_prolog` discards units and folds a constant to the magnitude
    the declaration WROTE, so a minor-unit constant exports 100x too large.
    It is pre-existing for every scaled unit (`30 day` exports as `30` though
    the engine stores 2592000 seconds) and the output carries a `LOSSY:`
    comment — but a comment is not a guard, and for money the error is a
    wrong legal answer. Pinned here so it cannot change silently in either
    direction; see todo/exporter-folds-scaled-units-to-the-wrong-magnitude-
    2026-09-11.md for the fix (the exporter CAN resolve the jurisdiction,
    because `-import_from(united_states, [dollar, cent])` is in front of it).
    """
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    out = clausal_source_to_prolog(
        "-import_from(united_states, [dollar, cent])\n"
        "-constant_number_units(sga_monthly, 155000, cent)\n"
        "pay(constant(sga_monthly)),\n")
    assert "pay(155000)" in out, (
        "if this now says pay(1550.00) the exporter has been fixed — delete "
        "this test and the warning in docs/currency.md")
    assert "LOSSY" in out, "the divergence must at least be recorded"
