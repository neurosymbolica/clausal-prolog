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

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal import reflection as R
from clausal.pythonic_ast import nodes as simple_ast


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


_MATCHERS = """\
-import_from(reflection, [
    reified_clause, reified_subterm, op_node,
])

# decompose: name every operator node reachable in a source
OpName(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, NAME, _)
)

# decompose: capture operands too
OpParts(SRC, NAME, ARGS) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, NAME, ARGS)
)

# match-by-class (NAME bound): succeeds only where a GtE node is present
HasGtE(SRC) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", _)
)

# a whole Clause is bound but is not an operator node -> op_node fails
ClauseIsOp(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    op_node(CLAUSE, NAME, _)
)

# construct: build a Gt node from a class name + operands
BuildGt(NEW, L, R) <- op_node(NEW, "Gt", [L, R])

# operator-swap: decompose a GtE node and rebuild it as a Gt over the same
# operands — the pure-Clausal match->rewrite this builtin exists for
SwapGtEtoGt(SRC, NEW) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", ARGS),
    op_node(NEW, "Gt", ARGS)
)

# construct: an unknown class name fails cleanly
BuildBogus(NEW) <- op_node(NEW, "Bogus", [1, 2])

# decompose with an explicit [L, R] list pattern (binds both operands)
GtEParts(SRC, L, R) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", [L, R])
)

# generic construct: caller supplies class name + operand list
BuildNode(NEW, NAME, ARGS) <- op_node(NEW, NAME, ARGS)

# construct with an operand bound *before* op_node runs -> shallow-deref stores
# the value, so the built node renders
BuildBound(NEW, V) <- (V is 5, op_node(NEW, "Negate", [V]))
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
        sols = _solutions("OpName", "Small(X) <- (X >= 1)\n", name, module=matchers)
        assert [n for (n,) in sols] == ["GtE"]

    def test_names_arithmetic_and_relational_nodes(self, matchers):
        name = Var()
        sols = _solutions("OpName", "Big(X) <- (X + 1 >= 10)\n", name, module=matchers)
        assert {n for (n,) in sols} == {"GtE", "Add"}

    def test_captures_operands_in_field_order(self, matchers):
        name, args = Var(), Var()
        sols = _solutions("OpParts", "Small(X) <- (X >= 1)\n", name, args, module=matchers)
        assert len(sols) == 1
        nm, operands = sols[0]
        assert nm == "GtE"
        assert isinstance(operands, list) and len(operands) == 2
        # field order is [left, right]; right is the integer literal 1
        assert deref(operands[1]) == 1

    def test_match_by_class_name_succeeds(self, matchers):
        sols = _solutions("HasGtE", "Small(X) <- (X >= 1)\n", module=matchers)
        assert len(sols) == 1

    def test_match_by_class_name_rejects_other_operator(self, matchers):
        # a Lt-only body has no GtE node
        sols = _solutions("HasGtE", "Tiny(X) <- (X < 1)\n", module=matchers)
        assert sols == []

    def test_non_operator_node_fails_cleanly(self, matchers):
        name = Var()
        sols = _solutions("ClauseIsOp", "Small(X) <- (X >= 1)\n", name, module=matchers)
        assert sols == []

    def test_list_pattern_binds_both_operands(self, matchers):
        left, right = Var(), Var()
        sols = _solutions("GtEParts", "Small(X) <- (X >= 1)\n", left, right, module=matchers)
        assert len(sols) == 1
        l, r = sols[0]
        assert deref(r) == 1  # right operand is the integer literal 1

    def test_unary_and_comparison_named_together(self, matchers):
        # `X is -Y` reifies as Unify(left=X, right=Negate(operand=Y))
        name = Var()
        sols = _solutions("OpName", "Neg(X, Y) <- (X is -Y)\n", name, module=matchers)
        assert [n for (n,) in sols] == ["Unify", "Negate"]

    def test_compare_chain_excluded_but_its_inner_nodes_named(self, matchers):
        # `1 < X < 10` reifies as a CompareChain (not renderable, excluded) whose
        # inner Lt nodes ARE operator nodes.
        name = Var()
        sols = _solutions("OpName", "Mid(X) <- (1 < X < 10)\n", name, module=matchers)
        names = [n for (n,) in sols]
        assert "CompareChain" not in names
        assert names == ["Lt", "Lt"]

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
        for _ in call("BuildGt", new, 3, 4, module=matchers):
            nodes.append(deref(new))  # capture before backtracking undoes it
        assert len(nodes) == 1
        node = nodes[0]
        assert isinstance(node, simple_ast.Gt)
        assert node.left == 3 and node.right == 4

    def test_unknown_class_name_fails_cleanly(self, matchers):
        new = Var()
        sols = list(call("BuildBogus", new, module=matchers))
        assert sols == []

    def test_wrong_arity_operand_list_fails_cleanly(self, matchers):
        new = Var()
        # Gt is binary; a one-element operand list cannot build it
        assert list(call("BuildNode", new, "Gt", [1], module=matchers)) == []

    def test_non_list_operands_fail_cleanly(self, matchers):
        new = Var()
        assert list(call("BuildNode", new, "Gt", 5, module=matchers)) == []

    def test_builds_a_unary_node(self, matchers):
        new = Var()
        rendered = []
        for _ in call("BuildNode", new, "Negate", [5], module=matchers):
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
        for _ in call("BuildBound", new, v, module=matchers):
            rendered.append(R.render_source(deref(new)))
        assert rendered == ["-5"]

    def test_boolean_operator_round_trips_python_side(self):
        """``And`` (BoolOp kin) is in the registry; not easily produced from
        surface syntax, so exercise construct+decompose directly."""
        from clausal.modules import reflection as refl

        built = []
        new = Var()
        for _ in call(refl.op_node, new, "And", [1, 2]):
            built.append(deref(new))
        assert len(built) == 1 and isinstance(built[0], simple_ast.And)
        # decompose it back
        name, args = Var(), Var()
        got = []
        for _ in call(refl.op_node, built[0], name, args):
            got.append((deref(name), [deref(a) for a in deref(args)]))
        assert got == [("And", [1, 2])]

    def test_constructed_node_round_trips_through_renderer(self, matchers):
        import ast as _ast

        new = Var()
        sources = []
        for _ in call("BuildGt", new, 1, 2, module=matchers):
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
        for _ in call("SwapGtEtoGt", "Small(X) <- (X >= 1)\n", new, module=matchers):
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
