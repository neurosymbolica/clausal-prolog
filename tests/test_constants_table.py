"""`-constants_number_currency` — a TABLE of money, defining the predicate.

Operator's ruling, 2026-09-12. Most statutory money in downstream code is
in tables rather than single facts: indexed money rows far outnumber the
single-value constants migrated. One domain alone holds dozens of rows, and
it is stopped on this.

**Half of it already worked.** `-constant_value` accepts a structured RHS, so
a table declares fine as DATA — verified:

    -constant_value(tbl, [(1, 29200), (2, 53600)])
    row(K, V) <- in_((K, V), constant(tbl))    ->  [(1, 29200), (2, 53600)]

What failed is the only part that matters: a table could not carry a UNIT.
`-constant_value(tbl, [(1, 29200(usd_cent))])` is a SyntaxError, so a domain
could have its money in a declared table and still have nothing the engine
could check.

**The declaration DEFINES the predicate the rulebase already calls**
(operator's ruling), so a domain migrates by replacing N fact lines with one
declaration and NO call site changes. Binding a list instead would have turned
N rows into N edits plus a rewrite of every consumer.

**The money column is DECLARED, never inferred.** a downstream user's four real
shapes put it in arg 2 of 2, in arg 3 of 4, and inside a nested list, and one
carries a two-date validity window beside the amount. Any positional rule
would guess wrong on at least one shape, and guessing wrong is silent — which
is the failure this whole vocabulary exists to remove.
"""
import textwrap

import pytest

from decimal import Decimal

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tct_{name}", str(path))


def _rows(module, goal, arity):
    vs = [Var() for _ in range(arity)]
    return [tuple(deref(v) for v in vs) for _ in
            call(goal, *vs, module=module.__dict__["$module"])]


def test_the_declaration_defines_the_predicate(tmp_path):
    """The property the whole design turns on: existing call sites keep
    working, so a domain migrates by deleting fact lines."""
    m = _load(tmp_path, "defines", """
        -module(defines, [snap_max/2])
        -import_from(united_states, [usd, usd_cent])
        -constants_number_currency(snap_max/2,
                                   [(1, 29200), (2, 53600)],
                                   usd_cent, money_at(2))
    """)
    from clausal.modules.countries.united_states import usd
    rows = _rows(m, "snap_max", 2)
    assert [k for k, _ in rows] == [1, 2]
    assert [v.value for _, v in rows] == [Decimal("292.00"), Decimal("536.00")]
    assert all(v.dims == {"usd": 1} for _, v in rows)


def test_a_call_site_written_the_old_way_still_works(tmp_path):
    """Stated separately from the test above because it is the MIGRATION
    claim, not the definition claim: a rule that called the facts calls the
    declaration identically."""
    m = _load(tmp_path, "callsite", """
        -module(callsite, [allot/2])
        -import_from(united_states, [usd, usd_cent])
        -constants_number_currency(snap_max/2,
                                   [(1, 29200), (2, 53600)],
                                   usd_cent, money_at(2))

        allot(SIZE, A) <- snap_max(SIZE, A)
    """)
    rows = _rows(m, "allot", 2)
    assert [k for k, _ in rows] == [1, 2]


def test_money_at_names_a_column_other_than_the_last(tmp_path):
    """a downstream user's shape C: `threshold_entry(revenue, date, 2500000000,
    "s45A ...")` — money is arg 3 of 4, with a citation after it."""
    m = _load(tmp_path, "at3", """
        -double_quotes(atom)
        -module(at3, [entry/4])
        -private([revenue, assets])
        -import_from(united_states, [usd, usd_cent])
        -constants_number_currency(entry/4,
                                   [(revenue, 1900, 250000000000, "s45A"),
                                    (assets,  1900, 50000000000,  "s45B")],
                                   usd_cent, money_at(3))
    """)
    rows = _rows(m, "entry", 4)
    assert [r[0] for r in rows] == ["revenue", "assets"]
    assert [r[2].value for r in rows] == [Decimal("2500000000.00"),
                                          Decimal("500000000.00")]


def test_only_the_money_column_is_touched(tmp_path):
    """The negative control for `money_at`: every other cell arrives exactly
    as written, including one that is also an integer."""
    m = _load(tmp_path, "untouched", """
        -module(untouched, [row/3])
        -import_from(united_states, [usd, usd_cent])
        -constants_number_currency(row/3,
                                   [(1, 29200, 2016)],
                                   usd_cent, money_at(2))
    """)
    [(a, b, c)] = _rows(m, "row", 3)
    assert a == 1 and c == 2016, "the other integers are NOT quantities"
    assert b.value == Decimal("292.00")


def test_the_money_column_must_be_declared(tmp_path):
    """No positional default. Four real shapes put money in four places, and
    a rule that guesses is a rule that guesses SILENTLY."""
    with pytest.raises(SyntaxError, match="money_at"):
        _load(tmp_path, "nocol", """
            -import_from(united_states, [usd, usd_cent])
            -constants_number_currency(t/2, [(1, 29200)], usd_cent)
        """)


def test_a_column_index_out_of_range_is_refused(tmp_path):
    with pytest.raises(SyntaxError, match="money_at"):
        _load(tmp_path, "oob", """
            -import_from(united_states, [usd, usd_cent])
            -constants_number_currency(t/2, [(1, 29200)], usd_cent, money_at(5))
        """)


def test_a_row_of_the_wrong_width_is_refused(tmp_path):
    """The arity in the indicator is the contract; a row that does not match
    it would otherwise define a predicate of two different shapes."""
    with pytest.raises(SyntaxError, match="arity|width|column"):
        _load(tmp_path, "width", """
            -import_from(united_states, [usd, usd_cent])
            -constants_number_currency(t/2,
                                       [(1, 29200), (2, 53600, 99)],
                                       usd_cent, money_at(2))
        """)


def test_a_non_numeric_money_cell_is_refused(tmp_path):
    """Same claim the single-value form enforces: only numbers carry units."""
    with pytest.raises(SyntaxError, match="number"):
        _load(tmp_path, "nonnum", """
            -private([not_a_number])
            -import_from(united_states, [usd, usd_cent])
            -constants_number_currency(t/2,
                                       [(1, not_a_number)],
                                       usd_cent, money_at(2))
        """)


def test_the_unit_must_be_money(tmp_path):
    """The directive is named for its claim, as the single-value form is."""
    with pytest.raises(Exception, match="not an amount of money"):
        _load(tmp_path, "notmoney", """
            -import_from(py.units, [metre])
            -constants_number_currency(t/2, [(1, 5)], metre, money_at(2))
        """)


# ── the general-unit sibling ─────────────────────────────────────────────────
#
# The single-value family has two members — `-constant_number_units` for any
# unit, `-constant_number_currency` for money, the second named for the
# stricter claim it enforces. The table family mirrors it exactly, and the
# COLUMN keyword follows the same per-directive naming the family already
# uses for its third argument ("units" in one, "currency" in the other):
# `number_at(N)` for the general form, `money_at(N)` for the money one.


def test_the_units_form_takes_any_unit(tmp_path):
    m = _load(tmp_path, "units_tbl", """
        -module(units_tbl, [span/2])
        -import_from(py.units, [metre])
        -constants_number_units(span/2,
                                [(short, 5), (long, 900)],
                                metre, number_at(2))
        -private([short, long])
    """)
    rows = _rows(m, "span", 2)
    from clausal.modules.units import metre
    assert [r[0] for r in rows] == ["short", "long"]
    assert [r[1].value for r in rows] == [5, 900]
    assert all(r[1].dims == {"metre": 1} for r in rows)


def test_the_units_form_accepts_a_currency_too(tmp_path):
    """It is the general form: money is a unit. The currency form exists to
    enforce the stricter CLAIM, not because this one cannot hold money."""
    m = _load(tmp_path, "units_money", """
        -module(units_money, [fee/2])
        -import_from(united_states, [usd, usd_cent])
        -constants_number_units(fee/2, [(1, 29200)], usd_cent, number_at(2))
    """)
    [(k, v)] = _rows(m, "fee", 2)
    assert k == 1 and v.value == Decimal("292.00")


def test_the_units_form_does_not_demand_money(tmp_path):
    """The negative control that distinguishes the two directives: `metre`
    is refused by the currency form and accepted here."""
    from clausal.terms import UnitsMismatch
    with pytest.raises((UnitsMismatch, TypeError), match="not an amount of money"):
        _load(tmp_path, "cur_metre", """
            -import_from(py.units, [metre])
            -constants_number_currency(t/2, [(1, 5)], metre, money_at(2))
        """)
    m = _load(tmp_path, "unit_metre", """
        -module(unit_metre, [t/2])
        -import_from(py.units, [metre])
        -constants_number_units(t/2, [(1, 5)], metre, number_at(2))
    """)
    assert len(_rows(m, "t", 2)) == 1


def test_each_form_names_its_own_column_keyword(tmp_path):
    """`money_at` in the units form is as wrong as `number_at` in the money
    form — the keyword states which claim the directive is making."""
    with pytest.raises(SyntaxError, match="number_at"):
        _load(tmp_path, "wrongkw", """
            -import_from(py.units, [metre])
            -constants_number_units(t/2, [(1, 5)], metre, money_at(2))
        """)


# ── the scale lint must see a migrated table as migrated ─────────────────────
#
# The lint was designed to EMPTY as sites convert, and a falling count was
# offered as a better progress measure than counting edited files. A table
# declaration it does not recognise breaks exactly that: converting that domain's
# rows would move the count by ZERO, so the progress signal reads "nothing
# happened" on the largest migration downstream (a downstream user, 2026-09-12).
#
# The discriminator was right and the exemption was missing: the generated
# facts still carry bare numbers in their NON-money columns, so the rule fired
# on a row whose money column is a quantity.


def _scale_warnings(tmp_path, name, text):
    import warnings as _w
    from clausal.lint_warnings import ClausalScaleInNameWarning
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        _load(tmp_path, name, text)
    return [str(c.message) for c in caught
            if issubclass(c.category, ClausalScaleInNameWarning)]


def test_a_migrated_table_does_not_warn(tmp_path):
    assert _scale_warnings(tmp_path, "tbl_quiet", """
        -module(tbl_quiet, [snap_usd_cents/2])
        -import_from(united_states, [usd, usd_cent])
        -constants_number_currency(snap_usd_cents/2,
                                   [(1, 29200), (2, 53600)],
                                   usd_cent, money_at(2))
    """) == []


def test_a_hand_written_fact_carrying_a_unit_does_not_warn(tmp_path):
    """The general rule, not a special case for the directive: if a row
    carries a unit ANYWHERE, the scale is represented where the engine can
    check it, which is the whole thing the lint asks for."""
    assert _scale_warnings(tmp_path, "hand_quiet", """
        -module(hand_quiet, [fee_cents/2])
        -import_from(united_states, [usd, usd_cent])

        fee_cents(1, 29200 (usd_cent)),
    """) == []


def test_an_unmigrated_bare_fact_still_warns(tmp_path):
    """The negative control. Exempting the migrated case must not exempt the
    case the lint exists for."""
    w = _scale_warnings(tmp_path, "bare_warns", """
        -module(bare_warns, [snap_usd_cents/2])

        snap_usd_cents(1, 29200),
    """)
    assert len(w) == 1 and "snap_usd_cents" in w[0]


def test_a_units_table_does_not_warn_either(tmp_path):
    assert _scale_warnings(tmp_path, "units_quiet", """
        -module(units_quiet, [span_cents/2])
        -import_from(united_states, [usd, usd_cent])
        -constants_number_units(span_cents/2, [(1, 5)], usd_cent, number_at(2))
    """) == []


def test_the_scale_suffixes_are_a_DECLARED_UNION(tmp_path):
    """Derived plus retired, because this lint asks a RESIDUE question.

    Deriving from `MINOR_UNIT_WORDS` answers "does this conform to the current
    vocabulary". Asking whether an identifier claims a scale nothing
    represents is about words the authority may already have FORGOTTEN — and
    the forgetting is the event that makes the question necessary
    (a downstream checker, 2026-09-12, who found that a census deriving only
    from the authority would have reported a confident zero on the four
    bodies carrying `dollar` after the rename).

    So: derive for conformance, hand-maintain for residue, and say which is
    which rather than letting a derived set pretend to be total.
    """
    from clausal.templating.term_rewriting import _scale_suffixes, _name_claims_a_scale
    from clausal.modules.countries import _data
    suffixes = _scale_suffixes()
    derived = set(_data.MINOR_UNIT_WORDS.values())
    assert derived and derived <= suffixes, "the derived half is present"
    assert suffixes - derived, "the hand-maintained half is present"
    # Spellings no table names today and a corpus may still carry.
    for name in ("fee_pennies", "fee_centimes", "fee_fils", "rate_bps"):
        assert _name_claims_a_scale(name), name


def test_the_hand_maintained_half_notices_when_it_should_SHRINK():
    """A half expected to shrink needs something that notices when it should
    have (a downstream checker, 2026-09-12). The non-empty control catches an
    empty hand list; nothing caught a REDUNDANT one — a word the authority has
    since taken over, left behind by hand, which is the same staleness in the
    other direction.

    `bps`/`percent` move into the derived half when ratio units land, and the
    overlap control is what will say so instead of letting the list quietly
    carry them forever.
    """
    from clausal.templating.term_rewriting import (
        _HAND_MAINTAINED_SCALE_WORDS, _derived_scale_words, _scale_suffixes)
    derived = _derived_scale_words()
    assert derived, "positive control: the derived half is not empty"
    assert _HAND_MAINTAINED_SCALE_WORDS, "and neither is the hand half"
    assert not (_HAND_MAINTAINED_SCALE_WORDS & derived), (
        "a hand-maintained word is now in the vocabulary — drop it")
    assert _scale_suffixes() >= derived | _HAND_MAINTAINED_SCALE_WORDS
