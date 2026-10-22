"""A unit imported under an alias exports exactly as the unit itself.

`-import_from(united_states, [alias(usd, us_dollar)])` binds the local name
`us_dollar` to the currency `usd` (the seam compiler maps the local name to
`united_states.usd`). The exporter resolves units by NAME from static data, and
`us_dollar` names nothing there, so a module importing a currency unit under an
alias was refused outright ("a unit the exporter cannot resolve") at its first
`-constant_number_currency(..., us_dollar)`; and an inline `5(us_dollar_cent)`
slipped past the scaled-unit refusal and dropped its factor.

The alias now resolves to its source unit before conversion, so the aliased
module, its plain twin (`-import_from(united_states, [usd, usd_cent])`) and its
dotted twin (`-import_module(united_states)` with `united_states.usd`) export to
the SAME Prolog text, in every unit position: a singular declaration, a table
declaration, a constant asked for in a unit, a runtime value asked for in a
unit, and an inline quantity.
"""
import pytest

from clausal.tools.clausal_to_prolog import (
    UntranslatableConstructError, clausal_source_to_prolog)
from clausal.tools.prolog_dialect import Dialect

_BODY = """\
-constant_number_currency(lim, 23, {usd})
-constants_number_currency(ded/2, [(1, 204), (2, 217)], {usd}, money_at(2))
lim_cents(C) <- (C == constant(lim) / {cent})
ded_cents(K, C) <- (ded(K, A), C == A / {cent})
pay(X) <- (X == 5({usd}))
"""
_HEAD = "-module(m, [lim_cents(C), ded(K, A), ded_cents(K, C), pay(X)])\n"

PLAIN = (_HEAD + "-import_from(united_states, [usd, usd_cent])\n"
         + _BODY.format(usd="usd", cent="usd_cent"))
DOTTED = (_HEAD + "-import_module(united_states)\n"
          + _BODY.format(usd="united_states.usd",
                         cent="united_states.usd_cent"))
ALIASED = (_HEAD + "-import_from(united_states, "
           "[alias(usd, us_dollar), alias(usd_cent, us_dollar_cent)])\n"
           + _BODY.format(usd="us_dollar", cent="us_dollar_cent"))

DIALECTS = ["iso", "swi", "scryer", "trealla"]


def _export(src, dialect, **kw):
    return clausal_source_to_prolog(src, dialect=getattr(Dialect, dialect)(), **kw)


@pytest.mark.parametrize("dialect", DIALECTS)
def test_aliased_plain_and_dotted_twins_export_identically(dialect):
    plain = _export(PLAIN, dialect)
    assert _export(ALIASED, dialect) == plain
    assert _export(DOTTED, dialect) == plain


@pytest.mark.parametrize("dialect", DIALECTS)
def test_the_aliased_export_carries_the_source_unit_and_converts(dialect):
    out = _export(ALIASED, dialect)
    assert "us_dollar" not in out, out
    assert "2300" in out, out                       # 23 usd asked in cents
    assert "A * 100" in out or "A*100" in out, out  # a runtime value in cents


def test_strict_mode_accepts_a_unit_alias():
    """A unit alias is not the refused predicate rename: nothing is lost."""
    assert (clausal_source_to_prolog(ALIASED, strict=True)
            == clausal_source_to_prolog(PLAIN, strict=True))


def test_plain_module_specs_twins_agree():
    assert (clausal_source_to_prolog(ALIASED, module_specs="plain")
            == clausal_source_to_prolog(PLAIN, module_specs="plain"))


def test_an_aliased_scaled_inline_quantity_is_refused_like_its_source():
    """`5(us_dollar_cent)` is 0.05 usd stored; dropping the unit keeps 5. The
    source spelling `5(usd_cent)` is refused for that; the alias must be too,
    not slip through because its local name is unknown."""
    tail = "p(X) <- (X == 5({}))\n"
    with pytest.raises(NotImplementedError, match="scaled unit"):
        clausal_source_to_prolog(
            "-import_from(united_states, [usd_cent])\n" + tail.format("usd_cent"))
    with pytest.raises(NotImplementedError, match="scaled unit"):
        clausal_source_to_prolog(
            "-import_from(united_states, [alias(usd_cent, c)])\n"
            + tail.format("c"))


def test_a_predicate_alias_is_still_refused():
    """Only UNIT aliases resolve: a predicate alias stays the refusal of the
    2026-09-29 ruling (no import renaming; qualify instead)."""
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog(
            "-import_from(a.b, [alias(g, gg)])\np(X) <- (gg(X, 1))\n",
            strict=True)
