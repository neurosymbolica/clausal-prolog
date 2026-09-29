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

from clausal import cell_args, cell_functor
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
    assert type(term) is tuple and cell_functor(term) == "error"
    return cell_args(term)[0]


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
    # A word boundary: "call_cleanup(" must not be found inside
    # "setup_call_cleanup(".
    missing = [name for (name, _) in SPECIAL_FORMS
               if name != "halt"
               and not re.search(rf"(?<![\w.]){re.escape(name)}\(", text)]
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
    assert len(SPECIAL_FORMS) == 19     # findall/4 joined (slice 4)
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
    for name, arity in (("once", 2), ("findall", 5), ("throw", 0)):
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
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[1] == ("/", "match", 1)


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


@pytest.mark.parametrize("via", ["prun", "pcell"])
def test_a_module_predicate_binding_wins_over_a_same_named_builtin(re_host, via):
    """py.random's permutation/2 imported: the body gives ONE answer (a
    shuffle), and call/1 of the cell -- built in term position or in the
    clause -- gives the same one, not the builtin's six permutations."""
    from clausal.logic.solve import call
    body = [_norm(P) for P in [Var()] for _ in call("pb", P, module=re_host)]
    P = Var()
    got = [_norm(P) for _ in call(via, P, module=re_host)]
    assert len(body) == 1
    assert len(got) == 1 and sorted(got[0]) == [1, 2, 3]


def test_an_aliased_module_predicate_term_runs(re_host):
    from clausal.logic.solve import call
    M = Var()
    body = [_norm(M) for _ in call("ab", M, module=re_host)]
    M = Var()
    assert [_norm(M) for _ in call("arun", M, module=re_host)] == body == [{}]
    M, G = Var(), Var()
    got = [_norm(G) for _ in call("ag", M, G, module=re_host)]
    assert got[0][0] == "py.re.search"


# ── ISO errors (13211-1 first, Scryer on the box where ISO is silent) ───────


def test_findall_of_an_unbound_goal_is_an_instantiation_error(host):
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", Var(), Var(), Var()))
    assert _formal(ei) == "instantiation_error"


def test_findall_of_a_number_is_a_type_error(host):
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", Var(), 4, Var()))
    assert cell_functor(_formal(ei)) == "type_error"
    assert cell_args(_formal(ei)) == ("callable", 4)


def test_findall_of_a_body_with_a_number_names_the_whole_body(host):
    """Scryer: findall(_, (fail, 4), _) -> type_error(callable, (fail, 4))."""
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", Var(), (False, 4), Var()))
    assert cell_args(_formal(ei)) == ("callable", (False, 4))


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
    assert cell_args(_formal(ei)) == ("callable", 4)


def test_throw_of_an_unbound_ball_is_an_instantiation_error(host):
    """ISO 7.8.10.3 -- as a cell AND written in a body (row 32)."""
    with pytest.raises(LogicException) as ei:
        _call(host, ("throw", Var()))
    assert _formal(ei) == "instantiation_error"
    Y = Var()
    from clausal.logic.solve import call
    got = [_norm(Y) for _ in call("b", 32, Var(), Y, module=host)]
    assert cell_args(got[0])[0] == "instantiation_error"


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
    assert cell_functor(e) == "error" and cell_args(e)[0] == "instantiation_error"
    E = Var()
    goal = ("catch", ("findall", Var(), 4, Var()), E, True)
    [(e,)] = _call(host, goal, out=(E,))
    assert cell_functor(cell_args(e)[0]) == "type_error"


@pytest.mark.parametrize("args, indicator", [
    ((("once", ("p", Var())), "z"), ("once", 2)),
    ((("findall", Var(), ("p", Var()), Var()), "z", "w"), ("findall", 5)),
    (("findall", Var()), ("findall", 1)),
])
def test_call_n_extras_past_a_special_form_name_no_procedure(host, args,
                                                            indicator):
    """Scryer: ``call(once(p(Y)), z)`` -> existence_error(procedure, once/2)."""
    with pytest.raises(LogicException) as ei:
        _call(host, *args)
    formal = _formal(ei)
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[1] == ("/", *indicator)


# ── the result of findall/bagof/setof must be a list or a partial list ─────


NON_LIST_ROWS = {1: "foo", 2: 3, 3: ("boom", 1), 4: "foo", 5: "foo", 6: 7}


@pytest.mark.parametrize("pred", ["nb", "nb_run"])
@pytest.mark.parametrize("n", sorted(NON_LIST_ROWS))
def test_a_non_list_result_is_a_type_error(host, pred, n):
    """ISO 8.10.1.3 d / 8.10.2.3 c / 8.10.3.3 c, Scryer alike (checked on the
    box: ``findall(X, p(X), foo)`` -> type_error(list, foo), also for bagof
    and setof, also when the goal has no solution).  It was a silent
    failure, in the body AND through call/1."""
    from clausal.logic.solve import call
    with pytest.raises(LogicException) as ei:
        list(call(pred, n, module=host))
    formal = _formal(ei)
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal) == ("list", NON_LIST_ROWS[n])


def test_the_result_is_checked_before_the_goal_runs(host):
    """Scryer: ``findall(X, _, foo)`` is type_error(list, foo), not the
    instantiation_error of its goal."""
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", Var(), Var(), "foo"))
    assert cell_args(_formal(ei)) == ("list", "foo")


@pytest.mark.parametrize("n, expected", [
    (1, [1]), (2, [2]), (3, [[1, 2, 3]]), (4, ["_"]), (5, [1]), (6, []),
])
def test_a_partial_list_result_is_fine(host, n, expected):
    from clausal.logic.solve import call
    R = Var()
    assert [_norm(R) for _ in call("pl", n, R, module=host)] == expected


@pytest.mark.parametrize("n, answers", [(1, 1), (2, 0)])
def test_a_constant_list_is_a_list(host, n, answers):
    """roborev on eb3c4216: ``type() in (list, bytes)`` refused a
    ``_FrozenList`` -- the list a ``-constant_value`` holds -- so a findall
    into ``++nums`` raised type_error(list, [1, 2, 3]).  It unifies (or not)
    as a list again."""
    from clausal.logic.solve import call
    assert len(list(call("cf", n, module=host))) == answers


@pytest.mark.parametrize("text, answers", [("ab", 1), ("ax", 0)])
def test_a_string_is_the_list_of_its_chars(host, text, answers):
    """The ('$chars', s) carrier -- a double-quoted string under ISO's
    double_quotes(chars) -- is a list, so it is no type_error: findall's
    collected chars unify with it, or do not.  A bare str is an ATOM."""
    from clausal.logic.cells import chars
    from clausal.logic.atoms import char_atom
    C = Var()
    goal = ("findall", C,
            nodes.in_(left=C, right=[char_atom("a"), char_atom("b")]),
            chars(text))
    assert len(_call(host, goal)) == answers
    with pytest.raises(LogicException) as ei:
        _call(host, ("findall", C, nodes.in_(left=C, right=["a"]), "ab"))
    assert cell_args(_formal(ei)) == ("list", "ab")


def test_a_constant_list_is_a_frozen_list_subclass(host):
    """The positive control for the test above: the value IS a subclass."""
    from clausal.logic.compiler.globals_env import _is_list_or_partial_list
    from clausal.logic.constants import _FrozenList
    frozen = _FrozenList([1, 2, 3])
    assert type(frozen) is not list and isinstance(frozen, list)
    assert _is_list_or_partial_list(frozen)


@pytest.mark.parametrize("body, cell", [("b", "fcell"), ("ob", "ocell")])
def test_an_imported_name_wins_over_the_special_form(re_host, body, cell):
    """roborev on eb3c4216: ``-import_from(py.re, [findall])`` makes the
    body's findall/3 the REGEX predicate (the import rewrites the call), and
    ``-import_from(m, [once])`` makes once/1 m's; call/1 of the bare cell
    must run the same import, not the special form."""
    from clausal.logic.solve import call
    X = Var()
    expected = [_norm(X) for _ in call(body, X, module=re_host)]
    X = Var()
    assert [_norm(X) for _ in call(cell, X, module=re_host)] == expected
    assert expected                      # not vacuous: regex answers, once gives 5


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
