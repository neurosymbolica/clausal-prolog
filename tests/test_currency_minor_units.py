"""Minor currency units — a scaled unit of the base currency it belongs to.

The operator's ruling, 2026-09-11: a declaration must name the currency AND
the scale where the ENGINE can see both, instead of encoding them in the
parameter's identifier where only a human can read them:

    -constant_number_units(sga_monthly, 155000, usd_cent)

A minor unit is an ORDINARY scaled unit — `Quantity(Decimal('0.01'), dollar)`,
the same shape as `kilometre = Quantity(1000, {metre: 1})` — so it works in a
declaration, in value position and in arithmetic, with no special case
anywhere. Two properties make it safe for money and are tested here:

  * the factor is DERIVED from the currency's ISO scale, so it cannot drift
    from it, and
  * it is a `Decimal`, never a binary float, so `155000 usd_cent` is exactly
    `Decimal('1550.00')`.

`constant_number_units/3` still reports the DECLARED pair (`155000, usd_cent`),
which is what lets a gate check that a parameter's unit matches the unit its
NAME claims. See docs/currency.md.
"""
import textwrap
from decimal import Decimal

import pytest

from clausal.logic.cells import chars, chars_text
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
    from clausal.modules.countries.united_states import usd_cent, usd
    assert isinstance(usd_cent, Quantity)
    assert usd_cent.dims == {"usd": 1}, "a cent is a dollar amount, not a dimension"


def test_the_minor_factor_is_decimal_never_float():
    """The constraint money exists to keep. A float factor is what puts money
    in binary floating point; `gram = Quantity(1e-3, {kilogram: 1})` is why
    `7 gram` is 0.007 and not exact."""
    from clausal.modules.countries.united_states import usd_cent
    from clausal.modules.countries.european_union import eur_cent
    assert isinstance(usd_cent.value, Decimal)
    assert isinstance(eur_cent.value, Decimal)


def test_the_factor_is_derived_from_the_currency_scale():
    """Not a hand-written 0.01 — derived, so it cannot disagree with the
    scale the rest of the currency machinery rounds and formats to."""
    from clausal.modules.countries._currency import _make_minor_unit
    from clausal.modules.countries.bahrain import bhd   # ISO scale 3
    from clausal.modules.countries.united_states import usd   # scale 2
    assert _make_minor_unit(usd).value == Decimal("0.01")
    assert _make_minor_unit(bhd).value == Decimal("0.001"), (
        "a thousandths currency gets thousandths, from its own scale")


def test_a_currency_with_no_minor_unit_is_refused():
    """16 currencies are ISO scale 0 (yen, won): there is no minor unit to
    name, and inventing one at scale 0 would make `1 minor` == `1 yen`."""
    from clausal.modules.countries._currency import _make_minor_unit
    from clausal.modules.countries.japan import yen
    with pytest.raises(ValueError, match="no minor unit"):
        _make_minor_unit(yen)


def test_each_currencys_cent_is_its_own():
    """A minor unit whose WORD is shared carries its currency in its NAME.

    `cent` belongs to AUD, EUR and USD alike, so the bare word names none of
    them and does not exist; `penny` and `satang` are unique and stay bare.
    Operator's ruling, 2026-09-11."""
    from clausal.modules.countries.united_states import usd_cent, usd
    from clausal.modules.countries.european_union import eur_cent, euro
    assert usd_cent.dims == {"usd": 1}
    assert eur_cent.dims == {"euro": 1}


# ── declaring a constant in minor units ───────────────────────────────────────

def test_a_minor_unit_declaration_stores_the_base_currency_amount(tmp_path):
    """One representation: after declaration it IS a dollar amount, which is
    what makes it addable to dollars with no conversion logic."""
    m = _load(tmp_path, "store", """
        -import_from(united_states, [usd, usd_cent])
        -constant_number_units(mu_sga_monthly, 155000, usd_cent)
    """)
    from clausal.modules.countries.united_states import usd
    assert m.mu_sga_monthly.value == Decimal("1550.00")
    assert isinstance(m.mu_sga_monthly.value, Decimal)
    assert m.mu_sga_monthly.dims == {"usd": 1}


def test_the_declared_minor_pair_is_what_slash_3_reports(tmp_path):
    """The recoverability the operator asked for: a statutory "155000 cents"
    reads back as 155000 cents, not as 1550 dollars."""
    m = _load(tmp_path, "declared", """
        -module(declared, [look/2, mu_fee])
        -import_from(european_union, [euro, eur_cent])
        -constant_number_units(mu_fee, 5000, eur_cent)

        look(N, U) <- constant_number_units(mu_fee, N, U)
    """)
    assert _one(m, "look", 2) == (5000, ("eur_cent",))


def test_a_minor_amount_adds_to_a_major_amount(tmp_path):
    """The operator's stated requirement: "euro numbers must be addable to
    eur_cents"."""
    m = _load(tmp_path, "add", """
        -module(add, [total/1])
        -import_from(european_union, [euro, eur_cent])

        total(T) <- (eval_(5000 (eur_cent), A), eval_(10.00 (euro), B),
                     eval_(A + B, T))
    """)
    (total,) = _one(m, "total", 1)
    assert total.value == Decimal("60.00")


def test_a_minor_unit_works_in_value_position(tmp_path):
    """An ordinary scaled unit, so the annotation sugar takes it too — the
    corpus has values duplicated as bare literals beside their parameter."""
    m = _load(tmp_path, "sugar", """
        -module(sugar, [fee/1])
        -import_from(united_states, [usd, usd_cent])

        fee(F) <- eval_(155000 (usd_cent), F)
    """)
    (fee,) = _one(m, "fee", 1)
    assert fee.value == Decimal("1550.00")


def test_the_qualified_form_names_the_currency(tmp_path):
    """Two currencies in one file: bare-import one, qualify the other —
    the rule that already governs `dinar`."""
    m = _load(tmp_path, "qual", """
        -module(qual, [eu/1, us/1])
        -import_from(united_states, [usd, usd_cent])
        -import_module(european_union)

        eu(A) <- eval_(5000 (european_union.eur_cent), A)
        us(A) <- eval_(5000 (usd_cent), A)
    """)
    from clausal.modules.countries.european_union import euro
    from clausal.modules.countries.united_states import usd
    (eu,) = _one(m, "eu", 1)
    (us,) = _one(m, "us", 1)
    assert eu.value == Decimal("50.00") and eu.dims == {"euro": 1}
    assert us.value == Decimal("50.00") and us.dims == {"usd": 1}


def test_minor_units_of_different_currencies_do_not_add(tmp_path):
    """The negative control: the dimension safety is inherited unchanged, so
    a cent of one currency is still not a cent of another."""
    from clausal.terms import UnitsMismatch
    m = _load(tmp_path, "mismatch", """
        -module(mismatch, [bad/1])
        -import_from(united_states, [usd, usd_cent])
        -import_module(european_union)

        bad(X) <- (eval_(100 (usd_cent), A), eval_(100 (european_union.eur_cent), B),
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


def test_a_minor_unit_declaration_exports_the_BASE_magnitude():
    """Was a REFUSAL until 2026-09-13 (option 3): the exporter folded the
    DECLARED magnitude, emitting `pay(155000)` where the engine holds 1550.00
    dollar -- a 100x money error flagged only by a comment, and a comment is
    not a guard. It now converts, so the refusal is no longer needed.

    This test kept its coverage and changed its expectation: the thing it
    guards against is still `pay(155000)`."""
    out = _export("-import_from(united_states, [usd, usd_cent])\n"
                  "-constant_number_units(sga_monthly, 155000, usd_cent)\n"
                  "pay(constant(sga_monthly)),\n")
    # `pay(1550)`: an integral scaled fold is an exact INT at a use site since
    # the 2026-09-13 float fix (iso-export-lane's finding). The guard that
    # matters is unchanged -- it must never be the declared 155000.
    assert "pay(1550)" in out, out
    assert "pay(155000)" not in out


def test_a_scaled_physical_unit_declaration_converts_too():
    """Not a currency special case, and it never was: `30 day` folded to 30
    while the engine stores 2592000 seconds. Now converted, same as money."""
    out = _export("-import_from(py.units, [day])\n"
                  "-constant_number_units(standstill, 30, day)\n"
                  "wait(constant(standstill)),\n")
    assert "wait(2592000)" in out, out
    assert "wait(30)" not in out


def test_the_declaration_crosses_carrying_its_unit():
    """Replaces two tests that asserted the refusal's WORDING. There is no
    refusal on this path now -- the declaration is emitted, so the unit is
    present in the exported program rather than named in an error about why it
    could not be."""
    out = _export("-import_from(py.units, [day])\n"
                  "-constant_number_units(standstill, 30, day)\n"
                  "wait(constant(standstill)),\n")
    assert "constant_number_units(" in out and "day" in out, out



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
    from clausal.modules.countries.european_union import eur_cent
    assert (12345678901234565 * eur_cent).value == Decimal("123456789012345.65")


# ── the same refusal on the INLINE quantity path ─────────────────────────────
#
# The declaration is only ONE of the two ways a rulebase writes a minor-unit
# amount. `pay(155000(usd_cent))` reaches a different lowering (`_try_quantity`),
# which kept the magnitude and dropped the unit for every unit, base or
# scaled — so option 1 covered one shape and left the identical 100x defect
# open on the other. Found by corpus-lane, 2026-09-11, on this tree.


def test_the_exporter_refuses_an_inline_quantity_in_a_scaled_unit():
    with pytest.raises(NotImplementedError, match="scaled unit"):
        _export("-import_from(united_states, [usd, usd_cent])\n"
                "pay(155000(usd_cent)),\n")


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
    and declaring it in `united_states.usd_cent` would have been the 100x-adjacent
    confusion this feature exists to prevent, with the engine's blessing."""
    from clausal.modules.countries.australia import aud_cent, aud
    from clausal.modules.countries.united_states import usd_cent
    assert aud_cent.value == Decimal("0.01") and aud_cent.dims == {"aud": 1}
    assert aud_cent.dims != usd_cent.dims, "an AUD cent is not a USD cent"


def test_the_thai_satang_is_a_scaled_unit_of_the_baht():
    from clausal.modules.countries.thailand import satang, baht
    assert satang.value == Decimal("0.01") and satang.dims == {"baht": 1}
    assert (150000 * satang).value == Decimal("1500.00")


def test_sterlings_minor_unit_is_penny_singular():
    """The corpus spells its identifiers `_pence`, but a unit name is
    singular here as everywhere else in the vocabulary — `metre`, not
    `metres`. Operator's ruling, 2026-09-11."""
    from clausal.modules.countries import united_kingdom
    from clausal.modules.countries.united_kingdom import penny, sterling
    assert penny.value == Decimal("0.01") and penny.dims == {"sterling": 1}
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
        binding = _data.CURRENCY_BINDINGS[row["code"]]
        assert getattr(module, binding) is not None, code
        assert unit.dims == {binding: 1}, code


def test_the_exporter_refuses_every_named_minor_unit():
    """The refusal is keyed on the table, so widening the table must widen
    the refusal — not leave the new units exporting 100x too large."""
    from clausal.modules.countries import _data
    for code, minor_name in _data.MINOR_UNITS.items():
        row = next(r for r in _data.CURRENCIES if r["code"] == code)
        with pytest.raises(NotImplementedError, match="scaled unit"):
            _export(f"-import_from({row['jurisdiction']}, "
                    f"[{_data.CURRENCY_BINDINGS[row['code']]}, {minor_name}])\n"
                    f"pay(5000({minor_name})),\n")


# ── a mismatch must SAY which is which ───────────────────────────────────────
#
# `australia.aud_cent + united_states.usd_cent` correctly raised UnitsMismatch and
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
    from clausal.modules.countries.australia import aud_cent
    from clausal.modules.countries.united_states import usd_cent
    left, right = _mismatch_sides(1 * aud_cent, 1 * usd_cent)
    assert left != right, f"both sides rendered as {left!r}"
    # Since the renderer switched to the BOUND identifier (2026-09-12) the two
    # sides differ by construction and need no `(AUD)` qualifier — the
    # identifiers are what a rulebase writes, and those were never ambiguous.
    assert (left, right) == ("aud", "usd"), (left, right)


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
            f"clausal.modules.countries.{r['jurisdiction']}"),
            _data.CURRENCY_BINDINGS[r["code"]]) for r in rows]
        left, right = _mismatch_sides(Quantity(1, units[0]),
                                      Quantity(1, units[1]))
        assert left != right, f"{name}: both sides rendered as {left!r}"


def test_an_unambiguous_mismatch_keeps_its_plain_message():
    """The negative control, and the reason this is conditional: the common
    case is two differently-named units, where a code adds noise and nothing
    else. Disambiguation is triggered by the collision, not by currency."""
    from clausal.modules.countries.european_union import euro
    from clausal.modules.countries.united_states import usd
    left, right = _mismatch_sides(Quantity(1, euro), Quantity(1, usd))
    # `euro` keeps its word because the word is unique; `usd` is the code
    # because `dollar` is shared by 22 currencies and does not resolve.
    assert (left, right) == ("euro", "usd")


def test_a_compound_mismatch_qualifies_only_the_colliding_component():
    """The trigger is computed on the whole rendering; the effect must land
    only on the parts that actually collide. `second` is the SAME dimension
    object on both sides — it was never ambiguous and qualifying it violates
    the rule the qualification exists to serve (corpus-lane, 2026-09-11)."""
    from clausal.terms import Quantity
    from clausal.modules.countries.australia import aud
    from clausal.modules.countries.united_states import usd as usd
    from clausal.modules.units import second
    left, right = _mismatch_sides(Quantity(1, {aud: 1, second: -1}),
                                  Quantity(1, {usd: 1, second: -1}))
    # The property is unchanged and now reads directly: the colliding
    # component differs, the shared one is IDENTICAL on both sides. What
    # changed is that the renderer emits a re-readable unit expression, so
    # the shared part is `/ second` rather than `·second^-1`.
    assert (left, right) == ("aud / second", "usd / second"), (left, right)
    assert left.split(" / ")[1] == right.split(" / ")[1] == "second"


def test_the_mismatch_message_is_identical_across_runs():
    """An error message that differs between runs of identical code defeats
    log diffing and makes two reports of one fault look like two faults. A
    memory address does exactly that, so no message may contain one. Run in
    fresh interpreters, because within one process an id is stable and the
    defect is invisible."""
    import subprocess, sys
    program = (
        "from clausal.terms import Quantity, UnitsMismatch\n"
        "from clausal.modules.countries.australia import aud as a\n"
        "from clausal.modules.countries.united_states import usd as u\n"
        "from clausal.modules.units import second\n"
        "try:\n"
        "    Quantity(1, {a: 1, second: -1}) + Quantity(1, {u: 1, second: -1})\n"
        "except UnitsMismatch as e:\n"
        "    print(e)\n")
    seen = {subprocess.run([sys.executable, "-c", program], check=True,
                           capture_output=True, text=True).stdout
            for _ in range(3)}
    assert len(seen) == 1, f"message varies between runs: {seen}"


# ── the name carries the currency exactly where the word does not ────────────
#
# Operator's ruling, 2026-09-11: `cent` belongs to AUD, EUR and USD alike, so
# a bare `cent` names none of them; `penny` and `satang` are unique and stay
# bare. This is not decoration — it closes two gaps by construction rather
# than guarding them. Two jurisdictions can no longer shadow each other's
# minor unit on import, and `/3` names the currency without needing the
# qualified form (which records nothing, `_units_ast_to_term` returning None
# for an Attribute).


def test_a_shared_subunit_word_is_never_bound_bare():
    """The gap this closes: `-import_from` of two jurisdictions used to bind
    `cent` twice, silently, last-one-wins — a rulebase computing in silently
    USD "cents" is wrong and never raises, because nothing ever meets a euro
    amount to mismatch against."""
    from clausal.modules.countries import european_union, united_states, australia
    for module in (european_union, united_states, australia):
        assert not hasattr(module, "cent"), (
            f"{module.__name__} still binds a bare `cent`")


def test_a_unique_subunit_word_stays_bare():
    """`satang` is Thailand's alone and `penny` is sterling's alone, so
    nothing is gained by prefixing them and the operator ruled they stay."""
    from clausal.modules.countries import thailand, united_kingdom
    assert hasattr(thailand, "satang") and not hasattr(thailand, "thb_satang")
    assert hasattr(united_kingdom, "penny") and not hasattr(united_kingdom, "gbp_penny")


def test_both_minor_units_import_into_one_file_without_shadowing(tmp_path):
    """The whole point, end to end: two currencies' minor units in one file,
    each resolving to its own currency. Before the rename this file bound
    `cent` twice and the second silently won."""
    m = _load(tmp_path, "both", """
        -module(both, [eu/1, us/1])
        -import_from(european_union, [euro, eur_cent])
        -import_from(united_states, [usd, usd_cent])

        eu(A) <- eval_(5000 (eur_cent), A)
        us(A) <- eval_(5000 (usd_cent), A)
    """)
    from clausal.modules.countries.european_union import euro
    from clausal.modules.countries.united_states import usd
    (eu,), (us,) = _one(m, "eu", 1), _one(m, "us", 1)
    assert eu.dims == {"euro": 1} and us.dims == {"usd": 1}
    assert eu.value == us.value == Decimal("50.00")


def test_slash_3_names_the_currency_without_the_qualified_form(tmp_path):
    """`/3` reports the declared SPELLING, so the spelling now carries the
    currency. Previously both sides answered `cent` and a gate could not tell
    EUR cents from USD cents from /3 at all."""
    m = _load(tmp_path, "named", """
        -module(named, [eu/2, us/2, n_eu, n_us])
        -import_from(european_union, [euro, eur_cent])
        -import_from(united_states, [usd, usd_cent])
        -constant_number_units(n_eu, 5000, eur_cent)
        -constant_number_units(n_us, 5000, usd_cent)

        eu(N, U) <- constant_number_units(n_eu, N, U)
        us(N, U) <- constant_number_units(n_us, N, U)
    """)
    assert _one(m, "eu", 2) == (5000, ("eur_cent",))
    assert _one(m, "us", 2) == (5000, ("usd_cent",))


def test_the_naming_rule_is_derived_from_the_table_not_hand_written():
    """A word used by more than one currency is prefixed with its ISO code;
    a word used by one is not. Checked against the table so the rule cannot
    drift from the names actually bound."""
    import importlib
    from collections import Counter
    from clausal.modules.countries import _data
    words = Counter(_data.MINOR_UNIT_WORDS.values())
    assert words, "positive control: the word table is not empty"
    assert any(c > 1 for c in words.values()), (
        "positive control: some subunit WORD really is shared, or this test "
        "proves nothing")
    for code, word in _data.MINOR_UNIT_WORDS.items():
        row = next(r for r in _data.CURRENCIES if r["code"] == code)
        expected = f"{code.lower()}_{word}" if words[word] > 1 else word
        assert _data.MINOR_UNITS[code] == expected, code
        module = importlib.import_module(
            f"clausal.modules.countries.{row['jurisdiction']}")
        assert hasattr(module, expected), f"{code}: {expected} not bound"


def test_the_committed_names_are_what_the_generator_would_emit():
    """`_data.py` is GENERATED but was hand-edited, because babel (a
    build-only dependency) is not installed in this venv and the generator
    cannot be run here. So the one thing that could silently drift — the
    curated words and the rule that resolves them — is checked directly
    against the generator source, which needs no babel to read.
    """
    import ast
    from clausal.modules.countries import _data

    source = ast.parse(open("scripts/gen_currencies.py", encoding="utf-8").read())
    ns = {}
    for node in source.body:
        wanted = (isinstance(node, ast.Assign)
                  and getattr(node.targets[0], "id", "") == "MINOR_UNIT_WORDS")
        wanted |= (isinstance(node, ast.FunctionDef)
                   and node.name == "minor_unit_names")
        if wanted:
            exec(compile(ast.Module([node], []), "<gen>", "exec"), ns)
    assert "minor_unit_names" in ns and ns.get("MINOR_UNIT_WORDS"), (
        "positive control: the generator's rule and word table were found")

    assert ns["MINOR_UNIT_WORDS"] == _data.MINOR_UNIT_WORDS
    assert ns["minor_unit_names"](ns["MINOR_UNIT_WORDS"]) == _data.MINOR_UNITS
    # The rule must do something, or agreement proves nothing.
    assert ns["minor_unit_names"](
        {"XXX": "cent", "YYY": "cent", "ZZZ": "krone"}) == {
            "XXX": "xxx_cent", "YYY": "yyy_cent", "ZZZ": "krone"}


# ── major currencies: a shared word is replaced by the ISO code ──────────────
#
# Operator's ruling, 2026-09-11. `dinar` is bound in bahrain, kuwait, jordan,
# algeria, iraq, libya, tunisia and serbia alike, so the bare word names none
# of them; `bhd`, `kwd`, … name exactly one each. A word is kept ONLY when
# exactly one CURRENT currency uses it — the convention the generator already
# applies within a jurisdiction ("the current currency keeps the plain word"),
# extended across them. That also settles `try`, which is a Python keyword and
# could never be an identifier: TRY is the only current lira, so it keeps the
# word and the code is never needed.


def _binding_table():
    from clausal.modules.countries import _data
    return _data.CURRENCY_BINDINGS


def test_a_word_shared_by_several_current_currencies_is_not_bound():
    from clausal.modules.countries import united_states, australia, bahrain, kuwait
    for module in (united_states, australia):
        assert not hasattr(module, "dollar"), module.__name__
    for module in (bahrain, kuwait):
        assert not hasattr(module, "dinar"), module.__name__
    assert united_states.usd.iso_code == "USD"
    assert australia.aud.iso_code == "AUD"
    assert bahrain.bhd.iso_code == "BHD"
    assert kuwait.kwd.iso_code == "KWD"


def test_a_unique_word_is_untouched():
    from clausal.modules.countries import european_union, japan, thailand, united_kingdom
    assert european_union.euro.iso_code == "EUR"
    assert japan.yen.iso_code == "JPY"
    assert thailand.baht.iso_code == "THB"
    assert united_kingdom.sterling.iso_code == "GBP"
    assert not hasattr(japan, "jpy"), "a unique word needs no code alias"


def test_the_only_current_user_of_a_word_keeps_it():
    """`lira` is shared with two WITHDRAWN currencies, so TRY keeps the word —
    which is also the only reason `try`, a Python keyword, never has to be an
    identifier. `mark` likewise: BAM is current, DEM is not."""
    import importlib
    turkiye = importlib.import_module("clausal.modules.countries.turkiye")
    italy = importlib.import_module("clausal.modules.countries.italy")
    germany = importlib.import_module("clausal.modules.countries.germany")
    bosnia = importlib.import_module("clausal.modules.countries.bosnia_herzegovina")
    assert turkiye.lira.iso_code == "TRY"
    assert italy.itl.iso_code == "ITL" and not hasattr(italy, "lira")
    assert bosnia.mark.iso_code == "BAM"
    assert germany.dem.iso_code == "DEM" and not hasattr(germany, "mark")
    assert "try" not in _binding_table().values(), "a Python keyword was bound"


def test_no_identifier_is_bound_in_two_jurisdictions():
    """The property the whole rename exists for: after it, a bare currency
    name means exactly one currency, so two of them can never shadow each
    other on import."""
    import importlib
    from collections import defaultdict
    from clausal.modules.countries import _data
    where = defaultdict(set)
    for r in _data.CURRENCIES:
        where[_data.CURRENCY_BINDINGS[r["code"]]].add(r["jurisdiction"])
    assert where, "positive control: the binding table is not empty"
    ambiguous = {n: js for n, js in where.items() if len(js) > 1}
    assert not ambiguous, ambiguous


def test_every_binding_resolves_and_carries_its_own_metadata():
    import importlib
    from clausal.modules.countries import _data
    for r in _data.CURRENCIES:
        ident = _data.CURRENCY_BINDINGS[r["code"]]
        mod = importlib.import_module(
            f"clausal.modules.countries.{r['jurisdiction']}")
        obj = getattr(mod, ident, None)
        assert obj is not None, f"{r['jurisdiction']}.{ident} missing"
        assert obj.iso_code == r["code"] and obj.scale == r["scale"]


def test_the_everyday_word_survives_for_DISPLAY():
    """The code replaces the identifier you WRITE, not the word the system
    prints. A judgment says "dollar", not "USD"."""
    from clausal.terms import Quantity, _format_money
    from clausal.modules.countries.united_states import usd
    assert usd._name == "dollar"
    assert _format_money(Decimal("500.00"), usd, "name", "half_up") == "500.00 dollar"
    assert _format_money(Decimal("500.00"), usd, "code", "half_up") == "500.00 USD"


def test_a_currency_written_by_its_code_still_exports(tmp_path):
    """The exporter's base-unit set is keyed on what source can WRITE. If it
    still held the old words, `500(usd)` would be refused as a scaled unit."""
    out = _export("-import_from(united_states, [usd])\n"
                  "-constant_number_units(cap, 5000, usd)\n"
                  "fine(constant(cap)),\n")
    assert "fine(5000)" in out


def test_both_dinars_import_into_one_file(tmp_path):
    """The question that prompted this: bahrain's dinar and kuwait's, in one
    file, each meaning exactly one thing."""
    m = _load(tmp_path, "dinars", """
        -module(dinars, [bh/1, kw/1])
        -import_from(bahrain, [bhd])
        -import_from(kuwait, [kwd])

        bh(A) <- eval_(5 (bhd), A)
        kw(A) <- eval_(5 (kwd), A)
    """)
    from clausal.modules.countries.bahrain import bhd
    from clausal.modules.countries.kuwait import kwd
    (bh,), (kw,) = _one(m, "bh", 1), _one(m, "kw", 1)
    assert bh.dims == {"bhd": 1} and kw.dims == {"kwd": 1}


# ── -constant_number_currency: the directive that declares MONEY ─────────────
#
# Named for its claim and enforcing it, like -constant_number_units before it.
# The gap it closes, measured on this tree: a wrong or mistyped currency was
# ALREADY caught, because a currency identifier has to be bound to be written
# (`-constant_number_units(fee, 5000, dollar)` is a NameError). What was not
# caught is a unit that loads fine and is not money —
# `-constant_number_units(fee, 5000, metre)` yields Quantity(5000, metre),
# an int-valued length, in silence. Operator, 2026-09-11.


def test_a_currency_constant_declares_and_stores_money(tmp_path):
    m = _load(tmp_path, "cc_ok", """
        -module(cc_ok, [look/2, cc_sga])
        -import_from(united_states, [usd])
        -constant_number_currency(cc_sga, 5000, usd)

        look(N, U) <- constant_number_units(cc_sga, N, U)
    """)
    from clausal.modules.countries.united_states import usd
    assert m.cc_sga.value == Decimal("5000") and m.cc_sga.dims == {"usd": 1}
    assert isinstance(m.cc_sga.value, Decimal)
    # A money constant IS a united constant: the stricter declaration does not
    # hide it from the view that already exists.
    assert _one(m, "look", 2) == (5000, ("usd",))


def test_a_non_currency_unit_is_refused(tmp_path):
    """The gap. `metre` loads perfectly well under -constant_number_units and
    gives a length; asked for money, the engine should say so."""
    with pytest.raises(TypeError, match="not an amount of money"):
        _load(tmp_path, "cc_metre", """
            -import_from(py.units, [metre])
            -constant_number_currency(fee, 5000, metre)
        """)


def test_the_refusal_names_the_directive_and_the_alternative(tmp_path):
    with pytest.raises(TypeError) as exc:
        _load(tmp_path, "cc_msg", """
            -import_from(py.units, [metre])
            -constant_number_currency(fee, 5000, metre)
        """)
    text = str(exc.value)
    assert "metre" in text and "-constant_number_units" in text, text


def test_a_compound_unit_is_refused(tmp_path):
    """Money is an AMOUNT, not a rate. `usd / second` is a perfectly good unit
    expression and belongs to the general directive."""
    with pytest.raises(SyntaxError, match="single currency"):
        _load(tmp_path, "cc_rate", """
            -import_from(united_states, [usd])
            -import_from(py.units, [second])
            -constant_number_currency(burn, 5000, usd / second)
        """)


def test_a_non_number_is_refused(tmp_path):
    """Inherited from the units form, and it must stay inherited: the value
    check is about what carries a unit, not about which unit."""
    with pytest.raises(SyntaxError, match="only numbers carry units"):
        _load(tmp_path, "cc_str", """
            -import_from(united_states, [usd])
            -constant_number_currency(fee, 'hello', usd)
        """)


def test_the_precision_check_still_applies(tmp_path):
    """Sub-scale digits are refused by the currency constructor, and routing
    through a money-specific directive must not skip it."""
    from clausal.terms import CurrencyPrecisionError
    with pytest.raises(CurrencyPrecisionError):
        _load(tmp_path, "cc_prec", """
            -import_from(united_states, [usd])
            -constant_number_currency(fee, 0.001, usd)
        """)


def test_a_minor_unit_is_accepted_by_the_currency_directive(tmp_path):
    """A minor unit of a currency IS money, and the property the declaration
    asserts is "this constant is money" — which it satisfies.

    Refusing it split the two safety properties across two directives so that
    an author could have the currency gate or the minor-unit scale but never
    both — and every one of the 139 identifiers the corpus migration is about
    is `_cents`/`_satang`/`_pence`, so the gate would have covered the case
    the migration is least likely to produce (corpus-lane, 2026-09-11).
    """
    m = _load(tmp_path, "cc_minor", """
        -import_from(united_states, [usd, usd_cent])
        -constant_number_currency(cc_sga_minor, 155000, usd_cent)
    """)
    from clausal.modules.countries.united_states import usd
    assert m.cc_sga_minor.value == Decimal("1550.00")
    assert m.cc_sga_minor.dims == {"usd": 1}


def test_the_gate_is_money_SHAPE_not_currency_TYPE(tmp_path):
    """What "money" means mechanically: dims is a single currency at exponent
    one. That admits a currency and a minor unit of one, and nothing else --
    `usd**2` is an area in dollars and `usd / second` is a rate, neither of
    which is an amount of money.

    **`kilometre` is the discriminating row** (corpus-lane, 2026-09-11): a
    `Quantity` over a single non-currency base at exponent one, structurally
    identical to `usd_cent` in every respect except `is_currency`. Every
    other refusal here fails for a SHAPE reason and would still fail under a
    checker that had dropped the currency test; only this one separates
    "money shape" from "single-dimension scaled quantity", and it is the row
    a future widening will trip over."""
    from clausal.terms import Quantity
    from clausal.modules.countries.united_states import usd, usd_cent
    from clausal.modules.countries.european_union import eur_cent
    from clausal.modules.units import metre, second, kilometre
    from clausal.logic.constants import check_currency_unit

    for ok in (usd, usd_cent, eur_cent):
        assert check_currency_unit("x", ok, "-constant_number_currency") is ok
    for bad in (metre, second, kilometre,
                Quantity(1, {usd: 1, second: -1}), Quantity(1, {usd: 2})):
        with pytest.raises(TypeError, match="not an amount of money"):
            check_currency_unit("x", bad, "-constant_number_currency")


def test_the_general_directive_is_unchanged(tmp_path):
    """The negative control. -constant_number_units still takes any unit,
    including a non-money one; the new directive adds a claim, it does not
    restrict the old one."""
    m = _load(tmp_path, "cc_neg", """
        -import_from(py.units, [metre])
        -constant_number_units(cc_len, 5000, metre)
    """)
    assert m.cc_len.value == 5000


def test_the_exporter_knows_the_currency_directive():
    """A new directive the exporter does not recognise becomes an
    unknown-directive warning and the constant silently stops folding. It
    takes the same path as the other two: refuse a scaled unit, fold a base
    one, record the discard."""
    out = _export("-import_from(united_states, [usd])\n"
                  "-constant_number_currency(cap, 5000, usd)\n"
                  "fine(constant(cap)),\n")
    assert "fine(5000)" in out
    # Was: the LOSSY note names the directive. There is no LOSSY note on this
    # path since 2026-09-13 -- the declaration is EMITTED, so the directive
    # name appears as a clause rather than in a comment about what was lost.
    assert "constant_number_currency(" in out, out


def test_the_currency_directive_is_listed_as_known():
    """The unknown-directive error enumerates what IS known; a directive
    missing from that list is unfindable by the reader who mistyped it."""
    with pytest.raises(SyntaxError) as exc:
        import textwrap, tempfile, os
        from clausal.import_hook import _load_module
        d = tempfile.mkdtemp()
        p = os.path.join(d, "unknown_dir.clausal")
        open(p, "w").write("-no_such_directive(x)\n")
        _load_module("unknown_dir_probe", p)
    text = str(exc.value)
    assert "known directives" in text
    for spelling in ("-constant_value", "-constant_number_units",
                     "-constant_number_currency"):
        assert spelling in text, f"{spelling} missing from the list"


# ── the scale-in-a-name lint ─────────────────────────────────────────────────
#
# Operator, 2026-09-11: "bare integers for currencies is begging for trouble."
# Measured, and the second case is why — it is not a wrong number, it is a
# REVERSED answer:
#
#     bare ints :  155000 > 1550   -> True    "exceeds the threshold"
#     as money  :  1550.00 > 1550  -> False   it does not
#
# and two 'cents' integers of different currencies sum silently where the
# money form raises `dollar (AUD) vs dollar (USD)`.
#
# Declaring the constant fixes the constant. It does nothing for a bare
# literal in a FACT -- `minimum_leverage_bps(300)` -- which is exactly the
# shape at leverage_ratio.clausal:111, where the deciding literal is bare and
# the declared fact is the copy that cannot change an answer.


def _lint_warnings(tmp_path, name, text):
    import warnings as _w
    from clausal.lint_warnings import ClausalScaleInNameWarning
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        _load(tmp_path, name, text)
    return [str(c.message) for c in caught
            if issubclass(c.category, ClausalScaleInNameWarning)]


def test_a_fact_whose_name_claims_a_scale_and_carries_a_bare_number(tmp_path):
    [w] = _lint_warnings(tmp_path, "sc_fact", """
        minimum_leverage_bps(300),
    """)
    assert "minimum_leverage_bps" in w and "bps" in w


def test_the_lint_names_the_way_out(tmp_path):
    [w] = _lint_warnings(tmp_path, "sc_msg", "sum_eur_cents(155000),\n")
    assert "-constant_number_currency" in w, w


def test_a_name_without_a_scale_suffix_is_silent(tmp_path):
    """The negative control that matters most: this lint reads every clause
    in every file, so a false positive is noise everywhere."""
    assert _lint_warnings(tmp_path, "sc_plain", "threshold(300),\n") == []


def test_a_scale_name_carrying_a_UNITED_value_is_silent(tmp_path):
    """The discriminator. A converted site is a quantity, not a bare literal,
    so doing the right thing silences the lint — which is what makes it a
    migration instrument rather than a permanent complaint."""
    assert _lint_warnings(tmp_path, "sc_united", """
        -import_from(united_states, [usd, usd_cent])
        fee_cents(155000 (usd_cent)),
    """) == []


def test_a_scale_name_with_no_literal_is_silent(tmp_path):
    """A variable carries no scale claim to check."""
    assert _lint_warnings(tmp_path, "sc_var", """
        fee_cents(X) <- (X == 1)
    """) == []


def test_a_unitless_constant_whose_name_claims_a_scale(tmp_path):
    """The other half: the declaration form. `-constant_value` takes no unit,
    so a scale in the NAME is the only record — which is the defect."""
    [w] = _lint_warnings(tmp_path, "sc_const", """
        -constant_value(sc_fee_cents, 155000)
    """)
    assert "sc_fee_cents" in w


def test_a_declared_money_constant_is_silent(tmp_path):
    """Declaring it is the fix, so declaring it must stop the warning."""
    assert _lint_warnings(tmp_path, "sc_ok", """
        -import_from(united_states, [usd, usd_cent])
        -constant_number_currency(sc_ok_fee_cents, 155000, usd_cent)
    """) == []


def test_the_lint_fires_once_per_identifier(tmp_path):
    """Per (file, identifier), like the TitleCase lint: 139 corpus sites
    warning once each is a worklist, warning per occurrence is noise."""
    w = _lint_warnings(tmp_path, "sc_once", """
        minimum_leverage_bps(300),
        minimum_leverage_bps(400),
        other_ratio_bps(50),
    """)
    assert len(w) == 2, w


def test_the_lint_is_BLIND_to_a_literal_under_an_unscaled_functor(tmp_path):
    """The limit, pinned — and it is the case the lint was first MOTIVATED by,
    which is why it is a test and not a footnote.

    a leverage-ratio domain has a scale-named fact at :93 that no longer decides
    anything, and the 3% floor that DOES decide is a bare `300` in an argument
    of `check_ratio_gte/6` at :111. The functor claims no scale, so nothing in
    the source keys the literal to one and the lint cannot see it.

    The consequence is the sharp one (corpus-lane, 2026-09-11): converting :93
    silences the domain while the deciding literal is untouched. **The lint
    emptying is not "this domain is done."** Self-emptying is a real property
    and a real progress signal for the sites it CAN see; it is not a
    completeness claim.
    """
    warned = _lint_warnings(tmp_path, "blind", """
        -implicit_atoms
        minimum_leverage_bps(300),
        ratio_ok(P) <- check_ratio_gte(P, tier1, total, 300, below, ok)
    """)
    assert warned == [w for w in warned if "minimum_leverage_bps" in w]
    assert len(warned) == 1, "only the scale-NAMED site is seen"


def test_body_position_is_reached_so_the_name_is_the_discriminator(tmp_path):
    """The control that makes the test above a statement about NAMES rather
    than about positions: same argument slot, scale-named functor, warns."""
    warned = _lint_warnings(tmp_path, "blind_ctl", """
        -implicit_atoms
        ratio_ok(P) <- ( check_ratio_gte(P, tier1, total, 300, below, ok),
                         floor_bps(300) )
    """)
    assert len(warned) == 1 and "floor_bps" in warned[0], warned


# ── compatible_units/2: the assertion that RAISES ────────────────────────────
#
# `has_units/2` answers the same relation by SUCCEEDING or FAILING, and a goal
# failure is swallowed: a guard that fails just makes the rule not fire, so a
# caller who passed the wrong thing gets "no" rather than "you passed the
# wrong thing". Measured before building:
#
#     has_units(A, euro)   A is euro     succeeds
#     has_units(A, metre)  A is euro     FAILS silently
#     has_units(5, euro)   bare number   FAILS silently
#
# Operator, 2026-09-11: a bare number is never compatible — not even with
# `dimensionless`. It is the only version that closes the hole for RATIOS,
# where a bare `0.03` would otherwise pass as dimensionless and the check
# would wave through exactly the case it exists to catch.


def _compat(value, unit):
    from clausal.modules.units import compatible_units_check
    return compatible_units_check(value, unit)


def test_a_matching_unit_is_compatible():
    from clausal.modules.countries.european_union import euro
    from clausal.modules.units import metre
    assert _compat(Quantity(Decimal("5.00"), euro), euro) is True
    assert _compat(Quantity(5, metre), metre) is True


def test_scale_is_IGNORED_for_compatibility():
    """A scaled unit normalises at construction, so by here the scale is
    already applied and the only question left is the dimension. `5 kilometre`
    is a metre-thing; `155000 usd_cent` is a dollar amount."""
    from clausal.modules.countries.united_states import usd, usd_cent
    from clausal.modules.units import metre, kilometre
    assert _compat(155000 * usd_cent, usd) is True
    assert _compat(155000 * usd_cent, usd_cent) is True
    assert _compat(5 * kilometre, metre) is True


def test_a_mismatched_unit_RAISES_where_has_units_would_fail():
    from clausal.terms import UnitsMismatch
    from clausal.modules.countries.european_union import euro
    from clausal.modules.units import metre
    with pytest.raises(UnitsMismatch, match="euro"):
        _compat(Quantity(Decimal("5.00"), euro), metre)


def test_a_bare_number_raises_even_against_dimensionless():
    """The ruling, and the reason for it: once ratios are dimensionless, a
    bare 0.03 passing as "dimensionless" would wave through the very case the
    check exists to catch."""
    from clausal.terms import UnitsMismatch
    from clausal.modules.countries.european_union import euro
    from clausal.modules.units import dimensionless
    for unit in (euro, dimensionless):
        with pytest.raises(UnitsMismatch, match="carries no unit"):
            _compat(5, unit)
    with pytest.raises(UnitsMismatch, match="carries no unit"):
        _compat(0.03, dimensionless)


def test_a_dimensionless_QUANTITY_is_compatible_with_dimensionless():
    """The negative control for the rule above: the objection is to a bare
    NUMBER, not to a dimensionless quantity. A ratio built by division is
    exactly that, and it must pass."""
    from clausal.modules.countries.european_union import euro
    from clausal.modules.units import dimensionless
    ratio = Quantity(Decimal("10"), euro) / Quantity(Decimal("4"), euro)
    assert dict(ratio.dims) == {}
    assert _compat(ratio, dimensionless) is True


def test_two_currencies_are_not_compatible():
    from clausal.terms import UnitsMismatch
    from clausal.modules.countries.european_union import euro
    from clausal.modules.countries.united_states import usd
    with pytest.raises(UnitsMismatch):
        _compat(Quantity(Decimal("5.00"), euro), usd)


def test_compatible_units_same_named_currencies_are_distinguished():
    """A second message path is a second chance to say "dollar vs dollar".

    `_require_same_dims` learned this morning to qualify two sides that
    render identically; this predicate builds its own message and reproduced
    the defect immediately. The fix is to REUSE that logic, not to write a
    second copy of it (corpus-lane found the original, 2026-09-11)."""
    from clausal.terms import UnitsMismatch
    from clausal.modules.countries.australia import aud
    from clausal.modules.countries.united_states import usd
    with pytest.raises(UnitsMismatch) as exc:
        _compat(Quantity(Decimal("5"), aud), usd)
    text = str(exc.value)
    assert "expected usd" in text and "got aud" in text, text


def test_compatible_units_raises_rather_than_fails_in_clausal(tmp_path):
    """The whole reason it exists: in a goal position `has_units/2` FAILING
    is swallowed, and the caller gets "no" instead of a diagnosis. This
    aborts the query, and `catch/3` binds the message — the documented
    contract for UnitsMismatch."""
    from clausal.logic.exceptions import LogicException
    m = _load(tmp_path, "compat", """
        -module(compat, [ok/0, bad/0, caught/1])
        -import_from(py.units, [compatible_units])
        -import_from(european_union, [euro])
        -import_from(united_states, [usd])
        -import_from(clausal.terms, [UnitsMismatch])

        ok  <- (eval_(5.00(euro), A), compatible_units(A, euro))
        bad <- (eval_(5.00(euro), A), compatible_units(A, usd))
        caught(M) <- catch((eval_(5.00(euro), A), compatible_units(A, usd)),
                           ++UnitsMismatch(M), 1 == 1)
    """)
    mod = m.__dict__["$module"]
    assert len(list(call("ok", module=mod))) == 1
    with pytest.raises(LogicException):
        list(call("bad", module=mod))
    v = Var()
    [msg] = [deref(v) for _ in call("caught", v, module=mod)]
    assert "expected" in str(msg) and "euro" in str(msg), msg


# ── currency_code/2 as a relation, and the accessors that failed open ────────
#
# Measured before building, all three by execution:
#
#     currency_code(euro, X)      -> 'EUR'           forward works
#     currency_code(C, "EUR")     -> NO SOLUTIONS    silent
#     currency_code(C, ++"EUR")   -> NO SOLUTIONS    silent
#     currency_scale(C_UNUSED, S) -> NO SOLUTIONS    silent
#
# and no code->currency path existed anywhere. one e-invoicing domain carries
# its currency as RUNTIME DATA (`currency: eur`) and cannot attach units to
# its twelve money fields without one. Its BR-CO total-consistency rules
# therefore cannot detect a mixed-currency invoice; under units they would
# (corpus-lane, who built the data shape and measured it).
#
# The third defect is the one that shaped this: `"EUR"` written in a rulebase
# is an ATOM, `iso_code` is a Python STRING, and they do not unify — so even
# the forward CHECK was a trap, and <downstream-domain> writes a third spelling (`eur`)
# again. Operator, 2026-09-11: one relation, accepting either spelling.


def _codes(module, goal, arity=1):
    vs = [Var() for _ in range(arity)]
    return [tuple(deref(v) for v in vs) for _ in
            call(goal, *vs, module=module.__dict__["$module"])]


def test_a_code_binds_its_currency_in_every_spelling(tmp_path):
    """`eur` is <downstream-domain>'s spelling, `"EUR"` the one a reader writes, `++"EUR"`
    the Python string. All three must reach the same currency."""
    m = _load(tmp_path, "code_rev", """
        -double_quotes(atom)
        -module(code_rev, [lower/1, upper/1, pystr/1])
        -implicit_atoms
        -import_from(currency, [currency_code])

        lower(C) <- currency_code(C, eur)
        upper(C) <- currency_code(C, "EUR")
        pystr(C) <- currency_code(C, ++"EUR")
    """)
    from clausal.modules.countries.european_union import euro
    for goal in ("lower", "upper", "pystr"):
        assert _codes(m, goal) == [(euro,)], goal


def test_the_forward_direction_is_unchanged(tmp_path):
    """Nothing that works today may break: it still answers the canonical
    uppercase string."""
    m = _load(tmp_path, "code_fwd", """
        -module(code_fwd, [code/1])
        -import_from(currency, [currency_code])
        -import_from(european_union, [euro])

        code(X) <- currency_code(euro, X)
    """)
    assert _codes(m, "code") == [(chars("EUR"),)]


def test_an_unknown_code_fails_rather_than_raising(tmp_path):
    """No such pair is an ordinary "no". Raising would make a lookup
    unusable as a test."""
    m = _load(tmp_path, "code_no", """
        -module(code_no, [nope/1])
        -implicit_atoms
        -import_from(currency, [currency_code])

        nope(C) <- currency_code(C, zzz)
    """)
    assert _codes(m, "nope") == []


def test_both_unbound_enumerates_the_whole_vocabulary(tmp_path):
    """Enumeration yields ALL 254, historical included, because the relation
    must be complete: `currency_code(dem_currency, X)` answers forward, so
    the reverse and the enumeration have to reach it too. "Is this a CURRENT
    currency" is a different question — `currency_end/2` answers it — and
    conflating them would make this relation asymmetric."""
    from clausal.modules.countries import _data
    m = _load(tmp_path, "code_enum", """
        -module(code_enum, [pair/2])
        -import_from(currency, [currency_code])

        pair(C, Code) <- currency_code(C, Code)
    """)
    rows = _codes(m, "pair", 2)
    assert len(rows) == len(_data.CURRENCIES) == 254
    codes = {chars_text(r[1]) for r in rows}
    assert "EUR" in codes and "DEM" in codes, "historical are reachable"


def test_an_accessor_RAISES_on_an_unbound_currency(tmp_path):
    """The fail-open shape: these are functions of a currency, and a silent
    no-solution at a boundary is how a typo'd field becomes "no answer"."""
    from clausal.logic.exceptions import LogicException
    m = _load(tmp_path, "acc_unbound", """
        -module(acc_unbound, [scale/1, symbol/1])
        -import_from(currency, [currency_scale, currency_symbol])

        scale(S)  <- currency_scale(C_UNUSED, S)
        symbol(S) <- currency_symbol(C_UNUSED, S)
    """)
    for goal in ("scale", "symbol"):
        with pytest.raises(LogicException):
            _codes(m, goal)


def test_the_accessors_still_work_when_bound(tmp_path):
    """The negative control for the raise above."""
    m = _load(tmp_path, "acc_ok", """
        -module(acc_ok, [scale/1])
        -import_from(currency, [currency_scale])
        -import_from(european_union, [euro])

        scale(S) <- currency_scale(euro, S)
    """)
    assert _codes(m, "scale") == [(2,)]


# ── number/1 accepts a quantity; quantity/1 says it explicitly ───────────────
#
# The most dangerous thing found this session, and it was found by building
# the migration rather than by reading it (corpus-lane, 2026-09-11). <downstream-domain>
# guards every money field with `number(V)` in `sum_field/3`, documented as
# "a member whose KEY is absent or non-numeric contributes nothing... empty
# list -> 0". Measured before the fix:
#
#     total, guard number/1, bare money    -> 10000
#     total, guard number/1, united money  -> 0        SILENTLY
#
# So attaching units to <downstream-domain>'s twelve money fields would make every total
# zero, every BR-CO consistency rule compare 0 against 0, and the domain's
# entire conformance surface vacuously TRUE with a green suite.
#
# Operator's ruling: a Quantity IS a number carrying a unit. Guards pass it
# through, and the failure mode inverts — code that guards and then does BARE
# arithmetic raises UnitsMismatch instead of quietly summing zero.


def test_number_accepts_a_quantity(tmp_path):
    m = _load(tmp_path, "numq", """
        -module(numq, [money_q/0, physical_q/0, plain/0])
        -import_from(currency, [money])
        -import_from(european_union, [euro])
        -import_from(py.units, [metre])

        money_q    <- (money(10000, euro, Q), number(Q))
        physical_q <- (eval_(5 (metre), Q), number(Q))
        plain      <- number(10000)
    """)
    mod = m.__dict__["$module"]
    for goal in ("money_q", "physical_q", "plain"):
        assert len(list(call(goal, module=mod))) == 1, goal


def test_a_guarded_total_no_longer_drops_money_to_zero(tmp_path):
    """The failure this exists to prevent, end to end."""
    m = _load(tmp_path, "guarded", """
        -module(guarded, [total/1])
        -import_from(currency, [money])
        -import_from(european_union, [euro])

        amount(Q) <- money(10000, euro, Q)
        total(S)  <- (findall(V, (amount(V), number(V)), L), sum_list(L, S))
    """)
    from clausal.modules.countries.european_union import euro
    v = Var()
    [total] = [deref(v) for _ in call("total", v, module=m.__dict__["$module"])]
    assert total.value == Decimal("10000") and total.dims == {"euro": 1}


def test_integer_and_float_stay_STRICT(tmp_path):
    """`number` means numeric-valued; `integer`/`float_` name a specific ISO
    representation, and a Quantity is neither. Widening those too would make
    `integer(V)` — which is how a rulebase asserts minor-unit scale — silently
    true for an amount in any scale at all."""
    m = _load(tmp_path, "strictint", """
        -module(strictint, [as_int/0, as_float/0])
        -import_from(currency, [money])
        -import_from(european_union, [euro])

        as_int   <- (money(10000, euro, Q), integer(Q))
        as_float <- (money(10000, euro, Q), float_(Q))
    """)
    mod = m.__dict__["$module"]
    for goal in ("as_int", "as_float"):
        assert list(call(goal, module=mod)) == [], goal


def test_a_guard_followed_by_BARE_arithmetic_raises(tmp_path):
    """Why accepting is safe rather than merely convenient: the case a guard
    was protecting now fails LOUDLY instead of silently summing zero."""
    # 2026-09-12: a comparison goes through the units side channel, which
    # throws the ISO 13211 term error(system_error(units_mismatch), Ctx)
    # (spec docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md)
    # — still LOUD, and now selectable by catch/3.
    from clausal.logic.atoms import mint
    from clausal.logic.exceptions import LogicException
    m = _load(tmp_path, "bare_arith", """
        -module(bare_arith, [cmp/0])
        -import_from(currency, [money])
        -import_from(european_union, [euro])

        cmp <- (money(10000, euro, Q), number(Q), Q > 0)
    """)
    with pytest.raises(LogicException) as ei:
        list(call("cmp", module=m.__dict__["$module"]))
    inner = ei.value.term.args[0]
    assert inner.functor == "system_error" and inner.args[0] == mint("units_mismatch")


def test_quantity_1_is_the_affirmative_test(tmp_path):
    m = _load(tmp_path, "quant1", """
        -module(quant1, [yes/0, no_plain/0, no_atom/0])
        -implicit_atoms
        -import_from(currency, [money])
        -import_from(european_union, [euro])

        yes      <- (money(10000, euro, Q), quantity(Q))
        no_plain <- quantity(10000)
        no_atom  <- quantity(foo)
    """)
    mod = m.__dict__["$module"]
    assert len(list(call("yes", module=mod))) == 1
    assert list(call("no_plain", module=mod)) == []
    assert list(call("no_atom", module=mod)) == []


def test_number_still_refuses_what_it_always_refused(tmp_path):
    """The negative control: widening to quantities must not widen to
    anything else."""
    m = _load(tmp_path, "numneg", """
        -module(numneg, [an_atom/0, a_bool/0, a_list/0])
        -implicit_atoms

        an_atom <- number(foo)
        a_bool  <- number(true)
        a_list  <- number([1, 2])
    """)
    mod = m.__dict__["$module"]
    for goal in ("an_atom", "a_bool", "a_list"):
        assert list(call(goal, module=mod)) == [], goal


def test_sum_list_sums_quantities(tmp_path):
    """`number/1` passing quantities through is only half the chain: the
    aggregate has to add them. Python's `sum()` seeds with a bare 0, so
    `0 + Quantity` raised — loud rather than silent, but it left <downstream-domain>'s
    totals unbuildable. Seeding from the first element fixes it and keeps
    every other case identical."""
    from clausal.modules.countries.european_union import euro
    m = _load(tmp_path, "sumq", """
        -module(sumq, [money_total/1, plain_total/1, empty_total/1])
        -import_from(currency, [money])
        -import_from(european_union, [euro])

        money_total(S) <- (money(10000, euro, A), money(2500, euro, B),
                           sum_list([A, B], S))
        plain_total(S) <- sum_list([1, 2, 3], S)
        empty_total(S) <- sum_list([], S)
    """)
    mod = m.__dict__["$module"]

    def one(goal):
        v = Var()
        [r] = [deref(v) for _ in call(goal, v, module=mod)]
        return r

    total = one("money_total")
    assert total.value == Decimal("12500") and total.dims == {"euro": 1}
    assert one("plain_total") == 6
    assert one("empty_total") == 0


def test_summing_mixed_currencies_raises(tmp_path):
    """The property that makes <downstream-domain>'s BR-CO rules worth uniting: a
    mixed-currency invoice cannot total silently."""
    from clausal.terms import UnitsMismatch
    m = _load(tmp_path, "summix", """
        -module(summix, [bad/1])
        -import_from(currency, [money])
        -import_from(european_union, [euro])
        -import_from(united_states, [usd])

        bad(S) <- (money(1, euro, A), money(1, usd, B), sum_list([A, B], S))
    """)
    with pytest.raises(UnitsMismatch):
        v = Var()
        list(call("bad", v, module=m.__dict__["$module"]))


# ── reflected operands: 5 + money must say what money + 5 says ───────────────
#
# Asked whether UnitsMismatch subclasses TypeError (it does not — it derives
# from Exception), which exposed what the old sum_list was really catching:
# `Quantity.__radd__` returns NotImplemented for a bare number, so PYTHON
# raises `unsupported operand type(s)`, and that plain TypeError became
# `type_error(number, <Quantity>)` — naming the quantity as the offender, and
# now self-contradictory, since `number/1` says a Quantity IS a number.


def test_reflected_add_and_subtract_raise_the_same_as_forward():
    from clausal.terms import UnitsMismatch
    from clausal.modules.countries.european_union import euro
    q = Quantity(Decimal("5"), euro)
    with pytest.raises(UnitsMismatch, match="Cannot add"):
        5 + q
    with pytest.raises(UnitsMismatch, match="Cannot subtract"):
        5 - q


def test_scaling_by_a_bare_number_still_works():
    """The negative control: multiplying a quantity by a dimensionless number
    is legal in both orders and must not be swept up."""
    from clausal.modules.countries.european_union import euro
    q = Quantity(Decimal("5"), euro)
    assert (5 * q).value == Decimal("25")
    assert (q * 5).value == Decimal("25")


def test_a_dimensionless_quantity_still_adds_to_a_bare_number():
    """The other negative control: the fast path that made __radd__ return a
    value rather than NotImplemented."""
    from clausal.modules.units import dimensionless
    assert (5 + Quantity(2, dimensionless)).value == 7
    assert (5 - Quantity(2, dimensionless)).value == 3


def test_an_unrelated_type_still_gets_pythons_TypeError():
    """NotImplemented must survive for types the protocol should handle: only
    a NUMBER meeting a dimensioned quantity is a units error."""
    from clausal.modules.countries.european_union import euro
    with pytest.raises(TypeError):
        "a" + Quantity(Decimal("5"), euro)


def test_sum_list_reports_the_same_error_in_either_order(tmp_path):
    """The defect this fixes, at the level it was found: `[1, Q]` used to give
    `type_error(number, <Quantity>)` while `[Q, 1]` gave UnitsMismatch."""
    from clausal.terms import UnitsMismatch
    m = _load(tmp_path, "ordsum", """
        -module(ordsum, [money_first/1, bare_first/1])
        -import_from(currency, [money])
        -import_from(european_union, [euro])

        money_first(S) <- (money(1, euro, Q), sum_list([Q, 1], S))
        bare_first(S)  <- (money(1, euro, Q), sum_list([1, Q], S))
    """)
    mod = m.__dict__["$module"]
    for goal in ("money_first", "bare_first"):
        with pytest.raises(UnitsMismatch, match="Cannot add"):
            v = Var()
            list(call(goal, v, module=mod))


def test_the_inline_refusal_names_the_directive_that_was_WRITTEN():
    """A diagnostic must not name something the source does not contain.

    The refusal hardcoded `-constant_number_units` even when the author wrote
    `-constant_number_currency`, sending them to look for a directive that is
    not in their file (iso-export-lane, 2026-09-11).

    Retargeted 2026-09-13: the DECLARATION path no longer refuses at all (it
    converts), so this now guards the INLINE path, which still refuses and
    still has to name what was written. The claim is unchanged; only the
    surface that can violate it has moved.
    """
    for unit in ("aud_cent", "usd_cent"):
        with pytest.raises(NotImplementedError) as exc:
            _export(f"-import_from(australia, [aud, aud_cent])\n"
                    f"-import_from(united_states, [usd, usd_cent])\n"
                    f"pay(200000000({unit})),\n")
        assert unit in str(exc.value), str(exc.value)


def test_sum_list_still_accepts_every_numeric_kind(tmp_path):
    """REGRESSION, found on canonical by the harness lane's answer diff.

    `06290b23` added pre-validation to `sum_list/2` so that a single
    non-numeric element could not be returned unchanged by the new
    first-element seeding. The predicate it validated with was
    `isinstance(v, (int, float))` — which excludes `Fraction` and `Decimal`,
    both of which the old `sum()` accepted because they simply add.

    It surfaced as `type_error(number, Fraction(49...))` on one domain, at
    SOLVE time rather than load time, on the axis I ranked second while
    predicting zero. `Decimal` is the worse half and nothing caught it: it is
    the magnitude of every currency amount, so any rulebase summing stripped
    money would have raised.
    """
    from fractions import Fraction
    m = _load(tmp_path, "numkinds", """
        -double_quotes(atom)
        -module(numkinds, [fracs/1, decs/1, ints/1])

        fracs(S) <- sum_list([++__import__("fractions").Fraction(1, 2),
                              ++__import__("fractions").Fraction(1, 3)], S)
        decs(S)  <- sum_list([++__import__("decimal").Decimal("1.10"),
                              ++__import__("decimal").Decimal("2.20")], S)
        ints(S)  <- sum_list([1, 2, 3], S)
    """)
    mod = m.__dict__["$module"]

    def one(goal):
        v = Var()
        [r] = [deref(v) for _ in call(goal, v, module=mod)]
        return r

    assert one("fracs") == Fraction(5, 6)
    assert one("decs") == Decimal("3.30")
    assert one("ints") == 6


def test_sum_list_still_rejects_a_genuine_non_number(tmp_path):
    """The negative control: the pre-validation exists so a one-element list
    of a non-number is not returned unchanged by the seeding. Widening it back
    must not remove that."""
    from clausal.logic.exceptions import LogicException
    m = _load(tmp_path, "notnum", """
        -module(notnum, [bad/1])
        -implicit_atoms

        bad(S) <- sum_list([foo], S)
    """)
    with pytest.raises(LogicException, match="type_error"):
        v = Var()
        list(call("bad", v, module=m.__dict__["$module"]))
