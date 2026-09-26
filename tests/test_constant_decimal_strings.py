"""A STRING in the number position of the constants family is an exact Decimal.

Operator's ruling, 2026-09-12: `-constant_number_units(fee, "292.00", usd)`.

**The gap it closes, measured before building it.** A written `292.00` is a
Python FLOAT literal, and it loses its trailing zero before any `Quantity`
exists -- `-constant_number_units(fee, 292.00, usd)` stores
`Decimal('292.0')`. The scale a statute wrote is gone by the time the engine
sees the value, and no amount of care downstream can recover it. A string
literal carries the digits verbatim, so `Decimal("292.00")` keeps the scale.

That makes this the counterpart of minor units, reached from the other side:
minor units let a statutory "29200 cents" stay recoverable by declaring the
SCALE; a decimal string lets a statutory "292.00 dollars" stay exact by
declaring the DIGITS.

Applies to all four members of the family -- the two single-value directives
and the two table ones -- because statutory amounts mostly live in tables and
the gap bites hardest there.
"""
import textwrap
from decimal import Decimal

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tcds_{name}", str(path))


def _rows(module, goal, arity):
    vs = [Var() for _ in range(arity)]
    return [tuple(deref(v) for v in vs) for _ in
            call(goal, *vs, module=module.__dict__["$module"])]


# ── the feature, stated as the difference it makes ───────────────────────────


def test_a_decimal_string_keeps_the_scale_a_float_literal_loses(tmp_path):
    """THE test. Both declarations say "292.00"; only one of them still says
    so once the engine holds it. If the conversion were wrong in a way that
    produced the right NUMBER, every other test here would still pass."""
    m = _load(tmp_path, "scale", """
        -double_quotes(atom)
        -import_from(united_states, [usd])
        -constant_number_units(s_from_string, "292.00", usd)
        -constant_number_units(s_from_float, 292.00, usd)
    """)
    assert str(m.s_from_string.value) == "292.00"      # scale preserved
    assert str(m.s_from_float.value) == "292.0"        # scale already lost
    assert m.s_from_string.value == m.s_from_float.value   # same NUMBER


def test_the_string_form_stores_a_decimal_not_a_string(tmp_path):
    m = _load(tmp_path, "kind", """
        -double_quotes(atom)
        -import_from(united_states, [usd])
        -constant_number_units(s_fee, "19.99", usd)
    """)
    from clausal.modules.countries.united_states import usd
    assert isinstance(m.s_fee.value, Decimal)
    assert m.s_fee.value == Decimal("19.99")
    assert m.s_fee.dims == {"usd": 1}


def test_the_currency_directive_takes_it_too(tmp_path):
    m = _load(tmp_path, "currency", """
        -double_quotes(atom)
        -import_from(united_states, [usd])
        -constant_number_currency(s_sga, "1550.00", usd)
    """)
    assert str(m.s_sga.value) == "1550.00"


def test_a_non_currency_unit_takes_it_too(tmp_path):
    """A string is an explicit request for exactness, whatever the dimension
    -- it is not a currency special case."""
    m = _load(tmp_path, "metre", """
        -double_quotes(atom)
        -import_from(py.units, [metre])
        -constant_number_units(s_span, "5.00", metre)
    """)
    assert str(m.s_span.value) == "5.00"


def test_slash_3_reports_the_decimal_not_the_string(tmp_path):
    """The /3 channel reports the DECLARED magnitude, and the declared
    magnitude is the Decimal -- the string is how it was spelled, not what
    was declared.

    The constant has a name used nowhere else in this file on purpose:
    `constant_number_units/3` is registered per module but NOT filtered by
    module at query time, so two modules declaring one name make it answer
    twice. Filed as todo/constant-number-units-3-answers-across-modules.
    """
    m = _load(tmp_path, "declared", """
        -double_quotes(atom)
        -module(declared, [look/2, s_declared_fee])
        -import_from(united_states, [usd])
        -constant_number_units(s_declared_fee, "292.00", usd)

        look(N, U) <- constant_number_units(s_declared_fee, N, U)
    """)
    vs = [Var(), Var()]
    rows = [tuple(deref(v) for v in vs) for _ in
            call("look", *vs, module=m.__dict__["$module"])]
    assert len(rows) == 1
    n, u = rows[0]
    assert n == Decimal("292.00") and not isinstance(n, str)
    assert u == ("usd",)


# ── the table half, where most statutory money lives ─────────────────────────


def test_a_money_table_takes_decimal_strings(tmp_path):
    m = _load(tmp_path, "table_money", """
        -double_quotes(atom)
        -module(table_money, [s_max/2])
        -import_from(united_states, [usd])
        -constants_number_currency(s_max/2,
                                   [(1, "292.00"), (2, "536.00")],
                                   usd, money_at(2))
    """)
    rows = _rows(m, "s_max", 2)
    assert [str(v.value) for _, v in rows] == ["292.00", "536.00"]


def test_a_units_table_takes_decimal_strings(tmp_path):
    m = _load(tmp_path, "table_units", """
        -double_quotes(atom)
        -module(table_units, [s_span/2])
        -import_from(py.units, [metre])
        -constants_number_units(s_span/2, [(short, "5.00")], metre,
                                number_at(2))
        -private([short])
    """)
    rows = _rows(m, "s_span", 2)
    assert [str(v.value) for _, v in rows] == ["5.00"]


def test_a_table_may_mix_written_numbers_and_strings(tmp_path):
    """Rows are independent: adopting the string form for the row that needs
    it does not force a rewrite of the rest of the table."""
    m = _load(tmp_path, "table_mixed", """
        -double_quotes(atom)
        -module(table_mixed, [s_mix/2])
        -import_from(united_states, [usd])
        -constants_number_currency(s_mix/2, [(1, "292.00"), (2, 536)], usd,
                                   money_at(2))
    """)
    rows = _rows(m, "s_mix", 2)
    assert [str(v.value) for _, v in rows] == ["292.00", "536"]


# ── what must STILL be refused ───────────────────────────────────────────────


def test_a_non_numeric_string_is_still_refused(tmp_path):
    """The gate is narrowed, not removed. `"abc"` is the case the directive's
    name exists to refuse -- only numbers carry units."""
    with pytest.raises(SyntaxError, match="is not a number"):
        _load(tmp_path, "bad", """
            -double_quotes(atom)
            -import_from(united_states, [usd])
            -constant_number_units(s_bad, "abc", usd)
        """)


def test_the_refusal_still_names_the_directive_and_the_value(tmp_path):
    with pytest.raises(SyntaxError) as exc:
        _load(tmp_path, "bad_msg", """
            -double_quotes(atom)
            -import_from(united_states, [usd])
            -constant_number_currency(s_bad2, "twelve", usd)
        """)
    assert "-constant_number_currency" in str(exc.value)
    assert "twelve" in str(exc.value)


@pytest.mark.parametrize("bad", ["Infinity", "NaN", "-Infinity"])
def test_decimal_special_values_are_not_amounts(tmp_path, bad):
    """`Decimal("NaN")` parses. It is not a sum of money, and accepting it
    would put a non-finite value where every downstream comparison silently
    answers False."""
    with pytest.raises(SyntaxError, match="is not a number"):
        _load(tmp_path, f"special_{bad.strip('-')}", f"""
            -double_quotes(atom)
            -import_from(united_states, [usd])
            -constant_number_units(s_inf, "{bad}", usd)
        """)


def test_a_table_still_refuses_a_non_numeric_string(tmp_path):
    with pytest.raises(SyntaxError, match="not a number literal"):
        _load(tmp_path, "table_bad", """
            -double_quotes(atom)
            -module(table_bad, [s_t/2])
            -import_from(united_states, [usd])
            -constants_number_currency(s_t/2, [(1, "abc")], usd, money_at(2))
        """)


def test_constant_value_keeps_a_string_a_string(tmp_path):
    """`-constant_value` is NOT in the family this changes. It takes any
    value, and a string there is a string constant -- reading it as a number
    would silently retype every text constant in the corpus."""
    m = _load(tmp_path, "plain", """
        -double_quotes(atom)
        -constant_value(s_greeting, "292.00")
    """)
    assert m.s_greeting == "292.00"
    assert isinstance(m.s_greeting, str)


def test_the_currency_precision_check_still_applies(tmp_path):
    """Sub-scale digits are refused as before -- the check now runs against
    an exact Decimal instead of a float, which if anything makes it sharper."""
    with pytest.raises(Exception) as exc:
        _load(tmp_path, "precision", """
            -double_quotes(atom)
            -import_from(united_states, [usd])
            -constant_number_currency(s_over, "19.999", usd)
        """)
    assert "19.999" in str(exc.value) or "precision" in str(exc.value).lower()


def test_a_scale_named_constant_declared_as_a_string_is_silent(tmp_path):
    """Pinned as a DECISION rather than left as an accident: the scale lint
    keys on a bare numeric literal, so the string form does not trip it. That
    is right -- the site carries its unit, which is what the lint asks for --
    but it means the warning count falls for string migrations too."""
    from clausal.lint_warnings import ClausalScaleInNameWarning
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load(tmp_path, "scalename", """
            -double_quotes(atom)
            -import_from(united_states, [usd])
            -constant_number_units(s_fee_cents, "292.00", usd)
        """)
    assert not [w for w in caught
                if issubclass(w.category, ClausalScaleInNameWarning)]


# ── the chars-mode module (the -double_quotes default after the flip) ────────


def test_a_chars_mode_table_takes_decimal_strings(tmp_path):
    """Under ``-double_quotes(chars)`` a ``"292.00"`` row value arrives as the
    chars CARRIER ``('$chars', '292.00')``, not a bare str. The table path
    must read the digits through it -- measured 2026-09-26: rejecting the
    carrier made every currency/units table of decimal strings fail to load
    in a chars-mode module with ``('$chars', '292.00') is not a decimal
    number``."""
    m = _load(tmp_path, "chars_table", """
        -double_quotes(chars)
        -module(chars_table, [s_max/2, s_span/2])
        -import_from(united_states, [usd])
        -import_from(py.units, [metre])
        -constants_number_currency(s_max/2,
                                   [(1, "292.00"), (2, 536)],
                                   usd, money_at(2))
        -constants_number_units(s_span/2, [(short, "5.00")], metre,
                                number_at(2))
        -private([short])
    """)
    rows = _rows(m, "s_max", 2)
    assert [str(v.value) for _, v in rows] == ["292.00", "536"]
    rows = _rows(m, "s_span", 2)
    assert [str(v.value) for _, v in rows] == ["5.00"]


def test_a_chars_mode_single_value_takes_a_decimal_string(tmp_path):
    m = _load(tmp_path, "chars_single", """
        -double_quotes(chars)
        -import_from(united_states, [usd])
        -constant_number_currency(s_fee, "292.00", usd)
    """)
    assert str(m.s_fee.value) == "292.00"


def test_a_chars_mode_table_still_refuses_a_non_numeric_string(tmp_path):
    with pytest.raises(SyntaxError, match="is not a number"):
        _load(tmp_path, "chars_bad", """
            -double_quotes(chars)
            -import_from(united_states, [usd])
            -constants_number_currency(s_bad/2, [(1, "abc")], usd,
                                       money_at(2))
        """)
