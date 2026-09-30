"""Exporting constants is a per-DIALECT capability.

Operator, 2026-09-13: there are two sides — ours, where we can do what we
want, and the export side, where another Prolog has to understand the file. So
the exporter takes a switch rather than one side of a trade-off.

See docs/superpowers/specs/2026-09-13-exporter-option-3-design.md.

    iso              facts      module filled in by the EXPORTER (no
                                prolog_load_context/2 in ISO)
    scryer, trealla  expansion  the directive; the hook sees the module
    swi              expansion
    gprolog          none       refuse -- no module system either

Unchanged in every dialect: a use site folds to the BASE magnitude, never the
declared one. `155000 usd_cent` is `1550.00`, and emitting `155000` was the
100x defect this whole todo existed for.
"""
from decimal import Decimal

import pytest

from clausal.tools.prolog_dialect import Dialect


def _clauses_only(out):
    """Output with comments and use_module lines stripped.

    Asserting on raw output gave two FALSE PASSES: `"constant_number_units("
    in out` matched the text inside the `/* LOSSY: */` comment, and `"euro" in
    out` matched `:- use_module('european_union', [euro])`. A test that can be
    satisfied by the thing it is meant to replace is not a test.
    """
    import re
    out = re.sub(r"/\*.*?\*/", "", out, flags=re.S)
    return "\n".join(l for l in out.splitlines()
                      if not l.strip().startswith(":- use_module"))


def _export(src, dialect=None):
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    if dialect is None:
        return clausal_source_to_prolog(src)
    return clausal_source_to_prolog(src, dialect=dialect)


MINOR = ('-import_from(united_states, [usd, usd_cent])\n'
         '-constant_number_units(sga, 155000, usd_cent)\n'
         'pay(constant(sga)),\n')
RATIO = ('-import_from(py.units, [basis_point])\n'
         '-constant_number_units(floor_r, 300, basis_point)\n'
         'lim(constant(floor_r)),\n')
BASE = ('-import_from(european_union, [euro])\n'
        '-constant_number_units(fee, 5000, euro)\n'
        'pay(constant(fee)),\n')


# ── the capability field ─────────────────────────────────────────────────────


def test_every_dialect_declares_its_constants_capability():
    """Derived from the factories, so a new dialect cannot forget to say."""
    for factory in ("iso", "swi", "scryer", "trealla", "gprolog"):
        d = getattr(Dialect, factory)()
        assert d.constants in ("none", "facts", "expansion"), (factory, d.constants)


def test_the_capability_matches_what_each_system_can_do():
    assert Dialect.iso().constants == "facts"        # no prolog_load_context/2
    assert Dialect.scryer().constants == "expansion"
    assert Dialect.trealla().constants == "expansion"
    assert Dialect.swi().constants == "expansion"
    assert Dialect.gprolog().constants == "none"     # no module system either


# ── the magnitude, which is dialect-independent ──────────────────────────────


def test_a_minor_unit_constant_folds_to_the_BASE_magnitude():
    """THE correctness test, and the reason this todo existed: `155000 usd_cent`
    is 1550.00 dollars, and emitting 155000 was a 100x money error announced
    only by a comment."""
    out = _export(MINOR, Dialect.iso())
    # An integral scaled fold is an exact INT at a use site since 2026-09-13.
    # The guard that matters is unchanged: never the declared 155000.
    assert "pay(1550)" in out, out
    assert "pay(155000)" not in out


def test_a_ratio_unit_constant_folds_to_the_BASE_magnitude():
    out = _export(RATIO, Dialect.iso())
    assert "lim(0.03" in out, out
    assert "lim(300)" not in out


def test_a_base_unit_constant_is_unchanged():
    """The regression guard: a base unit's declared magnitude IS the stored
    one, so conversion must be a no-op rather than a rounding trip."""
    out = _export(BASE, Dialect.iso())
    assert "pay(5000)" in out, out


def test_an_unresolvable_unit_still_refuses_in_every_dialect():
    src = ('-import_from(py.units, [metre])\n'
           '-constant_number_units(x, 5, metre * unknown_thing_xyz)\n'
           'q(constant(x)),\n')
    for factory in ("iso", "scryer", "trealla"):
        with pytest.raises(NotImplementedError):
            _export(src, getattr(Dialect, factory)())


# ── what each dialect emits ─────────────────────────────────────────────────


def test_iso_emits_a_FACT_with_the_module_filled_in():
    """ISO has no prolog_load_context/2, so the exporter supplies the module —
    which it knows statically, exactly as the engine's transformer does."""
    out = _clauses_only(_export(BASE, Dialect.iso()))
    assert "constant_number_units(" in out, out
    assert ":- constant_number_units(" not in out   # a fact, not a directive


def test_scryer_and_trealla_emit_the_DIRECTIVE_for_expansion():
    for factory in ("scryer", "trealla"):
        out = _clauses_only(_export(BASE, getattr(Dialect, factory)()))
        assert ":- constant_number_units(" in out, (factory, out)


def test_gprolog_refuses_rather_than_emitting_something_that_will_not_run():
    with pytest.raises(NotImplementedError, match="constant"):
        _export(BASE, Dialect.gprolog())


def test_the_declaration_carries_the_UNIT_not_just_the_number():
    """The whole point of option 3: the pair crosses. A LOSSY comment saying
    the unit was discarded is what this replaces."""
    out = _clauses_only(_export(BASE, Dialect.iso()))
    assert "euro" in out, out


# ── does the emitted program actually RUN? ───────────────────────────────────
#
# The refusal this replaces existed to avoid "emitting something that parses
# and does not run" (clausal_to_prolog.py's own words). Only execution
# disproves that, and both binaries are present, so this is a real test.

from tests._oracles import SCRYER, TREALLA, run_scryer


def _run(binary, program, goal):
    import subprocess, tempfile, os
    d = tempfile.mkdtemp()
    pl = os.path.join(d, "w.pl")
    with open(pl, "w") as fh:
        fh.write(program)
    if binary == SCRYER:
        # Never Scryer's stdin toplevel: the clean build hangs on it.
        proc = run_scryer(pl, [goal] if goal.strip() else [], timeout=30)
    else:
        proc = subprocess.run([binary, pl], input=goal + "\n",
                              capture_output=True, text=True, timeout=30)
    return proc.stdout + proc.stderr


@pytest.mark.parametrize("binary,name", [(SCRYER, "scryer"), (TREALLA, "trealla")])
def test_the_iso_FACTS_form_runs_and_answers_the_pair(binary, name):
    """The `facts` form needs no prelude and no non-ISO feature, so it must run
    as-is on any conforming system. Asserted on both, because "it is ISO" is a
    claim and running it is an observation."""
    import os
    if not os.path.exists(binary):
        pytest.skip(f"{name} not built at {binary}")
    out = _export(BASE, Dialect.iso())
    body = "\n".join(l for l in out.splitlines()
                     if not l.strip().startswith(":- module")
                     and not l.strip().startswith(":- use_module"))
    program = body + "\n:- initialization(main).\nmain :- " \
        "( constant_number_units(M, fee, N, U) -> " \
        "write(got(M,N,U)) ; write(no_answer) ), nl, halt.\n"
    res = _run(binary, program, "")
    assert "got(" in res, res
    assert "5000" in res and "euro" in res, res


# ── the decimal representation: float vs rational ────────────────────────────
#
# Operator, 2026-09-13: "could add an option for decimals to be represented as
# e.g. 1_550_00/100". Measured first: `155000/100` as a TERM is preserved
# exactly in Scryer and Trealla, while `is 155000/100` evaluates to 1550.0 and
# `155000 rdiv 100` normalises to 1550 -- so only the UNEVALUATED term keeps the
# scale. SICStus's infix `r/2` is a third option, unimplemented because `3r2`
# is a syntax error in both systems available here.


def _rational(dialect_name="iso"):
    import dataclasses
    return dataclasses.replace(getattr(Dialect, dialect_name)(),
                               decimal_repr="rational")


def test_float_is_the_default_so_existing_output_is_unchanged():
    """Adopting `rational` for the roster is a deliberate change needing its own
    export-bytes measurement; it must not arrive as a side effect."""
    for factory in ("iso", "swi", "scryer", "trealla", "gprolog"):
        assert getattr(Dialect, factory)().decimal_repr == "float", factory


def test_the_rational_form_keeps_the_SCALE_a_float_loses():
    """THE test. `1550.00` is read as a float by every Prolog and prints as
    `1550.0`; `1_550_00/100` keeps both halves, so two decimal places are
    recoverable from the denominator."""
    out = _clauses_only(_export(MINOR, _rational()))
    assert "1_550_00/100" in out, out
    assert "1550.00," not in out, out


def test_the_use_site_stays_a_NUMBER_under_rational():
    """Applies to the DECLARATION only: at a use site `F > 155000/100` is
    evaluated back to a float anyway, so the rational buys nothing there and
    complicates the arithmetic."""
    out = _clauses_only(_export(MINOR, _rational()))
    # `pay(1550)` -- a NUMBER, and exactly so: an integral scaled fold is an
    # int at a use site (see the integral test below), while the DECLARATION
    # keeps the scale as 1_550_00/100. The two differ on purpose.
    assert "pay(1550)" in out, out


def test_an_integer_magnitude_is_not_made_rational():
    """Nothing to preserve, so nothing is changed -- a base-unit integer
    constant must not acquire a denominator."""
    out = _clauses_only(_export(BASE, _rational()))
    assert "5000" in out and "/1" not in out, out


def test_the_grouping_separates_minor_units_and_thousands():
    from clausal.tools.clausal_to_prolog import _group_digits
    assert _group_digits(155000, 2) == "1_550_00"       # the operator's example
    assert _group_digits(1234567890, 2) == "12_345_678_90"
    assert _group_digits(5, 2) == "0_05"                # pads below one unit
    assert _group_digits(-155000, 2) == "-1_550_00"


@pytest.mark.parametrize("system", ["scryer", "trealla"])
def test_the_rational_form_reads_back_exactly_in_the_real_system(system):
    """Asserted by RUNNING it: the grouped rational must parse, and both halves
    must come back, or the scale is not actually recoverable."""
    import os, subprocess, tempfile
    binary = {"scryer": SCRYER, "trealla": TREALLA}[system]
    if not os.path.exists(binary):
        pytest.skip(f"{system} not built")
    d = tempfile.mkdtemp()
    prog = os.path.join(d, "r.pl")
    with open(prog, "w") as fh:
        fh.write(":- initialization(main).\n"
                 "main :- X = 1_550_00/100, X = N/Dn, "
                 "write(halves(N,Dn)), nl, halt.\n")
    if system == "scryer":
        res = run_scryer(prog, [], timeout=30, binary=binary).stdout
    else:
        res = subprocess.run([binary, prog], capture_output=True, text=True,
                             timeout=30, stdin=subprocess.DEVNULL).stdout
    assert "halves(155000,100)" in res.replace(" ", ""), res


def test_a_scaled_fold_that_lands_on_a_whole_unit_stays_an_INTEGER():
    """Reported by a downstream user on canonical 750e6ae1, and it was mine.

    `155000 aud_cent` is `Decimal('1550.00')`, which IS integral -- so an exact
    integer was available and the emitter wrote `1550.00`, a Prolog FLOAT. The
    base-unit case stayed integer, so the scaled path silently converted exact
    cents into binary floating point: the hazard the operator ruled against when
    rejecting dimensionless constants, arriving by another route.

    The engine holds currency exactly (an exact Fraction since d2411c72), so the
    exactness existed and was being discarded at emission.
    """
    out = _export('-import_from(australia, [aud, aud_cent])\n'
                  '-constant_number_units(cap, 155000, aud_cent)\n'
                  'v(constant(cap)),\n')
    use_site = [l for l in out.splitlines() if l.startswith("v(")]
    assert use_site == ["v(1550)."], out
    # scoped to the USE SITE: the declaration legitimately carries 1550.00,
    # which is where the scale lives and what decimal_repr="rational" renders.
    assert "1550.0" not in use_site[0], out


def test_a_genuinely_fractional_fold_is_still_a_float_and_that_is_KNOWN():
    """The residual, pinned so it is a tracked limit rather than a surprise.

    A conversion that does not land on a whole unit has no exact Prolog
    representation at a USE SITE: `decimal_repr="rational"` covers declarations,
    but a use site must be arithmetically usable, and under the operator's
    `#=` ruling CLP(Z) is integer-only -- so a fractional money amount cannot be
    a clpz constraint at all. That is a design question for a downstream exporter, not
    something to settle by changing this emitter.
    """
    out = _export('-import_from(australia, [aud, aud_cent])\n'
                  '-constant_number_units(odd, 15505, aud_cent)\n'
                  'v(constant(odd)),\n')
    assert "v(155.05)." in out, out
