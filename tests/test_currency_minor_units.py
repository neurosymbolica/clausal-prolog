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


# ── float money literals: warn where the literal may already be lost ─────────
#
# Measured on this code path: a decimal with <=15 significant digits ALWAYS
# survives float -> Decimal(str(f)); 16 digits fails ~12% of the time; 17+
# essentially always. There is no decimal literal syntax, so a money amount
# written with more than 15 significant digits may already have been rounded
# by the tokenizer before any currency code sees it. It cannot be recovered
# there -- but the band in which it is unsafe IS knowable, and saying so is
# the difference between a loud problem and a silent one.


def _warns(value, unit):
    import warnings as _w
    from clausal.lint_warnings import ClausalCurrencyLiteralWarning
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        Quantity(value, unit)
    return [c for c in caught
            if issubclass(c.category, ClausalCurrencyLiteralWarning)]


def test_a_float_money_literal_above_the_band_warns():
    from clausal.modules.countries.european_union import euro
    [w] = _warns(123456789012345.69, euro)          # 17 significant digits
    assert "significant digits" in str(w.message)


def test_the_warning_says_what_to_do_instead():
    """A warning that does not name the fix makes the reader invent one."""
    from clausal.modules.countries.european_union import euro
    [w] = _warns(123456789012345.69, euro)
    text = str(w.message)
    assert "minor unit" in text, text


def test_a_float_money_literal_inside_the_band_is_silent():
    """The negative control, and the reason the band is 15 and not lower:
    every ordinary money amount must stay quiet or the warning is noise."""
    from clausal.modules.countries.european_union import euro
    for exact in (19.99, 1550.00, 0.1, 123456789012.34):
        assert _warns(exact, euro) == [], exact


def test_an_integer_magnitude_never_warns():
    """An int is exact at any size -- which is what makes minor units the
    recommended fix rather than a second-best one."""
    from clausal.modules.countries.european_union import euro
    assert _warns(99999999999999999999, euro) == []


def test_a_decimal_magnitude_never_warns():
    """Already exact; nothing was lost to a float."""
    from clausal.modules.countries.european_union import euro
    assert _warns(Decimal("123456789012345.69"), euro) == []


def test_a_non_currency_float_never_warns():
    """The negative control for scope: this is a claim about MONEY, where
    the exact decimal is the point. A physical measurement carries no such
    claim, and warning there would be noise on every float in the corpus."""
    from clausal.modules.units import metre
    assert _warns(123456789012345.69, metre) == []


# ── the Prolog exporter: refuses what it cannot export faithfully ────────────
#
# Ruled 2026-09-11 after three independent censuses agreed the cost is zero
# today: no corpus file declares a constant at all (corpus-lane), no exported
# .pl carries a non-base unit comment (iso-export-lane), and the only exporter
# test in this repo uses `euro`, a base unit. Refusing stops being free the
# moment the constants migration starts, so the window is now.


def _export(src):
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    return clausal_source_to_prolog(src)


def test_the_exporter_refuses_a_constant_declared_in_a_minor_unit():
    """The magnitude the exporter would fold is the DECLARED one, so this
    used to emit `pay(155000)` where the engine holds 1550.00 dollar -- a
    100x money error flagged only by a comment. A comment is not a guard."""
    with pytest.raises(NotImplementedError, match="scaled unit"):
        _export("-import_from(united_states, [dollar, cent])\n"
                "-constant_number_units(sga_monthly, 155000, cent)\n"
                "pay(constant(sga_monthly)),\n")


def test_the_exporter_refuses_a_scaled_physical_unit():
    """Not a currency special case: `30 day` folded to 30 while the engine
    stores 2592000 seconds. The defect was always general."""
    with pytest.raises(NotImplementedError, match="scaled unit"):
        _export("-import_from(py.units, [day])\n"
                "-constant_number_units(standstill, 30, day)\n"
                "wait(constant(standstill)),\n")


def test_the_refusal_names_the_unit_and_the_way_out():
    with pytest.raises(NotImplementedError) as exc:
        _export("-import_from(py.units, [day])\n"
                "-constant_number_units(standstill, 30, day)\n"
                "wait(constant(standstill)),\n")
    text = str(exc.value)
    assert "day" in text and "base unit" in text, text


def test_a_base_unit_constant_still_exports():
    """The negative control. A base unit needs no rescale, so its declared
    magnitude IS the stored magnitude and folding it is faithful."""
    out = _export("-import_from(european_union, [euro])\n"
                  "-constant_number_units(max_fine, 5000, euro)\n"
                  "fine(constant(max_fine)),\n")
    assert "fine(5000)" in out


def test_a_compound_of_base_units_still_exports():
    """`metre / second` is built from base units and carries no factor, so
    it is as faithful as `euro` -- the refusal must not swallow it."""
    out = _export("-import_from(py.units, [metre, second])\n"
                  "-constant_number_units(limit, 30, metre / second)\n"
                  "speed(constant(limit)),\n")
    assert "speed(30)" in out


def test_a_float_money_literal_above_the_band_can_lose_the_amount():
    """The HAZARD itself, not the warning about it.

    The tests above assert that a warning appears, which a value in the band
    that happens to survive would also satisfy — so they cannot tell a real
    loss from a safe example, and a docs example built on a surviving value
    passed them (caught by corpus-lane, 2026-09-11). This one asserts the
    loss, which is the claim the documentation actually makes.

    `123456789012345.65` cannot be WRITTEN as a float literal: the parser
    produces the nearest float, whose repr is `...66`, so the source text is
    gone before any currency code runs.
    """
    from clausal.modules.countries.european_union import euro
    assert Quantity(123456789012345.65, euro).value == Decimal("123456789012345.66")
    assert Quantity(123456789012345.65, euro).value != Decimal("123456789012345.65")


def test_the_band_is_a_hazard_not_a_certainty():
    """Why the warning says "may not be". Neighbours on both sides of the
    docs example lose a cent, while two 17-digit values survive intact — so
    a warning that claimed loss would be wrong about one amount in six."""
    from clausal.modules.countries.european_union import euro
    lost = {"123456789012345.63", "123456789012345.65", "123456789012345.68"}
    intact = {"123456789012345.67", "123456789012345.69"}
    for text in lost:
        assert Quantity(float(text), euro).value != Decimal(text), text
    for text in intact:
        assert Quantity(float(text), euro).value == Decimal(text), text


def test_minor_units_keep_the_amount_the_float_literal_loses():
    """The pair that shows the recommendation works: the same amount the
    float literal cannot express is exact as an integer count of cents."""
    from clausal.modules.countries.european_union import cent
    assert (12345678901234565 * cent).value == Decimal("123456789012345.65")


# ── the same refusal on the INLINE quantity path ─────────────────────────────
#
# The declaration is only ONE of the two ways a rulebase writes a minor-unit
# amount. `pay(155000(cent))` reaches a different lowering (`_try_quantity`),
# which kept the magnitude and dropped the unit for every unit, base or
# scaled — so option 1 covered one shape and left the identical 100x defect
# open on the other. Found by corpus-lane, 2026-09-11, on this tree.


def test_the_exporter_refuses_an_inline_quantity_in_a_scaled_unit():
    with pytest.raises(NotImplementedError, match="scaled unit"):
        _export("-import_from(united_states, [dollar, cent])\n"
                "pay(155000(cent)),\n")


def test_the_exporter_refuses_an_inline_scaled_physical_unit():
    with pytest.raises(NotImplementedError, match="scaled unit"):
        _export("-import_from(py.units, [day])\n"
                "wait(30(day)),\n")


def test_an_inline_base_unit_quantity_still_exports():
    """The negative control: a base unit's magnitude IS the stored one, and
    discarding the unit there is the 2026-09-08 ruling, not a defect."""
    out = _export("-import_from(european_union, [euro])\n"
                  "fine(5000(euro)),\n")
    assert "fine(5000)" in out


# ── the three currencies added for the corpus census ─────────────────────────
#
# corpus-lane measured the population the migration has to express: 139
# identifiers, 114 `_cents` / 18 `_satang` / 7 `_pence`, across 14 eu, 7 us,
# 4 au, 1 uk and 1 th domains. Six of those domains used a currency with no
# minor unit, so "attach the true unit" was not an option that existed for
# them and the migration would have had to go base-units in some places and
# minor-units in others. Operator widened the table, 2026-09-11.


def test_the_australian_cent_is_its_own_unit():
    """`target_au_turnover_cents` is AUD cents. The identifier that most
    needs a compiler-checkable unit was the one that could not have one —
    and declaring it in `united_states.cent` would have been the 100x-adjacent
    confusion this feature exists to prevent, with the engine's blessing."""
    from clausal.modules.countries.australia import cent, dollar
    from clausal.modules.countries.united_states import cent as usd_cent
    assert cent.value == Decimal("0.01") and cent.dims == {dollar: 1}
    assert cent.dims != usd_cent.dims, "an AUD cent is not a USD cent"


def test_the_thai_satang_is_a_scaled_unit_of_the_baht():
    from clausal.modules.countries.thailand import satang, baht
    assert satang.value == Decimal("0.01") and satang.dims == {baht: 1}
    assert (150000 * satang).value == Decimal("1500.00")


def test_sterlings_minor_unit_is_penny_singular():
    """The corpus spells its identifiers `_pence`, but a unit name is
    singular here as everywhere else in the vocabulary — `metre`, not
    `metres`. Operator's ruling, 2026-09-11."""
    from clausal.modules.countries import united_kingdom
    from clausal.modules.countries.united_kingdom import penny, sterling
    assert penny.value == Decimal("0.01") and penny.dims == {sterling: 1}
    assert not hasattr(united_kingdom, "pence"), "one spelling, not two"


def test_every_named_minor_unit_exists_and_matches_its_scale():
    """The table and the modules cannot drift: every entry must resolve, and
    its factor must be the one its currency's ISO scale implies."""
    import importlib
    from clausal.modules.countries import _data
    assert _data.MINOR_UNITS, "positive control: the table is not empty"
    for code, minor_name in _data.MINOR_UNITS.items():
        row = next(r for r in _data.CURRENCIES if r["code"] == code)
        module = importlib.import_module(
            f"clausal.modules.countries.{row['jurisdiction']}")
        unit = getattr(module, minor_name)
        assert unit.value == Decimal(1).scaleb(-row["scale"]), code
        assert unit.dims == {getattr(module, row["name"]): 1}, code


def test_the_exporter_refuses_every_named_minor_unit():
    """The refusal is keyed on the table, so widening the table must widen
    the refusal — not leave the new units exporting 100x too large."""
    from clausal.modules.countries import _data
    for code, minor_name in _data.MINOR_UNITS.items():
        row = next(r for r in _data.CURRENCIES if r["code"] == code)
        with pytest.raises(NotImplementedError, match="scaled unit"):
            _export(f"-import_from({row['jurisdiction']}, "
                    f"[{row['name']}, {minor_name}])\n"
                    f"pay(5000({minor_name})),\n")


# ── a mismatch must SAY which is which ───────────────────────────────────────
#
# `australia.cent + united_states.cent` correctly raised UnitsMismatch and
# said "dollar vs dollar" — a true error in a form indistinguishable from an
# engine bug, on exactly the case the AUD widening exists to catch. 25 of the
# 153 distinct currency names are shared by two or more ISO codes (dollar 22,
# franc 17, pound 12), so it is the diagnostic for the whole family.
# Found by corpus-lane, 2026-09-11.


def _mismatch_sides(left, right):
    from clausal.terms import UnitsMismatch
    with pytest.raises(UnitsMismatch) as exc:
        left + right
    text = str(exc.value)
    assert " vs " in text, text
    return text.rsplit(": ", 1)[1].split(" vs ")


def test_same_named_currencies_are_distinguished_in_the_message():
    from clausal.modules.countries.australia import cent as au_cent
    from clausal.modules.countries.united_states import cent as us_cent
    left, right = _mismatch_sides(1 * au_cent, 1 * us_cent)
    assert left != right, f"both sides rendered as {left!r}"
    assert "AUD" in left and "USD" in right, (left, right)


def test_every_ambiguous_currency_name_renders_distinguishably():
    """Over the whole shared-name family, not one pair. A renderer that can
    produce two identical sides has failed whatever the names happen to be."""
    from collections import Counter
    from clausal.terms import Quantity
    import importlib
    from clausal.modules.countries import _data

    by_name = Counter(r["name"] for r in _data.CURRENCIES)
    shared = [n for n, k in by_name.items() if k > 1]
    assert shared, "positive control: some currency names ARE shared"

    for name in shared:
        rows = [r for r in _data.CURRENCIES if r["name"] == name][:2]
        units = [getattr(importlib.import_module(
            f"clausal.modules.countries.{r['jurisdiction']}"), r["name"])
            for r in rows]
        left, right = _mismatch_sides(Quantity(1, units[0]),
                                      Quantity(1, units[1]))
        assert left != right, f"{name}: both sides rendered as {left!r}"


def test_an_unambiguous_mismatch_keeps_its_plain_message():
    """The negative control, and the reason this is conditional: the common
    case is two differently-named units, where a code adds noise and nothing
    else. Disambiguation is triggered by the collision, not by currency."""
    from clausal.modules.countries.european_union import euro
    from clausal.modules.countries.united_states import dollar
    left, right = _mismatch_sides(Quantity(1, euro), Quantity(1, dollar))
    assert (left, right) == ("euro", "dollar")


def test_a_compound_mismatch_qualifies_only_the_colliding_component():
    """The trigger is computed on the whole rendering; the effect must land
    only on the parts that actually collide. `second` is the SAME dimension
    object on both sides — it was never ambiguous and qualifying it violates
    the rule the qualification exists to serve (corpus-lane, 2026-09-11)."""
    from clausal.terms import Quantity
    from clausal.modules.countries.australia import dollar as aud
    from clausal.modules.countries.united_states import dollar as usd
    from clausal.modules.units import second
    left, right = _mismatch_sides(Quantity(1, {aud: 1, second: -1}),
                                  Quantity(1, {usd: 1, second: -1}))
    assert "(AUD)" in left and "(USD)" in right
    shared_left = [p for p in left.split("·") if p.startswith("second")]
    shared_right = [p for p in right.split("·") if p.startswith("second")]
    assert shared_left == shared_right == ["second^-1"], (left, right)


def test_the_mismatch_message_is_identical_across_runs():
    """An error message that differs between runs of identical code defeats
    log diffing and makes two reports of one fault look like two faults. A
    memory address does exactly that, so no message may contain one. Run in
    fresh interpreters, because within one process an id is stable and the
    defect is invisible."""
    import subprocess, sys
    program = (
        "from clausal.terms import Quantity, UnitsMismatch\n"
        "from clausal.modules.countries.australia import dollar as a\n"
        "from clausal.modules.countries.united_states import dollar as u\n"
        "from clausal.modules.units import second\n"
        "try:\n"
        "    Quantity(1, {a: 1, second: -1}) + Quantity(1, {u: 1, second: -1})\n"
        "except UnitsMismatch as e:\n"
        "    print(e)\n")
    seen = {subprocess.run([sys.executable, "-c", program], check=True,
                           capture_output=True, text=True).stdout
            for _ in range(3)}
    assert len(seen) == 1, f"message varies between runs: {seen}"
