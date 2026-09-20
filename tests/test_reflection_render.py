"""Round-trip tests for clausal.reflection render_ast/render_source — the
inverse of reify_ast. Invariant: reify(render_source(clause)) is structurally
identical to clause (positions ignored)."""

import dataclasses
import glob
import os

import pytest

from clausal.logic.solve import solve   # P2: a cell goal is driven, never iterated
from clausal.reflection import (
    vfield,
    is_v,
    Atom,
    Clause,
    Escape,
    FormatString,
    Goal,
    ReifyError,
    RenderError,
    reify_source,
    render_ast,
    render_source,
)


def strip_positions(term):
    """Recursively null every ``position`` field so structural == ignores
    source location. Reified terms carry ``_fields``; simple_ast operator
    nodes are dataclasses (their position is compare=False, but we normalise
    anyway to reach nested position-bearing terms)."""
    if isinstance(term, list):
        return [strip_positions(x) for x in term]
    # P2: a reified-vocabulary term is a CELL, so it must be recognised
    # BEFORE the generic tuple branch below -- which would otherwise walk
    # its slots as plain data and never null the `position` one, leaving
    # every round-trip comparison to fail on positions it meant to ignore.
    from clausal.reflection import _VOCAB_FIELDS
    if (isinstance(term, tuple) and term and isinstance(term[0], str)
            and term[0] in _VOCAB_FIELDS):
        names = _VOCAB_FIELDS[term[0]]
        return (term[0], *[
            None if name == "position" else strip_positions(value)
            for name, value in zip(names, term[1:])
        ])
    if isinstance(term, tuple):
        return tuple(strip_positions(x) for x in term)
    if isinstance(term, dict):
        return {k: strip_positions(v) for k, v in term.items()}
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return dataclasses.replace(term, **{
            f.name: (None if f.name == "position" else strip_positions(getattr(term, f.name)))
            for f in dataclasses.fields(term)
        })
    fields = getattr(type(term), "_fields", None)
    if fields is not None:
        return type(term)(*[
            None if name == "position" else strip_positions(getattr(term, name))
            for name in fields
        ])
    return term


def only_clause(src):
    clauses = [i for i in reify_source(src) if is_v(i, Clause)]
    assert len(clauses) == 1, f"expected one clause, got {len(clauses)}"
    return clauses[0]


def assert_round_trips(src):
    """render_source then re-reify equals the original clause (ignoring positions)."""
    original = only_clause(src)
    rendered_text = render_source(original)
    reparsed = only_clause(rendered_text + "\n")
    assert strip_positions(reparsed) == strip_positions(original), (
        f"round-trip mismatch for {src!r}\n  rendered: {rendered_text!r}"
    )


class TestFacts:
    @pytest.mark.parametrize("src", [
        "edge(1, 2),\n",
        "item('widget', 2.5),\n",
        "status(ok, 1),\n",
        "temp(-40),\n",
        "rule(X, Y),\n",
    ])
    def test_fact_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src,expected", [
        ("edge(1, 2),\n", "edge(1, 2),"),
        ("status(ok, 1),\n", "status(ok, 1),"),
        ("per_se(a, b),\n", "per_se(a, b),"),
    ])
    def test_fact_surface_is_bare_head_comma(self, src, expected):
        # A fact must render to the canonical clausal surface ``head,`` (bare head
        # + trailing comma), NOT the Python 1-tuple literal ``(head,)``. Both
        # re-reify to the same Clause (the structural round-trip is blind to this),
        # but the parenthesized form is non-idiomatic surface that the mutation
        # auditor would splice into a ``.clausal`` file. Guard the surface itself.
        rendered = render_source(only_clause(src))
        assert rendered == expected, f"fact surface not canonical: {rendered!r}"
        assert not rendered.startswith("("), (
            f"fact rendered as a parenthesized tuple: {rendered!r}"
        )


class TestRules:
    @pytest.mark.parametrize("src", [
        "connected(X, Y) <- edge(X, Y)\n",
        "grandparent(X, Z) <- (parent(X, Y), parent(Y, Z))\n",
        "reachable(X) <- edge(_, _)\n",
        "three(A) <- (pa(A), qa(A), ra(A))\n",
    ])
    def test_rule_round_trips(self, src):
        assert_round_trips(src)


class TestOperators:
    @pytest.mark.parametrize("src", [
        "positive(N) <- (N > 0)\n",
        "at_least(N) <- (N >= 10)\n",
        "eq(N) <- (N == 0)\n",
        "neq(N) <- (N != 0)\n",
        "sum(X, Y, Z) <- (Z is X + Y)\n",
        "prod(X, Y, Z) <- (Z is X * Y)\n",
        "diff(X, Y, Z) <- (Z is X - Y)\n",
        "unify2(X, Y) <- (X is Y)\n",
        "dif2(X, Y) <- (X is not Y)\n",
        "free(A) <- (not busy(A))\n",
        "either(A) <- (pa(A) or qa(A))\n",
        "both(A) <- (pa(A) and qa(A))\n",
        "neg(X, Y) <- (Y is -X)\n",
        "cons_tail(T) <- head([a, b | T])\n",
        "star_tail(T) <- head([a, b, *T])\n",
    ])
    def test_operator_round_trips(self, src):
        assert_round_trips(src)


class TestCompoundAndKwargs:
    @pytest.mark.parametrize("src", [
        "holds(state(A)) <- check(A)\n",
        "deep(pp(qq(rr(X)))) <- base(X)\n",
        "with_list(pp([1, 2, 3])),\n",
        "nested([pp(X), qq(Y)]),\n",
    ])
    def test_compound_round_trips(self, src):
        assert_round_trips(src)


class TestIfThenElse:
    @pytest.mark.parametrize("src", [
        "pick(X, Y) <- (Y is if_(X > 0, 1, 2))\n",
    ])
    def test_ite_round_trips(self, src):
        assert_round_trips(src)


class TestEscapes:
    @pytest.mark.parametrize("src", [
        "calc(X, Y) <- (Y is ++(X + 1))\n",
        "calc2(X, Y, Z) <- (Z is ++(X * Y + 1))\n",
    ])
    def test_escape_round_trips(self, src):
        assert_round_trips(src)


class TestSubscript:
    @pytest.mark.parametrize("src", [
        "get(P, I) <- (I is P[flags])\n",
        "get_dotted(P, I) <- (I is P[a.b.c])\n",
    ])
    def test_subscript_round_trips(self, src):
        assert_round_trips(src)

    def test_dot_sugar_flattens_to_subscript(self):
        """``P.k`` is source sugar: it reifies (and renders) as ``P[k]``.

        The renderer does not preserve the ``.`` spelling — flattening is the
        accepted trade in
        docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md.
        """
        # nv
        dotted = only_clause("get_dot(P, I) <- (I is P.flags)\n")
        bracket = only_clause("get_dot(P, I) <- (I is P[flags])\n")
        assert strip_positions(dotted) == strip_positions(bracket)

    def test_read_once_lowering_is_idempotent(self):
        """Rendering a lowered clause and re-reifying must not re-lower it."""
        # nv
        original = only_clause("twice(P, I) <- (chk(P.k), I is P.k)\n")
        once = render_source(original)
        twice = render_source(only_clause(once + "\n"))
        assert once == twice
        assert strip_positions(only_clause(once + "\n")) == \
            strip_positions(original)


class TestDictLiteral:
    @pytest.mark.parametrize("src", [
        "merge(A, B) <- (A is {**B, foo: B})\n",
        "merge2(A, B, C) <- (A is {**B, foo: C, bar: B})\n",
    ])
    def test_dict_literal_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src", [
        # Non-splat dict with a bare-atom key: `{foo: V}` is rewritten to
        # DictTerm({$intern_atom('foo'): V}); the atom key reifies to an
        # unhashable Goal, so it must NOT key a raw Python dict. Must round-trip.
        "K(B) <- (X is {foo: B})\n",
        "K2(B) <- (X is {foo: B, bar: 2})\n",
        # Mixed atom + string/int keys in one literal.
        "K3(B) <- (X is {foo: B, 'baz': 3})\n",
    ])
    def test_atom_key_dict_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src", [
        # Non-splat dict with a logic-VAR key: `{K: V}` reifies the key to a
        # Variable, which is unhashable, so it must NOT key a raw Python dict.
        # Must round-trip (same DictLiteral route as atom keys).
        "F(O) <- (K is 'a', O is {K: 20})\n",
        # Mixed var + string/int keys, and var + atom keys, in one literal.
        "F2(K, O) <- (O is {K: 20, 'baz': 3})\n",
        "F3(K, B, O) <- (O is {foo: B, K: 20})\n",
    ])
    def test_var_key_dict_round_trips(self, src):
        assert_round_trips(src)

    def test_var_key_dict_shares_splat_representation(self):
        # A var key must reify to the SAME shape whether or not the literal
        # also splats — one DictLiteral representation for the auditor.
        splat = vfield(only_clause("A(K, B) <- (X is {**B, K: 2})\n"), "goals")[0]
        plain = only_clause("A(K, B) <- (X is {K: 2})\n").goals[0]
        splat_key = strip_positions(splat).right.keys[-1]
        plain_key = strip_positions(plain).right.keys[-1]
        assert splat_key == plain_key, (
            f"var key differs by splat: {plain_key!r} vs {splat_key!r}"
        )

    def test_atom_key_dict_shares_splat_representation(self):
        # An atom key must reify to the SAME shape whether or not the literal
        # also splats — one DictLiteral representation for the auditor.
        splat = vfield(only_clause("A(B) <- (X is {**B, foo: B})\n"), "goals")[0]
        plain = only_clause("A(B) <- (X is {foo: B})\n").goals[0]
        splat_key = strip_positions(splat).right.keys[-1]
        plain_key = strip_positions(plain).right.keys[-1]
        assert splat_key == plain_key, (
            f"atom key differs by splat: {plain_key!r} vs {splat_key!r}"
        )


class TestArrowLambda:
    @pytest.mark.parametrize("src", [
        "run0(C) <- run(( () <- base()), C)\n",
        "run1(C) <- run((X <- base(X)), C)\n",
        "run_n(C) <- run(((ID, PR) <- req(ID, PR)), C)\n",
        "run_body(C) <- run((X <- (Y is X + 1)), C)\n",
        "run_two(C) <- run((X <- p(X)), (Y <- q(Y)), C)\n",
    ])
    def test_arrow_lambda_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src", [
        # A genuine `X < -N` comparison must NOT be tightened into a lambda arrow.
        "cmp(X) <- (X < -1)\n",
        "cmp_var(X, Y) <- (X < -Y)\n",
    ])
    def test_spaced_comparison_not_arrow(self, src):
        assert_round_trips(src)


class TestFormatString:
    @pytest.mark.parametrize("src", [
        'greet(name, M) <- (M is f"hi {name}")\n',
        'msg(X, S) <- (S is f"val={X}")\n',
    ])
    def test_format_string_round_trips(self, src):
        assert_round_trips(src)


class TestCompareChain:
    @pytest.mark.parametrize("src", [
        "range(X) <- (0 < X < 10)\n",
        "range2(X) <- (0 <= X <= 10)\n",
        "mixed(X) <- (0 < X <= 10)\n",
        "four(X, Y) <- (0 < X < Y < 100)\n",
        "eqs(X, Y) <- (X == Y == 3)\n",
        "chained(X, Y) <- (X is Y is 3)\n",
        "member(X, L) <- (0 < X in L)\n",
        # An operand that is itself an expression, and a negated operand — the
        # rendered `<` must stay a comparison, never tighten into a `<-` arrow.
        "expr(X, Y) <- (0 < X + 1 < Y)\n",
        "neg_operand(X) <- (-5 < X < 5)\n",
    ])
    def test_compare_chain_round_trips(self, src):
        assert_round_trips(src)

    def test_chain_surface_is_a_single_chain(self):
        # Hand-written from the language's own syntax: a chain renders as ONE
        # Python comparison chain, not a conjunction of two comparisons.
        rendered = render_source(only_clause("range(X) <- (0 < X < 10)\n"))
        assert rendered == "range(X) <- (0 < X < 10)", rendered

    def test_unlinked_chain_raises(self):
        # A mutated chain whose adjacent operands no longer agree
        # (`0 < X` then `Y < 10`) cannot be written as a Python chain at all —
        # emitting `0 < X < 10` would silently drop Y. Refuse.
        from clausal.pythonic_ast.nodes import CompareChain, Lt
        from clausal.reflection import Variable, is_v, vfield

        chain = CompareChain(comparisons=[
            Lt(left=0, right=Variable("X")),
            Lt(left=Variable("Y"), right=10),
        ])
        with pytest.raises(RenderError):
            render_source(chain)

    def test_single_comparison_chain_raises(self):
        # A one-comparison CompareChain has no chain surface: `0 < X` re-reifies
        # to a bare Lt node, not a CompareChain. Refuse rather than corrupt.
        from clausal.pythonic_ast.nodes import CompareChain, Lt
        from clausal.reflection import Variable, is_v, vfield

        with pytest.raises(RenderError):
            render_source(CompareChain(comparisons=[Lt(left=0, right=Variable("X"))]))

    def test_chain_of_unrenderable_op_raises(self):
        from clausal.pythonic_ast.nodes import Add, CompareChain

        with pytest.raises(RenderError):
            render_source(CompareChain(comparisons=[
                Add(left=1, right=2), Add(left=2, right=3),
            ]))


class TestSetLiteral:
    @pytest.mark.parametrize("src", [
        "has(S) <- (S is {a})\n",
        "has3(S) <- (S is {a, b, c})\n",
        "has_ints(S) <- (S is {1, 2, 3})\n",
        "has_mixed(S, X) <- (S is {1, 'two', X})\n",
        "has_splat(S, T) <- (S is {a, *T})\n",
        "has_nested(S, X) <- (S is {pp(X), b})\n",
    ])
    def test_set_literal_round_trips(self, src):
        assert_round_trips(src)

    def test_set_surface_is_braces(self):
        # Hand-written surface: a set literal is `{...}`, not `set([...])`.
        rendered = render_source(only_clause("has_ints(S) <- (S is {1, 2})\n"))
        assert rendered == "has_ints(S) <- (S is {1, 2})", rendered

    def test_empty_set_literal_raises(self):
        # There is no empty-set surface: `{}` is a dict, and ast.unparse emits
        # `{*()}` for an empty ast.Set, which re-reifies as a one-element set
        # holding a splatted empty tuple. Refuse rather than corrupt.
        from clausal.pythonic_ast.nodes import SetLiteral

        with pytest.raises(RenderError):
            render_source(SetLiteral(elements=[]))


class TestPlainConstants:
    @pytest.mark.parametrize("src", [
        # `ast.Constant` payloads the reifier yields as themselves. bool/int/
        # float/complex/str were already covered; None and bytes were not.
        "nil(X) <- (X is None)\n",
        "nil_arg(X) <- chk(X, None)\n",
        "bytes(X) <- (X is b'ab')\n",
        "bytes_arg(X) <- chk(X, b'\\x00')\n",
        # `...` reifies but does not *compile* (the goal compiler rejects it), so
        # it is not live surface — still, render inverts reify, so it must
        # round-trip rather than raise.
        "dots(X) <- (X is ...)\n",
    ])
    def test_constant_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src,expected", [
        ("nil(X) <- (X is None)\n", "nil(X) <- (X is None)"),
        ("bytes(X) <- (X is b'ab')\n", "bytes(X) <- (X is b'ab')"),
        ("dots(X) <- (X is ...)\n", "dots(X) <- (X is ...)"),
    ])
    def test_constant_surface(self, src, expected):
        assert render_source(only_clause(src)) == expected


class TestInertPythonExprNodes:
    """``await``/``yield`` in a clause body compile to inert *term* structures
    (``Await(value=…)`` / ``Yield(value=…)``) — no coroutine involved. They are
    reachable surface, so the renderer must round-trip them."""

    @pytest.mark.parametrize("src", [
        "aw(L, M) <- (M is await L)\n",
        "aw_expr(L, M) <- (M is await pp(L))\n",
        "yi(M) <- (M is (yield))\n",
        "yi_val(X, M) <- (M is (yield X))\n",
        "yi_from(X, M) <- (M is (yield from X))\n",
    ])
    def test_inert_node_round_trips(self, src):
        assert_round_trips(src)


class TestOutOfScope:
    def test_module_directive_raises(self):
        items = reify_source("-module(m)\n")
        directive = next(i for i in items if type(i).__name__ == "ModuleDirective")
        with pytest.raises(RenderError):
            render_source(directive)

    def test_python_code_raises(self):
        items = reify_source("def helper():\n    return 1\n")
        pycode = next(i for i in items if type(i).__name__ == "PythonCode")
        with pytest.raises(RenderError):
            render_source(pycode)


class TestBoundLogicVars:
    """A reified term may hold a *logic* ``Var`` (not a reified ``Variable``) —
    e.g. an operator node built by ``op_node/3`` over an operand that is later
    bound.  The renderer must follow the binding; an unbound var stays a loud
    ``RenderError`` (no surface form)."""

    def test_bound_var_operand_renders_its_value(self):
        from clausal.logic.variables import Var, Trail, unify
        from clausal.pythonic_ast import nodes as simple_ast

        trail = Trail()
        x = Var()
        unify(x, 5, trail)
        node = simple_ast.Gt(left=x, right=1)
        assert render_source(node) == "5 > 1"
        # and it re-reifies to a Gt over the dereferenced operands
        back = vfield(reify_source("H <- (5 > 1)\n")[0], "goals")[0]
        rebuilt = reify_source(f"H <- ({render_source(node)})\n")[0].goals[0]
        assert strip_positions(rebuilt) == strip_positions(back)

    def test_bound_var_nested_deeper_in_term_renders(self):
        from clausal.logic.variables import Var, Trail, unify
        from clausal.pythonic_ast import nodes as simple_ast

        trail = Trail()
        x = Var()
        unify(x, 7, trail)
        # var buried inside a list operand of a Goal, not at the top level
        node = Goal("f", [simple_ast.Add(left=x, right=1)], [])
        assert render_source(node) == "f(7 + 1)"

    def test_bound_var_holding_a_reified_compound_renders(self):
        from clausal.logic.variables import Var, Trail, unify
        from clausal.pythonic_ast import nodes as simple_ast

        trail = Trail()
        x = Var()
        unify(x, Goal("f", [1, 2], []), trail)  # var bound to a compound, not a scalar
        node = simple_ast.Gt(left=x, right=1)
        assert render_source(node) == "f(1, 2) > 1"

    def test_unbound_var_still_raises(self):
        from clausal.logic.variables import Var
        from clausal.pythonic_ast import nodes as simple_ast

        node = simple_ast.Gt(left=Var(), right=1)
        with pytest.raises(RenderError):
            render_source(node)


def _bound(value):
    """A fresh logic Var bound to *value* (binding persists past the Trail)."""
    from clausal.logic.variables import Var, Trail, unify

    x = Var()
    unify(x, value, Trail())
    return x


class TestBoundLogicVarsInFields:
    """Bound logic Vars in *name/structural field* positions that bypass
    ``term()`` — ``Goal.name``/``args``/``kwargs``, ``Clause.goals``,
    ``Variable.name``, ``Escape.code``, dict keys.  Each must render the bound
    value; an unbound var (or a post-deref duplicate dict key) must raise
    ``RenderError``, never ``TypeError``/``AttributeError``.  Mirrors
    ``TestBoundLogicVars``; see the renderer-deref name/structural-fields todo."""

    def test_goal_name_bound_var_renders(self):
        assert render_source(Goal(_bound("foo"), [1], [])) == "foo(1)"

    def test_goal_args_list_bound_var_renders(self):
        assert render_source(Goal("f", _bound([1, 2]), [])) == "f(1, 2)"

    def test_goal_kwargs_list_bound_var_renders(self):
        assert render_source(Goal("f", [], _bound([("k", 1)]))) == "f(k=1)"

    def test_clause_goals_bound_var_renders(self):
        clause = Clause(Goal("H", [], []), _bound([Goal("g", [], [])]), None)
        assert render_source(clause) == "H() <- (g())"

    def test_variable_name_bound_var_renders(self):
        from clausal.reflection import Variable, is_v, vfield

        assert render_source(Variable(_bound("X"))) == "X"

    def test_escape_code_bound_var_renders(self):
        assert render_source(Escape(_bound("len(L)"), None, None)) == "++len(L)"

    def test_render_ast_top_level_var_bound_to_clause_renders(self):
        clause = Clause(Goal("H", [], []), [Goal("g", [], [])], None)
        assert render_source(_bound(clause)) == "H() <- (g())"

    def test_dict_literal_intern_atom_key_bound_var_renders(self):
        from clausal.pythonic_ast import nodes as simple_ast

        key = Goal("$intern_atom", ["foo"], [])
        node = simple_ast.DictLiteral(keys=[_bound(key)], values=[1])
        assert render_source(node) == "{foo: 1}"

    def test_goal_kwarg_entry_bound_var_renders(self):
        # the whole (name, value) pair is a bound var, not just its name
        assert render_source(Goal("f", [], [_bound(("k", 1))])) == "f(k=1)"

    def test_goal_kwarg_name_bound_var_renders(self):
        assert render_source(Goal("f", [], [(_bound("k"), 1)])) == "f(k=1)"

    def test_dict_literal_key_container_bound_var_renders(self):
        from clausal.pythonic_ast import nodes as simple_ast

        key = Goal("$intern_atom", ["foo"], [])
        node = simple_ast.DictLiteral(keys=_bound([key]), values=[1])
        assert render_source(node) == "{foo: 1}"

    def test_dict_literal_intern_atom_args_bound_var_renders(self):
        from clausal.pythonic_ast import nodes as simple_ast

        key = Goal("$intern_atom", _bound(["foo"]), [])
        node = simple_ast.DictLiteral(keys=[key], values=[1])
        assert render_source(node) == "{foo: 1}"

    def test_lambda_param_name_bound_var_renders(self):
        import ast as _ast
        import dataclasses
        from clausal.reflection import reify_ast, is_v, vfield

        lam = reify_ast(_ast.parse("((X, Y) <- foo(X, Y))", mode="eval").body)
        ground = render_source(lam)
        p0 = dataclasses.replace(lam.params.params[0], name=_bound("X"))
        params = dataclasses.replace(lam.params, params=[p0, lam.params.params[1]])
        assert render_source(dataclasses.replace(lam, params=params)) == ground

    def test_duplicate_keys_differing_ast_but_equal_surface_raise(self):
        # bound(-1) and bound(Negate(1)) dump-differ but both unparse to "-1";
        # the collision key must be the surface text, or a key silently drops.
        from clausal.pythonic_ast import nodes as simple_ast

        term = {_bound(-1): "a", _bound(simple_ast.Negate(operand=1)): "b"}
        with pytest.raises(RenderError):
            render_source(term)

    @pytest.mark.parametrize("term_factory", [
        lambda V: Goal(V(), [1], []),                 # Goal.name
        lambda V: Goal("f", V(), []),                 # Goal.args container
        lambda V: Goal("f", [], V()),                 # Goal.kwargs container
        lambda V: Goal("f", [], [V()]),               # kwarg entry
    ])
    def test_unbound_var_in_field_position_raises_render_error(self, term_factory):
        from clausal.logic.variables import Var

        with pytest.raises(RenderError):
            render_source(term_factory(Var))

    def test_duplicate_dict_keys_after_deref_raise(self):
        # two distinct key vars, both bound to 5 -> collide after deref; a silent
        # drop would break round-trip fidelity, so refuse.
        term = {_bound(5): "a", _bound(5): "b"}
        with pytest.raises(RenderError):
            render_source(term)


class TestPromotedStrSeqFields:
    """Sequence fields carrying a promoted ``str`` instead of a char list.

    Under the strings-as-lists rule (F018), engine reconstruction sites
    promote a list of provably 1-char strs to the equivalent ``str``
    (``maybe_promote_to_str``) — so a reified term that rode through a rule
    answer can come back with ``Goal.args == "t"`` where ``["t"]`` was built
    (the head-fold on ``TAG is "t"`` in ``catch_trampolined.clausal`` did
    exactly this).  The promoted str IS that char list, so a seq field must
    read it as one rather than refuse it as "not a sequence"."""

    def test_goal_args_promoted_single_char_str_renders_as_its_char_list(self):
        assert render_source(Goal("f", "t", [])) == render_source(Goal("f", ["t"], []))

    def test_goal_args_promoted_multi_char_str_renders_as_its_char_list(self):
        assert render_source(Goal("f", "ab", [])) == render_source(
            Goal("f", ["a", "b"], [])
        )

    def test_clause_goals_promoted_str_renders_as_its_char_list(self):
        promoted = Clause(Goal("H", [], []), "t", None)
        listed = Clause(Goal("H", [], []), ["t"], None)
        assert render_source(promoted) == render_source(listed)


# ── Comprehensions ───────────────────────────────────────────────────────────
# A comprehension in a clause body is an inert *term* structure, like
# await/yield: nothing iterates it, so the loop variable is a bare name that has
# to resolve like any other.  An undeclared one is a strict-atoms NameError and a
# logic variable is a plain NameError — which is why these were once written off
# as "does not compile", and as node kinds no legal source produces.  Declare the
# name and the comprehension compiles, runs, and its clause reifies with a
# ListComp in it, so it does reach the renderer.


class TestComprehensions:

    DECLARED_LOOP_VAR = "-private([x])\n\nsq(L, M) <- (M is [x * x for x in L])\n"

    def test_a_declared_loop_var_compiles_runs_and_reifies_a_ListComp(self, tmp_path):
        """The reachability the exclusion list used to deny.

        `x` is a declared atom, so nothing is undefined: the module imports, the
        predicate yields a solution, and M is bound to the ListComp term itself
        (a comprehension is not evaluated in a clause body — it is structure)."""
        from clausal.import_hook import _load_module
        from clausal.logic.variables import Var, deref
        from clausal.pythonic_ast import nodes as simple_ast

        path = tmp_path / "comp.clausal"
        path.write_text(self.DECLARED_LOOP_VAR)
        module = _load_module("_test_render_comprehension", str(path))

        result = Var()
        bindings = []
        for _ in solve(module.sq([1, 2, 3], result), module):
            bindings.append(deref(result))

        assert len(bindings) == 1, "the clause must yield exactly one solution"
        assert isinstance(bindings[0], simple_ast.ListComp)

        clause = only_clause(self.DECLARED_LOOP_VAR)
        assert isinstance(vfield(clause, "goals")[0].right, simple_ast.ListComp)

    def test_the_reachable_clause_round_trips(self):
        """It raised `RenderError: cannot render operator node: ListComp`."""
        assert_round_trips("sq(L, M) <- (M is [x * x for x in L]),\n")

    @pytest.mark.parametrize("src", [
        "L1(L, M) <- (M is [x * x for x in L]),\n",
        "S1(L, M) <- (M is {x for x in L}),\n",
        "D1(L, M) <- (M is {x: x for x in L}),\n",
        "G1(L, M) <- (M is (x for x in L)),\n",
        "F1(L, M) <- (M is [x for x in L if x]),\n",
        "F2(L, M) <- (M is [x for x in L if x if y]),\n",
        "N1(L, K, M) <- (M is [x for x in L for y in K]),\n",
        "N2(L, M) <- (M is [[x for x in y] for y in L]),\n",
        "V1(L, M) <- (M is [x for X in L]),\n",       # logic-variable target
        "V2(L, M) <- (M is [x for _ in L]),\n",       # anonymous target
        "V3(L, M) <- (M is [x for [a, b] in L]),\n",  # list target
        "V4(L, M) <- (M is [x for a.b in L]),\n",     # dotted-atom target
        "A1(L, M) <- (M is [x async for x in L]),\n",
        "K1(L, M, Z) <- (M is [Z * x for x in L]),\n",
    ])
    def test_every_comprehension_surface_round_trips(self, src):
        assert_round_trips(src)

    def test_a_comprehension_with_no_for_clause_is_refused(self):
        """`[E]` with no clauses is the list-literal surface, not a ListComp."""
        from clausal.pythonic_ast import nodes as simple_ast

        with pytest.raises(RenderError, match="no for-clause"):
            render_source(simple_ast.ListComp(element=1, clauses=[]))

    def test_a_tuple_target_is_refused_rather_than_written_bare(self):
        """`for x, y in L` is refused by the reifier, so no reified term carries
        a tuple target — only a mutated one can, and `ast.unparse` would write it
        bare, which does not read back."""
        from clausal.pythonic_ast import nodes as simple_ast
        from clausal.reflection import Variable, is_v, vfield

        node = simple_ast.ListComp(
            element=Atom("x"),
            clauses=[simple_ast.ForClause(
                target=(Atom("x"), Atom("y")), iterable=Variable("L"))],
        )
        with pytest.raises(RenderError, match="tuple comprehension target"):
            render_source(node)

    def test_a_non_ForClause_clause_is_refused(self):
        from clausal.pythonic_ast import nodes as simple_ast

        node = simple_ast.ListComp(element=1, clauses=[Atom("x")])
        with pytest.raises(RenderError, match="not a ForClause"):
            render_source(node)


# ── Mechanical completeness sweep ────────────────────────────────────────────
# The set of simple_ast node classes a reified clause body can contain is closed:
# EmbedTransformer builds bodies by calling node_ast("<ClassName>", …), either
# with a literal name or with a name looked up in one of its BINOP_CLS /
# UNARYOP_CLS / BOOLOP_CLS / CMPOP_CLS tables.  Enumerate that set from the
# source and require every member to be either renderable or *explicitly*
# excluded with a reason — so a newly emittable node kind cannot be added
# without a rendering decision being recorded here.

#: Emittable node kinds the renderer deliberately does not have an
#: ``_operator_ast`` branch for, each with the reason.
RENDER_EXCLUSIONS = {
    # Consumed by the reifier itself: these never survive into a reified term,
    # they are translated to reified vocabulary (Goal / Atom / tuple / …).
    "Predicate": "reified as Clause",
    "Call": "reified as Goal",
    "Keyword": "reified into Goal.kwargs",
    "LoadName": "reified as Atom",
    "LoadAttr": "reified as a dotted Atom",
    "IfExpr": "reified as IfThenElse",
    "TupleLiteral": "reified as a Python tuple",
    # Not a term on its own: a ForClause is rendered by the comprehension that
    # owns it, so reaching _operator_ast with a bare one means the term was
    # mutated — refused loudly, by design.  The four comprehension kinds were
    # once excluded here too, on the claim that they "do not compile (NameError
    # on the loop var)" and that no legal source produces them.  Both were
    # false: the NameError is what an *undeclared* loop variable gets, and
    # declaring it (`-private([x])`) makes the comprehension compile, run and
    # reach the renderer.  They are rendered now — see TestComprehensions.
    "ForClause": "rendered by its owning comprehension, never a term on its own",
}


def _emittable_node_class_names():
    """Node class names EmbedTransformer can emit into a clause body."""
    import ast as _ast

    from clausal.templating import term_rewriting

    source = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(term_rewriting.__file__))),
        "templating", "term_rewriting.py",
    )
    names = set()
    for node in _ast.walk(_ast.parse(open(source, encoding="utf-8").read())):
        if (
            isinstance(node, _ast.Call)
            and isinstance(node.func, _ast.Name)
            and node.func.id == "node_ast"
            and node.args
            and isinstance(node.args[0], _ast.Constant)
        ):
            names.add(node.args[0].value)
    for table_name in ("BINOP_CLS", "UNARYOP_CLS", "BOOLOP_CLS", "CMPOP_CLS"):
        names.update(getattr(term_rewriting, table_name).values())
    return names


def test_emittable_node_kinds_are_all_decided():
    """No emittable node kind may be silently unrenderable."""
    from clausal.reflection import RENDER_NODE_CLASS_NAMES, is_v, vfield

    emittable = _emittable_node_class_names()
    assert emittable, "node_ast sweep found nothing — the extraction broke"
    undecided = sorted(emittable - RENDER_NODE_CLASS_NAMES - set(RENDER_EXCLUSIONS))
    assert not undecided, (
        "clause bodies can contain node kinds the renderer neither handles nor "
        f"documents an exclusion for: {undecided}"
    )


def test_render_exclusions_are_not_stale():
    """Every documented exclusion must still be emittable and still unhandled —
    otherwise the list is lying about the renderer's coverage."""
    from clausal.reflection import RENDER_NODE_CLASS_NAMES, is_v, vfield

    emittable = _emittable_node_class_names()
    assert not (set(RENDER_EXCLUSIONS) - emittable), (
        "excluded node kinds are no longer emittable: "
        f"{sorted(set(RENDER_EXCLUSIONS) - emittable)}"
    )
    assert not (set(RENDER_EXCLUSIONS) & RENDER_NODE_CLASS_NAMES), (
        "node kinds listed as excluded are in fact handled: "
        f"{sorted(set(RENDER_EXCLUSIONS) & RENDER_NODE_CLASS_NAMES)}"
    )


CORPUS_DIR = os.environ.get("CLAUSAL_CORPUS_DIR", "")


def _corpus_files():
    if not CORPUS_DIR or not os.path.isdir(CORPUS_DIR):
        return []
    return sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.clausal"), recursive=True))


@pytest.mark.skipif(not _corpus_files(), reason="CLAUSAL_CORPUS_DIR not set or absent")
@pytest.mark.parametrize("path", _corpus_files())
def test_corpus_clause_round_trips(path):
    """Every Clause in every file of an external corpus, if one is configured
    (via ``CLAUSAL_CORPUS_DIR``), renders and re-reifies identically.

    Only Clause items are exercised: every file opens with -module/-import_from
    which reify to ModuleDirective/PythonCode — node kinds the renderer
    deliberately raises on. A RenderError on a real clause is a hard failure
    (a silently-corrupt mutant would falsely 'survive' in a source-rewriting
    tool)."""
    try:
        items = reify_source(open(path, encoding="utf-8").read(), filename=path)
    except ReifyError as exc:
        pytest.skip(f"source not reifiable ({exc})")
    clauses = [i for i in items if is_v(i, Clause)]
    if not clauses:
        pytest.skip("no clauses in file")
    for clause in clauses:
        rendered = render_source(clause)              # must not raise RenderError
        reparsed = [i for i in reify_source(rendered + "\n") if is_v(i, Clause)]
        assert len(reparsed) == 1, f"{path}: render produced {len(reparsed)} clauses:\n{rendered}"
        assert strip_positions(reparsed[0]) == strip_positions(clause), (
            f"{path}: round-trip mismatch\n  rendered: {rendered!r}"
        )


# ── Corruption / contract guards (Fable review findings) ─────────────────────
# The renderer must NEVER emit text that re-reifies to a different structure, and
# must raise RenderError (not a raw SyntaxError / silent corruption) for anything
# it cannot faithfully render. These cover surface shapes and mutated terms that
# the corpus sweep does not reach.


class TestCorruptionGuards:
    def test_lambda_in_clause_head_round_trips(self):
        # C1: a lambda arrow-as-term in HEAD position must not leak the sentinel.
        assert_round_trips("holds((X <- p(X))) <- check(1)\n")

    def test_nested_unary_plus_not_confused_with_escape(self):
        # C2: `+(+X)` must not silently collapse to the `++X` escape surface.
        # It either round-trips faithfully or raises RenderError — never corrupts.
        clause = only_clause("calc(X, Y) <- (Y is +(+X))\n")
        try:
            rendered = render_source(clause)
        except RenderError:
            return  # contract-honouring: refused rather than corrupt
        reparsed = only_clause(rendered + "\n")
        assert strip_positions(reparsed) == strip_positions(clause), (
            f"+(+X) silently corrupted to: {rendered!r}"
        )

    def test_render_source_of_standalone_lambda_term(self):
        # I1: rendering a lambda sub-term directly (the auditor's use case) must
        # not leak the sentinel marker.
        clause = only_clause("ho(F) <- run((X <- base(X)), F)\n")
        lambda_term = vfield(clause, "goals")[0].args[0]
        rendered = render_source(lambda_term)
        assert "__clausal_lambda_arrow__" not in rendered, (
            f"sentinel leaked in standalone lambda render: {rendered!r}"
        )
        # And it must re-parse to the same lambda structure.
        reparsed = only_clause(f"wrap(G) <- run({rendered}, G)\n")
        assert strip_positions(reparsed.goals[0].args[0]) == strip_positions(lambda_term)

    def test_escape_with_invalid_code_raises_render_error(self):
        # I3: a mutated Escape whose code is not valid Python must raise
        # RenderError, not a raw SyntaxError.
        with pytest.raises(RenderError):
            render_source(Escape("X +", [], None))

    def test_format_string_with_invalid_code_raises_render_error(self):
        # I3: same contract for FormatString.
        with pytest.raises(RenderError):
            render_source(FormatString("f'{", [], None))

    def test_non_identifier_atom_renders_single_quoted(self):
        """THE FLIP (spec §6.7) INVERTS the I2/M1 refusal for an ATOM: an
        atom whose spelling is not an identifier renders ``'…'`` -- a
        single-quoted literal is an atom in EVERY ``-double_quotes`` mode, so
        the output re-reads as the atom it rendered.  A non-identifier GOAL
        (predicate) name still refuses: there is no quoted call syntax.
        """
        assert render_source(Atom("has space")) == "'has space'"
        assert (render_source(Goal("weird", [Atom("has space")], []))
                == "weird('has space')")
        # ...and it round-trips as an atom, not as a string.
        clause = only_clause("W('has space'),\n")
        assert render_source(clause) == "W('has space'),"
        assert strip_positions(only_clause(render_source(clause) + "\n")) \
            == strip_positions(clause)
        # The reserved lambda sentinel is still refused -- it is not a term.
        with pytest.raises(RenderError):
            render_source(Atom("__clausal_lambda_arrow__"))
        # A non-identifier PREDICATE name has no renderable surface.
        with pytest.raises(RenderError):
            render_source(Goal("has space", [], []))

    def test_string_renders_double_quoted(self):
        """A STRING must come back DOUBLE-quoted (spec §6.7/§7) -- single
        quotes would re-read as an atom in every mode -- and a ``bytes``
        literal keeps its own quoting untouched.
        """
        assert render_source(Goal("W", ["has space"], [])) == 'W("has space")'
        assert render_source(Goal("W", [b"ab"], [])) == "W(b'ab')"


class TestRawCellRendering:
    """P3-2 Task 7: a raw runtime CELL (the tagged-tuple compound
    representation, ``clausal/logic/cells.py``) reaching the renderer --
    e.g. via ``op_node/3``'s construct mode or ``replace_subterm/4``'s
    rebuilt RESULT, both of which can hold/rebuild a raw tuple that was
    never through ``reify_source`` -- must render as the term it is, not a
    Python tuple literal (which is what the generic ``isinstance(value,
    tuple)`` case rendered it as before this branch existed, and what a
    ``TUPLE_TAG`` cell raised ``RenderError`` trying to render, since the
    ``TUPLE_TAG`` marker itself -- the ``tuple`` type object -- has no
    ``term()`` case of its own)."""

    def test_str_functor_cell_renders_as_a_call(self):
        assert render_source(("point", 1, 2)) == "point(1, 2)"

    def test_nested_cell_renders(self):
        assert render_source(("pt", 1, ("q", 2))) == "pt(1, q(2))"

    def test_zero_arg_str_functor_cell_renders_bare(self):
        # Spec §6.7: an arity-0 cell is an ATOM, not a zero-argument call,
        # so it renders as the bare name (it used to render ``atom_like()``,
        # which this test pinned before atoms became cells).
        assert render_source(("atom_like",)) == "atom_like"

    def test_tuple_data_cell_renders_as_a_plain_tuple(self):
        from clausal.logic.cells import TUPLE_TAG

        assert render_source((TUPLE_TAG, 1, 2)) == "(1, 2)"

    def test_hidden_atom_functor_renders_the_human_form(self):
        """P3-1 Task 6 (-hide, §1b): reused WITHOUT quoting for a functor
        position, matching the ``Atom`` case's NAME substitution."""
        from clausal.logic.atoms import mangle

        mangled = mangle("mymod", "secret")
        assert render_source((mangled, 1)) == "mymod.secret(1)"

    def test_rendered_cell_round_trips_through_reify_ast(self):
        """render -> reify: the rendered ``ast.Call`` node reifies back to
        the equivalent ``Goal`` a matcher would build from ``point(1, 2)``
        written as source -- the practical round-trip, since a raw runtime
        cell and the static-reification vocabulary (``Goal``) are different
        representations of the same call by design (see the module
        docstring: "Goal ... a predicate call *and* any compound term")."""
        from clausal.reflection import reify_ast, is_v, vfield

        node = render_ast(("point", 1, 2))
        assert reify_ast(node) == Goal("point", [1, 2], [])
