"""A unit imported under an alias exports exactly as the unit itself.

`-import_from(united_states, [alias(usd, us_dollar)])` binds the local name
`us_dollar` to the currency `usd` (the seam compiler maps the local name to
`united_states.usd`). The exporter resolves units by NAME from static data, and
`us_dollar` names nothing there, so a module importing a currency unit under an
alias was refused outright ("a unit the exporter cannot resolve") at its first
`-constant_number_currency(..., us_dollar)`; and an inline `5(us_dollar_cent)`
slipped past the scaled-unit refusal and dropped its factor.

The alias now resolves to its source unit IN UNIT POSITIONS (and only for an
import from a unit vocabulary module), so the aliased module, its plain twin (`-import_from(united_states, [usd, usd_cent])`) and its
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
    """A unit alias is not the refused predicate rename: nothing is renamed
    in the output, the alias is resolved in unit positions."""
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


# A predicate alias whose SOURCE name is also a unit word (`day` is one, as
# are `second`, `mark`, `gold`, `m`...), from a module that is not a unit
# vocabulary, while the module defines its own day/2. Resolving aliases by
# WORD renamed `helper_day(X, 3)` to `day(X, 3)` and captured the local day/2.
UNIT_WORD_PREDICATE = """\
-module(m, [p(X), day(D, N)])
-import_from(my.helpers, [alias(day, helper_day)])
day(mon, 1),
p(X) <- (helper_day(X, 3))
"""


def test_a_unit_word_predicate_alias_is_still_refused_in_strict_mode():
    with pytest.raises(UntranslatableConstructError, match="alias.day, helper_day"):
        clausal_source_to_prolog(UNIT_WORD_PREDICATE, strict=True)


def test_a_unit_word_predicate_alias_warns_and_is_not_renamed():
    out = clausal_source_to_prolog(UNIT_WORD_PREDICATE)
    assert "WARNING" in out and "alias(day, helper_day)" in out, out
    assert "helper_day(X, 3)" in out, out
    assert "day(X, 3)" not in out.replace("helper_day(X, 3)", ""), out


# The source unit's NAME used as the module's own atom beside the alias --
# which is why real code aliases. The alias resolves in unit positions only,
# so the two stay distinct, as they are in the engine.
KERNEL = "-module(kern, [usd, tag(X)])\ntag(usd),\n"
CONSUMER = """\
-module(consumer, [same(A, B), rate(U, N), cents(C)])
-import_from({pkg}.kern, [usd, tag])
-import_from(united_states, [alias(usd, us_dollar), alias(usd_cent, us_dollar_cent)])
-constant_number_currency(lim, 2, us_dollar)
rate(us_dollar, 3),
same(A, B) <- (rate(A, _), tag(B), A is B)
cents(C) <- (C == constant(lim) / us_dollar_cent)
"""


def test_the_source_units_name_as_a_local_atom_is_not_captured():
    out = clausal_source_to_prolog(CONSUMER.format(pkg="pk"))
    assert "rate(us_dollar, 3)" in out, out          # the term position: as written
    assert "use_module('pk/kern')" in out, out      # the kernel import is kept
    assert "imported only units" not in out, out
    assert "200" in out, out                         # the unit position resolved


def test_engine_and_exported_answers_agree_on_the_local_atom(tmp_path, monkeypatch):
    import importlib
    import os

    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from tests._oracles import SCRYER, run_scryer

    pkg = "unit_alias_atom_pkg"
    (tmp_path / pkg).mkdir()
    (tmp_path / pkg / "__init__.py").write_text("")
    (tmp_path / pkg / "kern.seam").write_text(KERNEL)
    (tmp_path / pkg / "consumer.seam").write_text(CONSUMER.format(pkg=pkg))
    monkeypatch.syspath_prepend(str(tmp_path))
    consumer = importlib.import_module(f"{pkg}.consumer")
    a, b, c = Var(), Var(), Var()
    assert list(call(consumer.same, a, b)) == []     # the engine: no solution
    assert [int(str(c)) for _ in call(consumer.cents, c)] == [200]

    if not os.path.exists(SCRYER):
        pytest.skip(f"Scryer not built at {SCRYER}")
    out = clausal_source_to_prolog(CONSUMER.format(pkg=pkg))
    body = "\n".join(line for line in out.splitlines()
                     if not line.startswith(":- use_module('"))
    (tmp_path / "consumer.pl").write_text(body + "\ntag(usd).\n")
    proc = run_scryer("consumer.pl", ["same(A, B).", "cents(C)."],
                      cwd=tmp_path, timeout=30)
    answers = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    assert answers == ["false.", "C = 200."], proc.stdout + proc.stderr


@pytest.mark.parametrize("imports", [
    "-import_from(united_states, [alias(usd, money_unit), alias(usd_cent, money_unit)])",
    "-import_from(united_states, [alias(usd, money_unit)])\n"
    "-import_from(australia, [alias(aud, money_unit)])",
])
def test_one_local_name_for_two_units_is_refused(imports):
    """The engine refuses this within one directive and keeps the LATER
    binding across two; the exporter refuses both rather than pick a unit."""
    with pytest.raises(NotImplementedError, match="money_unit"):
        clausal_source_to_prolog(imports + "\np(X) <- (X == 5(money_unit))\n")


def test_the_same_unit_alias_twice_is_one_import():
    src = ("-import_from(united_states, [alias(usd, d), alias(usd, d)])\n"
           "-constant_number_currency(lim, 2, d)\n")
    assert "usd" in clausal_source_to_prolog(src, dialect=Dialect.scryer())


def test_only_the_named_vocabulary_module_resolves():
    """`usd` from a module that is not a unit vocabulary is not a unit."""
    with pytest.raises(NotImplementedError, match="cannot resolve"):
        clausal_source_to_prolog(
            "-import_from(my.money, [alias(usd, d)])\n"
            "-constant_number_currency(lim, 2, d)\n")
