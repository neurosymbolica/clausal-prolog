"""Ruling S in CLAUSE SOURCE: a bare arity>=1 predicate name in data
position stores the PLAIN atom of its name, in both eras -- and every
goal-taking builtin handed that atom resolves it by name in the CALLER's
module, the way ``call/N`` does.

``todo/done/bare-predicate-name-in-clause-source-is-the-binding-not-the-atom-2026-09-24.md``.
Before: ``r(b)`` stored ``b/1``'s CLASS (a ``LoadName`` lowered to a runtime
``Name`` load), so a plain ``r(b)`` query answered 0.  Just lowering it to the
atom broke 25 tests, because the goal-first list builtins could only run a
goal OBJECT and failed silently on an atom.
"""
from __future__ import annotations

import ast

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle, mint
from clausal.logic.compiler.terms_to_ast import lowering_scope, term_to_ast_expr
from clausal.logic.predicate import mint_predicate_handle
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, deref
from clausal.logic.exceptions import LogicException
from clausal.terms import Compound, LoadName

_SRC = """\
-module({name}, [z/0, b/1, add/3, q/1, r/1, l/1, g_map/0, g_call/0,
                 g_fold/1, g_part/2, g_phrase/0, greet/2, tpos/2,
                 g_tf/1, g_tp/2])
z <- True,
b(1),
add(X, Y, Z) <- (Z == X + Y),
q(z),
r(b),
l([b, 2]),
g_map <- maplist(b, [1, 1]),
g_call <- call(b, 1),
g_fold(S) <- foldl(add, [1, 2, 3], 0, S),
g_part(I, E) <- partition(b, [1, 2, 1], I, E),
greet >> (["h", "i"])
g_phrase <- phrase(greet, ["h", "i"]),
tpos(X, T) <- (X > 0, T is True),
tpos(X, T) <- (X <= 0, T is False),
g_tf(R) <- tfilter(tpos, [1, -2, 3], R),
g_tp(I, E) <- tpartition(tpos, [1, -2, 3], I, E),
"""


@pytest.fixture
def mod(tmp_path, request):
    name = f"bpn_{request.node.name.replace('[', '_').replace(']', '')}"
    p = tmp_path / f"{name}.clausal"
    p.write_text(_SRC.format(name=name))
    return _load_module(name, str(p))


def _answers(lm, functor, n=1):
    xs = [Var() for _ in range(n)]
    out = []
    for _ in call(functor, *xs, module=lm):
        v = [deref(x) for x in xs]
        out.append(v[0] if n == 1 else tuple(v))
    return out


def test_the_stored_value_is_the_plain_atom(mod):
    lm = mod.__dict__["$module"]
    assert _answers(lm, "q") == ["z"]
    assert _answers(lm, "r") == ["b"]
    assert type(_answers(lm, "r")[0]) is str
    assert _answers(lm, "l") == [["b", 2]]
    assert len(list(call("r", "b", module=lm))) == 1, "a plain query answers"


def test_goal_taking_builtins_resolve_the_atom_in_the_caller(mod):
    lm = mod.__dict__["$module"]
    assert len(list(call("g_map", module=lm))) == 1
    assert len(list(call("g_call", module=lm))) == 1
    assert _answers(lm, "g_fold") == [6]
    assert _answers(lm, "g_part", 2) == [([1, 1], [2])]
    assert len(list(call("g_phrase", module=lm))) == 1


def test_the_reified_list_builtins_drive_a_named_goal(mod):
    """tfilter/3 and tpartition/4 ran the goal in a plain inline loop, which
    cannot drive a ``MetaCallGoal`` (formerly ``_NamedGoal``; it delegates to call/N through a
    StepGenerator): the delegation step read as a solution with T unbound,
    and every element was dropped -- ``tfilter(tpos, [1, -2, 3], R)``
    answered ``R = []`` (2026-09-25; test_09 test_regression_tfilter_user_reified)."""
    lm = mod.__dict__["$module"]
    assert _answers(lm, "g_tf") == [[1, 3]]
    assert _answers(lm, "g_tp", 2) == [([1, 3], [-2])]


def test_a_query_passing_the_binding_or_the_atom_answers(mod):
    """The query side (``_ground_value``) already lowered a class/handle to
    the atom; maplist answered 0 for it until the atom resolved by name.

    After the W4b-2d flip the load binds ``b`` to its HANDLE, so there is no
    class era left to parametrize over, and the stand-in flip that rebound
    it by hand is gone: the binding is asserted to be the handle instead."""
    lm = mod.__dict__["$module"]
    md = mod.__dict__
    binding = md["b"]
    assert binding == mint_predicate_handle(lm.db, "b"), binding
    for goal in (binding, "b"):
        assert len(list(solve(("maplist", goal, [1]), lm))) == 1, goal
        assert len(list(solve(("maplist", goal, [2]), lm))) == 0, goal


def test_the_lowering_bakes_the_plain_atom_in_both_eras(mod):
    # Post-flip the load already binds the handle (no stand-in flip, no
    # class arm -- that arm would silently run the handle era too).
    md = dict(mod.__dict__)
    assert md["b"] == mint_predicate_handle(md["$module"].db, "b"), md["b"]
    with lowering_scope(md):
        expr = term_to_ast_expr(LoadName(name="b"), {})
    assert isinstance(expr, ast.Constant) and expr.value == "b"


def test_a_hide_data_atom_keeps_its_load(tmp_path):
    """A ``-hide`` DATA atom is mangled but no predicate: not lowered here
    (its runtime load IS its mangled spelling)."""
    md = {"hidden": mangle("somemod", "hidden")}
    with lowering_scope(md):
        expr = term_to_ast_expr(LoadName(name="hidden"), {})
    assert isinstance(expr, ast.Name)


def test_a_wrong_arity_atom_goal_still_names_the_arity(mod):
    """``maplist(b, L, L2)`` against b/1: the refusal a body call gets."""
    from clausal.predicate_diagnostics import PredicateArityMismatchError
    lm = mod.__dict__["$module"]
    with pytest.raises(PredicateArityMismatchError):
        list(solve(("maplist", "b", [1], Var()), lm))




def _L():
    return Var()


# One row per builtin that resolves a NAMED goal through
# ``higher_order._resolve_named_goal``: call/N, phrase/2,3, time_goal/1 and
# every goal-first list builtin (``_GOAL_FIRST_LIST_BUILTINS``).  Each calls
# a name the caller binds ONLY at another arity (b/1, add/3).
_WRONG_ARITY_GOALS = [
    ("call_1_atom", lambda: ("call", "b"), "b", 0),
    ("call_3_atom", lambda: ("call", "b", 1, 2), "b", 2),
    ("call_2_cell", lambda: ("call", ("add", 1), 2), "add", 2),
    ("phrase_2", lambda: ("phrase", "b", ["x"]), "b", 2),
    ("phrase_3", lambda: ("phrase", ("b", 1), ["x"], _L()), "b", 3),
    ("time_goal_1_atom", lambda: ("time_goal", "b"), "b", 0),
    ("time_goal_1_cell", lambda: ("time_goal", ("add", 1)), "add", 1),
    ("maplist_2", lambda: ("maplist", "add", [1]), "add", 1),
    ("maplist_3", lambda: ("maplist", "add", [1], _L()), "add", 2),
    ("include_3", lambda: ("include", "add", [1], _L()), "add", 1),
    ("exclude_3", lambda: ("exclude", "add", [1], _L()), "add", 1),
    ("foldl_4", lambda: ("foldl", "b", [1], 0, _L()), "b", 3),
    ("take_while_3", lambda: ("take_while", "add", [1], _L()), "add", 1),
    ("drop_while_3", lambda: ("drop_while", "add", [1], _L()), "add", 1),
    ("span_4", lambda: ("span", "add", [1], _L(), _L()), "add", 1),
    ("group_by_3", lambda: ("group_by", "add", [1], _L()), "add", 2),
    ("sort_by_3", lambda: ("sort_by", "add", [1], _L()), "add", 2),
    ("max_by_3", lambda: ("max_by", "add", [1], _L()), "add", 2),
    ("min_by_3", lambda: ("min_by", "add", [1], _L()), "add", 2),
    ("filter_map_3", lambda: ("filter_map", "add", [1], _L()), "add", 2),
    ("partition_4", lambda: ("partition", "add", [1], _L(), _L()), "add", 1),
    ("tfilter_3", lambda: ("tfilter", "add", [1], _L()), "add", 2),
    ("tpartition_4", lambda: ("tpartition", "add", [1], _L(), _L()), "add", 2),
]


@pytest.mark.parametrize("goal, name, arity",
                         [r[1:] for r in _WRONG_ARITY_GOALS],
                         ids=[r[0] for r in _WRONG_ARITY_GOALS])
def test_a_named_goal_at_a_missing_arity_raises_iso_existence_error(
        mod, goal, name, arity):
    """Ruling Q3 (2026-09-25, "do what Scryer does"): a NAMED goal (atom or
    cell) that nothing defines at the called arity, while the caller binds
    the name to a predicate at another, RAISES
    ``existence_error(procedure, Name/Arity)`` -- ``_resolve_named_goal``'s
    other-arity refusal -- rather than failing silently.  Pinned for every
    builtin sharing that resolver."""
    from clausal.predicate_diagnostics import PredicateArityMismatchError
    from clausal.terms import Compound
    lm = mod.__dict__["$module"]
    with pytest.raises(PredicateArityMismatchError) as exc:
        list(solve(goal(), lm))
    term = exc.value.term
    assert isinstance(term, Compound) and term.functor == "error", term
    formal = term.args[0]
    assert formal.functor == "existence_error" and formal.args[0] == mint("procedure")
    pi = formal.args[1]
    assert isinstance(pi, Compound) and pi.functor == "/"
    assert tuple(pi.args) == (mint(name), arity)



def _renamed(goal, old, new):
    """*goal* with every str slot equal to *old* (the goal name, at any
    nesting of cells) replaced by *new*."""
    if type(goal) is tuple:
        return tuple(_renamed(g, old, new) for g in goal)
    return new if goal == old else goal


@pytest.mark.parametrize("goal, name, arity",
                         [r[1:] for r in _WRONG_ARITY_GOALS],
                         ids=[r[0] for r in _WRONG_ARITY_GOALS])
def test_a_named_goal_naming_an_unknown_procedure_raises_iso_existence_error(
        mod, goal, name, arity):
    """Ruling 2 (operator, 2026-09-25, "like Scryer"): a meta-call naming an
    UNKNOWN procedure raises ``existence_error(procedure, Name/Arity)``,
    catchable -- it used to FAIL silently (the retired §4.2 contract).  The
    same builtins, the same arities, with the name bound to nothing; a
    phrase nonterminal N//A is N/(A+2)."""
    lm = mod.__dict__["$module"]
    with pytest.raises(LogicException) as exc:
        list(solve(_renamed(goal(), name, "nosuch"), lm))
    term = exc.value.term
    assert term.functor == "error", term
    formal = term.args[0]
    assert formal.functor == "existence_error" and formal.args[0] == mint("procedure")
    assert formal.args[1] == Compound("/", (mint("nosuch"), arity))


def test_the_unknown_procedure_raise_is_catchable_in_source(tmp_path):
    name = "bpn_catch_unknown"
    p = tmp_path / f"{name}.clausal"
    p.write_text(
        f"-module({name}, [])\n"
        "-private([procedure, bpn_absent_proc])\n"
        "caught(PI) <- catch(maplist(bpn_absent_proc, [1]),"
        " error(existence_error(procedure, PI), _), True)\n")
    # A distinct atom, not ``nosuch``: a -private atom declared here leaks into
    # another module's ``m.nosuch(...)`` resolution (pre-existing on main;
    # todo/private-atom-leaks-into-another-modules-qualified-call-2026-09-25.md).
    lm = _load_module(name, str(p)).__dict__["$module"]
    pi = Var()
    assert [deref(pi) for _ in call("caught", pi, module=lm)] == [
        Compound("/", (mint("bpn_absent_proc"), 1))]


def test_listing_a_bare_name_is_not_a_predicate_indicator(mod):
    """Source ``listing(b)`` passes the ATOM -- no longer b/1's class.
    Operator ruling 2026-09-25 ("do what Scryer does"): a bare atom is ``type_error(predicate_indicator, b)``
    (it named ``b/0`` and raised existence_error before 2026-09-25).
    ``listing(b/1)`` is the spelling."""
    from clausal.logic.exceptions import LogicException
    lm = mod.__dict__["$module"]
    with pytest.raises(LogicException) as exc:
        list(solve(("listing", "b"), lm))
    formal = exc.value.term.args[0]
    assert formal.functor == "type_error"
    assert formal.args == (mint("predicate_indicator"), mint("b"))
    assert len(list(solve(("listing", ("/", "b", 1)), lm))) == 1
