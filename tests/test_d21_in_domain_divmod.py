"""D21: `in_domain/3` and `divmod_/4` are REWRITTEN for export, not renamed.

The dialect map used to rename them to `ins/3` and `divmod/4`. Neither exists:
Scryer's `ins` is the BINARY operator `Vs ins Lo..Hi` (and `in` its one-variable
form), and Scryer has no `divmod/4` at all (measured 2026-09-29). So:

* `in_domain(V, Lo, Hi)` becomes `ins(L, Lo..Hi)` for a list literal,
  `in(N, Lo..Hi)` for an integer literal, and a mutually exclusive type
  dispatch for anything else, because a variable may hold a list at run time
  (`length(QS, N), in_domain(QS, 1, N)`).
* `divmod_(X, Y, Q, R)` becomes
  `integer(X), integer(Y), Y =\\= 0, Q is X div Y, R is X mod Y` -- floor
  division, as the engine's Python `divmod`; the guards carry its failure
  cases (unbound, non-integer, zero divisor).

The engine-agreement tests consult the output in real Scryer and Trealla and
compare every answer list with the live Clausal engine's, case by case.
"""
from __future__ import annotations

import os
import subprocess

import pytest

import clausal.import_hook  # noqa: F401  -- installs the .clausal finder/loader
from clausal import solve
from clausal.import_hook import _load_module
from clausal.logic.variables import Var, deref
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_dialect import Dialect, resolve_name
from tests._oracles import SCRYER, TREALLA


#: name -> goal body binding L. Every case is a findall, so the whole answer
#: set is compared, not just the first answer: a rewrite that adds or loses a
#: solution shows up as a different list.
CASES = {
    "dm_pos":      "findall([Q, R], divmod_(17, 5, Q, R), L)",
    "dm_negx":     "findall([Q, R], divmod_(-7, 2, Q, R), L)",
    "dm_negy":     "findall([Q, R], divmod_(7, -2, Q, R), L)",
    "dm_negboth":  "findall([Q, R], divmod_(-7, -2, Q, R), L)",
    "dm_zero":     "findall([Q, R], divmod_(10, 0, Q, R), L)",
    "dm_unbound":  "findall([Q, R], divmod_(X, 5, Q, R), L)",
    "dm_check_ok": "findall(1, divmod_(17, 5, 3, 2), L)",
    "dm_check_no": "findall(1, divmod_(17, 5, 3, 99), L)",
    "dm_float":    "findall([Q, R], divmod_(7.5, 2, Q, R), L)",
    "dm_boundvar": "findall([Q, R], (X is -9, divmod_(X, 4, Q, R)), L)",
    "id_var":      "findall(X, (in_domain(X, 1, 3), label([X])), L)",
    "id_var_once": "findall(1, in_domain(X, 1, 3), L)",
    "id_varlist":  "findall(VS, (length(VS, 2), in_domain(VS, 0, 1), label(VS)), L)",
    "id_litlist":  "findall([A, B], (in_domain([A, B], 1, 2), label([A, B])), L)",
    "id_int_in":   "findall(1, in_domain(5, 1, 9), L)",
    "id_int_out":  "findall(1, in_domain(10, 1, 9), L)",
    "id_intvar":   "findall(1, (X is 4, in_domain(X, 1, 9)), L)",
    "id_nil":      "findall(1, in_domain([], 1, 9), L)",
    "id_nilvar":   "findall(1, (X is [], in_domain(X, 1, 9)), L)",
    "id_atom":     "findall(1, (X is 'foo', in_domain(X, 1, 9)), L)",
    "id_single":   "findall(X, in_domain(X, 4, 4), L)",
}

#: What the engine runs. Both are global builtins there, and importing them
#: from clausal.logic.clpfd changes how the engine dispatches them, so the
#: ground truth is taken WITHOUT the import ...
TRUTH_SOURCE = "".join(f"{n}(L) <- ({g})\n" for n, g in CASES.items())
#: ... and the export WITH it, as a real source spells it: that import is what
#: brings in `label/1`, which Scryer does not autoload.
EXPORT_SOURCE = "-import_from(clausal.logic.clpfd, [in_domain, label])\n" + TRUTH_SOURCE
#: length/2 needs library(lists) in Scryer; the translator alone does not add
#: it (the export pipeline's library pass does).
LISTS_IMPORT = ":- use_module(library(lists), [length/2]).\n"


def _fmt(value) -> str:
    value = deref(value)
    if isinstance(value, list):
        return "[" + ",".join(_fmt(v) for v in value) + "]"
    if isinstance(value, Var):
        return "_"
    return str(value)


@pytest.fixture(scope="module")
def truth(tmp_path_factory):
    path = tmp_path_factory.mktemp("d21") / "d21_cases.clausal"
    path.write_text(TRUTH_SOURCE)
    mod = _load_module("d21_cases_truth", str(path))
    out = {}
    for name in CASES:
        answer = Var()
        for _ in solve((name, answer), mod):
            out[name] = _fmt(answer)
            break
        else:
            out[name] = "no_solution"
    return out


def test_the_ground_truth_is_what_the_engine_documents(truth):
    """Pins the engine side, so an agreement test cannot pass against a
    ground truth that has itself drifted: floor quotient and a remainder with
    the divisor's sign, failure on zero / unbound / float, one solution per
    in_domain call, `[]` accepted, an atom refused."""
    assert truth == {
        "dm_pos": "[[3,2]]", "dm_negx": "[[-4,1]]", "dm_negy": "[[-4,-1]]",
        "dm_negboth": "[[3,-1]]", "dm_zero": "[]", "dm_unbound": "[]",
        "dm_check_ok": "[1]", "dm_check_no": "[]", "dm_float": "[]",
        "dm_boundvar": "[[-3,3]]",
        "id_var": "[1,2,3]", "id_var_once": "[1]",
        "id_varlist": "[[0,0],[0,1],[1,0],[1,1]]",
        "id_litlist": "[[1,1],[1,2],[2,1],[2,2]]",
        "id_int_in": "[1]", "id_int_out": "[]", "id_intvar": "[1]",
        "id_nil": "[1]", "id_nilvar": "[1]", "id_atom": "[]", "id_single": "[4]",
    }


def _run(binary, flags, pl_path):
    goal = ", ".join(
        f"({n}(L{i}) -> write({n}=L{i}) ; write({n}=no_solution)), nl"
        for i, n in enumerate(CASES)) + ", halt"
    proc = subprocess.run([binary, *flags, str(pl_path), "-g", goal],
                          cwd=pl_path.parent, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)
    return dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line), proc


@pytest.mark.parametrize("dialect", ["iso", "scryer", "trealla"])
@pytest.mark.parametrize("engine, binary, flags", [
    pytest.param("scryer", SCRYER, [], marks=pytest.mark.skipif(
        not os.path.exists(SCRYER), reason="Scryer not built here")),
    pytest.param("trealla", TREALLA, ["-q"], marks=pytest.mark.skipif(
        not os.path.exists(TREALLA), reason="Trealla not built here")),
])
def test_every_case_agrees_with_the_engine(tmp_path, truth, dialect, engine, binary, flags):
    pl = tmp_path / f"d21_{dialect}.pl"
    pl.write_text(LISTS_IMPORT + clausal_source_to_prolog(
        EXPORT_SOURCE, dialect=getattr(Dialect, dialect)()))
    got, proc = _run(binary, flags, pl)
    # A run that stopped early (an error raised mid-goal) prints fewer lines;
    # say so rather than report a handful of "missing" disagreements.
    assert len(got) == len(CASES), (proc.stdout, proc.stderr)
    disagree = {n: (truth[n], got[n].replace(" ", "")) for n in CASES
                if got[n].replace(" ", "") != truth[n]}
    assert disagree == {}


# ── emission shape ────────────────────────────────────────────────────

def _body(src, dialect=None):
    return clausal_source_to_prolog(src, dialect=dialect or Dialect.scryer())


def test_a_list_literal_becomes_ins():
    out = _body("p(A, B) <- (in_domain([A, B], 0, 3))\n")
    assert "ins([A, B], ..(0, 3))" in out
    assert "ins([A, B], 0, 3)" not in out


def test_an_integer_literal_becomes_in():
    assert "in(5, ..(1, 9))" in _body("p() <- (in_domain(5, 1, 9))\n")


def test_a_variable_gets_the_type_dispatch():
    out = _body("p(V) <- (in_domain(V, 1, 9))\n")
    # The dispatch is the clause's whole body here, so it carries no outer
    # brackets (`;` binds looser than `,` but tighter than `:-`).
    assert ("(var(V) ; integer(V)), in(V, ..(1, 9)) ; "
            "nonvar(V), (V == [] ; V = [_|_], ins(V, ..(1, 9)))") in out


def test_divmod_expands_to_floor_division():
    out = _body("p(Q, R) <- (divmod_(17, 5, Q, R))\n")
    for goal in ("integer(17)", "integer(5)", "5 =\\= 0",
                 "Q is div(17, 5)", "R is 17 mod 5"):
        assert goal in out
    assert "divmod(" not in out and "divmod_(" not in out


def test_the_clp_import_brackets_in_and_ins():
    """`[in/2]` is a syntax error in Scryer once clpz's operators are in
    force (a listless clpz import earlier in the file does that); `(in)/2`
    reads on both engines."""
    out = _body("p(V) <- (in_domain(V, 1, 9))\n")
    assert ":- use_module(library(clpz), [(in)/2, (ins)/2])." in out


@pytest.mark.parametrize("dialect", ["iso", "scryer", "swi", "trealla"])
def test_no_dialect_renames_to_a_missing_predicate(dialect):
    out = _body("p(V, Q, R) <- (in_domain(V, 1, 9), divmod_(7, 2, Q, R))\n",
                getattr(Dialect, dialect)())
    assert "ins(V, 1, 9)" not in out and "divmod(" not in out
    assert "in_domain(" not in out and "divmod_(" not in out


def test_gprolog_keeps_its_genuine_three_argument_form():
    out = _body("p(V) <- (in_domain(V, 1, 9))\n", Dialect.gprolog())
    assert "fd_domain(V, 1, 9)" in out
    assert resolve_name("in_domain", Dialect.gprolog()) == "fd_domain"


# ── reverse direction (.pl import) ────────────────────────────────────

def _reverse(body):
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    return prolog_to_clausal(f"p(V, N) :- {body}.\n")


@pytest.mark.parametrize("src", [
    "p(V) <- (in_domain(V, 1, 9))\n",
    "p(A, B) <- (in_domain([A, B], 0, 3))\n",
    "p() <- (in_domain(5, 1, 9))\n",
])
def test_every_forward_shape_reads_back_as_in_domain(src):
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    back = prolog_to_clausal(_body(src))
    assert "in_domain(" in back
    assert " in " not in back and "ins(" not in back and "nonvar(" not in back
    assert "-import_from" not in back       # in/ins were the forward pass's own import


def test_a_disjunction_that_only_resembles_the_dispatch_is_not_folded():
    """Two different targets: a hand-written disjunction, translated as one."""
    back = _reverse("((var(V) ; integer(V)), in(V, ..(1, 9)) ; "
                    "nonvar(N), (N == [] ; N = [_|_], ins(N, ..(1, 9))))")
    assert back.count("in_domain(") == 2          # each clpz call on its own
    assert " or " in back and "nonvar(N)" in back


def test_in_over_something_other_than_a_range_is_not_folded():
    """Only `in(T, Lo..Hi)` is the forward pass's; any other `in/2` keeps the
    reverse map's existing reading (membership, `in_`)."""
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    assert "in_domain" not in prolog_to_clausal("p(V, D) :- in(V, D).\n")


def test_the_iso_dialect_imports_clpfd_as_a_library_not_a_path():
    """The iso dialect used to emit use_module('clausal/logic/clpfd'), a path
    neither engine can load; the agreement test above now runs it."""
    out = clausal_source_to_prolog(
        "-import_from(clausal.logic.clpfd, [in_domain, label])\n"
        "p(V) <- (in_domain(V, 1, 3), label([V]))\n", dialect=Dialect.iso())
    assert "use_module(library(clpz))" in out
    assert "clausal/logic/clpfd" not in out
