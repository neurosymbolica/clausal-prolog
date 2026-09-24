"""call/1 runs a goal TERM of every body shape (ISO 13211-1 §7.6.2).

Step 1 of the ISO ``clause/2`` plan (2026-09-25): a Body that ``clause/2``
hands back must be callable.  Before this, only a predicate-call goal was:
``call(G)`` with ``G`` a conjunction failed SILENTLY, and a comparison,
``if_`` or negation raised ``type_error(callable, ...)``
(``_registry._ensure_trampoline_dispatch`` refuses every AST node).

The central check is the ROW TABLE in ``tests/fixtures/call_body_terms.clausal``:
for each row, ``b(N, X, Y)`` is the goal written as a clause body and
``g(N, X, Y, G)`` builds the same text in term position; ``run(N, X, Y)``
calls it.  Both must answer alike for every input -- the compiled body is the
specification (see ``clausal/logic/builtins/call_body.py`` for the shape table
and the mechanism).

C/Python parity: the same table is re-run in a subprocess with the C
trampoline import blocked, so the whole engine runs on ``_trampoline_py``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var, deref, is_var
from clausal.pythonic_ast import nodes

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "call_body_terms"
OTHER = "call_body_terms_other"
ROWS = range(1, 31)
UNBOUND = "unbound"
INPUTS = (UNBOUND, 0, 1, 2, 3, 9)


def _load(name):
    from clausal.import_hook import _load_module
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = _load_module(name, str(FIXTURES / f"{name}.clausal"))
    return mod.__dict__["$module"]


@pytest.fixture(scope="module")
def host():
    _load(OTHER)
    return _load(HOST)


def _norm(v):
    from clausal.logic.solve import _deref_walk
    v = _deref_walk(v)
    return "_" if is_var(v) else v


def _answers(module, name, *args):
    from clausal.logic.solve import call
    return list(call(name, *args, module=module))


def _row_answers(module, name, n, x):
    X = Var() if x == UNBOUND else x
    Y = Var()
    from clausal.logic.solve import call
    try:
        return [[_norm(X), _norm(Y)] for _ in call(name, n, X, Y, module=module)]
    except LogicException as e:                         # pragma: no cover
        return f"raise {e.term}"


def _term(exc_info):
    return exc_info.value.term


def _formal(term):
    """``error(Formal, Context)`` -> Formal."""
    assert term.functor == "error"
    return term.args[0]


# ── the row table: term position answers exactly as the clause body ─────────


@pytest.mark.parametrize("x", INPUTS)
@pytest.mark.parametrize("n", ROWS)
def test_term_answers_like_the_clause_body(host, n, x):
    body = _row_answers(host, "b", n, x)
    term = _row_answers(host, "run", n, x)
    assert term == body


def test_the_table_is_not_vacuous(host):
    """A table where every row fails on both sides would pass the test
    above: count the rows that actually ANSWER."""
    answering = {n for n in ROWS for x in INPUTS
                 if _row_answers(host, "run", n, x)}
    failing = {n for n in ROWS for x in INPUTS
               if not _row_answers(host, "run", n, x)}
    # Row 13 is ``False``: it never answers, by construction.
    assert set(ROWS) - answering == {13}
    assert len(failing) >= 20       # and most rows also have a failing input


def test_a_residual_constraint_is_posted_like_the_body(host):
    """``X > 0`` with X unbound posts the constraint in both spellings: a
    later ``X is 0`` fails and ``X is 3`` succeeds (rows 1 and 29)."""
    X = Var()
    from clausal.logic.solve import call
    for _ in call("run", 1, X, Var(), module=host):
        assert is_var(deref(X))
        break
    assert _row_answers(host, "run", 29, UNBOUND) == [[3, "_"]]


# ── the five verified defects (2026-09-25), as regressions ──────────────────


def test_defect_t1_comparison_term(host):
    assert len(_answers(host, "t1", 1)) == 1
    assert _answers(host, "t1", 0) == []


def test_defect_t2_conjunction_term_was_silently_empty(host):
    Y = Var()
    got = [deref(Y) for _ in _answers_gen(host, "t2", 1, Y)]
    assert got == [1]


def _answers_gen(module, name, *args):
    from clausal.logic.solve import call
    return call(name, *args, module=module)


def test_defect_t3_comparison_written_in_call(host):
    assert len(_answers(host, "t3", 1)) == 1
    assert _answers(host, "t3", 0) == []


def test_defect_t4_as_written_is_dif_so_the_goal_is_unbound(host):
    """``G is not (X == 1)`` is ``G is not ...`` -- dif(G, X == 1) -- so G
    stays unbound and ``call(G)`` is now the ISO instantiation_error, where it
    used to fail silently for every X."""
    for x in (1, 2):
        with pytest.raises(LogicException) as info:
            _answers(host, "t4", x)
        assert _formal(_term(info)) == "instantiation_error"


def test_defect_t4_with_the_negation_parenthesized(host):
    assert _answers(host, "t4b", 1) == []
    assert len(_answers(host, "t4b", 2)) == 1


def test_defect_t5_if_term(host):
    assert len(_answers(host, "t5", 1)) == 1
    assert _answers(host, "t5", 2) == []


# ── ISO errors ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("pred, extra", [("call_it", ()), ("call_it2", ("x",))])
def test_an_unbound_goal_is_an_instantiation_error(host, pred, extra):
    """Scryer: ``call(_)`` and ``call(_, x)`` -> instantiation_error."""
    with pytest.raises(LogicException) as info:
        _answers(host, pred, Var(), *extra)
    assert _formal(_term(info)) == "instantiation_error"


def _type_error_culprit(host, goal):
    with pytest.raises(LogicException) as info:
        _answers(host, "call_it", goal)
    formal = _formal(_term(info))
    assert formal.functor == "type_error"
    assert formal.args[0] == "callable"
    return formal.args[1]


def test_a_number_in_a_conjunction_is_a_type_error_naming_the_whole_body(host):
    """Scryer: ``call((fail, 1))`` -> type_error(callable, (fail, 1)) -- the
    WHOLE body is checked before anything runs, so the failing first conjunct
    does not hide it."""
    X = Var()
    culprit = _type_error_culprit(host, (("r", 0), 1))
    assert culprit == (("r", 0), 1)
    culprit = _type_error_culprit(host, (1, ("p", X)))
    assert culprit[0] == 1 and culprit[1][0] == "p"
    assert _type_error_culprit(host, (("p", X), 2.5))[1] == 2.5


def test_a_number_under_or_and_if_is_a_type_error(host):
    """Or and if_ are transparent like ISO ``;`` and ``->``.  A culprit holding
    an AST node is its string form (a raw node breaks catch/3 matching)."""
    X = Var()
    culprit = _type_error_culprit(host, nodes.Or(left=("p", X), right=1))
    assert isinstance(culprit, str) and "1" in culprit
    culprit = _type_error_culprit(
        host, nodes.IfExpr(test=("p", X), body=7, orelse=True))
    assert isinstance(culprit, str) and "7" in culprit


def test_a_variable_goal_inside_a_body_is_call_of_it(host):
    """ISO 7.6.2: a Var in a goal position is ``call(V)``, checked when it is
    REACHED -- Scryer ``call((fail, _))`` fails, ``call((true, _))`` raises."""
    assert _answers(host, "call_it", (("r", 0), Var())) == []
    with pytest.raises(LogicException) as info:
        _answers(host, "call_it", (("r", 9), Var()))
    assert _formal(_term(info)) == "instantiation_error"
    G2 = Var()
    X = Var()
    # bound by the time it is reached: runs
    goal = (nodes.Unify(left=G2, right=("s", X)), G2)
    assert [deref(X) for _ in _answers_gen(host, "call_it", goal)] == [2, 3]


def test_the_iso_control_construct_cells_are_still_refused(host):
    """Unchanged: ``(",", A, B)`` is the ISO spelling the surface never
    builds; it stays refused with its own diagnostic, not interpreted."""
    with pytest.raises(LogicException) as info:
        _answers(host, "call_it", (",", ("p", Var()), ("s", Var())))
    assert _formal(_term(info)).args[0] == \
        "callable_control_construct_unsupported"


def test_a_body_node_with_call_n_extras_is_still_refused(host):
    """call/N with extras over a body node is not a body call (Scryer:
    existence_error for ','/3); the pre-existing type_error is kept."""
    with pytest.raises(LogicException) as info:
        _answers(host, "call_it2", nodes.Gt(left=Var(), right=0), 1)
    assert _formal(_term(info)).functor == "type_error"


# ── module qualification, nesting, caching ──────────────────────────────────


def test_a_qualified_body_runs_in_the_named_module(host):
    """``M:(p(X), X > 15)``: M is the context of the WHOLE body, so ``p`` is
    M's (10, 20), not the host's (1, 2)."""
    X = Var()
    goal = (":", OTHER, (("p", X), nodes.Gt(left=X, right=15)))
    assert [deref(X) for _ in _answers_gen(host, "call_it", goal)] == [20]
    X = Var()
    assert [deref(X) for _ in _answers_gen(
        host, "call_it", (("p", X), nodes.Gt(left=X, right=0)))] == [1, 2]


def test_a_qualified_leaf_inside_a_body(host):
    X = Var()
    goal = ((":", OTHER, ("p", X)), nodes.Lt(left=X, right=15))
    assert [deref(X) for _ in _answers_gen(host, "call_it", goal)] == [10]


def test_a_body_nested_in_a_body_via_a_bound_variable(host):
    X, G = Var(), Var()
    inner = (("p", X), ("s", X))
    goal = (nodes.Unify(left=G, right=inner), G)
    assert [deref(X) for _ in _answers_gen(host, "call_it", goal)] == [2]


def test_one_compile_per_shape_not_per_value(host):
    """Argument values are run-time parameters, so calling one shape with
    fifty different values adds at most one compiled query."""
    from clausal.logic import solve as S
    for x in range(3):                     # warm the shape
        _answers(host, "t2", x, Var())
    before = len(S._query_cache)
    for x in range(3, 53):
        assert len(_answers(host, "t2", x, Var())) == 1
    assert len(S._query_cache) - before <= 1


def test_a_tabled_leaf_under_not_is_emitted_as_the_direct_call(host):
    """The compiler picks WFS-sound tabled negation for ``not t(X)`` only when
    it sees the call; a ``call(P)`` wrapper would hide it."""
    from clausal.logic.builtins.call_body import _Converter
    conv = _Converter(host.db)
    node = conv.goal(nodes.Not(operand=("reach", Var())))
    assert isinstance(node.operand, nodes.Call)
    assert node.operand.func.name == "reach"
    node = conv.goal(nodes.Not(operand=("p", Var())))
    assert node.operand.func.name == "call"


# ── C / Python drive-loop parity ────────────────────────────────────────────


_PARITY_SCRIPT = textwrap.dedent(r"""
    import json, sys, warnings
    BLOCK = sys.argv[1] == "py"
    if BLOCK:
        class _Block:
            def find_spec(self, name, path=None, target=None):
                if name == "clausal.logic.runtime._trampoline":
                    raise ImportError("blocked: run on the Python twin")
                return None
        sys.meta_path.insert(0, _Block())
    sys.path.insert(0, sys.argv[2])
    sys.path.insert(0, sys.argv[3])
    import clausal.logic.trampoline as T
    import test_call_runs_body_terms as tc
    host = tc._load(tc.OTHER) and tc._load(tc.HOST)
    out = {"impl": T.StepGenerator.__module__,
           "rows": {f"{n}/{x}": tc._row_answers(host, "run", n, x)
                    for n in tc.ROWS for x in tc.INPUTS}}
    print(json.dumps(out))
""")


def _run_table(which):
    root = Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, "-c", _PARITY_SCRIPT, which, str(root),
         str(Path(__file__).resolve().parent)],
        capture_output=True, text=True, timeout=300, cwd=str(root),
        env={**os.environ, "PYTHONWARNINGS": "ignore"},
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_c_and_python_trampolines_answer_the_table_alike():
    c = _run_table("c")
    py = _run_table("py")
    assert c["impl"] != py["impl"]
    assert py["impl"] == "clausal.logic._trampoline_py"
    assert len(c["rows"]) == len(ROWS) * len(INPUTS) == 180
    assert sum(1 for v in c["rows"].values() if v) >= 30
    assert c["rows"] == py["rows"]
