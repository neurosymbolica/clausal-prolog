"""Mike's ruling (D59): Clausal Prolog (``.clausal``) is the cut-free
language, ``.pl`` may cut, and ``.clausal`` may not call into ``.pl``.  A
``.seam`` module is cut-free too.  Each path by which a cut or an
if-then-else could reach a ``.clausal`` or ``.seam`` module is pinned here:
load, a goal built at run time and handed to every meta-call, assert, a
module-qualified goal in either direction, a ``.pl`` predicate handle, and the
Python entry points (``solve`` with cells and with compiler nodes).

The rule each pin rests on: the db the goal is CONVERTED against decides
(``call_body.cut_allowed``).  For call/N that is the calling module's db; for
``M:G`` it is M's, because ``:`` runs G as M's goal."""
from __future__ import annotations

import pytest

PL = """\
:- module(plcut, [first/1, cutter/1]).
p(1). p(2). p(3).
first(X) :- p(X), !.
cutter(X) :- call(X), !.
"""

# A .clausal module.  Every row catches the error so the answer is the
# formal term; ``foo`` as a catcher lets an inner catch/3 pass the error out.
CL = """\
q(1). q(2).
t1(R) :- catch((G = (q(_), !), call(G), R = ran), error(E, _), R = E).
t2(R) :- catch((G = (q(_) -> true ; true), call(G), R = ran), error(E, _), R = E).
t3(R) :- catch(assertz((h :- !)), error(E, _), R = E).
t4(R) :- catch(assertz(plcut:(h :- !)), error(E, _), R = E).
"""

# The same run-time cut reaching each meta-call of a .clausal module.
CL_META = """\
q(1). q(2).
m_callN(R) :- catch((G = ','(q(_)), call(G, !), R = ran), error(E, _), R = E).
m_univ(R) :- catch((G =.. [',', q(_), !], call(G), R = ran), error(E, _), R = E).
m_var_goal(R) :- catch((G = (q(_), !), G, R = ran), error(E, _), R = E).
m_call_call(R) :- catch((G = (q(_), !), call(call, G), R = ran), error(E, _), R = E).
m_findall(R) :- catch((G = (q(_), !), findall(x, G, L), R = L), error(E, _), R = E).
m_bagof(R) :- catch((G = (q(_), !), bagof(x, G, L), R = L), error(E, _), R = E).
m_setof(R) :- catch((G = (q(_), !), setof(x, G, L), R = L), error(E, _), R = E).
m_aggregate_all(R) :- catch((G = (q(_), !), aggregate_all(count, G, L), R = L), error(E, _), R = E).
m_not(R) :- catch((G = (q(_), !), (\\+ G, R = no ; R = yes)), error(E, _), R = E).
m_once(R) :- catch((G = (q(_), !), once(G), R = ran), error(E, _), R = E).
m_forall(R) :- catch((G = (q(_), !), forall(G, true), R = ran), error(E, _), R = E).
m_catch(R) :- catch((G = (q(_), !), catch(G, foo, true), R = ran), error(E, _), R = E).
m_call_nth(R) :- catch((G = (q(_), !), call_nth(G, 1), R = ran), error(E, _), R = E).
m_scc(R) :- catch((G = (q(_), !), setup_call_cleanup(true, G, true), R = ran), error(E, _), R = E).
m_call_cleanup(R) :- catch((G = (q(_), !), call_cleanup(G, true), R = ran), error(E, _), R = E).
m_freeze(R) :- catch((G = (q(_), !), freeze(V, G), V = 1, R = ran), error(E, _), R = E).
m_when(R) :- catch((G = (q(_), !), when(nonvar(V), G), V = 1, R = ran), error(E, _), R = E).
m_phrase(R) :- catch((G = ([a], !), phrase(G, [a]), R = ran), error(E, _), R = E).
m_if_then(R) :- catch((G = (q(_) -> true), call(G), R = ran), error(E, _), R = E).
m_soft_cut(R) :- catch((G = ';'('*->'(q(_), true), true), call(G), R = ran), error(E, _), R = E).
"""

REFUSED = ("existence_error", "procedure", ("/", "!", 0))
ITE_REFUSED = ("existence_error", "procedure", ("/", "->", 2))
PL_EDGE = ("permission_error", "access", "prolog_module", "plcut")


def _formal(exc):
    return exc.term[1]


# ── load ────────────────────────────────────────────────────────────────────

def test_clausal_source_still_refuses_cut_and_ite_at_load(native):
    for src in ("p :- !.\n", "p :- ( true -> true ; true ).\n",
                "p :- ( true -> true ).\n", "s --> [a], !.\n",
                "p :- call((true, !)).\n", "p :- findall(x, (true -> true), _).\n"):
        with pytest.raises(SyntaxError, match=r"is refused.*: Clausal is cut-free with no committed choice"):
            native.load("cl_refused", src, suffix=".clausal")


def test_seam_source_cannot_spell_a_cut(native):
    with pytest.raises(SyntaxError):
        native.load("seam_refused", "q(1),\np(X) <- (q(X), !),\n", suffix=".seam")


# ── a goal built at run time in a .clausal module ──────────────────────────

def test_runtime_built_cut_from_clausal_is_still_refused(native, ans):
    mod = native.load("clcut", CL, suffix=".clausal")
    assert ans(mod, "t1") == [REFUSED]
    assert ans(mod, "t2") == [ITE_REFUSED]


@pytest.mark.parametrize("row", [
    "callN", "univ", "var_goal", "call_call", "findall", "bagof", "setof",
    "aggregate_all", "not", "once", "forall", "catch", "call_nth", "scc",
    "call_cleanup", "freeze", "when", "phrase"])
def test_every_meta_call_of_clausal_refuses_a_runtime_cut(native, ans, row):
    mod = native.load("clcut_meta", CL_META, suffix=".clausal")
    assert ans(mod, "m_" + row) == [REFUSED], row


def test_clausal_refuses_runtime_if_then_and_soft_cut(native, ans):
    mod = native.load("clcut_ite", CL_META, suffix=".clausal")
    assert ans(mod, "m_if_then") == [ITE_REFUSED]
    assert ans(mod, "m_soft_cut") == [("existence_error", "procedure",
                                     ("/", "*->", 2))]


def test_a_cut_that_is_the_whole_goal_is_true_in_clausal(native, ans):
    """ISO 7.8.3: ``call(!)`` cuts nothing -- unchanged, on every surface."""
    mod = native.load("clcut_whole",
                      "w(R) :- G = !, call(G), R = ran.\n", suffix=".clausal")
    assert ans(mod, "w") == ["ran"]


# ── assert ──────────────────────────────────────────────────────────────────

def test_asserting_a_rule_is_refused_everywhere(native, ans):
    """Rules cannot be asserted at run time (A09-F005) -- so a cut can never
    be asserted into a .clausal module from anywhere; pin the existing error.
    Asserting into a .pl module from .clausal is refused one step earlier:
    .clausal may not reach a .pl module at all."""
    native.load("plcut", PL)
    mod = native.load("clcut2", CL, suffix=".clausal")
    assert ans(mod, "t3") == [("permission_error", "assert", "rule", "h")]
    assert ans(mod, "t4") == [PL_EDGE]


def test_a_pl_module_cannot_assert_a_cutting_rule_into_clausal(native, ans):
    native.load("clm_target", "q(1). q(2).\n", suffix=".clausal")
    pl = native.load("pl_asserter",
                     "r(R) :- catch(assertz(clm_target:(h :- !)), error(E, _), R = E).\n")
    assert ans(pl, "r") == [("permission_error", "assert", "rule", "h")]


# ── module-qualified goals ──────────────────────────────────────────────────

def test_clausal_cannot_reach_a_pl_module_by_qualification(native, ans):
    """S39 + D59: a qualified goal, a qualified closure, a qualified
    run-time body -- every form into a .pl module is the edge refusal."""
    native.load("plcut", PL)
    mod = native.load("clcut_q", """\
a(R) :- catch((plcut:first(X), R = X), error(E, _), R = E).
b(R) :- catch((call(plcut:first, X), R = X), error(E, _), R = E).
c(R) :- catch((G = (q(_), !), call(plcut:G), R = ran), error(E, _), R = E).
d(R) :- catch((G = (q(_), !), plcut:cutter(G), R = ran), error(E, _), R = E).
q(1).
""", suffix=".clausal")
    for row in "abcd":
        assert ans(mod, row) == [PL_EDGE], row


def test_a_pl_module_qualifying_into_clausal_gets_no_cut(native, ans):
    """``M:G`` runs G as M's goal: when M is .clausal the body is converted
    against M's db, which refuses the cut -- whoever built it."""
    native.load("clm_q", "q(1). q(2).\n", suffix=".clausal")
    pl = native.load("pl_q", """\
r1(R) :- catch((G = (q(_), !), call(clm_q:G), R = ran), error(E, _), R = E).
r2(R) :- catch((call(clm_q:(q(X), !)), R = X), error(E, _), R = E).
r3(R) :- catch((call(clm_q:(q(X) -> true ; true)), R = X), error(E, _), R = E).
r4(L) :- findall(X, clm_q:q(X), L).
""")
    assert ans(pl, "r1") == [REFUSED]
    assert ans(pl, "r2") == [REFUSED]
    assert ans(pl, "r3") == [ITE_REFUSED]
    assert ans(pl, "r4") == [[1, 2]]     # control: the edge itself is open


# ── .seam ───────────────────────────────────────────────────────────────────

SEAM_SRC = """\
q(1),
q(2),
cg1(G) <- call(G),
cg2(G, L) <- findall(X-Y, (call(G, X), (Y is 1 or Y is 2)), L),
"""


@pytest.fixture
def seam(native):
    return native.load("seamcut", SEAM_SRC, suffix=".seam").__dict__["$module"]


def _seam_run(seam, goal):
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import call
    try:
        return len(list(call("cg1", goal, module=seam)))
    except LogicException as e:
        return _formal(e)


def _seam_rows():
    from clausal.logic.variables import Var
    x = Var()
    cut = (",", ("q", x), "!")
    v1, v2 = Var(), Var()
    return [
        ("ite", (";", ("->", ("q", x), "true"), "true"), ITE_REFUSED),
        ("if_then", ("->", ("q", x), "true"), ITE_REFUSED),
        ("catch", ("catch", cut, "foo", "true"), REFUSED),
        ("scc", ("setup_call_cleanup", "true", cut, "true"), REFUSED),
        ("call_cleanup", ("call_cleanup", cut, "true"), REFUSED),
        ("freeze", (",", ("freeze", v1, cut), ("=", v1, 1)), REFUSED),
        ("when", (",", ("when", ("nonvar", v2), cut), ("=", v2, 1)), REFUSED),
        ("bagof", ("bagof", x, cut, Var()), REFUSED),
        ("setof", ("setof", x, cut, Var()), REFUSED),
        ("call_nth", ("call_nth", cut, 1), REFUSED),
        ("call/2 builds it", ("call", (",", ("q", x)), "!"), REFUSED),
        ("\\+ \\+", ("\\+", ("\\+", cut)), REFUSED),
        ("nested findall", ("findall", 1, ("findall", x, cut, Var()), Var()),
         REFUSED),
    ]


def test_every_meta_call_of_seam_refuses_a_runtime_cut(seam):
    """The rows tests/test_meta_call_cut_refused.py does not already hold."""
    for label, goal, want in _seam_rows():
        assert _seam_run(seam, goal) == want, label


def test_a_pl_closure_called_from_seam_keeps_its_cut_local(native, seam):
    """S40: a .seam predicate handed a .pl predicate sees that predicate's
    own answers; its cut is clause-local and cannot reach the caller's
    ``or``.  (The same handle from .clausal is the edge refusal.)"""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    pl = native.load("plcut", PL)
    first = pl.__dict__["first"]
    out = Var()
    got = [walk(deref(out)) for _ in call("cg2", first, out, module=seam)]
    assert [[(t.left, t.right) for t in row] for row in got] == [[(1, 1), (1, 2)]]
    cl = native.load("clcut_handle",
                     "cg2(G, L) :- findall(X-Y, (call(G, X), (Y = 1 ; Y = 2)), L).\n",
                     suffix=".clausal")
    with pytest.raises(LogicException) as ei:
        list(call("cg2", first, Var(), module=cl))
    assert _formal(ei.value) == PL_EDGE


def test_seam_qualifying_into_a_pl_module_runs_as_that_module(native, seam):
    """``M:G`` runs G as M's goal, so a body qualified into a .pl module is
    converted against the .pl db and may cut there -- local to the call, as
    every .pl meta-call cut is.  This is the same reach a .seam module has
    through any .pl predicate that calls its argument (``plcut:cutter(G)``).
    A cut qualified to the seam module itself cuts nothing."""
    from clausal.logic.variables import Var
    native.load("plcut", PL)
    x = Var()
    assert _seam_run(seam, (":", "plcut", (",", ("p", x), "!"))) == 1
    assert _seam_run(seam, (":", "plcut", ("cutter", (",", ("p", x), "!")))) == 1
    assert _seam_run(seam, (",", (":", "plcut", ("p", x)), "!")) == REFUSED
    assert _seam_run(seam, (":", "plcut", (",", ("p", x),
                                           (":", "seamcut", "!")))) == 3


# ── Python entry points ─────────────────────────────────────────────────────

def _targets(native, seam):
    from clausal.logic.database import Module
    cl = native.load("clcut_py", "q(1). q(2).\n", suffix=".clausal")
    return [("clausal", cl), ("seam", seam), ("python", Module("pycut"))]


def test_solve_refuses_control_cells_on_cut_free_modules(native, seam):
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    for name, mod in _targets(native, seam):
        for goal in ((",", ("q", Var()), "!"),
                     (";", ("->", ("q", Var()), "true"), "true"),
                     ("->", ("q", Var()), "true")):
            with pytest.raises(LogicException) as ei:
                list(solve(goal, module=mod))
            assert _formal(ei.value)[:2] == (
                "type_error", "callable_control_construct_unsupported"), name


def test_call_refuses_a_cut_node_from_python(native, seam):
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import call
    from clausal.pythonic_ast import nodes
    cl = native.load("clcut_cg", "cg(G) :- call(G).\n", suffix=".clausal")
    for mod in (cl, seam):
        pred = "cg" if mod is cl else "cg1"
        for goal in (nodes.Cut(), nodes.IfThenElse(test=True, body=True,
                                                   orelse=True)):
            with pytest.raises(LogicException) as ei:
                list(call(pred, goal, module=mod))
            assert _formal(ei.value)[:2] == ("type_error", "callable")


def _node_goals(x):
    from clausal.pythonic_ast import nodes
    q = nodes.Call(func=nodes.LoadName(name="q"), args=[x], kwargs=[])
    return [
        ("TupleLiteral[q, Cut]", nodes.TupleLiteral(elements=[q, nodes.Cut()]),
         REFUSED),
        ("And(q, Cut)", nodes.And(left=q, right=nodes.Cut()), REFUSED),
        ("Or(q, Cut)", nodes.Or(left=q, right=nodes.Cut()), REFUSED),
        ("Not(TupleLiteral[q, Cut])",
         nodes.Not(operand=nodes.TupleLiteral(elements=[q, nodes.Cut()])),
         REFUSED),
        ("IfThenElse", nodes.IfThenElse(test=q, body=True, orelse=True),
         ITE_REFUSED),
        ("IfThen", nodes.IfThenElse(test=q, body=True, orelse=None),
         ITE_REFUSED),
        ("And(q, IfThenElse)",
         nodes.And(left=True, right=nodes.IfThenElse(test=q, body=True,
                                                     orelse=True)),
         ITE_REFUSED),
    ]


def test_solve_refuses_cut_and_ite_nodes_on_cut_free_modules(native, seam):
    """A compiler-node goal from Python is converted against the module's db
    like a cell is: Cut and IfThenElse nodes are refused unless the db is a
    .pl module's.  (They used to compile and cut: ``solve(TupleLiteral([q(X),
    Cut()]), module=<.clausal>)`` gave X=1 only.)"""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    for name, mod in _targets(native, seam):
        for label, goal, want in _node_goals(Var()):
            with pytest.raises(LogicException) as ei:
                list(solve(goal, module=mod))
            assert _formal(ei.value) == want, (name, label)


def test_a_whole_query_cut_node_is_true_like_the_atom(native, seam):
    """A Cut node that is the whole query cuts nothing (ISO 7.8.3), as
    ``solve("!")`` -- kept on every surface."""
    from clausal.logic.solve import solve
    from clausal.pythonic_ast import nodes
    for name, mod in _targets(native, seam):
        assert len(list(solve(nodes.Cut(), module=mod))) == 1, name
        assert len(list(solve("!", module=mod))) == 1, name


def test_solve_runs_cut_and_ite_nodes_on_a_pl_module(native):
    """Control: the same nodes compile and cut against a .pl db."""
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var, deref, is_var
    pl = native.load("pl_nodes", "q(1). q(2).\n")
    want = {"TupleLiteral[q, Cut]": [1], "And(q, Cut)": [1],
            "Or(q, Cut)": [1, 2, None], "IfThenElse": [1], "IfThen": [1]}
    for label, goal, _ in _node_goals(x := Var()):
        if label not in want:
            continue
        got = []
        for _ in solve(goal, module=pl):
            v = deref(x)
            got.append(None if is_var(v) else v)
        assert got == want[label], label
