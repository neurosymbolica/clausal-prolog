"""Round-trip tests for clausal.reflection render_ast/render_source — the
inverse of reify_ast. Invariant: reify(render_source(clause)) is structurally
identical to clause (positions ignored)."""

import dataclasses
import glob
import os

import pytest

from clausal.reflection import (
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
    clauses = [i for i in reify_source(src) if isinstance(i, Clause)]
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
        "Edge(1, 2),\n",
        "Item('widget', 2.5),\n",
        "Status(ok, 1),\n",
        "Temp(-40),\n",
        "Rule(X, Y),\n",
    ])
    def test_fact_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src,expected", [
        ("Edge(1, 2),\n", "Edge(1, 2),"),
        ("Status(ok, 1),\n", "Status(ok, 1),"),
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
        "Connected(X, Y) <- Edge(X, Y)\n",
        "Grandparent(X, Z) <- (Parent(X, Y), Parent(Y, Z))\n",
        "Reachable(X) <- Edge(_, _)\n",
        "Three(A) <- (Pa(A), Qa(A), Ra(A))\n",
    ])
    def test_rule_round_trips(self, src):
        assert_round_trips(src)


class TestOperators:
    @pytest.mark.parametrize("src", [
        "Positive(N) <- (N > 0)\n",
        "AtLeast(N) <- (N >= 10)\n",
        "Eq(N) <- (N == 0)\n",
        "Neq(N) <- (N != 0)\n",
        "Sum(X, Y, Z) <- (Z is X + Y)\n",
        "Prod(X, Y, Z) <- (Z is X * Y)\n",
        "Diff(X, Y, Z) <- (Z is X - Y)\n",
        "Unify2(X, Y) <- (X is Y)\n",
        "Dif2(X, Y) <- (X is not Y)\n",
        "Free(A) <- (not Busy(A))\n",
        "Either(A) <- (Pa(A) or Qa(A))\n",
        "Both(A) <- (Pa(A) and Qa(A))\n",
        "Neg(X, Y) <- (Y is -X)\n",
        "ConsTail(T) <- Head([a, b | T])\n",
        "StarTail(T) <- Head([a, b, *T])\n",
    ])
    def test_operator_round_trips(self, src):
        assert_round_trips(src)


class TestCompoundAndKwargs:
    @pytest.mark.parametrize("src", [
        "Holds(State(A)) <- Check(A)\n",
        "Deep(Pp(Qq(Rr(X)))) <- Base(X)\n",
        "WithList(Pp([1, 2, 3])),\n",
        "Nested([Pp(X), Qq(Y)]),\n",
    ])
    def test_compound_round_trips(self, src):
        assert_round_trips(src)


class TestIfThenElse:
    @pytest.mark.parametrize("src", [
        "Pick(X, Y) <- (Y is If(X > 0, 1, 2))\n",
    ])
    def test_ite_round_trips(self, src):
        assert_round_trips(src)


class TestEscapes:
    @pytest.mark.parametrize("src", [
        "Calc(X, Y) <- (Y is ++(X + 1))\n",
        "Calc2(X, Y, Z) <- (Z is ++(X * Y + 1))\n",
    ])
    def test_escape_round_trips(self, src):
        assert_round_trips(src)


class TestSubscript:
    @pytest.mark.parametrize("src", [
        "Get(P, I) <- (I is P[flags])\n",
        "GetDotted(P, I) <- (I is P[a.b.c])\n",
    ])
    def test_subscript_round_trips(self, src):
        assert_round_trips(src)


class TestDictLiteral:
    @pytest.mark.parametrize("src", [
        "Merge(A, B) <- (A is {**B, foo: B})\n",
        "Merge2(A, B, C) <- (A is {**B, foo: C, bar: B})\n",
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

    def test_atom_key_dict_shares_splat_representation(self):
        # An atom key must reify to the SAME shape whether or not the literal
        # also splats — one DictLiteral representation for the auditor.
        splat = only_clause("A(B) <- (X is {**B, foo: B})\n").goals[0]
        plain = only_clause("A(B) <- (X is {foo: B})\n").goals[0]
        splat_key = strip_positions(splat).right.keys[-1]
        plain_key = strip_positions(plain).right.keys[-1]
        assert splat_key == plain_key, (
            f"atom key differs by splat: {plain_key!r} vs {splat_key!r}"
        )


class TestArrowLambda:
    @pytest.mark.parametrize("src", [
        "Run0(C) <- run(( () <- base()), C)\n",
        "Run1(C) <- run((X <- base(X)), C)\n",
        "RunN(C) <- run(((ID, PR) <- req(ID, PR)), C)\n",
        "RunBody(C) <- run((X <- (Y is X + 1)), C)\n",
        "RunTwo(C) <- run((X <- p(X)), (Y <- q(Y)), C)\n",
    ])
    def test_arrow_lambda_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src", [
        # A genuine `X < -N` comparison must NOT be tightened into a lambda arrow.
        "Cmp(X) <- (X < -1)\n",
        "CmpVar(X, Y) <- (X < -Y)\n",
    ])
    def test_spaced_comparison_not_arrow(self, src):
        assert_round_trips(src)


class TestFormatString:
    @pytest.mark.parametrize("src", [
        'Greet(Name, M) <- (M is f"hi {Name}")\n',
        'Msg(X, S) <- (S is f"val={X}")\n',
    ])
    def test_format_string_round_trips(self, src):
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
        back = reify_source("H <- (5 > 1)\n")[0].goals[0]
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
        from clausal.reflection import Variable

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
        from clausal.reflection import reify_ast

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


CORPUS_DIR = "/workspace/clausify-domains"


def _corpus_files():
    if not os.path.isdir(CORPUS_DIR):
        return []
    return sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.clausal"), recursive=True))


@pytest.mark.skipif(not _corpus_files(), reason=f"corpus {CORPUS_DIR} absent")
@pytest.mark.parametrize("path", _corpus_files())
def test_corpus_clause_round_trips(path):
    """Every Clause in every corpus file renders and re-reifies identically.

    Only Clause items are exercised: every file opens with -module/-import_from
    which reify to ModuleDirective/PythonCode — node kinds the renderer
    deliberately raises on. A RenderError on a real clause is a hard failure
    (a silently-corrupt mutant would falsely 'survive' in the auditor)."""
    try:
        items = reify_source(open(path, encoding="utf-8").read(), filename=path)
    except ReifyError as exc:
        pytest.skip(f"source not reifiable ({exc})")
    clauses = [i for i in items if isinstance(i, Clause)]
    if not clauses:
        pytest.skip("no clauses in file")
    for clause in clauses:
        rendered = render_source(clause)              # must not raise RenderError
        reparsed = [i for i in reify_source(rendered + "\n") if isinstance(i, Clause)]
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
        assert_round_trips("Holds((X <- p(X))) <- Check(1)\n")

    def test_nested_unary_plus_not_confused_with_escape(self):
        # C2: `+(+X)` must not silently collapse to the `++X` escape surface.
        # It either round-trips faithfully or raises RenderError — never corrupts.
        clause = only_clause("Calc(X, Y) <- (Y is +(+X))\n")
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
        clause = only_clause("Ho(F) <- run((X <- base(X)), F)\n")
        lambda_term = clause.goals[0].args[0]
        rendered = render_source(lambda_term)
        assert "__clausal_lambda_arrow__" not in rendered, (
            f"sentinel leaked in standalone lambda render: {rendered!r}"
        )
        # And it must re-parse to the same lambda structure.
        reparsed = only_clause(f"Wrap(G) <- run({rendered}, G)\n")
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

    def test_non_identifier_atom_raises_render_error(self):
        # I2/M1: a mutated Atom/Goal name that is not a valid identifier (or is
        # the reserved sentinel) must raise RenderError, not emit malformed text.
        with pytest.raises(RenderError):
            render_source(Goal("Weird", [Atom("has space")], []))
        with pytest.raises(RenderError):
            render_source(Atom("__clausal_lambda_arrow__"))
