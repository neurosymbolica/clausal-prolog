"""call/N runs a SPECIAL-FORM cell and a ModulePredicate cell exactly as the
same goal runs written in a clause body.

Before this (main 8b02f4f8) both failed SILENTLY:

    call(("findall", X, ("p", X), L))           -> no answer
    call(("match", "\\\\d+", "123"))              -> no answer   (py.re match)

and neither could be BUILT in term position: ``G is findall(X, p(X), L)``
raised NameError "not in scope as a term class", ``G is match(P, S)``
TypeError "'ModulePredicate' object is not callable".

The special forms are the goals the compiler lowers inline
(``terms_to_goalop``'s MetaCall arms and ``eval_/2``); ``call_body.
SPECIAL_FORMS`` is the table, held to the compiler below in both directions.

The central check is the ROW TABLE in
``tests/fixtures/call_special_forms.clausal``: ``b(N, X, Y)`` is the goal
written as a clause body, ``g(N, X, Y, G)`` builds the same text in term
position, ``run(N, X, Y)`` calls it.  The Python-built cells below do not
depend on the term-position half, so they fail on main as well.

C/Python parity: the table is re-run in a subprocess with the C trampoline
import blocked (the ``test_call_runs_body_terms`` pattern).
"""
from __future__ import annotations

import datetime
import json
import os
import re
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
HOST = "call_special_forms"
RE_HOST = "call_special_forms_re"
ROWS = range(1, 35)
UNBOUND = "unbound"
DATE = datetime.date(2026, 9, 25)
INPUTS = (UNBOUND, 0, 1, 2, 3, DATE)


def _load(name):
    from clausal.import_hook import _load_module
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = _load_module(name, str(FIXTURES / f"{name}.clausal"))
    return mod.__dict__["$module"]


@pytest.fixture(scope="module")
def host():
    return _load(HOST)


@pytest.fixture(scope="module")
def re_host():
    return _load(RE_HOST)


def _norm(v):
    from clausal.logic.solve import _deref_walk
    v = _deref_walk(v)
    if is_var(v):
        return "_"
    if isinstance(v, (list, tuple)):
        return type(v)(_norm(e) for e in v)
    return v


def _row_answers(module, name, n, x):
    from clausal.logic.solve import call
    X = Var() if x == UNBOUND else x
    Y = Var()
    try:
        return [[_norm(X), _norm(Y)] for _ in call(name, n, X, Y, module=module)]
    except LogicException as e:
        return f"raise {_norm(e.term)!r}"
    except TypeError as e:
        # eval_(X + 1, Y) with X unbound or a date is a Python TypeError in
        # BOTH spellings (row 15); anything else is a converter crash.
        if n == 15:
            return "raise TypeError"
        raise


def _call(module, *args, out=()):
    """Answers of ``call(*args)`` as run from *module*: per answer, the
    normalised values of the Vars in *out*, read WHILE the answer stands."""
    from clausal.logic.solve import call
    return [tuple(_norm(v) for v in out)
            for _ in call("call", *args, module=module)]


def _formal(exc_info):
    term = exc_info.value.term
    assert term.functor == "error"
    return term.args[0]


# ── the row table: term position answers exactly as the clause body ─────────


@pytest.mark.parametrize("x", INPUTS)
@pytest.mark.parametrize("n", ROWS)
def test_term_answers_like_the_clause_body(host, n, x):
    body = _row_answers(host, "b", n, x)
    assert _row_answers(host, "run", n, x) == body


def test_the_table_is_not_vacuous(host):
    answered = [n for n in ROWS if _row_answers(host, "b", n, 2)
                and isinstance(_row_answers(host, "b", n, 2), list)]
    # 5 and 10 fail by design; everything else answers at X = 2.
    assert len(answered) >= 30, answered


def test_the_table_covers_every_special_form(host):
    """Every special form but halt/0,1 (below) has a row in the fixture."""
    from clausal.logic.builtins.call_body import SPECIAL_FORMS
    text = (FIXTURES / f"{HOST}.clausal").read_text()
    missing = [name for (name, _) in SPECIAL_FORMS
               if name != "halt" and f"{name}(" not in text]
    assert not missing


# ── the table is the compiler's: both directions ────────────────────────────


def _lowered(name, arity):
    from clausal.logic.compiler.terms_to_goalop import _convert
    return _convert(nodes.Call(func=nodes.LoadName(name=name),
                               args=[Var() for _ in range(arity)],
                               kwargs=[]), None)


def test_every_table_entry_is_lowered_inline_by_the_compiler():
    from clausal.logic.builtins.call_body import SPECIAL_FORMS
    from clausal.logic.compiler.ir import SubCall
    assert len(SPECIAL_FORMS) == 18
    for (name, arity), roles in SPECIAL_FORMS.items():
        assert len(roles) == arity, name
        assert not isinstance(_lowered(name, arity), SubCall), (name, arity)


def test_every_compiler_meta_kind_is_in_the_table():
    import typing
    from clausal.logic.builtins.call_body import SPECIAL_FORMS
    from clausal.logic.compiler.ir import MetaKind
    kinds = set(typing.get_args(MetaKind)) - {"naf_tabled"}
    assert kinds
    assert kinds <= {name for name, _ in SPECIAL_FORMS}


def test_a_neighbouring_arity_is_an_ordinary_call():
    from clausal.logic.builtins.call_body import is_special_form
    from clausal.logic.compiler.ir import SubCall
    for name, arity in (("once", 2), ("findall", 4), ("throw", 0)):
        assert isinstance(_lowered(name, arity), SubCall)
        assert not is_special_form(name, arity)


# ── Python-built cells (these do not need the term-position half) ──────────


def test_a_findall_cell_runs(host):
    X, L = Var(), Var()
    assert [a for (a,) in _call(host, ("findall", X, ("p", X), L), out=(L,))] \
        == [[1, 2, 3]]


def test_call_n_folds_onto_a_special_form(host):
    X, L = Var(), Var()
    assert [a for (a,) in _call(host, ("findall", X, ("p", X)), L, out=(L,))] \
        == [[1, 2, 3]]
    X, L = Var(), Var()
    assert [a for (a,) in _call(host, "findall", X, ("p", X), L, out=(L,))] \
        == [[1, 2, 3]]
    X = Var()
    assert [a for (a,) in _call(host, "once", ("p", X), out=(X,))] == [1]
    E = Var()
    assert [a for (a,) in _call(host, "catch", ("throw", "oops"), E,
                                    True, out=(E,))] == ["oops"]
    with pytest.raises(LogicException) as ei:
        _call(host, "throw", "oops")
    assert ei.value.term == "oops"


def test_nested_special_form_cells(host):
    """findall inside once inside catch, as cells built in Python."""
    X, L = Var(), Var()
    goal = ("catch", ("once", ("findall", X, ("p", X), L)), Var(), False)
    assert [a for (a,) in _call(host, goal, out=(L,))] == [[1, 2, 3]]
    Y, Z = Var(), Var()
    goal = ("catch", ("once", ("throw", ("boom", 7))), ("boom", Z),
            ("=", Y, Z))
    assert _call(host, goal, out=(Y, Z)) == [(7, 7)]


def test_a_special_form_inside_a_body_term(host):
    X, Z, L = Var(), Var(), Var()
    goal = (("p", X), ("findall", Z, ("s", Z), L))
    assert _call(host, goal, out=(X, L))[0] == (1, [2, 3])


def test_a_qualified_special_form(host):
    X, L = Var(), Var()
    goal = (":", HOST, ("findall", X, ("p", X), L))
    assert [a for (a,) in _call(host, goal, out=(L,))] == [[1, 2, 3]]


def test_halt_is_the_special_form(host):
    with pytest.raises(SystemExit) as ei:
        _call(host, "halt")
    assert ei.value.code == 0
    with pytest.raises(SystemExit) as ei:
        _call(host, ("halt", 3))
    assert ei.value.code == 3


# ── ModulePredicate cells ───────────────────────────────────────────────────


def test_a_module_predicate_cell_runs(host):
    assert len(_call(host, ("match", r"\d+", "123"))) == 1
    assert _call(host, ("match", r"\d+", "abc")) == []
    assert len(_call(host, ("match", re.compile(r"\d+"), "123"))) == 1


def test_a_module_predicate_cell_folds_like_call_n(host):
    assert len(_call(host, ("match", r"\d+"), "123")) == 1
    G = Var()
    assert [a for (a,) in _call(host, ("search", "b"), "abc", G, out=(G,))] == [{}]


def test_a_module_predicate_at_an_unregistered_arity_is_its_existence_error(host):
    """The binding's own answer, as in a body: match/1 is not registered."""
    with pytest.raises(LogicException) as ei:
        _call(host, ("match", "a"))
    formal = _formal(ei)
    assert formal.functor == "existence_error"
    assert formal.args[1].args == ("match", 1)


def test_a_module_predicate_goal_is_built_as_its_cell(host):
    """``G is (match(P, S), ...)`` builds the cell ``("match", P, S)`` -- the
    BASE name, which resolves to the same binding in this module."""
    from clausal.logic.solve import call
    G = Var()
    got = [_norm(G) for _ in call("g", 29, Var(), Var(), G, module=host)]
    assert got[0][0] == ("match", r"\d+", "123")


def test_an_imported_findall_stays_the_regex_predicate(re_host):
    """``-import_from(py.re, [findall])``: the body's findall/3 is the regex
    predicate, so the term must not become the special-form cell."""
    from clausal.logic.solve import call
    L = Var()
    body = [_norm(L) for _ in call("b", L, module=re_host)]
    L = Var()
    assert [_norm(L) for _ in call("run", L, module=re_host)] == body
    assert len(body) == 2              # one answer per regex match
    L, G = Var(), Var()
    got = [_norm(G) for _ in call("g", L, G, module=re_host)]
    assert got[0][0] == "py.re.findall"


# ── ISO errors (13211-1 first, Scryer on the box where ISO is silent) ───────


def test_findall_of_an_unbound_goal_is_an_instantiation_error(host):
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", Var(), Var(), Var()))
    assert _formal(ei) == "instantiation_error"


def test_findall_of_a_number_is_a_type_error(host):
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", Var(), 4, Var()))
    assert _formal(ei).functor == "type_error"
    assert _formal(ei).args == ("callable", 4)


def test_findall_of_a_body_with_a_number_names_the_whole_body(host):
    """Scryer: findall(_, (fail, 4), _) -> type_error(callable, (fail, 4))."""
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", Var(), (False, 4), Var()))
    assert _formal(ei).args == ("callable", (False, 4))


@pytest.mark.parametrize("goal", [("once", None), ("forall", None, True),
                                  ("forall", True, None)])
def test_once_and_forall_of_an_unbound_goal(host, goal):
    goal = tuple(Var() if a is None else a for a in goal)
    with pytest.raises(LogicException) as ei:
        _call(host, goal)
    assert _formal(ei) == "instantiation_error"


def test_once_of_a_number_is_a_type_error(host):
    with pytest.raises(LogicException) as ei:
        _call(host, ("once", 4))
    assert _formal(ei).args == ("callable", 4)


def test_throw_of_an_unbound_ball_is_an_instantiation_error(host):
    """ISO 7.8.10.3 -- as a cell AND written in a body (row 32)."""
    with pytest.raises(LogicException) as ei:
        _call(host, ("throw", Var()))
    assert _formal(ei) == "instantiation_error"
    Y = Var()
    from clausal.logic.solve import call
    got = [_norm(Y) for _ in call("b", 32, Var(), Y, module=host)]
    assert got[0].args[0] == "instantiation_error"


def test_the_ball_is_a_copy(host):
    """ISO 7.8.10.1 b: the catcher unifies with a COPY of the ball, so the
    thrower's variable and the catcher's stay distinct (Scryer:
    ``catch(throw(f(Z)), f(W), true)`` leaves Z and W distinct)."""
    Y, Z = Var(), Var()
    seen = []
    from clausal.logic.solve import call
    for _ in call("call", ("catch", ("throw", ("boom", Y)), ("boom", Z), True),
                  module=host):
        seen.append(is_var(deref(Y)) and is_var(deref(Z))
                    and deref(Y) is not deref(Z))
    assert seen == [True]


def test_a_ball_bound_through_the_trail_survives_the_unwind(host):
    """``catch((X = 1, throw(f(X))), f(W), true)`` gives W = 1: the ball is
    copied BEFORE catch/3 undoes X's binding (it was ``_`` before)."""
    X, W = Var(), Var()
    goal = ("catch", (nodes.Unify(left=X, right=1), ("throw", ("boom", X))),
            ("boom", W), True)
    assert [a for (a,) in _call(host, goal, out=(W,))] == [1]


def test_catch_catches_the_error_of_its_own_goal(host):
    E = Var()
    [(e,)] = _call(host, ("catch", Var(), E, True), out=(E,))
    assert e.functor == "error" and e.args[0] == "instantiation_error"
    E = Var()
    goal = ("catch", ("findall", Var(), 4, Var()), E, True)
    [(e,)] = _call(host, goal, out=(E,))
    assert e.args[0].functor == "type_error"


@pytest.mark.parametrize("args, indicator", [
    ((("once", ("p", Var())), "z"), ("once", 2)),
    ((("findall", Var(), ("p", Var()), Var()), "z"), ("findall", 4)),
    (("findall", Var()), ("findall", 1)),
])
def test_call_n_extras_past_a_special_form_name_no_procedure(host, args,
                                                            indicator):
    """Scryer: ``call(once(p(Y)), z)`` -> existence_error(procedure, once/2)."""
    with pytest.raises(LogicException) as ei:
        _call(host, *args)
    formal = _formal(ei)
    assert formal.functor == "existence_error"
    assert formal.args[1].args == indicator


# ── a meta-interpreter's shape ──────────────────────────────────────────────


@pytest.mark.parametrize("head", ["all_p", "first_s", "safe_p", "pos_all",
                                  "ps"])
def test_a_stored_body_called_answers_like_the_compiled_clause(host, head):
    """The body of each clause, stored as a TERM (what clause/2 will hand
    back) and run by call/1 from a meta-interpreter, answers exactly as the
    compiled clause does."""
    from clausal.logic.solve import call
    if head == "pos_all":
        direct = [True for _ in call(head, module=host)]
        via_mi = [True for _ in call("mi", head, module=host)]
    else:
        Y = Var()
        direct = [_norm(Y) for _ in call(head, Y, module=host)]
        Y = Var()
        via_mi = [_norm(Y) for _ in call("mi", (head, Y), module=host)]
    assert direct
    assert via_mi == direct


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
    import test_call_runs_special_form_cells as tc
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
    assert len(c["rows"]) == len(ROWS) * len(INPUTS)
    assert sum(1 for v in c["rows"].values() if isinstance(v, list) and v) >= 120
    assert c["rows"] == py["rows"]
