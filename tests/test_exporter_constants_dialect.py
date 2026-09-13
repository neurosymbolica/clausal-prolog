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
    assert "pay(1550.00)" in out or "pay(1550.0)" in out, out
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

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"
TREALLA = "/workspace/trealla-prolog/tpl"


def _run(binary, program, goal):
    import subprocess, tempfile, os
    d = tempfile.mkdtemp()
    pl = os.path.join(d, "w.pl")
    with open(pl, "w") as fh:
        fh.write(program)
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
