"""Slice 5: the constraint libraries on the native ``.pl`` front end (plan
native-iso-reader-step2 §4 Slice 5, ruling D9).

* The ops an import installs, by Scryer's rule (measured with the Scryer
  build ``test_l3_s5_exit`` names): use_module/1 installs every op the
  module exports; an import LIST installs the exported ops it names (an op
  the module does not export is not installed) plus every exported op the
  module also declares with a top-level op/3.
* clpz's names as engine builtins, from a ``.pl``, from ``solve`` and from
  the seam in quoted form; a module's own definition of the name wins.
* ``{C}`` lowered to the seam's ``clpq.rational(C)``.

The exit cases (answers identical to Scryer's) are in test_l3_s5_exit.py.
"""
from __future__ import annotations

import os
import subprocess
import textwrap

import pytest

from clausal.tools import iso_l3 as L3

SCRYER = "/workspace/scryer-prolog-clpq/target/release/scryer-prolog"

EXPORTS_OP = ":- module(s5m, [p/1, op(700, xfx, ===>)]).\np(a ===> b).\n"
TOPLEVEL_OP = ":- module(s5m2, [p/1]).\n:- op(700, xfx, ===>).\np(a ===> b).\n"
BOTH = (":- module(s5m4, [p/1, op(700, xfx, ===>)]).\n"
        ":- op(700, xfx, ===>).\np(a ===> b).\n")

#: (importer's directive, the operator its next clause uses, Scryer's
#: verdict: True = the clause reads).  Measured 2026-09-30.
OP_IMPORTS = [
    (":- use_module(s5p/s5m).", "===>", True),
    (":- use_module(s5p/s5m, [p/1]).", "===>", False),
    (":- use_module(s5p/s5m, [p/1, op(700, xfx, ===>)]).", "===>", True),
    (":- use_module(s5p/s5m, [p/1, op(700, xfx, ====>)]).", "====>", False),
    (":- use_module(s5p/s5m2).", "===>", False),
    (":- use_module(s5p/s5m4, [p/1]).", "===>", True),
    (":- use_module(library(clpz), [label/1]).", "#<==>", True),
    (":- use_module(library(lambda), [(\\)/2]).", "+\\", False),
]


def _write(native, rel, text):
    path = native.tmp / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    init = path.parent / "__init__.py"
    if path.parent != native.tmp and not init.exists():
        init.write_text("")
    path.write_text(text, encoding="utf-8")
    dotted = rel.rsplit(".", 1)[0].replace("/", ".")
    native._names.extend([dotted, dotted.split(".")[0]])


def _op_libs(native):
    _write(native, "s5p/s5m.pl", EXPORTS_OP)
    _write(native, "s5p/s5m2.pl", TOPLEVEL_OP)
    _write(native, "s5p/s5m4.pl", BOTH)


@pytest.mark.parametrize("i", range(len(OP_IMPORTS)))
def test_an_import_installs_the_ops_scryer_installs(native, ans, i):
    directive, op, reads = OP_IMPORTS[i]
    _op_libs(native)
    text = f"{directive}\nt(X) :- X = (c {op} d).\n"
    if reads:
        mod = native.load(f"s5_ops{i}", text)
        assert ans(mod, "t") == [(op, "c", "d")]
    else:
        with pytest.raises(SyntaxError) as ei:
            native.load(f"s5_ops{i}", text)
        assert "SyntaxIssue" in str(ei.value) and ":2:" in str(ei.value)


def test_op_import_table_is_scryers_oracle(tmp_path):
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    (tmp_path / "s5p").mkdir()
    (tmp_path / "s5p" / "s5m.pl").write_text(EXPORTS_OP)
    (tmp_path / "s5p" / "s5m2.pl").write_text(TOPLEVEL_OP)
    (tmp_path / "s5p" / "s5m4.pl").write_text(BOTH)
    for i, (directive, op, reads) in enumerate(OP_IMPORTS):
        f = tmp_path / f"imp{i}.pl"
        f.write_text(f"{directive}\nt(X) :- X = (c {op} d).\n")
        proc = subprocess.run(
            [SCRYER, str(f), "-g", "(catch(t(X), _, fail) -> writeq(yes(X)) "
             "; write(no)), nl, halt"],
            cwd=tmp_path, capture_output=True, text=True, timeout=60)
        last = proc.stdout.strip().splitlines()[-1]
        assert last.startswith("yes(") == reads, (directive, proc.stdout)


# ── clpz builtins ──


def test_label_from_library_clpz_is_leftmost_first(native, ans):
    mod = native.load("s5_lab", ":- use_module(library(clpz)).\n"
                                "t([X,Y]) :- X in 1..3, Y in 1..2, label([X,Y]).\n")
    assert ans(mod, "t") == [[1, 1], [1, 2], [2, 1], [2, 2], [3, 1], [3, 2]]


def test_label_named_in_an_import_list_is_scryers_too(native, ans):
    mod = native.load("s5_lab2", ":- use_module(library(clpz), [label/1]).\n"
                                 "t([X,Y]) :- X in 1..3, Y in 1..2, label([X,Y]).\n")
    assert ans(mod, "t")[:2] == [[1, 1], [1, 2]]


def test_a_module_s_own_label_wins_over_the_library_s(native, ans):
    mod = native.load("s5_lab3", ":- use_module(library(clpz)).\n"
                                 "label(X) :- X = [mine].\n"
                                 "t(X) :- label(X).\n")
    assert ans(mod, "t") == [["mine"]]


def test_a_module_s_own_in_2_wins_over_the_builtin(native, ans):
    mod = native.load("s5_in", ":- use_module(library(clpz)).\n"
                               "X in Y :- X = Y.\n"
                               "t(X) :- X in 1..3.\n")
    assert ans(mod, "t") == [("..", 1, 3)]


def test_call_label_is_the_engine_s_OPEN_divergence(native, ans):
    """Pinned, not blessed: a META-called ``label/1`` resolves to the
    engine's global label/1 (first-fail), because call/N consults the
    builtin registry before a module's imports; a compiled call gets
    Scryer's (leftmost).  Scryer answers leftmost for both."""
    mod = native.load("s5_lab4", ":- use_module(library(clpz)).\n"
                                 "t(L) :- X in 1..3, Y in 1..2, "
                                 "G = label([X,Y]), call(G), L = [X,Y].\n")
    assert ans(mod, "t")[:2] == [[1, 1], [2, 1]]


def test_the_builtins_from_solve(tmp_path, monkeypatch):
    import importlib
    import sys
    import clausal
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    assert clausal.__file__.startswith(root), (clausal.__file__, root)
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var, walk
    (tmp_path / "s5_empty.clausal").write_text("s5_anchor(1),\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    sys.modules.pop("s5_empty", None)
    try:
        mod = importlib.import_module("s5_empty")
        X, B = Var(), Var()
        goal = ("call", (",", ("in", X, ("..", 0, 4)),
                         (",", ("#<==>", B, ("#>", X, 2)),
                          ("labeling", [], [X]))))
        got = [(walk(X), walk(B)) for _ in solve(goal, mod)]
    finally:
        sys.modules.pop("s5_empty", None)
    assert got == [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1)]


def test_the_builtins_from_the_seam_in_quoted_form(native, ans):
    mod = native.load("s5_seam", textwrap.dedent("""\
        -module(s5_seam, [t/1, u/1, down])
        t(P) <- ('ins'([X, Y], '\\\\/'(0, 1)), '#<==>'(B, '#='(X, Y)),
                 labeling([down], [X, Y]), P is [X, Y, B])
        u(X) <- ('in'(X, '\\\\/'(3, '\\\\/'(1, 7))), labeling([], [X]))
        """), suffix=".seam", frontend=None)
    assert ans(mod, "t") == [[1, 1, 1], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert ans(mod, "u") == [1, 3, 7]


def test_labeling_min_max_optimisation_is_refused_loudly(native, ans):
    from clausal.logic.exceptions import LogicException
    mod = native.load("s5_opt", ":- use_module(library(clpz)).\n"
                                "t(X) :- X in 1..3, labeling([max(X)], [X]).\n")
    with pytest.raises(LogicException) as ei:
        ans(mod, "t")
    assert "min(Expr)/max(Expr)" in str(ei.value)


def test_a_reified_comparison_over_abs_is_accepted(native, ans):
    """Scryer accepts ``B #<==> (abs(X) #= 2)``.  It was refused ("abs/1
    over a variable is not supported") while clpfd had no propagator for
    abs/1; abs/min/max are now lifted into their own propagators, so it
    answers as Scryer does.  A partial operand under it (``X // Y``) is
    still refused -- posted outside the reification it would prune Y = 0.
    A GROUND abs folds."""
    from clausal.logic.exceptions import LogicException
    mod = native.load("s5_rabs", ":- use_module(library(clpz)).\n"
                                 "t(X-B) :- X in -3..3, B #<==> (abs(X) #= 2), "
                                 "label([X, B]).\n"
                                 "u(B) :- B #<==> (abs(-2) #= 2).\n"
                                 "v(B) :- B #<==> (abs(X // Y) #= 2).\n")
    assert ans(mod, "t") == [("-", x, int(abs(x) == 2)) for x in range(-3, 4)]
    assert ans(mod, "u") == [1]
    with pytest.raises(LogicException) as ei:
        ans(mod, "v")
    assert "clpz_expression" in str(ei.value)


def test_a_local_label_at_another_arity_is_refused(native):
    with pytest.raises(SyntaxError) as ei:
        native.load("s5_lab5", ":- use_module(library(clpz)).\n"
                               "label(A, B) :- A = B.\n")
    assert "label/2 is defined here and label/1 is imported" in str(ei.value)


# ── clpq ──


def test_braces_without_library_clpq_are_an_ordinary_goal(native, ans):
    """As in Scryer: without the import, ``{X = 1}`` calls ``{}/1``."""
    from clausal.predicate_diagnostics import PredicateNotFoundError
    mod = native.load("s5_qnoimp", "t(X) :- {X = 1}.\n")
    with pytest.raises(PredicateNotFoundError, match="{}"):
        ans(mod, "t")


def test_clpq_braces_lower_to_the_seams_clpq_rational():
    mod, _stats, _ = L3.lower_module(":- use_module(library(clpq)).\n"
                                 "t(X) :- {X + 1 = 3, X >= 0}.\n")
    import ast
    text = ast.unparse(mod)
    assert "$LoadAttr(object=$LoadName(name='clpq'" in text
    assert "attr='rational'" in text
    assert "$TupleLiteral(elements=[$ArithEq(left=$Add(" in text
    assert "$GtE(" in text


@pytest.mark.parametrize("body, what", [
    ("{X ; Y}", "is not a constraint"),
    ("{X = foo(1)}", "is not a linear arithmetic expression"),
])
def test_a_clpq_brace_goal_it_cannot_lower_is_refused(native, body, what):
    with pytest.raises(SyntaxError) as ei:
        native.load("s5_qbad", f":- use_module(library(clpq)).\n"
                               f"t(X, Y) :- {body}.\n")
    assert what in str(ei.value) and ":2:" in str(ei.value)


def test_braces_as_data_stay_data(native, ans):
    mod = native.load("s5_qdata", "t(X) :- X = {a, b}.\n")
    assert ans(mod, "t") == [("{}", (",", "a", "b"))]
