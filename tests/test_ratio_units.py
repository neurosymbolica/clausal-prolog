"""Ratio units — `percent` and `basis_point` as dimensionless scaled units.

Filed as todo/ratio-declaration-units-basis-points-and-percent-2026-09-11.md
and built 2026-09-12. The same shape minor currency units already proved:

    basis_point = Quantity(Decimal('0.0001'), {})

an ordinary scaled unit, against the DIMENSIONLESS base rather than a
currency, so it needs no special case in the directive, in the `300
(basis_point)` annotation sugar or in arithmetic.

What it buys is what the currency half bought: `constant_number_units/3`
reports the DECLARED pair, so a statutory "300 basis points" reads back as
300 basis points while the engine holds the ratio 0.03 — and a domain can
stop encoding the scale in its parameter NAMES, where only a human can read
it.

**Where the exactness comes from, measured 2026-09-12 and not what the todo
assumed.** It is NOT the currency coercion: `_to_decimal` is keyed on an
`is_currency` dimension and lives in the other `Quantity.__init__` branch,
which a scaled unit returns before reaching. It is `_num_pair`, which is
dimension-agnostic and reads a float beside a `Decimal` as `Decimal(str(f))`.
So the one load-bearing requirement is that the FACTOR is a `Decimal` —
exactly the property `_make_minor_unit` argues for, and the property
`gram = Quantity(1e-3, ...)` does not have.
"""
import os
import textwrap
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import Quantity


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tru_{name}", str(path))


def _one(module, goal, arity):
    vs = [Var() for _ in range(arity)]
    rows = [tuple(deref(v) for v in vs) for _ in
            call(goal, *vs, module=module.__dict__["$module"])]
    assert len(rows) == 1, f"{goal} had {len(rows)} solutions, expected 1"
    return rows[0]


# ── the units themselves ─────────────────────────────────────────────────────


def test_a_basis_point_is_a_dimensionless_scaled_unit():
    from clausal.modules.units import basis_point
    assert isinstance(basis_point, Quantity)
    assert dict(basis_point.dims) == {}
    assert basis_point.value == Decimal("0.0001")


def test_a_percent_is_a_dimensionless_scaled_unit():
    from clausal.modules.units import percent
    assert isinstance(percent, Quantity)
    assert dict(percent.dims) == {}
    assert percent.value == Decimal("0.01")


def test_every_ratio_factor_is_decimal_never_float():
    """The one load-bearing property, and the one `gram` does not have.

    `gram = Quantity(1e-3, {kilogram: 1})` carries a binary float, which is
    why `7 gram` is 0.007000000000000001-adjacent rather than exact. A ratio
    multiplies a rate against money and thresholds, so a float factor would
    put the same hazard on the comparison that decides a case. Built with
    `scaleb` rather than written as a literal, as `_make_minor_unit` is.
    """
    from clausal.modules import units
    for name in units.RATIO_UNITS:
        factor = getattr(units, name).value
        assert isinstance(factor, Decimal), (
            f"{name} carries a {type(factor).__name__} factor")


def test_every_declared_ratio_unit_is_bound_in_the_module():
    """Enumerate from the AUTHORITY, not from a list written beside it
    (the harness lane's rule, 2026-09-12). Adding a ratio unit to
    `RATIO_UNITS` and forgetting to bind it fails here rather than surfacing
    as a NameError in a rulebase.
    """
    from clausal.modules import units
    assert units.RATIO_UNITS, "positive control: the ratio table is not empty"
    for name, exponent in units.RATIO_UNITS.items():
        unit = getattr(units, name, None)
        assert unit is not None, (
            f"RATIO_UNITS names {name!r}, which the module does not bind")
        assert unit.value == Decimal(1).scaleb(-exponent), (
            f"{name} is bound at {unit.value}, not the declared 10**-{exponent}")


# ── what a rulebase can write ────────────────────────────────────────────────


def test_a_ratio_declaration_stores_the_plain_ratio(tmp_path):
    """One representation, as with minor units: after declaration it IS the
    ratio 0.03, which is what makes it multiply against money with no
    conversion logic anywhere."""
    m = _load(tmp_path, "store", """
        -import_from(py.units, [basis_point])
        -constant_number_units(ru_min_leverage, 300, basis_point)
    """)
    assert m.ru_min_leverage.value == Decimal("0.0300")
    assert isinstance(m.ru_min_leverage.value, Decimal)
    assert dict(m.ru_min_leverage.dims) == {}


def test_the_declared_ratio_pair_is_what_slash_3_reports(tmp_path):
    """The recoverability that makes the migration worth doing: a statutory
    "300 basis points" reads back as 300 basis points, so a domain can stop
    spelling the scale into `minimum_leverage_bps`."""
    m = _load(tmp_path, "declared", """
        -module(declared, [look/2, ru_floor])
        -import_from(py.units, [basis_point])
        -constant_number_units(ru_floor, 300, basis_point)

        look(N, U) <- constant_number_units(ru_floor, N, U)
    """)
    assert _one(m, "look", 2) == (300, ("basis_point",))


def test_a_float_ratio_magnitude_does_not_go_binary(tmp_path):
    """`5.25 percent` is exactly 0.0525, not 0.052500000000000005.

    The property measured 2026-09-12: a float magnitude beside a `Decimal`
    factor is read through `Decimal(str(f))` by `_num_pair`. This is the test
    that fails if someone writes the factor as `1e-2`.
    """
    m = _load(tmp_path, "float", """
        -import_from(py.units, [percent])
        -constant_number_units(ru_rate, 5.25, percent)
    """)
    assert m.ru_rate.value == Decimal("0.0525")
    assert isinstance(m.ru_rate.value, Decimal)


def test_three_hundred_basis_points_is_three_percent(tmp_path):
    """Both dimensionless, both normalise, so they are the SAME quantity --
    which is what makes a domain free to declare in whichever the statute
    uses."""
    m = _load(tmp_path, "same", """
        -module(same, [both/2])
        -import_from(py.units, [basis_point, percent])

        both(A, B) <- (eval_(300 (basis_point), A), eval_(3 (percent), B))
    """)
    a, b = _one(m, "both", 2)
    assert a.value == b.value
    assert a.value == Decimal("0.03")


def test_a_ratio_of_money_is_money(tmp_path):
    """The shape a leverage-ratio domain needs: a ratio applied to an amount
    keeps the amount's dimension and its exact decimal magnitude."""
    m = _load(tmp_path, "ofmoney", """
        -module(ofmoney, [charge/1])
        -import_from(py.units, [basis_point])
        -import_from(united_states, [usd])

        charge(C) <- eval_(300 (basis_point) * 1550.00 (usd), C)
    """)
    from clausal.modules.countries.united_states import usd
    (c,) = _one(m, "charge", 1)
    assert c.value == Decimal("46.50")
    assert dict(c.dims) == {"usd": 1}


def test_a_ratio_does_not_add_to_a_dimensioned_amount(tmp_path):
    """Dimensionless is a dimension like any other here: the guard that stops
    euro meeting dollar stops a bare ratio meeting money."""
    from clausal.terms import UnitsMismatch
    m = _load(tmp_path, "noadd", """
        -module(noadd, [bad/1])
        -import_from(py.units, [percent])
        -import_from(united_states, [usd])

        bad(X) <- eval_(3 (percent) + 10 (usd), X)
    """)
    with pytest.raises(UnitsMismatch):
        _one(m, "bad", 1)


# ── the Prolog exporter ──────────────────────────────────────────────────────
#
# A ratio unit is a SCALED unit, so both of the 2026-09-11 refusals apply to
# it — and one of them was blind to it. `_is_known_scaled_unit` selected
# `isinstance(v, Quantity) and v.dims`, and `and v.dims` excludes exactly the
# shape a ratio unit has. The clause excluded NOTHING on the day it was
# written (there were no dimensionless Quantity constants), so nothing could
# notice it; ratio units are the first values it is wrong about. Measured
# blind with a positive control before the fix, 2026-09-12.
#
# It matters here more than for `cent`: dropping `basis_point` from
# `300(basis_point)` emits 300 against a stored 0.03, a 10000x error, and
# the leverage-ratio domain that motivated ratio units is on the
# export roster.


def _export(src):
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    return clausal_source_to_prolog(src)


def test_the_exporter_refuses_an_inline_quantity_in_a_ratio_unit():
    with pytest.raises(NotImplementedError, match="scaled unit"):
        _export("-import_from(py.units, [basis_point])\n"
                "floor(300(basis_point)),\n")


def test_a_ratio_unit_declaration_exports_the_BASE_magnitude():
    """Was a refusal until 2026-09-13 (option 3). The hazard it guarded is
    unchanged and is what this asserts: `300 basis_point` is the ratio 0.03,
    and emitting 300 would be a 10000x error."""
    out = _export("-import_from(py.units, [basis_point])\n"
                  "-constant_number_units(ru_floor, 300, basis_point)\n"
                  "floor(constant(ru_floor)),\n")
    assert "floor(0.03" in out, out
    assert "floor(300)" not in out


def test_every_declared_ratio_unit_is_refused_inline():
    """Enumerated from the authority, so a ratio unit added later cannot slip
    past the refusal by not being listed here."""
    from clausal.modules.units import RATIO_UNITS
    assert RATIO_UNITS, "positive control: the ratio table is not empty"
    for name in RATIO_UNITS:
        with pytest.raises(NotImplementedError, match="scaled unit"):
            _export(f"-import_from(py.units, [{name}])\n"
                    f"rate(7({name})),\n")


# ── the scale-in-a-name lint ─────────────────────────────────────────────────
#
# The lint's suffix set is a DECLARED UNION: a half derived from the
# vocabulary (which answers "does this conform to what exists now") and a
# hand-maintained half for spellings the vocabulary does NOT hold (which
# answers the residue question, about words the authority has forgotten).
# Ratio words sat in the hand half with a comment saying they move across
# when ratios become units. This is the move, and the union's own overlap
# assertion is what refuses to let the hand half keep them.


def _suffixes():
    from clausal.templating.term_rewriting import _scale_suffixes
    return _scale_suffixes()


def test_the_ratio_vocabulary_reaches_the_lint():
    """Derived, not listed: `basis_point` singular is a suffix now because
    the unit exists, and nothing had to be written down for it."""
    assert "basis_point" in _suffixes()
    assert "percent" in _suffixes()


def test_every_ratio_unit_name_is_a_scale_suffix():
    """Enumerated from the authority, so a ratio unit added to RATIO_UNITS
    extends the lint with no second edit."""
    from clausal.modules.units import RATIO_UNITS
    assert RATIO_UNITS, "positive control: the ratio table is not empty"
    missing = [n for n in RATIO_UNITS if n not in _suffixes()]
    assert not missing, f"{missing} name a ratio unit the lint cannot see"


def test_the_abbreviations_stay_hand_maintained():
    """`bps` and `pct` are not unit names and never will be derived, so they
    remain the hand half's job -- which is the half's whole purpose, and the
    reason shrinking it is not the same as emptying it."""
    from clausal.templating.term_rewriting import _HAND_MAINTAINED_SCALE_WORDS
    assert {"bps", "pct"} <= _HAND_MAINTAINED_SCALE_WORDS
    assert "percent" not in _HAND_MAINTAINED_SCALE_WORDS
    assert "basis_points" not in _HAND_MAINTAINED_SCALE_WORDS


def test_a_bare_number_is_not_compatible_with_a_ratio_unit():
    """`compatible_units/2` refuses a bare number even against a
    dimensionless unit, and ratios are the case that rule exists for: once
    `basis_point` is dimensionless, a bare 0.03 would otherwise satisfy every
    ratio claim there is. Written into the docstring on 2026-09-11, with no
    ratio unit yet in existence to check it against -- this is that check.
    """
    from clausal.modules.units import basis_point, compatible_units_check
    from clausal.terms import UnitsMismatch
    with pytest.raises(UnitsMismatch):
        compatible_units_check(0.03, basis_point)
    assert compatible_units_check(Quantity(300, basis_point), basis_point)


def test_a_ratio_and_a_percent_satisfy_each_others_claim():
    """Scale is already applied by the time the check runs, so the two ratio
    units name one dimension and either declares the other's value."""
    from clausal.modules.units import basis_point, percent, compatible_units_check
    assert compatible_units_check(Quantity(300, basis_point), percent)
    assert compatible_units_check(Quantity(3, percent), basis_point)


def test_a_converted_ratio_site_silences_the_scale_lint(tmp_path):
    """The migration's progress signal: a name claiming a scale goes quiet
    once the value carries the unit, so the warning count falls as sites are
    converted. (It is evidence of progress, not a measure of it -- see the
    three known distortions in docs/currency.md.)"""
    from clausal.lint_warnings import ClausalScaleInNameWarning
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load(tmp_path, "quiet", """
            -import_from(py.units, [basis_point])
            floor_basis_point(300 (basis_point)),
        """)
    assert not [w for w in caught
                if issubclass(w.category, ClausalScaleInNameWarning)]


def test_an_unconverted_ratio_site_still_warns(tmp_path):
    """The positive control for the test above: the same name with a bare
    literal is exactly what the lint is for, so silence there would mean the
    scanner never reached the file rather than that the site was clean."""
    from clausal.lint_warnings import ClausalScaleInNameWarning
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load(tmp_path, "loud", """
            floor_basis_point(300),
        """)
    assert [w for w in caught
            if issubclass(w.category, ClausalScaleInNameWarning)]


# ── the lint must not drag the units module into every load ──────────────────


def test_transforming_a_unit_free_file_does_not_import_the_units_module():
    """`clausal/logic/_units_flag.py` promises: "A program that imports no unit
    module pays nothing."

    Importing `clausal.modules.units` builds 84 `Quantity` constants at import
    time, and `Quantity.__init__` calls `_units_flag.touch()`. The flag is read
    at six sites in `clpfd.py` and four in `units_clp.py`, so switching it on
    makes every CLP program take the units side-channel branch — including
    programs with no units anywhere.

    The scale lint reads the ratio vocabulary on EVERY transform, so it must
    read it from a data-only module. This test failed when `_derived_scale_words`
    imported `clausal.modules.units` directly (2026-09-12); the ratio table moved
    to `clausal.modules._ratio_data`, which constructs nothing.

    Run in a subprocess because the flag is process-global and any earlier test
    in this file has already tripped it.
    """
    import subprocess
    import sys
    import textwrap
    probe = textwrap.dedent('''
        import sys, os, tempfile, pathlib
        sys.path.insert(0, os.getcwd())
        import clausal
        assert os.path.realpath(clausal.__file__).startswith(
            os.path.join(os.getcwd(), "")), clausal.__file__
        from clausal.import_hook import _load_module
        p = pathlib.Path(tempfile.mkdtemp()) / "plain.clausal"
        p.write_text("-private([a])\\nthing(a),\\nother(X) <- thing(X),\\n")
        _load_module("plain_probe_units_flag", str(p))
        from clausal.logic import _units_flag
        print("UNITS", "clausal.modules.units" in sys.modules)
        print("FLAG", _units_flag.active)
    ''')
    r = subprocess.run([sys.executable, "-c", probe], cwd=os.getcwd(),
                       capture_output=True, text=True)
    assert "UNITS" in r.stdout, f"probe did not run:\n{r.stdout}\n{r.stderr[-2000:]}"
    assert "UNITS False" in r.stdout, (
        "transforming a unit-free file imported clausal.modules.units, which "
        f"turns the CLP units side channel on for the whole process:\n{r.stdout}")
    assert "FLAG False" in r.stdout, (
        f"the units flag is active after a unit-free load:\n{r.stdout}")
