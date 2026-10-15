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
    native.load("seam_ok", "q(1),\np(X) <- (q(X), q(X)),\n", suffix=".seam")
    with pytest.raises(SyntaxError,
                       match=r"invalid syntax \(seam_refused\.seam, line 2\)"):
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
    """Each row builds its goal from its own fresh variables."""
    from clausal.logic.variables import Var

    def cut(x):
        return (",", ("q", x), "!")

    def frz(v):
        return (",", ("freeze", v, cut(Var())), ("=", v, 1))

    def when(v):
        return (",", ("when", ("nonvar", v), cut(Var())), ("=", v, 1))

    return [
        ("ite", lambda x: (";", ("->", ("q", x), "true"), "true"), ITE_REFUSED),
        ("if_then", lambda x: ("->", ("q", x), "true"), ITE_REFUSED),
        ("catch", lambda x: ("catch", cut(x), "foo", "true"), REFUSED),
        ("scc", lambda x: ("setup_call_cleanup", "true", cut(x), "true"),
         REFUSED),
        ("call_cleanup", lambda x: ("call_cleanup", cut(x), "true"), REFUSED),
        ("freeze", frz, REFUSED),
        ("when", when, REFUSED),
        ("bagof", lambda x: ("bagof", x, cut(x), Var()), REFUSED),
        ("setof", lambda x: ("setof", x, cut(x), Var()), REFUSED),
        ("call_nth", lambda x: ("call_nth", cut(x), 1), REFUSED),
        ("call/2 builds it", lambda x: ("call", (",", ("q", x)), "!"), REFUSED),
        ("\\+ \\+", lambda x: ("\\+", ("\\+", cut(x))), REFUSED),
        ("nested findall",
         lambda x: ("findall", 1, ("findall", x, cut(x), Var()), Var()),
         REFUSED),
    ]


def test_every_meta_call_of_seam_refuses_a_runtime_cut(seam):
    """The rows tests/test_meta_call_cut_refused.py does not already hold."""
    from clausal.logic.variables import Var
    for label, mk, want in _seam_rows():
        assert _seam_run(seam, mk(Var())) == want, label


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
    A cut qualified to the seam module itself cuts nothing.  Pinned as it
    is today; the question is open (todo/seam-qualified-goal-into-pl-may-
    cut-2026-10-14.md)."""
    from clausal.logic.variables import Var
    native.load("plcut", PL)
    assert _seam_run(seam, (":", "plcut", (",", ("p", Var()), "!"))) == 1
    assert _seam_run(seam, (":", "plcut", ("p", Var()))) == 3     # control
    assert _seam_run(seam, (":", "plcut", ("cutter", (",", ("p", Var()), "!")))) == 1
    assert _seam_run(seam, (",", (":", "plcut", ("p", Var())), "!")) == REFUSED
    assert _seam_run(seam, (":", "plcut", (",", ("p", Var()),
                                           (":", "seamcut", "!")))) == 3


# ── .clausal -> .seam -> .pl: the relay (ruling: pinned, not blocked) ──────

RELAY_PL = """\
:- module(pls, [p/1]).
p(1). p(2). p(3).
"""

RELAY_CL = """\
:- use_module(library(reif)).
r_cond_t(L) :- catch((G = (p(X), !), findall(X, cond_t(=(true), pls:G, _), L)), error(E, _), L = E).
r_cond_t_ite(L) :- catch((G = (p(X) -> true ; true), findall(X, cond_t(=(true), pls:G, _), L)), error(E, _), L = E).
r_cond_t_ctl(L) :- catch(findall(X, cond_t(=(true), pls:p(X), _), L), error(E, _), L = E).
r_seam_relay(L) :- catch((G = (p(X), !), M = seams, findall(X, call(M:cg1, pls:G), L)), error(E, _), L = E).
r_seam_relay_ctl(L) :- catch((M = seams, findall(X, call(M:cg1, pls:p(X)), L)), error(E, _), L = E).
"""


def test_clausal_relays_a_cut_into_pl_through_a_seam_meta_call(native, ans):
    """KNOWN, RULED NOT A BLOCKER (Task 6 fix round 1): the edge gate checks
    the IMMEDIATE caller, and a .seam frame (library(reif)'s cond_t/3, or a
    user ``cg1(G) <- call(G)``) is the trusted bridge, so a .clausal-built
    ``pls:(p(X), !)`` reaches the .pl module and is converted against ITS
    db: the cut (or the if-then-else commit) runs there, local to that call.
    The .clausal -> seam -> .pl crossing itself predates the series (the
    ``_ctl`` rows); the sandbox refuses the route
    (tests/test_sandbox.py::test_the_sandbox_refuses_the_clausal_seam_pl_relay).
    Open question for the operator:
    todo/seam-qualified-goal-into-pl-may-cut-2026-10-14.md."""
    native.load("pls", RELAY_PL)
    native.load("seams", "cg1(G) <- call(G),\n", suffix=".seam")
    cl = native.load("cls", RELAY_CL, suffix=".clausal")
    assert ans(cl, "r_cond_t") == [[1]]
    assert ans(cl, "r_cond_t_ite") == [[1]]
    assert ans(cl, "r_cond_t_ctl") == [[1, 2, 3]]
    assert ans(cl, "r_seam_relay") == [[1]]
    assert ans(cl, "r_seam_relay_ctl") == [[1, 2, 3]]


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


def test_call_treats_a_cut_node_as_the_cut(native, seam):
    """call/1 handed a Cut or IfThenElse node from Python answers as for the
    cells ``!`` and ``->``: a whole-goal cut is true, a nested cut is
    ``!/0`` refused, an if-then-else is ``->/2`` refused.  (They used to be
    ``type_error(callable, 'Cut()')`` -- one shape per spelling.)"""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from clausal.pythonic_ast import nodes
    cl = native.load("clcut_cg", "q(1). q(2).\ncg(G) :- call(G).\n",
                     suffix=".clausal")
    for mod, pred in ((cl, "cg"), (seam, "cg1")):
        assert len(list(call(pred, nodes.Cut(), module=mod))) == 1
        for goal, want in (
                (nodes.IfThenElse(test=True, body=True, orelse=True),
                 ITE_REFUSED),
                (nodes.And(left=("q", Var()), right=nodes.Cut()), REFUSED),
                ((",", ("q", Var()), nodes.Cut()), REFUSED)):
            with pytest.raises(LogicException) as ei:
                list(call(pred, goal, module=mod))
            assert _formal(ei.value) == want, (pred, goal)


def _q(x):
    from clausal.pythonic_ast import nodes
    return nodes.Call(func=nodes.LoadName(name="q"), args=[x], kwargs=[])


def _node_goals():
    """(label, make, refusal): *make(x)* builds the goal on a fresh x."""
    from clausal.pythonic_ast import nodes

    def tl_cut(x):
        return nodes.TupleLiteral(elements=[_q(x), nodes.Cut()])

    return [
        ("TupleLiteral[q, Cut]", tl_cut, REFUSED),
        ("And(q, Cut)", lambda x: nodes.And(left=_q(x), right=nodes.Cut()),
         REFUSED),
        ("Or(q, Cut)", lambda x: nodes.Or(left=_q(x), right=nodes.Cut()),
         REFUSED),
        ("Not(TupleLiteral[q, Cut])", lambda x: nodes.Not(operand=tl_cut(x)),
         REFUSED),
        ("IfThenElse",
         lambda x: nodes.IfThenElse(test=_q(x), body=True, orelse=True),
         ITE_REFUSED),
        ("IfThen",
         lambda x: nodes.IfThenElse(test=_q(x), body=True, orelse=None),
         ITE_REFUSED),
        ("And(q, IfThenElse)",
         lambda x: nodes.And(left=True, right=nodes.IfThenElse(
             test=_q(x), body=True, orelse=True)),
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
        for label, mk, want in _node_goals():
            with pytest.raises(LogicException) as ei:
                list(solve(mk(Var()), module=mod))
            assert _formal(ei.value) == want, (name, label)


def _meta_node_rows():
    """Review probe 6: a Cut / IfThenElse node in a meta-call's GOAL
    argument, the meta-call a node or a cell.  (row, make(x, L) ->
    (goal, out), control make, refusal).  The control is the same goal
    without the cut."""
    from clausal.logic.variables import Var
    from clausal.pythonic_ast import nodes

    def C(name, *a):
        return nodes.Call(func=nodes.LoadName(name=name), args=list(a),
                          kwargs=[])

    def cut(x):
        return nodes.TupleLiteral(elements=[_q(x), nodes.Cut()])

    def ite(x):
        return nodes.IfThenElse(test=_q(x), body=True, orelse=True)

    return [
        ("node findall(q, !)", lambda x, L: (C("findall", x, cut(x), L), L),
         lambda x, L: (C("findall", x, _q(x), L), L), REFUSED, [[1, 2]]),
        ("node findall(q -> true ; true)",
         lambda x, L: (C("findall", x, ite(x), L), L),
         lambda x, L: (C("findall", x, _q(x), L), L), ITE_REFUSED, [[1, 2]]),
        ("node catch((q, !), foo, true)",
         lambda x, L: (C("catch", cut(x), "foo", True), x),
         lambda x, L: (C("catch", _q(x), "foo", True), x), REFUSED, [1, 2]),
        ("node call_cleanup((q, !), true)",
         lambda x, L: (C("call_cleanup", cut(x), True), x),
         lambda x, L: (C("call_cleanup", _q(x), True), x), REFUSED, [1, 2]),
        ("node once(q -> true ; true)", lambda x, L: (C("once", ite(x)), x),
         lambda x, L: (C("once", _q(x)), x), ITE_REFUSED, [1]),
        ("cell findall(x, node(q, !), L)",
         lambda x, L: (("findall", x, cut(x), L), L),
         lambda x, L: (("findall", x, _q(x), L), L), REFUSED, [[1, 2]]),
        ("cell forall(q, node(true, !))",
         lambda x, L: (("forall", ("q", x), nodes.TupleLiteral(
             elements=[True, nodes.Cut()])), x),
         lambda x, L: (("forall", ("q", x), True), Var()), REFUSED, [None]),
    ]


def test_solve_refuses_a_cut_node_under_a_meta_call(native, seam):
    """The compiler is the choke point: a Cut or IfThenElse node is refused
    wherever it sits -- under findall/catch/call_cleanup/once/forall, built
    as a node or as a cell -- for any db that may not cut.  Each row's
    control (the same goal without the cut) answers in full."""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var, deref, is_var, walk
    for name, mod in _targets(native, seam):
        for label, mk, ctl, want, ctl_want in _meta_node_rows():
            if name == "python" and label.startswith("cell forall"):
                # forall runs q/1 before it converts the action, and the
                # Python-made module defines none: nothing to compare
                continue
            goal, _ = mk(Var(), Var())
            with pytest.raises(LogicException) as ei:
                list(solve(goal, module=mod))
            assert _formal(ei.value) == want, (name, label)
            if name == "python":        # no q/1 to run the control against
                continue
            goal, out = ctl(Var(), Var())
            got = []
            for _ in solve(goal, module=mod):
                v = walk(deref(out))
                got.append(None if is_var(v) else v)
            assert got == ctl_want, (name, label)


def test_a_whole_query_cut_node_is_true_like_the_atom(native, seam):
    """A Cut node that is the whole query cuts nothing (ISO 7.8.3), as
    ``solve("!")`` -- kept on every surface."""
    from clausal.logic.solve import solve
    from clausal.pythonic_ast import nodes
    for name, mod in _targets(native, seam):
        assert len(list(solve(nodes.Cut(), module=mod))) == 1, name
        assert len(list(solve("!", module=mod))) == 1, name


def test_a_whole_goal_cut_node_under_a_meta_call_is_true_like_the_atom(
        native, seam):
    """A Cut node that is the WHOLE goal of once/findall/bagof/setof/
    aggregate_all/forall/catch/``\\+`` is local to that call and cuts
    nothing (ISO 7.8.3): the answers are the atom ``'!'``'s, on every
    surface (it used to be ``existence_error(!/0)`` for the node and
    ``true`` for the atom).  A Cut node NESTED in such a goal is still
    refused on a cut-free surface."""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    from clausal.pythonic_ast import nodes
    pl = native.load("pl_whole", "q(1). q(2).\n")

    def wrapped(c):
        L = Var()
        return {
            "once": ("once", c), "findall": ("findall", 1, c, L),
            "bagof": ("bagof", 1, c, L), "setof": ("setof", 1, c, L),
            "aggregate_all": ("aggregate_all", "count", c, L),
            "forall": ("forall", c, True), "catch": ("catch", c, Var(), True),
            "once_once": ("once", ("once", c)),
            "findall_once": ("findall", 1, ("once", c), L),
        }
    for name, mod in _targets(native, seam) + [("pl", pl)]:
        atom = {k: len(list(solve(g, module=mod)))
                for k, g in wrapped("!").items()}
        node = {k: len(list(solve(g, module=mod)))
                for k, g in wrapped(nodes.Cut()).items()}
        assert node == atom and set(atom.values()) == {1}, (name, node, atom)
        # \\+ over a node: \\+ ! fails, \\+ \\+ ! succeeds.
        nn = nodes.Not(operand=nodes.Not(operand=nodes.Cut()))
        assert len(list(solve(nn, module=mod))) == 1, name
        assert list(solve(nodes.Not(operand=nodes.Cut()), module=mod)) == []
        assert len(list(solve(("findall", 1, nn, Var()), module=mod))) == 1
        if name == "pl":
            continue
        nested = nodes.And(left=True, right=nodes.Cut())
        for goal in (("once", nested), ("findall", 1, nested, Var()),
                     nodes.Not(operand=nested)):
            with pytest.raises(LogicException) as ei:
                list(solve(goal, module=mod))
            assert _formal(ei.value) == REFUSED, (name, goal)


def test_solve_runs_cut_and_ite_nodes_on_a_pl_module(native):
    """Control: the same nodes compile and cut against a .pl db."""
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var, deref, is_var
    pl = native.load("pl_nodes", "q(1). q(2).\n")
    want = {"TupleLiteral[q, Cut]": [1], "And(q, Cut)": [1],
            "Or(q, Cut)": [1, 2, None], "IfThenElse": [1], "IfThen": [1]}
    for label, mk, _ in _node_goals():
        if label not in want:
            continue
        x = Var()
        got = []
        for _ in solve(mk(x), module=pl):
            v = deref(x)
            got.append(None if is_var(v) else v)
        assert got == want[label], label
