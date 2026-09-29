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

import datetime
import json
import os
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var, deref, is_var
from clausal.pythonic_ast import nodes

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "call_body_terms"
OTHER = "call_body_terms_other"
ROWS = range(1, 37)
UNBOUND = "unbound"


class Opaque:
    """A value with no literal lowering and no hash (roborev on 152a8f64)."""
    __hash__ = None

    def __init__(self, tag):
        self.tag = tag

    def __eq__(self, other):
        return isinstance(other, Opaque) and other.tag == self.tag

    def __repr__(self):
        return f"Opaque({self.tag!r})"


DATE = datetime.date(2026, 9, 25)
INPUTS = (UNBOUND, 0, 1, 2, 3, 9, DATE, Opaque("o"))


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
    except LogicException as e:
        formal = cell_args(e.term)[0]
        return f"raise {cell_functor(formal) if type(formal) is tuple else formal}"
    except TypeError as e:
        # Only a DATE / Opaque input may meet a Python TypeError (``date > 0``
        # is one in BOTH spellings).  Anything else -- a converter crash --
        # propagates and fails the test (roborev on 4b4323ed).
        if isinstance(x, (datetime.date, Opaque)):
            return "raise TypeError"
        raise


def _term(exc_info):
    return exc_info.value.term


def _formal(term):
    """``error(Formal, Context)`` -> Formal."""
    assert type(term) is tuple and cell_functor(term) == "error"
    return cell_args(term)[0]


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
    # Only list-valued answers count: a "raise ..." string is not an answer.
    got = [(n, _row_answers(host, "run", n, x)) for n in ROWS for x in INPUTS]
    answering = {n for n, v in got if isinstance(v, list) and v}
    failing = {n for n, v in got if v == []}
    # Rows 13 and 33 fail by construction (``False``; ``..., fail``).
    assert set(ROWS) - answering == {13, 33}
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


def test_values_without_a_literal_lowering_reach_the_body(host):
    """roborev on 152a8f64: rows 31 (``Y is X, X == Y``) and 32 (``Y is X,
    X is Y``) with a date and an opaque unhashable object answer, in both
    spellings (the row test compares them)."""
    for x in (DATE, Opaque("o")):
        for n in (31, 32):
            assert _row_answers(host, "run", n, x) == [[x, x]], n
            assert _row_answers(host, "b", n, x) == [[x, x]], n


def test_fail_as_a_compiled_goal_is_failure(host):
    """Operator ruling 2026-09-25 (item 3): ``fail`` in a clause body used to
    be a call of an undefined fail/0 -- existence_error.  Rows 6 and 33-35
    are the compiled side of the table; these pin it directly."""
    assert _row_answers(host, "b", 6, 2) == []
    assert _row_answers(host, "b", 6, 1) == [[1, "_"]]
    assert _row_answers(host, "b", 33, UNBOUND) == []
    assert [a[0] for a in _row_answers(host, "b", 34, UNBOUND)] == [1, 2]
    assert [a[0] for a in _row_answers(host, "b", 35, UNBOUND)] == [1, 2]
    assert [a[0] for a in _row_answers(host, "b", 36, UNBOUND)] == [1, 2]


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
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal)[0] == "callable"
    return cell_args(formal)[1]


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


def _existence_indicator(host, pred, *args):
    with pytest.raises(LogicException) as info:
        _answers(host, pred, *args)
    formal = _formal(_term(info))
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[0] == "procedure"
    ind = cell_args(formal)[1]
    assert cell_functor(ind) == "/"
    return tuple(cell_args(ind))


def test_the_iso_control_construct_cells_run_as_bodies(host):
    """Operator ruling 2026-09-25 (item 4): ``(",", A, B)``, ``(";", A, B)``
    and ``("\\+", G)`` -- the runtime spelling is the str ``\\+`` -- run
    through the same converter as the Clausal spellings, nested too."""
    X = Var()
    got = [deref(X) for _ in _answers_gen(
        host, "call_it", (",", ("p", X), ("s", X)))]
    assert got == [2]
    X = Var()
    got = [deref(X) for _ in _answers_gen(
        host, "call_it", (";", ("p", X), ("s", X)))]
    assert got == [1, 2, 2, 3]
    X = Var()
    got = [deref(X) for _ in _answers_gen(
        host, "call_it", (",", ("p", X), ("\\+", ("s", X))))]
    assert got == [1]
    assert _answers(host, "call_it", ("\\+", ("p", 1))) == []
    # A number inside is the whole-body type_error, through the cells too.
    assert _type_error_culprit(host, (",", ("r", 0), 1)) == (",", ("r", 0), 1)


@pytest.mark.parametrize("functor", ["->", "*->"])
def test_committed_choice_cells_are_refused(host, functor):
    """``->`` and ``*->``: cut-free, no committed choice (ruled forever).
    existence_error(procedure, '->'/2) -- what an ISO system that lacks a
    construct answers -- with the reason in the message."""
    cell = (functor, ("p", Var()), ("s", Var()))
    assert _existence_indicator(host, "call_it", cell) == (functor, 2)
    with pytest.raises(LogicException) as info:
        _answers(host, "call_it", cell)
    assert "no committed choice" in info.value.message
    assert "if_(" in info.value.message


@pytest.mark.parametrize("goal, indicator", [
    ((("p", 1), ("s", 2)), (",", 3)),                  # call((A, B), X)
    (nodes.Or(left=("p", 1), right=("s", 2)), (";", 3)),
    (nodes.Not(operand=("p", 1)), ("\\+", 2)),
    (nodes.IfExpr(test=("p", 1), body=True, orelse=False), ("if_", 4)),
    (nodes.Gt(left=1, right=0), (">", 3)),
    # ISO names, checked on the box's Scryer (roborev on 4b4323ed: the
    # Clausal spelling ``==`` is both ArithEq and StructuralEq)
    (nodes.ArithEq(left=1, right=1), ("=:=", 3)),
    (nodes.StructuralEq(left=1, right=1), ("==", 3)),
    (nodes.ArithNeq(left=1, right=2), ("=\\=", 3)),
    (nodes.StructuralNeq(left=1, right=2), ("\\==", 3)),
    (nodes.Unify(left=1, right=1), ("=", 3)),
    (nodes.DoesNotUnify(left=1, right=2), ("\\=", 3)),
    (nodes.Lt(left=0, right=1), ("<", 3)),
    (nodes.LtE(left=0, right=1), ("=<", 3)),
    (nodes.GtE(left=1, right=0), (">=", 3)),
    ((",", ("p", 1), ("s", 2)), (",", 3)),              # the ISO cell
    ((";", ("p", 1), ("s", 2)), (";", 3)),
    (("\\+", ("p", 1)), ("\\+", 2)),
    (("->", ("p", 1), ("s", 2)), ("->", 3)),
    (True, ("true", 1)),
    ("true", ("true", 1)),
    ("fail", ("fail", 1)),
    ([1, 2], (".", 3)),
])
def test_call_n_extras_on_a_construct_name_no_procedure(host, goal, indicator):
    """Operator ruling 2026-09-25 (item 2), Scryer on the box:
    ``call((true,true),x)`` -> existence_error(procedure, ','/3);
    ``;``/3, ``\\+``/2, ``->``/3, ``true``/1, ``'.'/3`` alike."""
    assert _existence_indicator(host, "call_it2", goal, "x") == indicator


@pytest.mark.parametrize("goal", [
    42, 3.5, ("()", 1, 2), (tuple, 1, 2),
    nodes.Not(operand=1),                      # call(not 1): Not runs call(1)
])
def test_a_non_callable_top_level_goal_is_a_type_error(host, goal):
    """Operator ruling 2026-09-25 (item 1), retiring the translator's
    "section 4.2" silent-failure contract: Scryer ``call(42)``,
    ``call([a])``, ``call(\\+ 1)`` -> type_error(callable, G)."""
    with pytest.raises(LogicException) as info:
        _answers(host, "call_it", goal)
    formal = _formal(_term(info))
    assert cell_functor(formal) == "type_error" and cell_args(formal)[0] == "callable"


def test_a_list_or_string_goal_names_the_missing_procedure(host):
    """FLIPPED from round 2's type_error, operator rule 2026-09-25, ISO first: a non-empty list or string is the callable compound '.'/2, so call/1 of one names the missing procedure '.'/2; Scryer disagrees with itself (literal call([a]) -> existence_error, run-time G = [a], call(G) -> type_error).  ``call([1, 2])`` and
    ``call("ab")`` -> existence_error(procedure, '.'/2); with an extra
    argument the fold names '.'/3."""
    from clausal.logic.cells import chars
    for goal in ([1, 2], chars("ab")):
        assert _existence_indicator(host, "call_it", goal) == (".", 2)
        assert _existence_indicator(host, "call_it2", goal, "x") == (".", 3)


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


def test_one_compile_per_shape_not_per_value(host, monkeypatch):
    """Argument values are run-time parameters, so calling one shape with
    fifty different values compiles it ONCE.  Counts compiles directly (the
    query cache is FIFO-capped, so its size could pass vacuously); the
    positive control is the first call, which must compile."""
    import clausal.logic.compiler as C
    from clausal.logic import solve as S
    real = C.compile_predicate_trampoline
    compiles = []

    def counting(name, *a, **k):
        if name == "_query":
            compiles.append(name)
        return real(name, *a, **k)

    monkeypatch.setattr(C, "compile_predicate_trampoline", counting)
    S._query_cache.clear()
    assert len(_answers(host, "t2", 1, Var())) == 1
    assert len(compiles) == 1                    # positive control
    for x in range(2, 52):
        assert len(_answers(host, "t2", x, Var())) == 1
    assert len(compiles) == 1


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
    tc._load(tc.OTHER)
    host = tc._load(tc.HOST)
    out = {"impl": T.StepGenerator.__module__,
           "rows": {f"{n}/{x!r}": tc._row_answers(host, "run", n, x)
                    for n in tc.ROWS for x in tc.INPUTS}}
    print(json.dumps(out, default=repr))
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
    assert len(c["rows"]) == len(ROWS) * len(INPUTS) == 36 * 8
    assert sum(1 for v in c["rows"].values() if isinstance(v, list) and v) >= 30
    assert c["rows"] == py["rows"]


# ── ruling A: ``fail`` needs no declaration ─────────────────────────────────


def test_fail_needs_no_declaration(host):
    """Operator ruling 2026-09-25 (A): the fixture does NOT declare ``fail``
    and still loads; as a goal it fails (rows 6, 33-35), and in term position
    it is the ATOM ``fail`` (ISO), not a truth value."""
    X = Var()
    assert [deref(X) for _ in _answers_gen(host, "fail_atom", X)] == ["fail"]
    assert _answers(host, "call_it", "fail") == []
    assert _answers(host, "call_it", False) == []


# ── ruling B: goal-taking list builtins, phrase, time_goal ─────────────────


_LIST_BUILTIN_CALLS = [
    ("maplist", (42, [1])),
    ("maplist", (42, [1], Var())),
    ("maplist", (42, [1], [2], Var())),
    ("maplist", (42, [1], [2], [3], Var())),
    ("maplist", (42, [1], [2], [3], [4], Var())),
    ("maplist", (42, [1], [2], [3], [4], [5], Var())),
    ("maplist", (42, [1], [2], [3], [4], [5], [6], Var())),
    ("include", (42, [1], Var())),
    ("exclude", (42, [1], Var())),
    ("foldl", (42, [1], 0, Var())),
    ("foldl", (42, [1], [2], 0, Var())),
    ("foldl", (42, [1], [2], [3], 0, Var())),
    ("map_list_to_pairs", (42, [1], Var())),
    ("take_while", (42, [1], Var())),
    ("drop_while", (42, [1], Var())),
    ("span", (42, [1], Var(), Var())),
    ("group_by", (42, [1], Var())),
    ("sort_by", (42, [1], Var())),
    ("max_by", (42, [1], Var())),
    ("min_by", (42, [1], Var())),
    ("filter_map", (42, [1], Var())),
    ("partition", (42, [1], Var(), Var())),
    ("tfilter", (42, [1], Var())),
    ("tpartition", (42, [1], Var(), Var())),
]


def test_the_table_covers_every_goal_first_list_builtin():
    from clausal.logic.builtins.higher_order import _GOAL_FIRST_LIST_BUILTINS
    assert sorted((n, len(a)) for n, a in _LIST_BUILTIN_CALLS) == \
        sorted(_GOAL_FIRST_LIST_BUILTINS)


@pytest.mark.parametrize("name, args", _LIST_BUILTIN_CALLS,
                         ids=[f"{n}/{len(a)}" for n, a in _LIST_BUILTIN_CALLS])
def test_a_list_builtin_with_a_non_callable_goal_raises(host, name, args):
    """Operator ruling 2026-09-25 (B), Scryer: ``maplist(42, [1])`` ->
    type_error(callable, 42).  It used to fail silently."""
    from clausal.logic.solve import solve
    goal = (name,) + tuple(args)
    with pytest.raises(LogicException) as info:
        list(solve(goal, host))
    formal = _formal(_term(info))
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal)[0] == "callable" and cell_args(formal)[1] == 42


def test_the_goal_is_checked_only_when_called_as_in_scryer(host):
    """Scryer: ``maplist(42, [])`` succeeds -- the goal is never called."""
    from clausal.logic.solve import solve
    assert len(list(solve(("maplist", 42, []), host))) == 1


@pytest.mark.parametrize("rule", [42, 4.5, ("()", 1, 2), None])
@pytest.mark.parametrize("arity", [2, 3])
def test_phrase_of_a_non_callable_is_a_type_error(host, rule, arity):
    """Scryer: ``phrase(42, L)`` -> type_error(callable, 42) (it used to
    fail).  Tuple data and None are non-goals the same way."""
    from clausal.logic.solve import solve
    goal = ("phrase", rule, Var()) + ((Var(),) if arity == 3 else ())
    with pytest.raises(LogicException) as info:
        list(solve(goal, host))
    formal = _formal(_term(info))
    assert cell_functor(formal) == "type_error" and cell_args(formal)[0] == "callable"


@pytest.mark.parametrize("arity", [2, 3])
def test_phrase_of_a_list_or_string_keeps_failing(host, arity):
    """Pinned as-is: a list or string rule is a DCG TERMINAL, not a
    non-callable, so ruling B leaves it alone -- it fails, as it always has.
    NOTE this is NOT Scryer: ``phrase([a], L)`` gives ``L = [a]`` and
    ``phrase("ab", L)`` gives ``L = [a, b]`` there (box, 2026-09-25).
    Supporting terminal rules is a feature, parked in the report."""
    from clausal.logic.cells import chars
    from clausal.logic.solve import solve
    for rule in (["a"], chars("ab")):
        goal = ("phrase", rule, Var()) + ((Var(),) if arity == 3 else ())
        assert list(solve(goal, host)) == []


def test_time_goal_is_call_1_timed(host, capsys):
    """time_goal now answers what call/1 answers for every shape: a body and
    a qualified body run, a non-callable is type_error, unbound is
    instantiation_error (it used to fail for all of them)."""
    from clausal.logic.solve import solve
    X = Var()
    assert [deref(X) for _ in solve(
        ("time_goal", (("p", X), ("s", X))), host)] == [2]
    X = Var()
    assert [deref(X) for _ in solve(
        ("time_goal", (":", OTHER, ("p", X))), host)] == [10, 20]
    for goal, functor in ((42, "type_error"), (Var(), "instantiation_error")):
        with pytest.raises(LogicException) as info:
            list(solve(("time_goal", goal), host))
        f = _formal(_term(info))
        assert (cell_functor(f) if type(f) is tuple else f) == functor


# ── round 4: runtime cells / atoms / unbound goals in the list builtins ─────


def _ml(host, goal, *rest):
    from clausal.logic.solve import solve
    return list(solve(("maplist", goal) + rest, host))


def test_a_runtime_cell_goal_folds_like_call_n(host):
    """Operator ruling 2026-09-25, Scryer: ``maplist(p(1), L)`` calls
    ``p(1, E)`` per element -- it used to fail silently."""
    assert len(_ml(host, ("edge", 1), [2])) == 1
    assert _ml(host, ("edge", 1), [3]) == []
    from clausal.logic.solve import solve
    assert len(list(solve(("maplist", ("edge", 1), [2, 2]), host))) == 1


def test_a_plain_atom_goal_is_resolved_in_the_calling_module(host):
    assert len(_ml(host, "p", [1, 2])) == 1
    assert _ml(host, "p", [1, 5]) == []
    from clausal.logic.solve import solve
    L = Var()
    assert [deref(L) for _ in solve(("include", "s", [1, 2, 3], L), host)] \
        == [[2, 3]]


def test_a_qualified_goal_resolves_in_its_module(host):
    assert len(_ml(host, (":", OTHER, "p"), [10, 20])) == 1
    assert _ml(host, (":", OTHER, "p"), [1]) == []


def test_a_body_term_goal_is_call_n_of_it(host):
    """``maplist(X > 0, [1])`` is ``call(X > 0, 1)`` -- existence_error
    (>)/3 in Scryer and here."""
    with pytest.raises(LogicException) as info:
        _ml(host, nodes.Gt(left=Var(), right=0), [1])
    formal = _formal(_term(info))
    assert cell_functor(formal) == "existence_error"
    assert tuple(cell_args(cell_args(formal)[1])) == (">", 3)


@pytest.mark.parametrize("name, args", _LIST_BUILTIN_CALLS,
                         ids=[f"{n}/{len(a)}" for n, a in _LIST_BUILTIN_CALLS])
def test_an_unbound_goal_is_an_instantiation_error_per_element(host, name, args):
    """Operator ruling 2026-09-25, Scryer: ``maplist(_, [1])`` ->
    instantiation_error; the goal is reached only per element, so
    ``maplist(_, [])`` succeeds (box: maplist/2, maplist/3, foldl/4)."""
    from clausal.logic.solve import solve
    goal = (name, Var()) + tuple(args[1:])
    with pytest.raises(LogicException) as info:
        list(solve(goal, host))
    assert _formal(_term(info)) == "instantiation_error"


def test_an_unbound_goal_over_an_empty_list_succeeds(host):
    from clausal.logic.solve import solve
    assert len(list(solve(("maplist", Var(), []), host))) == 1
    assert len(list(solve(("maplist", Var(), [], []), host))) == 1
    L = Var()
    assert [deref(L) for _ in solve(("foldl", Var(), [], 0, L), host)] == [0]


def test_list_and_string_goals_answer_as_call_n_does(host):
    """FLIPPED, operator rule 2026-09-25 (check ISO first).  Core 13211-1
    has no maplist, but the WG17 Prolog prologue DEFINES it through call/N::

        maplist(G, [E|Es]) :- call(G, E), maplist(G, Es).

    (include/exclude/foldl the same way), so each element answers exactly
    what ``call(G, E)`` answers.  ``call([a], 1)`` / ``call("ab", 1)`` is
    ``existence_error(procedure, '.'/3)`` -- the fold makes the compound
    '.'/3 -- and so are ``maplist([a], [1])`` and ``maplist("ab", [1])``.

    Scryer DIFFERS (box, 2026-09-25): its maplist gives
    ``type_error(callable, [a])``.  The cause is NOT module qualification --
    checked: ``call(lists:[a], 1)`` and ``call(user:[a], 1)`` both give
    existence_error '.'/3 there.  It is that Scryer's RUNTIME call/N refuses
    a list goal (``G = [a], call(G, 1)`` -> type_error(callable, [a])),
    while a LITERAL ``call([a], 1)`` is expanded at compile time into the
    goal '.'(a, [], 1) (-> existence_error).  maplist hands call/N a runtime
    goal, so it inherits the type_error.  ISO decides otherwise: ``[a]`` is
    the compound '.'(a, []), which IS callable, so the fold makes '.'/3 and
    no such procedure exists -- existence_error, which is what this engine
    answers for both spellings."""
    from clausal.logic.cells import chars
    for goal in (["a"], chars("ab")):
        with pytest.raises(LogicException) as info:
            _ml(host, goal, [1])
        formal = _formal(_term(info))
        assert cell_functor(formal) == "existence_error"
        assert tuple(cell_args(cell_args(formal)[1])) == (".", 3)
        assert _existence_indicator(host, "call_it2", goal, 1) == (".", 3)


def _solve_all(host, goal):
    from clausal.logic.solve import solve
    return list(solve(goal, host))


def _outs(host, goal, out):
    from clausal.logic.solve import solve
    return [deref(out) for _ in solve(goal, host)]


def test_qualified_goals_in_include_and_foldl(host):
    """``(":", M, G)`` resolves in M for every builtin, as call/N does."""
    L = Var()
    assert _outs(host, ("include", (":", OTHER, "p"), [1, 10, 20, 3], L),
                 L) == [[10, 20]]
    assert len(_solve_all(host, ("maplist", (":", OTHER, "p"), [10]))) == 1


def test_cell_and_body_goals_in_maplist_include_foldl(host):
    """A cell goal folds; a body term is ``call(Body, E)``
    -- the fold names ``(>)/3`` etc., existence_error, as call/N says."""
    L = Var()
    assert _outs(host, ("include", ("edge", 1), [2, 3], L),
                 L) == [[2]]
    assert len(_solve_all(host, ("maplist", ("edge", 1), [2]))) == 1
    body = nodes.Gt(left=Var(), right=0)
    for goal, ind in (
            (("maplist", body, [1]), (">", 3)),
            (("include", body, [1], Var()), (">", 3)),
            (("foldl", body, [1], 0, Var()), (">", 5)),
            (("maplist", (("p", 1), ("s", 2)), [1]), (",", 3))):
        with pytest.raises(LogicException) as info:
            _solve_all(host, goal)
        formal = _formal(_term(info))
        assert cell_functor(formal) == "existence_error", goal
        assert tuple(cell_args(cell_args(formal)[1])) == ind


def test_a_handle_to_the_callers_own_module(host):
    """A mangled predicate HANDLE naming the calling module's own predicate
    stays on the goal-OBJECT route (``is_declared_predicate_name`` with the
    caller's db) and runs."""
    from clausal.logic.atoms import mangle
    handle = mangle(HOST, "p")
    assert len(_solve_all(host, ("maplist", handle, [1, 2]))) == 1
    assert _solve_all(host, ("maplist", handle, [1, 5])) == []
    L = Var()
    assert _outs(host, ("include", handle, [0, 1, 2, 3], L), L) == [[1, 2]]


def test_every_list_builtin_is_covered_for_the_unbound_goal():
    """The unbound-goal test above is parametrized over ALL 24 builtins --
    confirm the parametrization is the registry's list, not a subset."""
    from clausal.logic.builtins.higher_order import _GOAL_FIRST_LIST_BUILTINS
    assert len(_LIST_BUILTIN_CALLS) == len(_GOAL_FIRST_LIST_BUILTINS) == 24
