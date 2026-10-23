"""The `expansion` dialects' prelude — verified by RUNNING it.

The refusal this whole path replaced existed to avoid "emitting something that
parses and does not run" (clausal_to_prolog.py's own words), so a prelude that
is merely plausible is worth nothing. Each is executed under its own real
binary and asked to answer the declared pair back.

**There are two preludes because a single portable one does not work**, measured
2026-09-13. Scryer fires an unqualified imported `term_expansion/2`, refuses a
`user:`-qualified clause head, and rejects `ensure_loaded/1` as a directive.
Trealla will not fire an unqualified imported hook, and its
`prolog_load_context(module, M)` reports the module the HOOK is defined in --
so its prelude must be module-LESS and loaded with `ensure_loaded`, or every
file is attributed to the prelude. Opposite requirements, which is exactly why
this sits behind a per-dialect capability.
"""
import os
import subprocess
import tempfile

import pytest
from tests._oracles import SCRYER, TREALLA, run_scryer

BINARIES = {
    "scryer": SCRYER,
    "trealla": TREALLA,
}


def _run_program(system, binary, prog, cwd):
    """Load *prog* (its `:- initialization(main)` does the work) and halt.

    Scryer goes through run_scryer: stdin /dev/null and a trailing `-g halt`,
    because the clean build hangs in its toplevel otherwise. Trealla keeps its
    own invocation, with stdin closed so it never waits on a terminal."""
    if system == "scryer":
        return run_scryer(prog, [], cwd=cwd, timeout=40, binary=binary)
    return subprocess.run([binary, prog], capture_output=True, text=True,
                          timeout=40, cwd=cwd, stdin=subprocess.DEVNULL)


PRELUDE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clausal", "tools", "prolog_preludes")


def _run_with_prelude(system, program_body, module_name=None):
    """Copy the system's prelude beside a generated program and run it."""
    import shutil
    binary = BINARIES[system]
    if not os.path.exists(binary):
        pytest.skip(f"{system} not built at {binary}")
    d = tempfile.mkdtemp()
    src = os.path.join(PRELUDE_DIR, f"clausal_constants_{system}.pl")
    dst = os.path.join(d, f"cc_{system}.pl")
    shutil.copy(src, dst)
    prog = os.path.join(d, "prog.pl")
    with open(prog, "w") as fh:
        head = f":- module({module_name}, []).\n" if module_name else ""
        # Scryer takes `use_module` and refuses `ensure_loaded/1`; Trealla's
        # prelude must be module-LESS and loaded with `ensure_loaded`, or
        # `prolog_load_context(module, M)` reports the prelude's own module.
        # Measured 2026-09-13; see each prelude's header.
        load = (f":- ensure_loaded(cc_{system}).\n" if system == "trealla"
                else f":- use_module(cc_{system}).\n")
        fh.write(head + load + ":- initialization(main).\n"
                 ":- discontiguous(constant_number_units/3).\n"
                 ":- discontiguous(module_constant_units/4).\n"
                 ":- discontiguous(constant_value/2).\n"
                 ":- discontiguous(module_constant/3).\n" + program_body)
    proc = _run_program(system, binary, prog, d)
    return proc.stdout + proc.stderr


@pytest.mark.parametrize("system", sorted(BINARIES))
def test_the_prelude_expands_the_directive_and_answers_the_pair(system):
    """THE test: the exporter's `expansion` output, run as-is."""
    out = _run_with_prelude(system, (
        ":- constant_number_units(fee, 5000, euro).\n"
        "main :- ( constant_number_units(N, V, U) -> write(got(N,V,U)) "
        "; write(not_expanded) ), nl, halt.\n"))
    assert "got(fee,5000,euro)" in out.replace(" ", ""), out


@pytest.mark.parametrize("system", sorted(BINARIES))
def test_the_expansion_records_the_DECLARING_MODULE(system):
    """The whole reason term expansion was the asked-for route: the hook calls
    `prolog_load_context(module, M)` from inside itself, so the module the
    engine inserts at compile time is inserted here at load time instead."""
    out = _run_with_prelude(system, (
        ":- constant_number_units(fee, 5000, euro).\n"
        "main :- ( module_constant_units(M, fee, _, _) -> write(mod(M)) "
        "; write(no_module) ), nl, halt.\n"), module_name="a_named_module")
    # The module NAME, not merely that one was recorded. Asserting `mod(` alone
    # passed under a mutation replacing `prolog_load_context(module, M)` with a
    # hardcoded wrong module -- which is the one thing this test exists to
    # detect, since getting the REAL module is why term expansion was the
    # asked-for route.
    assert "mod(a_named_module)" in out, out


@pytest.mark.parametrize("system", sorted(BINARIES))
def test_a_value_only_constant_expands_too(system):
    out = _run_with_prelude(system, (
        ":- constant_value(pi_approx, 3).\n"
        "main :- ( constant_value(pi_approx, V) -> write(val(V)) "
        "; write(no_value) ), nl, halt.\n"))
    assert "val(3)" in out, out


@pytest.mark.parametrize("system", sorted(BINARIES))
def test_an_unexpanded_program_is_the_negative_control(system):
    """Without the prelude the directive is not expanded, so the query finds
    nothing. Proves the tests above observe the PRELUDE's effect rather than
    something the system does anyway."""
    binary = BINARIES[system]
    if not os.path.exists(binary):
        pytest.skip(f"{system} not built")
    d = tempfile.mkdtemp()
    prog = os.path.join(d, "bare.pl")
    with open(prog, "w") as fh:
        fh.write(":- initialization(main).\n"
                 ":- dynamic(module_constant_units/4).\n"
                 ":- constant_number_units(fee, 5000, euro).\n"
                 "main :- ( catch(module_constant_units(_,fee,_,_), _, fail) "
                 "-> write(unexpectedly_there) ; write(absent) ), nl, halt.\n")
    proc = _run_program(system, binary, prog, d)
    res = proc.stdout + proc.stderr
    # Either outcome proves the prelude is what makes the directive work, and
    # Scryer's is the stronger one: without the prelude the directive is not a
    # directive at all, so the program does not load rather than loading with
    # nothing recorded. Accepting both keeps the control honest about what each
    # system actually does instead of forcing one answer.
    assert "absent" in res or "domain_error(directive" in res, res


# ── end to end: the exporter's OWN output, unmodified ────────────────────────


@pytest.mark.parametrize("system", sorted(BINARIES))
def test_the_exporters_own_output_runs_unmodified(system):
    """The claim that matters, and the only one that cannot be faked by a
    hand-written program: take what the exporter emits for this dialect, copy
    the prelude beside it, run it, and ask for the declared pair back.

    Every earlier test in this file wrote its own program. This one writes
    none -- if the exporter emits the wrong load directive, names the wrong
    prelude, or orders the prelude after the declarations, only this fails.
    """
    import shutil
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    from clausal.tools.prolog_dialect import Dialect

    binary = BINARIES[system]
    if not os.path.exists(binary):
        pytest.skip(f"{system} not built at {binary}")

    out = clausal_source_to_prolog(
        "-module(fees, [pay/1])\n"
        "-import_from(united_states, [usd, usd_cent])\n"
        "-constant_number_units(sga, 155000, usd_cent)\n"
        "pay(constant(sga)),\n",
        dialect=getattr(Dialect, system)())

    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(PRELUDE_DIR, f"clausal_constants_{system}.pl"), d)
    # The import of the jurisdiction module is a Clausal concept with no Prolog
    # counterpart here, so drop that one line; everything else is verbatim.
    body = "\n".join(l for l in out.splitlines()
                     if "use_module('united_states'" not in l)
    prog = os.path.join(d, "fees.pl")
    with open(prog, "w") as fh:
        fh.write(body + "\n:- initialization(main).\n"
                 "main :- ( module_constant_units(M, sga, N, U) -> "
                 "write(got(M,N,U)) ; write(no_answer) ), nl, halt.\n")
    proc = _run_program(system, binary, prog, d)
    res = proc.stdout + proc.stderr
    assert "got(fees," in res.replace(" ", ""), res
    assert "usd_cent" in res, res         # the unit crossed
    # The DECLARED pair, `155000, usd_cent`, as the engine's
    # constant_number_units/3 reports it (operator ruling 2026-10-23). This
    # used to assert the BASE magnitude (`1550.0`) beside the declared unit --
    # a pair that was neither, and 100x too small through the accessor. The
    # use site `pay(constant(sga))` still folds to the base 1550 on its own.
    assert "got(fees,155000,usd_cent)" in res.replace(" ", ""), res
    assert "pay(1550)." in out and "1550.0" not in out, out


# ── constant_number_currency, and the accessors inside a named module ─────


@pytest.mark.parametrize("system", sorted(BINARIES))
def test_a_currency_constant_is_answered_by_constant_number_units(system):
    """The engine has no constant_number_currency/3: a -constant_number_currency
    declaration is recorded for constant_number_units/3, so the prelude
    expands it exactly as a units one. Before, Scryer refused the directive --
    domain_error(directive, constant_number_currency/3) -- and the rest of the
    module did not load."""
    out = _run_with_prelude(system, (
        ":- constant_number_currency(lim, 23, usd).\n"
        "main :- ( constant_number_units(N, V, U) -> write(got(N,V,U)) "
        "; write(not_expanded) ), nl, halt.\n"))
    assert "got(lim,23,usd)" in out.replace(" ", ""), out


# The accessors are called from INSIDE the declaring module, the normal use.
# Scryer's prelude used to define them in its own module, reading its own
# empty tables, so every one answered false there (units and currency alike)
# while the facts sat in the declaring module.
LOOK = """\
-module(look_cur, [look(N, U), look_len(N, U)])
-import_from(united_states, [usd])
-import_from(units, [metre])
-constant_number_currency(lim, 23, usd)
-constant_number_units(len, 5, metre)
look(N, U) <- constant_number_units(lim, N, U)
look_len(N, U) <- constant_number_units(len, N, U)
"""
LOOK_ANSWERS = ["look(23,usd)", "look_len(5,metre)"]


def test_the_engine_answers_the_look_predicates(tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from tests._suffix import SEAM

    path = tmp_path / f"look_cur{SEAM}"
    path.write_text(LOOK)
    m = _load_module("prelude_look_cur", str(path))
    n, u = Var(), Var()
    assert [(str(n), str(u)) for _ in call(m.look, n, u)] == [("23", "usd")]
    assert [(str(n), str(u)) for _ in call(m.look_len, n, u)] == [("5", "metre")]


@pytest.mark.parametrize("system", sorted(BINARIES))
def test_the_exported_module_answers_its_constants_from_inside(system):
    """The exporter's own output, run as-is under the real binary, answers
    what the engine answers (the test above), from inside the module."""
    import shutil
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    from clausal.tools.prolog_dialect import Dialect

    binary = BINARIES[system]
    if not os.path.exists(binary):
        pytest.skip(f"{system} not built at {binary}")
    out = clausal_source_to_prolog(LOOK, dialect=getattr(Dialect, system)())
    assert ":- constant_number_currency(lim, 23, usd)." in out, out
    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(PRELUDE_DIR, f"clausal_constants_{system}.pl"), d)
    # The jurisdiction and units imports are Clausal modules with no Prolog
    # counterpart here; everything else is verbatim.
    body = "\n".join(l for l in out.splitlines()
                     if not l.startswith(":- use_module('"))
    prog = os.path.join(d, "look_cur.pl")
    with open(prog, "w") as fh:
        # `look_cur:main`, qualified: Trealla runs an unqualified
        # initialization goal in `user` once a module imports a library.
        fh.write(body + "\n:- initialization(look_cur:main).\n"
                 "main :- look(N, U), write(look(N,U)), nl, "
                 "look_len(L, M), write(look_len(L,M)), nl, "
                 "( module_constant_units(look_cur, lim, _, _) -> "
                 "write(recorded) ; write(not_recorded) ), nl, halt.\n")
    proc = _run_program(system, binary, prog, d)
    res = proc.stdout + proc.stderr
    assert "domain_error" not in res and "Warning" not in res, res
    for answer in LOOK_ANSWERS:
        assert answer in res.replace(" ", ""), res
    assert "recorded" in res and "not_recorded" not in res, res


@pytest.mark.parametrize("system", sorted(BINARIES))
@pytest.mark.parametrize("directive, query, answer", [
    ("constant_number_units(fee, 5000, euro)", "constant_number_units(fee, V, U)",
     "got(5000,euro)"),
    ("constant_value(pi_approx, 3)", "constant_value(pi_approx, V)", "got(3)"),
])
def test_an_accessor_answers_inside_a_named_module(system, directive, query, answer):
    """Every accessor, asked from inside the module that declared it."""
    shape = answer[len("got("):-1].split(",")
    out = _run_with_prelude(system, (
        f":- {directive}.\n"
        f"main :- ( {query} -> write(got({', '.join(['V', 'U'][:len(shape)])})) "
        "; write(no_answer) ), nl, halt.\n"), module_name="a_named_module")
    assert answer in out.replace(" ", ""), out


# ── the declared pair, engine vs export (operator ruling 2026-10-23) ──────
#
# An exported declaration carries the pair AS WRITTEN -- `155000, usd_cent`,
# as the engine's constant_number_units/3 reports it (the 2026-09-11 ruling) --
# while every USE SITE still folds to the base magnitude on its own. Before,
# the declaration paired the BASE magnitude with the DECLARED unit
# (`1550.00, usd_cent`): 100x too small through the accessor. The ISO `facts`
# form now records the same two facts the expansion preludes write, so
# constant_number_units/3 answers in every dialect.

CMP = """\
-module(cmp, [cap_pair(N, U), dist_pair(N, U), len_pair(N, U), in_cents(X), in_km(X), cap_base(X), dist_base(X), len_base(X), cap_doubled(X)])
-import_from(united_states, [usd, usd_cent])
-import_from(units, [kilometre, metre])
-constant_number_currency(cap, 155000, usd_cent)
-constant_number_units(dist, 3, kilometre)
-constant_number_units(len, 5, metre)
cap_pair(N, U) <- constant_number_units(cap, N, U)
dist_pair(N, U) <- constant_number_units(dist, N, U)
len_pair(N, U) <- constant_number_units(len, N, U)
in_cents(X) <- (X == constant(cap) / usd_cent)
in_km(X) <- (X == constant(dist) / kilometre)
cap_base(X) <- (X == constant(cap))
dist_base(X) <- (X == constant(dist))
len_base(X) <- (X == constant(len))
cap_doubled(X) <- (X == constant(cap) * 2)
"""
CMP_PAIRS = ["cap_pair", "dist_pair", "len_pair"]
CMP_VALUES = ["in_cents", "in_km", "cap_base", "dist_base", "len_base",
              "cap_doubled"]


def _engine_text(value):
    """An engine answer spelled as a Prolog system prints it: a quantity by
    its (base-unit) magnitude, an integral number without a decimal point."""
    from decimal import Decimal
    from clausal.terms import Quantity
    if isinstance(value, Quantity):
        value = value.value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = int(value)
    return str(value)


def _cmp_engine_answers(tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests._suffix import SEAM

    path = tmp_path / f"cmp{SEAM}"
    path.write_text(CMP)
    m = _load_module("prelude_cmp_engine", str(path))
    answers = []
    for name in CMP_PAIRS:
        n, u = Var(), Var()
        answers += [f"{name}({_engine_text(deref(n))},{deref(u)})"
                    for _ in call(getattr(m, name), n, u)]
    for name in CMP_VALUES:
        x = Var()
        answers += [f"{name}({_engine_text(deref(x))})"
                    for _ in call(getattr(m, name), x)]
    return answers


def test_the_engine_reports_the_declared_pair_and_base_arithmetic(tmp_path):
    """The reference the exported programs are held to below."""
    assert _cmp_engine_answers(tmp_path) == [
        "cap_pair(155000,usd_cent)", "dist_pair(3,kilometre)",
        "len_pair(5,metre)", "in_cents(155000)", "in_km(3)",
        "cap_base(1550)", "dist_base(3000)", "len_base(5)",
        "cap_doubled(3100)"]


@pytest.mark.parametrize("dialect", ["iso", "swi", "scryer", "trealla"])
def test_every_dialect_declares_the_pair_as_written(dialect):
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    from clausal.tools.prolog_dialect import Dialect
    out = clausal_source_to_prolog(CMP, dialect=getattr(Dialect, dialect)())
    for pair in ("cap, 155000, usd_cent", "dist, 3, kilometre",
                 "len, 5, metre"):
        assert f"({pair})" in out or f", {pair})" in out, out
    assert "1550.0" not in out and "3000, kilometre" not in out, out
    # the use sites still fold to the BASE magnitude themselves
    import re
    clauses = out.split("cap_base(X) :-", 1)[1]
    assert re.search(r"\b1550\b", clauses), out
    assert re.search(r"\b3000\b", clauses), out


@pytest.mark.parametrize("system", sorted(BINARIES))
@pytest.mark.parametrize("dialect", ["iso", "expansion"])
def test_the_exported_program_answers_what_the_engine_answers(
        tmp_path, system, dialect):
    """Run the exporter's output under the real binary -- the `facts` form
    (Dialect.iso) and the system's own `expansion` dialect -- and compare
    every answer, the accessor's pairs AND the arithmetic over the constants,
    with the engine's."""
    import shutil
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    from clausal.tools.prolog_dialect import Dialect

    binary = BINARIES[system]
    if not os.path.exists(binary):
        pytest.skip(f"{system} not built at {binary}")
    expected = _cmp_engine_answers(tmp_path)
    factory = "iso" if dialect == "iso" else system
    out = clausal_source_to_prolog(CMP, dialect=getattr(Dialect, factory)())
    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(PRELUDE_DIR, f"clausal_constants_{system}.pl"), d)
    # The jurisdiction and units imports are Clausal modules with no Prolog
    # counterpart here; everything else is verbatim.
    body = "\n".join(l for l in out.splitlines()
                     if not l.startswith(":- use_module('"))
    # fresh variables per goal: `show/1` leaves each one bound
    goals = ([f"{n}(A{i}, B{i})" for i, n in enumerate(CMP_PAIRS)]
             + [f"{n}(X{i})" for i, n in enumerate(CMP_VALUES)])
    prog = os.path.join(d, "cmp.pl")
    with open(prog, "w") as fh:
        fh.write(body + "\n:- initialization(cmp:main).\n"
                 "show(G) :- ( call(G) -> write(G) ; write(no(G)) ), nl.\n"
                 "main :- " + ", ".join(f"show({g})" for g in goals)
                 + ", halt.\n")
    proc = _run_program(system, binary, prog, d)
    res = proc.stdout + proc.stderr
    got = [l.replace(" ", "") for l in res.splitlines()
           if l.split("(")[0] in CMP_PAIRS + CMP_VALUES]
    assert got == expected, res
