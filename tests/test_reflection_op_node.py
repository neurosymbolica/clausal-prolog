"""Tests for ``op_node/3`` — decompose/construct ``simple_ast`` operator nodes
from Clausal.

Companion to :mod:`test_reflection_builtins`.  ``op_node`` is the
``functor``/``unpack`` analogue for the operator-node kind: it lets a
pure-Clausal matcher name a reified comparison/arithmetic node by its
``simple_ast`` class and rebuild one from a class name plus operands, so the
Clausal-AST auditor's operator-swap mutations can be written in Clausal rather
than Python.  See ``todo/done/op-node-reflection-decompose-construct.md``.
"""

import pytest

from clausal import cell_args, cell_functor
from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal import reflection as R
from clausal.pythonic_ast import nodes as simple_ast


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


# DEFAULT-mode source (no ``-double_quotes(chars)``): every ``"…"`` below is a
# class NAME, so it must be an ATOM — that is the position ``op_node/3`` reads
# and answers (§6.4), and it is how ``docs/reflection.md`` writes the calls.
_MATCHERS = """\
-double_quotes(atom)
-import_from(reflection, [
    reified_clause, reified_subterm, op_node,
])

# decompose: name every operator node reachable in a source
op_name(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, NAME, _)
)

# decompose: capture operands too
op_parts(SRC, NAME, ARGS) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, NAME, ARGS)
)

# match-by-class (NAME bound): succeeds only where a GtE node is present
has_gt_e(SRC) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", _)
)

# a whole Clause is bound but is not an operator node -> op_node fails
clause_is_op(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    op_node(CLAUSE, NAME, _)
)

# construct: build a Gt node from a class name + operands
build_gt(NEW, L, R) <- op_node(NEW, "Gt", [L, R])

# operator-swap: decompose a GtE node and rebuild it as a Gt over the same
# operands — the pure-Clausal match->rewrite this builtin exists for
swap_gt_eto_gt(SRC, NEW) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", ARGS),
    op_node(NEW, "Gt", ARGS)
)

# construct: an unknown class name fails cleanly
build_bogus(NEW) <- op_node(NEW, "Bogus", [1, 2])

# decompose with an explicit [L, R] list pattern (binds both operands)
gt_e_parts(SRC, L, R) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", [L, R])
)

# generic construct: caller supplies class name + operand list
build_node(NEW, NAME, ARGS) <- op_node(NEW, NAME, ARGS)

# construct with an operand bound *before* op_node runs -> shallow-deref stores
# the value, so the built node renders
build_bound(NEW, V) <- (V is 5, op_node(NEW, "Negate", [V]))

# construct with an operand bound *after* op_node runs -> the renderer follows
# the binding (renderer-deref fix), so this also renders
build_late(NEW) <- (op_node(NEW, "Gt", [X, 1]), X is 5)
"""


@pytest.fixture(scope="module")
def matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("op_node") / "matchers.clausal"
    path.write_text(_MATCHERS)
    mod = _load_module("_test_op_node_matchers", str(path))
    return mod.__dict__["$module"]


def _solutions(functor, *args, module):
    """Run ``functor`` and return the list of deref'd tuples of the Var args."""
    var_positions = [i for i, a in enumerate(args) if isinstance(a, Var)]
    out = []
    for _ in call(functor, *args, module=module):
        out.append(tuple(deref(args[i]) for i in var_positions))
    return out


class TestDecompose:
    def test_names_a_relational_node(self, matchers):
        name = Var()
        sols = _solutions("op_name", chars("small(X) <- (X >= 1)\n"), name, module=matchers)
        assert [n for (n,) in sols] == [mint("GtE")]

    def test_names_arithmetic_and_relational_nodes(self, matchers):
        name = Var()
        sols = _solutions("op_name", chars("big(X) <- (X + 1 >= 10)\n"), name, module=matchers)
        assert {n for (n,) in sols} == {mint("GtE"), mint("Add")}

    def test_captures_operands_in_field_order(self, matchers):
        name, args = Var(), Var()
        sols = _solutions("op_parts", chars("small(X) <- (X >= 1)\n"), name, args, module=matchers)
        assert len(sols) == 1
        nm, operands = sols[0]
        assert nm == mint("GtE")
        assert isinstance(operands, list) and len(operands) == 2
        # field order is [left, right]; right is the integer literal 1
        assert deref(operands[1]) == 1

    def test_match_by_class_name_succeeds(self, matchers):
        sols = _solutions("has_gt_e", chars("small(X) <- (X >= 1)\n"), module=matchers)
        assert len(sols) == 1

    def test_match_by_class_name_rejects_other_operator(self, matchers):
        # a Lt-only body has no GtE node
        sols = _solutions("has_gt_e", chars("tiny(X) <- (X < 1)\n"), module=matchers)
        assert sols == []

    def test_non_operator_node_fails_cleanly(self, matchers):
        name = Var()
        sols = _solutions("clause_is_op", chars("small(X) <- (X >= 1)\n"), name, module=matchers)
        assert sols == []

    def test_list_pattern_binds_both_operands(self, matchers):
        left, right = Var(), Var()
        sols = _solutions("gt_e_parts", chars("small(X) <- (X >= 1)\n"), left, right, module=matchers)
        assert len(sols) == 1
        l, r = sols[0]
        assert deref(r) == 1  # right operand is the integer literal 1

    def test_unary_and_comparison_named_together(self, matchers):
        # `X is -Y` reifies as Unify(left=X, right=Negate(operand=Y))
        name = Var()
        sols = _solutions("op_name", chars("neg(X, Y) <- (X is -Y)\n"), name, module=matchers)
        assert [n for (n,) in sols] == [mint("Unify"), mint("Negate")]

    def test_compare_chain_excluded_but_its_inner_nodes_named(self, matchers):
        # `1 < X < 10` reifies as a CompareChain, which the renderer handles but
        # `op_node/3` excludes — its operands are a list of links, not a
        # left/right pair, so it has no decompose/construct shape here. Its
        # inner Lt nodes ARE operator nodes.
        name = Var()
        sols = _solutions("op_name", chars("mid(X) <- (1 < X < 10)\n"), name, module=matchers)
        names = [n for (n,) in sols]
        assert mint("CompareChain") not in names
        assert names == [mint("Lt"), mint("Lt")]

    def test_foreign_object_sharing_a_name_fails_cleanly(self):
        """A non-``simple_ast`` object whose class merely shares an operator's
        name must fail cleanly, not crash or false-match (regression: decompose
        once matched by name only)."""
        import ast
        import dataclasses

        from clausal.modules import reflection as refl

        # CPython ast.Gt is named "Gt" but is not a dataclass -> used to crash
        assert list(call(refl.op_node, ast.Gt(), Var(), Var())) == []

        @dataclasses.dataclass
        class Add:  # foreign dataclass named like an operator -> used to match
            left: int = 0
            right: int = 0

        assert list(call(refl.op_node, Add(7, 8), Var(), Var())) == []


class TestConstruct:
    def test_builds_a_gt_node(self, matchers):
        new = Var()
        nodes = []
        for _ in call("build_gt", new, 3, 4, module=matchers):
            nodes.append(deref(new))  # capture before backtracking undoes it
        assert len(nodes) == 1
        node = nodes[0]
        assert isinstance(node, simple_ast.Gt)
        assert node.left == 3 and node.right == 4

    def test_unknown_class_name_fails_cleanly(self, matchers):
        new = Var()
        sols = list(call("build_bogus", new, module=matchers))
        assert sols == []

    def test_wrong_arity_operand_list_fails_cleanly(self, matchers):
        new = Var()
        # Gt is binary; a one-element operand list cannot build it
        assert list(call("build_node", new, mint("Gt"), [1], module=matchers)) == []

    def test_non_list_operands_fail_cleanly(self, matchers):
        new = Var()
        assert list(call("build_node", new, mint("Gt"), 5, module=matchers)) == []

    def test_builds_a_unary_node(self, matchers):
        new = Var()
        rendered = []
        for _ in call("build_node", new, mint("Negate"), [5], module=matchers):
            node = deref(new)
            assert isinstance(node, simple_ast.Negate)
            assert node.operand == 5
            rendered.append(R.render_source(node))
        assert rendered == ["-5"]

    def test_operand_bound_before_construct_renders(self, matchers):
        # V is bound to 5 before op_node builds Negate([V]); shallow-deref stores
        # the value so render_source succeeds (deferred binding is the excluded
        # case, tracked separately).
        new, v = Var(), Var()
        rendered = []
        for _ in call("build_bound", new, v, module=matchers):
            rendered.append(R.render_source(deref(new)))
        assert rendered == ["-5"]

    def test_operand_bound_after_construct_renders(self, matchers):
        # X is unbound when op_node builds Gt([X, 1]), then bound to 5; the
        # renderer dereferences it (see the renderer-deref follow-up).
        new = Var()
        rendered = []
        for _ in call("build_late", new, module=matchers):
            rendered.append(R.render_source(deref(new)))
        assert rendered == ["5 > 1"]

    def test_boolean_operator_round_trips_python_side(self):
        """``And`` (BoolOp kin) is in the registry; not easily produced from
        surface syntax, so exercise construct+decompose directly."""
        from clausal.modules import reflection as refl

        built = []
        new = Var()
        for _ in call(refl.op_node, new, mint("And"), [1, 2]):
            built.append(deref(new))
        assert len(built) == 1 and isinstance(built[0], simple_ast.And)
        # decompose it back
        name, args = Var(), Var()
        got = []
        for _ in call(refl.op_node, built[0], name, args):
            got.append((deref(name), [deref(a) for a in deref(args)]))
        assert got == [(mint("And"), [1, 2])]

    def test_constructed_node_round_trips_through_renderer(self, matchers):
        import ast as _ast

        new = Var()
        sources = []
        for _ in call("build_gt", new, 1, 2, module=matchers):
            sources.append(R.render_source(deref(new)))  # render before backtracking
        assert sources == ["1 > 2"]
        # re-reifies to a Gt of the same operands
        back = R.reify_ast(_ast.parse(sources[0], mode="eval").body)
        assert isinstance(back, simple_ast.Gt)
        assert back.left == 1 and back.right == 2


class TestOperatorSwap:
    def test_gte_rewritten_to_gt_preserving_operands(self, matchers):
        """The headline use case: match a ``>=`` node and rebuild it as ``>``
        over the very same operands, entirely in Clausal."""
        new = Var()
        rendered = []
        for _ in call("swap_gt_eto_gt", chars("small(X) <- (X >= 1)\n"), new, module=matchers):
            node = deref(new)
            assert isinstance(node, simple_ast.Gt)
            rendered.append(R.render_source(node))
        assert rendered == ["X > 1"]


class TestPythonExports:
    def test_reflection_module_exports_op_node(self):
        from clausal.modules import reflection
        from clausal.modules.py import ModulePredicate

        assert isinstance(reflection.op_node, ModulePredicate)
        # registered at arity 3 under the reflection module
        assert repr(reflection.op_node) == "reflection.op_node/[3]"


# ── 2026-09-26: a STRING in the CLASS_NAME position is a type error, in BOTH
# modes.  Under the chars default a source-written ``op_node(SUB, "GtE", ARGS)``
# hands over the chars carrier; before this, decompose silently failed to
# unify it with the atom and construct fell through ``_class_name_spelling``'s
# unreachable ``type(name) is str`` arm to a silent None.

_CHARS_MATCHERS = """\
-import_from(reflection, [reified_clause, reified_subterm, op_node])
has_gt_e_str(SRC) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", _)
)
has_gt_e_atom(SRC) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, 'GtE', _)
)
build_gt_str(NEW, L, R) <- op_node(NEW, "Gt", [L, R])
"""


@pytest.fixture(scope="module")
def chars_matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("op_node_chars") / "matchers.clausal"
    path.write_text(_CHARS_MATCHERS)
    mod = _load_module("_test_op_node_chars_matchers", str(path))
    return mod.__dict__["$module"]


class TestStringClassNameIsATypeError:
    SRC = "p(X) <- (X >= 1)\n"

    def test_the_quoted_atom_still_matches(self, chars_matchers):
        assert list(call("has_gt_e_atom", chars(self.SRC), module=chars_matchers))

    def test_decompose_with_a_string_name_raises(self, chars_matchers):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            list(call("has_gt_e_str", chars(self.SRC), module=chars_matchers))
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom") and cell_args(formal)[1] == chars("GtE")

    def test_decompose_with_a_string_name_raises_even_with_no_operator_subterm(
            self, chars_matchers):
        """The name is checked before the node: a source with no operator
        node at all still surfaces the string mistake on its first subterm."""
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            list(call("has_gt_e_str", chars("p(X) <- q(X)\n"), module=chars_matchers))
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom") and cell_args(formal)[1] == chars("GtE")

    def test_construct_with_a_string_name_raises(self, chars_matchers):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            list(call("build_gt_str", Var(), 1, 2, module=chars_matchers))
        assert cell_args(cell_args(exc.value.term)[0])[1] == chars("Gt")
