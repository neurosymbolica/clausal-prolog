"""The reflection behaviors clausal-rewrite is built on, pinned as tests.

Each test documents an assumption of the rewrite driver or of a rule written in
Clausal.  A failure here is a DESIGN problem, not a bug to route around: the
rewriter reads clauses through :mod:`clausal.reflection` and writes rules as
ordinary Clausal predicates over the reified vocabulary, so if reification does
not preserve what these tests claim, the rules cannot be written this way at
all.
"""

import ast
import textwrap

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call
from clausal.logic.variables import Var, deref
from clausal.reflection import (
    vfield,
    Atom,
    Clause,
    Escape,
    Goal,
    Variable,
    reify_ast,
    render_source,
)


def _reify_stmt(source):
    """Reify the first statement of ``source`` the way the driver will.

    Always with the original source segment: reification reads the ``<-``
    arrow off the spacing, so a segment is not an optimization, it is the only
    thing that distinguishes a lambda from a comparison.
    """
    tree = ast.parse(source)
    stmt = tree.body[0]
    return reify_ast(stmt, source=ast.get_source_segment(source, stmt))


def _rules_module(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text))
    return _load_module(name, str(path)).__dict__["$module"]


def test_inline_lambda_arrow_and_genuine_lt_reify_differently():
    lam = _reify_stmt("t(B) <- (fold(((X) <- p(X)), B))\n")
    lt = _reify_stmt("t(A, B) <- (check(A < -B))\n")
    assert repr(vfield(lam, "goals")) != repr(vfield(lt, "goals"))
    assert "< -" not in render_source(lam)
    assert "A < -B" in render_source(lt)


def test_unify_goal_reifies_as_matchable_operator_node():
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    assert len(vfield(clause, "goals")) == 2
    assert type(vfield(clause, "goals")[1]).__name__ == "Unify"


def test_clausal_pattern_matches_unify_goal_and_extracts_sides(tmp_path):
    """The core move of a fold rule: destructure ``V is TERM`` in Clausal."""
    module = _rules_module(tmp_path, "_spike_unify_sides", """\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal, Variable, Atom])

        unify_sides((A is B), A, B),
        """)
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    left, right = Var(), Var()
    hits = 0
    for _ in call("unify_sides", vfield(clause, "goals")[1], left, right, module=module):
        hits += 1
        assert deref(left) == Variable("S")
        assert deref(right) == Goal("unknown", [Variable("M")], [])
        break
    assert hits == 1


def test_reified_subterm_walks_goal_lists_and_finds_variables(tmp_path):
    module = _rules_module(tmp_path, "_spike_occurs", """\
        -double_quotes(chars)
        -import_from(reflection, [reified_subterm, Variable])

        occurs_in(X, V) <- reified_subterm(X, V)
        """)
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    rest = [vfield(clause, "goals")[0]]  # the body minus the unify goal

    def occurs(container, name):
        for _ in call("occurs_in", container, Variable(name), module=module):
            return True
        return False

    assert occurs(rest, "M")  # M is used by m(K, M)
    assert not occurs(rest, "S")  # S is not -- which is what makes it foldable


def test_occurs_check_sees_into_a_freshly_built_term(tmp_path):
    """``reified_subterm`` follows bound logic variables while walking.

    It used not to: a term a rule had just rebuilt holds logic variables bound
    to the original's structure, and the walk stopped at them — so "construct
    the answer, then check the answer is sound" was not an available shape,
    and the head-fold's post-condition once passed vacuously (a clause with a
    star-unpacked list head came out with its element unbound).  The walk now
    derefs as it descends (matching ``replace_subterm``'s ``_rewrites``), so a
    variable is found in the rebuilt term exactly as in the original.  A
    PRE-condition is still the better rule design — it refuses before building
    anything — but a post-check is no longer a silent no-op.  See
    todo/reflection-gaps-found-by-the-rewriter.md, gap 1.
    """
    module = _rules_module(tmp_path, "_spike_rebuilt", """\
        -double_quotes(chars)
        -import_from(reflection, [reified_subterm, Goal, Variable])

        rebuild(Goal(NAME, ARGS, KW), Goal(NAME, ARGS, KW)),

        sees_direct(H, N) <- reified_subterm(H, Variable(N))
        sees_rebuilt(H, N) <- (rebuild(H, H2), reified_subterm(H2, Variable(N)))
        """)
    head = vfield(_reify_stmt("star(P, [a, *T]) <- (helper(P), T is [b])\n"), "head")
    assert any(True for _ in call("sees_direct", head, "T", module=module))
    assert any(True for _ in call("sees_rebuilt", head, "T", module=module))


def test_render_of_mutated_clause_emits_valid_clausal():
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    folded = Clause(
        Goal("r", [Variable("K"), Goal("unknown", [Variable("M")], [])], []),
        [vfield(clause, "goals")[0]],
        vfield(clause, "position"),
    )
    text = render_source(folded)
    assert "r(K, unknown(M))" in text
    assert "is unknown" not in text
    reparsed = reify_ast(ast.parse(text).body[0], source=text)
    assert vfield(reparsed, "head") == vfield(folded, "head")


# ---- eta-reduction (unnecessary_lambda) assumptions ------------------------
#
# The rule replaces a lambda that merely forwards its parameters --
# ``((X) <- add_one(X))`` -- with the bare reference ``add_one``.  That is only
# writable if (a) the ENGINE treats the two argument forms identically, and
# (b) reification distinguishes a forwarding lambda from everything the rule
# must refuse.  Both halves are pinned here.


def _clausal_module(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text))
    return _load_module(name, str(path)).__dict__["$module"]


def _solutions(module, name, *args):
    out = []
    for _ in call(name, *args, module=module):
        out.append(tuple(_deref_walk(arg) for arg in args))
    return out


def test_engine_accepts_bare_reference_where_lambda_is_accepted(tmp_path):
    """The two argument forms have IDENTICAL solutions -- maplist and foldl."""
    module = _clausal_module(tmp_path, "_spike_eta_equiv", """\
        add_one(X, Y) <- (Y == X + 1)
        add_step(X, ACC, OUT) <- (OUT == ACC + X)

        map_lambda(L, R) <- maplist(((X, Y) <- add_one(X, Y)), L, R)
        map_bare(L, R) <- maplist(add_one, L, R)

        fold_lambda(L, R) <- foldl(((X, A, O) <- add_step(X, A, O)), L, 0, R)
        fold_bare(L, R) <- foldl(add_step, L, 0, R)
        """)
    assert _solutions(module, "map_lambda", [1, 2, 3], Var()) == \
        _solutions(module, "map_bare", [1, 2, 3], Var()) == [([1, 2, 3], [2, 3, 4])]
    assert _solutions(module, "fold_lambda", [1, 2, 3], Var()) == \
        _solutions(module, "fold_bare", [1, 2, 3], Var()) == [([1, 2, 3], 6)]


def test_engine_accepts_bare_reference_through_user_call_goal(tmp_path):
    """Equivalence is call_goal's, not a builtin whitelist's: a user-defined
    higher-order predicate sees the same behavior from both forms."""
    module = _clausal_module(tmp_path, "_spike_eta_user", """\
        twice(G, X, Z) <- (call_goal(G, X, Y), call_goal(G, Y, Z))
        add_one(X, Y) <- (Y == X + 1)

        user_lambda(X, Z) <- twice(((A, B) <- add_one(A, B)), X, Z)
        user_bare(X, Z) <- twice(add_one, X, Z)
        """)
    assert _solutions(module, "user_lambda", 5, Var()) == \
        _solutions(module, "user_bare", 5, Var()) == [(5, 7)]


def test_engine_accepts_bare_dotted_reference(tmp_path):
    """A dotted callee eta-reduces to the dotted reference, same solutions."""
    helper = tmp_path / "etahelper.clausal"
    helper.write_text(
        "-module(etahelper, [bump(X, Y)])\n\nbump(X, Y) <- (Y == X + 1)\n"
    )
    _load_module("etahelper", str(helper))
    module = _clausal_module(tmp_path, "_spike_eta_dotted", """\
        -import_module(etahelper)

        dot_lambda(L, R) <- maplist(((X, Y) <- etahelper.bump(X, Y)), L, R)
        dot_bare(L, R) <- maplist(etahelper.bump, L, R)
        """)
    assert _solutions(module, "dot_lambda", [1, 2], Var()) == \
        _solutions(module, "dot_bare", [1, 2], Var()) == [([1, 2], [2, 3])]


def test_engine_lambda_param_shadows_the_enclosing_binding(tmp_path):
    """docs/lambdas.md 'Parameter shadowing': a param named like an enclosing
    variable shadows it, so eta-reduction stays sound in the collision case."""
    module = _clausal_module(tmp_path, "_spike_eta_shadow", """\
        -double_quotes(atom)
        big(X) <- (X > 3)

        shadow_case(L, R) <- (X is 99, maplist((X <- big(X)), L), R is "yes")
        bare_case(L, R) <- (X is 99, maplist(big, L), R is "yes")
        """)
    assert _solutions(module, "shadow_case", [4, 5], Var()) == \
        _solutions(module, "bare_case", [4, 5], Var()) == [([4, 5], mint("yes"))]


def test_forwarding_lambda_reifies_as_lambda_node_with_atom_params():
    """The shape the rule MATCHES: a raw ``Lambda`` node whose body is a
    ``Goal``, with param references reified as ``Atom`` (never ``Variable``)."""
    clause = _reify_stmt("t(L, R) <- (maplist(((X, Y) <- add_one(X, Y)), L, R))\n")
    lam = vfield(vfield(clause, "goals")[0], "args")[0]
    assert type(lam).__name__ == "Lambda"
    assert type(lam).__module__ == "clausal.pythonic_ast.nodes"
    assert [type(p).__name__ for p in lam.params.params] == ["PosOrKwParam"] * 2
    assert [p.name for p in lam.params.params] == ["X", "Y"]
    assert lam.body == Goal("add_one", [Atom("X"), Atom("Y")], [])


def test_bare_reference_reifies_as_atom():
    """The shape the rule CONSTRUCTS -- plain and dotted."""
    clause = _reify_stmt("t(L, R) <- (maplist(add_one, L, R))\n")
    assert vfield(vfield(clause, "goals")[0], "args")[0] == Atom("add_one")
    dotted = _reify_stmt("t(L) <- (maplist(mod.pred, L))\n")
    assert vfield(vfield(dotted, "goals")[0], "args")[0] == Atom("mod.pred")


def test_captured_enclosing_variable_reifies_as_variable_in_lambda_body():
    """Capture is VISIBLE: an enclosing-clause variable in the body is a
    ``Variable`` term, which can never equal the ``Atom`` a param reifies to.
    The rule's exact param/argument match is therefore also its capture fence."""
    clause = _reify_stmt("t(Z, L) <- (maplist((X <- add(X, Z)), L))\n")
    assert vfield(vfield(clause, "goals")[0], "args")[0].body == Goal("add", [Atom("X"), Variable("Z")], [])


def test_shadowing_param_reference_still_reifies_as_atom():
    """Reification agrees with the engine's shadowing: even when the clause has
    its own X, the lambda body's X is the param -- an ``Atom``."""
    clause = _reify_stmt("t(X, L) <- (m(X), maplist((X <- p(X)), L))\n")
    assert vfield(vfield(clause, "goals")[1], "args")[0].body == Goal("p", [Atom("X")], [])


def test_variable_callee_lambda_body_is_not_a_goal():
    """``(X <- F(X))`` with F a clause variable is a call through a variable;
    it reifies as an ``Escape``, so a body-is-a-Goal match refuses it."""
    from clausal.reflection import is_v  # noqa: PLC0415
    clause = _reify_stmt("t(F, L) <- (maplist((X <- F(X)), L))\n")
    assert is_v(vfield(vfield(clause, "goals")[0], "args")[0].body, Escape)


def test_zero_param_forwarding_lambda_reifies_with_empty_params():
    clause = _reify_stmt("t() <- (call_goal((() <- pings())))\n")
    lam = vfield(vfield(clause, "goals")[0], "args")[0]
    assert type(lam).__name__ == "Lambda"
    assert lam.params.params == []
    assert lam.body == Goal("pings", [], [])
