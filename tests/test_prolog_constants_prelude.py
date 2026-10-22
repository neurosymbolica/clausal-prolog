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
    # The BASE magnitude, not the declared 155000. Asserted as a VALUE, not a
    # spelling: the exporter writes `1550.00` and Prolog reads it as a float and
    # prints `1550.0`. The magnitude survives; the decimal SCALE does not,
    # because Prolog has no decimal type. Measured 2026-09-13 -- an earlier
    # version of this assertion looked for "1550.00" and failed on a correct
    # result, which is the right way round for an assertion to be wrong.
    assert "1550" in res and "155000" not in res, res


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
