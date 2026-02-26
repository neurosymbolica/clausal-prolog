"""
simple_ast — A simplified Python AST for manipulation.

Design principles:
  1. No context markers — node TYPE encodes usage (LoadName vs StoreName).
  2. No operator indirection — each operation is its own node type.
  3. No wrapper/carrier nodes — alias, withitem, etc. are inlined.
  4. Nodes split by semantic role (TupleLiteral vs TuplePattern).
  5. Parameters carry their own defaults, split by kind subclass.
  6. Grouped statements flattened (Delete, Import become per-item).
  7. No ExprStmt wrapper — expressions appear directly in statement bodies.

Usage:
    import ast, simple_ast
    tree = ast.parse(source)
    simple = simple_ast.simplify(tree)
"""

from __future__ import annotations
import ast
import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    # Sentinel
    "REMOVED",
    # Helpers
    "locate",
    "dump",
    "simplify",
    # Base
    "Node",
    "SourcePosition",
    # Intermediate bases
    "BinOp", "BoolOp", "CmpOp", "UnaryOp", "AugAssign",
    "AttrNode", "SubscriptNode", "ElementsLiteral", "PatternList",
    "ElemComp", "Branch", "Param",
    # Modules
    "Module", "Interactive", "Expression",
    # Literals
    "IntLiteral", "FloatLiteral", "ComplexLiteral", "StringLiteral",
    "BytesLiteral", "BoolLiteral", "NoneLiteral", "EllipsisLiteral",
    # Collection literals
    "ListLiteral", "TupleLiteral", "SetLiteral", "DictLiteral",
    # F-strings
    "FString", "FormattedExpr",
    # Names / Attributes / Subscripts
    "LoadName", "LoadAttr", "LoadSubscript",
    "StoreName", "StoreAttr", "StoreSubscript",
    "DeleteName", "DeleteAttr", "DeleteSubscript",
    "StarUnpack", "StarTarget", "Slice",
    # Destructuring patterns
    "TuplePattern", "ListPattern",
    # Binary operators
    "Add", "Sub", "Mult", "Div", "FloorDiv", "Mod", "Pow", "MatMult",
    "LShift", "RShift", "BitOr", "BitXor", "BitAnd",
    # Boolean operators
    "And", "Or",
    # Unary operators
    "UnaryPlus", "Negate", "Not", "Invert",
    # Comparison operators
    "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE", "Is", "IsNot", "In", "NotIn",
    "CompareChain",
    # Augmented assignment
    "AddAssign", "SubAssign", "MultAssign", "DivAssign", "FloorDivAssign",
    "ModAssign", "PowAssign", "MatMultAssign",
    "LShiftAssign", "RShiftAssign", "BitOrAssign", "BitXorAssign", "BitAndAssign",
    # Expressions
    "Call", "Keyword", "IfExpr", "NamedExpr", "Lambda",
    "Yield", "YieldFrom", "Await",
    # Comprehensions
    "ForClause", "ListComp", "SetComp", "DictComp", "GeneratorExpr",
    # Parameters
    "PosOnlyParam", "PosOrKwParam", "KwOnlyParam",
    "VarPositional", "VarKeyword", "Params",
    # Statements
    "Assign", "AnnAssign", "Return", "Pass", "Break", "Continue",
    "Raise", "Assert", "Global", "Nonlocal",
    # Logical / Prolog
    "Predicate",
    # Imports
    "Import", "ImportFrom",
    # Compound statements
    "If", "While", "For", "With", "Try", "ExceptHandler",
    # Definitions
    "FunctionDef", "ClassDef", "TypeAlias",
    # Type parameters
    "TypeVar", "ParamSpec", "TypeVarTuple",
    # Pattern matching
    "Match", "MatchCase", "MatchLiteral", "MatchSequence", "MatchMapping",
    "MatchClass", "MatchStar", "MatchAs", "MatchOr",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

REMOVED = object()


from transform_nodes import _transform_node_list

# ═══════════════════════════════════════════════════════════════════════════════
# Base
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Node:
    """Base class for all simplified AST nodes."""
    position: Optional[SourcePosition] = field(default=None, repr=False, compare=False)

    def visit_children(node, visit) -> None:
        """Visit all direct child nodes. Override in subclasses with children."""
        pass

    def children(node):
        children = []
        node.visit_children(children.append)
        return children

    def transform_children(node, transform) -> Node:
        """Transform all direct child nodes in place. Override in subclasses."""
        return node

    def transform_fields(node, **kwargs) -> Node:
        """Return a copy with changed fields, or self if nothing changed."""
        for key, new_val in kwargs.items():
            old_val = getattr(node, key)
            if old_val is not new_val:
                if not isinstance(old_val, (bool, int, float, str, bytes)) or old_val != new_val:
                    return dataclasses.replace(node, **kwargs)
        return node


@dataclass(frozen=True, slots=True)
class SourcePosition:
    lineno: int
    col_offset: int
    end_lineno: int
    end_col_offset: int


_LOC_FIELDS = frozenset(("position",))


def locate(
    src: ast.AST,
    dst: Node
) -> Node:
    """Copy source location from a CPython AST node to a simplified node.
    Do not use with Modules, Interactive, or Expression nodes.
    """
    dst.position = SourcePosition(
        src.lineno,
        src.col_offset,
        src.end_lineno,
        src.end_col_offset
    )
    return dst


# ═══════════════════════════════════════════════════════════════════════════════
# Intermediate base classes — carry shared fields and define visit/transform
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BinOp(Node):
    """Base for all binary operators: left op right."""
    left: Node = None   # type: ignore[assignment]
    right: Node = None  # type: ignore[assignment]

    def visit_children(bin_op, visit) -> None:
        visit(bin_op.left)
        visit(bin_op.right)

    def transform_children(bin_op, transform) -> BinOp:
        return bin_op.transform_fields(
            left=transform(bin_op.left),
            right=transform(bin_op.right),
        )


class BoolOp(BinOp):
    """Base for boolean binary operators (And, Or)."""
    pass


class CmpOp(BinOp):
    """Base for comparison operators (Eq, Lt, Is, In, …)."""
    pass


@dataclass
class UnaryOp(Node):
    """Base for unary operators."""
    operand: Node = None  # type: ignore[assignment]

    def visit_children(unary_op, visit) -> None:
        visit(unary_op.operand)

    def transform_children(unary_op, transform) -> UnaryOp:
        return unary_op.transform_fields( operand=transform(unary_op.operand))


@dataclass
class AugAssign(Node):
    """Base for augmented-assignment operators (+=, -=, …)."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]

    def visit_children(aug_assign, visit) -> None:
        visit(aug_assign.target)
        visit(aug_assign.value)

    def transform_children(aug_assign, transform) -> AugAssign:
        return aug_assign.transform_fields(
            target=transform(aug_assign.target),
            value=transform(aug_assign.value),
        )


@dataclass
class AttrNode(Node):
    """Base for attribute-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    attr: str = ""

    def visit_children(attr_node, visit) -> None:
        visit(attr_node.object)

    def transform_children(attr_node, transform) -> AttrNode:
        return attr_node.transform_fields( object=transform(attr_node.object))


@dataclass
class SubscriptNode(Node):
    """Base for subscript-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    index: Node = None   # type: ignore[assignment]

    def visit_children(subscript_node, visit) -> None:
        visit(subscript_node.object)
        visit(subscript_node.index)

    def transform_children(subscript_node, transform) -> SubscriptNode:
        return subscript_node.transform_fields(
            object=transform(subscript_node.object),
            index=transform(subscript_node.index),
        )


@dataclass
class ElementsLiteral(Node):
    """Base for collection literals that hold a flat element list."""
    elements: list[Node] = field(default_factory=list)

    def visit_children(elements_literal, visit) -> None:
        for elem in elements_literal.elements:
            visit(elem)

    def transform_children(elements_literal, transform) -> ElementsLiteral:
        return elements_literal.transform_fields(
            elements=_transform_node_list(elements_literal.elements, transform),
        )


@dataclass
class PatternList(Node):
    """Base for destructuring assignment targets (tuple/list patterns)."""
    targets: list[Node] = field(default_factory=list)

    def visit_children(pattern_list, visit) -> None:
        for target in pattern_list.targets:
            visit(target)

    def transform_children(pattern_list, transform) -> PatternList:
        return pattern_list.transform_fields(
            targets=_transform_node_list(pattern_list.targets, transform),
        )


@dataclass
class ElemComp(Node):
    """Base for element-based comprehensions (list/set/generator)."""
    element: Node = None  # type: ignore[assignment]
    clauses: list[ForClause] = field(default_factory=list)

    def visit_children(elem_comp, visit) -> None:
        visit(elem_comp.element)
        for clause in elem_comp.clauses:
            visit(clause)

    def transform_children(elem_comp, transform) -> ElemComp:
        return elem_comp.transform_fields(
            element=transform(elem_comp.element),
            clauses=_transform_node_list(elem_comp.clauses, transform),
        )


@dataclass
class Branch(Node):
    """Base for conditional branching statements (if, while)."""
    test: Node = None  # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)

    def visit_children(branch, visit) -> None:
        visit(branch.test)
        for child in branch.body:
            visit(child)
        for child in branch.orelse:
            visit(child)

    def transform_children(branch, transform) -> Branch:
        return branch.transform_fields(
            test=transform(branch.test),
            body=_transform_node_list(branch.body, transform),
            orelse=_transform_node_list(branch.orelse, transform),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Modules / Top-level
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Module(Node):
    body: list[Node] = field(default_factory=list)

    def visit_children(module, visit) -> None:
        for child in module.body:
            visit(child)

    def transform_children(module, transform) -> Module:
        return module.transform_fields( body=_transform_node_list(module.body, transform))

@dataclass
class Interactive(Node):
    body: list[Node] = field(default_factory=list)

    def visit_children(interactive, visit) -> None:
        for child in interactive.body:
            visit(child)

    def transform_children(interactive, transform) -> Interactive:
        return interactive.transform_fields( body=_transform_node_list(interactive.body, transform))

@dataclass
class Expression(Node):
    body: Node = None  # type: ignore[assignment]

    def visit_children(expression, visit) -> None:
        visit(expression.body)

    def transform_children(expression, transform) -> Expression:
        return expression.transform_fields( body=transform(expression.body))


# ═══════════════════════════════════════════════════════════════════════════════
# Literals
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class IntLiteral(Node):
    value: int = 0

@dataclass
class FloatLiteral(Node):
    value: float = 0.0

@dataclass
class ComplexLiteral(Node):
    value: complex = 0j

@dataclass
class StringLiteral(Node):
    value: str = ""

@dataclass
class BytesLiteral(Node):
    value: bytes = b""

@dataclass
class BoolLiteral(Node):
    value: bool = False

@dataclass
class NoneLiteral(Node):
    pass

@dataclass
class EllipsisLiteral(Node):
    pass

@dataclass
class ListLiteral(ElementsLiteral):
    pass

@dataclass
class TupleLiteral(ElementsLiteral):
    pass

@dataclass
class SetLiteral(ElementsLiteral):
    pass

@dataclass
class DictLiteral(Node):
    keys: list[Optional[Node]] = field(default_factory=list)    # None key = **splat
    values: list[Node] = field(default_factory=list)

    def visit_children(dict_literal, visit) -> None:
        for key in dict_literal.keys:
            if key is not None:
                visit(key)
        for value in dict_literal.values:
            visit(value)

    def transform_children(dict_literal, transform) -> DictLiteral:
        new_keys, keys_changed = [], False
        for k in dict_literal.keys:
            if k is None:
                new_keys.append(None)
            else:
                new_k = transform(k)
                if new_k is not k:
                    keys_changed = True
                new_keys.append(new_k)
        new_values = _transform_node_list(dict_literal.values, transform)
        return dict_literal.transform_fields(
            keys=new_keys if keys_changed else dict_literal.keys,
            values=new_values,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# F-strings
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FString(Node):
    parts: list[Node] = field(default_factory=list)  # StringLiteral | FormattedExpr

    def visit_children(f_string, visit) -> None:
        for part in f_string.parts:
            visit(part)

    def transform_children(f_string, transform) -> FString:
        return f_string.transform_fields( parts=_transform_node_list(f_string.parts, transform))

@dataclass
class FormattedExpr(Node):
    value: Node = None  # type: ignore[assignment]
    conversion: Optional[str] = None   # 's', 'r', 'a', or None
    format_spec: Optional[Node] = None

    def visit_children(formatted_expr, visit) -> None:
        visit(formatted_expr.value)
        if formatted_expr.format_spec is not None:
            visit(formatted_expr.format_spec)

    def transform_children(formatted_expr, transform) -> FormattedExpr:
        return formatted_expr.transform_fields(
            value=transform(formatted_expr.value),
            format_spec=transform(formatted_expr.format_spec) if formatted_expr.format_spec is not None else None,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Names / Attributes / Subscripts — split by context
# ═══════════════════════════════════════════════════════════════════════════════

# --- Load ---
@dataclass
class LoadName(Node):
    name: str = ""

@dataclass
class LoadAttr(AttrNode):
    pass

@dataclass
class LoadSubscript(SubscriptNode):
    pass

# --- Store ---
@dataclass
class StoreName(Node):
    name: str = ""

@dataclass
class StoreAttr(AttrNode):
    pass

@dataclass
class StoreSubscript(SubscriptNode):
    pass

# --- Delete ---
@dataclass
class DeleteName(Node):
    name: str = ""

@dataclass
class DeleteAttr(AttrNode):
    pass

@dataclass
class DeleteSubscript(SubscriptNode):
    pass

# --- Starred ---
@dataclass
class StarUnpack(Node):
    """*expr in a call or literal — unpacking."""
    value: Node = None  # type: ignore[assignment]

    def visit_children(star_unpack, visit) -> None:
        visit(star_unpack.value)

    def transform_children(star_unpack, transform) -> StarUnpack:
        return star_unpack.transform_fields( value=transform(star_unpack.value))

@dataclass
class StarTarget(Node):
    """*name in an assignment target — catch-all."""
    target: Node = None  # type: ignore[assignment]

    def visit_children(star_target, visit) -> None:
        visit(star_target.target)

    def transform_children(star_target, transform) -> StarTarget:
        return star_target.transform_fields( target=transform(star_target.target))


# ═══════════════════════════════════════════════════════════════════════════════
# Destructuring patterns (assignment targets that are sequences)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TuplePattern(PatternList):
    pass

@dataclass
class ListPattern(PatternList):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Binary Operators
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Add(BinOp):
    pass

@dataclass
class Sub(BinOp):
    pass

@dataclass
class Mult(BinOp):
    pass

@dataclass
class Div(BinOp):
    pass

@dataclass
class FloorDiv(BinOp):
    pass

@dataclass
class Mod(BinOp):
    pass

@dataclass
class Pow(BinOp):
    pass

@dataclass
class MatMult(BinOp):
    pass

@dataclass
class LShift(BinOp):
    pass

@dataclass
class RShift(BinOp):
    pass

@dataclass
class BitOr(BinOp):
    pass

@dataclass
class BitXor(BinOp):
    pass

@dataclass
class BitAnd(BinOp):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Boolean Operators (binary — chains are nested)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class And(BoolOp):
    pass

@dataclass
class Or(BoolOp):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Unary Operators
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UnaryPlus(UnaryOp):
    pass

@dataclass
class Negate(UnaryOp):
    pass

@dataclass
class Not(UnaryOp):
    pass

@dataclass
class Invert(UnaryOp):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Comparison Operators (binary — chains become CompareChain)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Eq(CmpOp):
    pass

@dataclass
class NotEq(CmpOp):
    pass

@dataclass
class Lt(CmpOp):
    pass

@dataclass
class LtE(CmpOp):
    pass

@dataclass
class Gt(CmpOp):
    pass

@dataclass
class GtE(CmpOp):
    pass

@dataclass
class Is(CmpOp):
    pass

@dataclass
class IsNot(CmpOp):
    pass

@dataclass
class In(CmpOp):
    pass

@dataclass
class NotIn(CmpOp):
    pass

@dataclass
class CompareChain(Node):
    """1 < x < 10 → CompareChain([Lt(1, x), Lt(x, 10)])

    Semantics: each intermediate operand is evaluated only once.
    For single comparisons, the individual Eq/Lt/etc. nodes are used directly.
    """
    comparisons: list[Node] = field(default_factory=list)

    def visit_children(compare_chain, visit) -> None:
        for cmp in compare_chain.comparisons:
            visit(cmp)

    def transform_children(compare_chain, transform) -> CompareChain:
        return compare_chain.transform_fields(
            comparisons=_transform_node_list(compare_chain.comparisons, transform),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Augmented Assignment (one node per operator)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AddAssign(AugAssign):
    pass

@dataclass
class SubAssign(AugAssign):
    pass

@dataclass
class MultAssign(AugAssign):
    pass

@dataclass
class DivAssign(AugAssign):
    pass

@dataclass
class FloorDivAssign(AugAssign):
    pass

@dataclass
class ModAssign(AugAssign):
    pass

@dataclass
class PowAssign(AugAssign):
    pass

@dataclass
class MatMultAssign(AugAssign):
    pass

@dataclass
class LShiftAssign(AugAssign):
    pass

@dataclass
class RShiftAssign(AugAssign):
    pass

@dataclass
class BitOrAssign(AugAssign):
    pass

@dataclass
class BitXorAssign(AugAssign):
    pass

@dataclass
class BitAndAssign(AugAssign):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Expressions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Call(Node):
    func: Node = None  # type: ignore[assignment]
    args: list[Node] = field(default_factory=list)
    kwargs: list[Keyword] = field(default_factory=list)

    def visit_children(call, visit) -> None:
        visit(call.func)
        for arg in call.args:
            visit(arg)
        for kw in call.kwargs:
            visit(kw)

    def transform_children(call, transform) -> Call:
        return call.transform_fields(
            func=transform(call.func),
            args=_transform_node_list(call.args, transform),
            kwargs=_transform_node_list(call.kwargs, transform),
        )

@dataclass
class Keyword(Node):
    """A single keyword argument. name=None means **splat."""
    name: Optional[str] = None
    value: Node = None  # type: ignore[assignment]

    def visit_children(keyword, visit) -> None:
        visit(keyword.value)

    def transform_children(keyword, transform) -> Keyword:
        return keyword.transform_fields( value=transform(keyword.value))

@dataclass
class IfExpr(Node):
    """Ternary: body if test else orelse."""
    test: Node = None    # type: ignore[assignment]
    body: Node = None    # type: ignore[assignment]
    orelse: Node = None  # type: ignore[assignment]

    def visit_children(if_expr, visit) -> None:
        visit(if_expr.test)
        visit(if_expr.body)
        visit(if_expr.orelse)

    def transform_children(if_expr, transform) -> IfExpr:
        return if_expr.transform_fields(
            test=transform(if_expr.test),
            body=transform(if_expr.body),
            orelse=transform(if_expr.orelse),
        )

@dataclass
class NamedExpr(Node):
    """:= walrus operator."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]

    def visit_children(named_expr, visit) -> None:
        visit(named_expr.target)
        visit(named_expr.value)

    def transform_children(named_expr, transform) -> NamedExpr:
        return named_expr.transform_fields(
            target=transform(named_expr.target),
            value=transform(named_expr.value),
        )

@dataclass
class Lambda(Node):
    params: Params = None  # type: ignore[assignment]
    body: Node = None      # type: ignore[assignment]

    def visit_children(lambda_node, visit) -> None:
        visit(lambda_node.params)
        visit(lambda_node.body)

    def transform_children(lambda_node, transform) -> Lambda:
        return lambda_node.transform_fields(
            params=transform(lambda_node.params),
            body=transform(lambda_node.body),
        )

@dataclass
class Yield(Node):
    value: Optional[Node] = None

    def visit_children(yield_node, visit) -> None:
        if yield_node.value is not None:
            visit(yield_node.value)

    def transform_children(yield_node, transform) -> Yield:
        return yield_node.transform_fields(
            value=transform(yield_node.value) if yield_node.value is not None else None,
        )

@dataclass
class YieldFrom(Node):
    value: Node = None  # type: ignore[assignment]

    def visit_children(yield_from, visit) -> None:
        visit(yield_from.value)

    def transform_children(yield_from, transform) -> YieldFrom:
        return yield_from.transform_fields( value=transform(yield_from.value))

@dataclass
class Await(Node):
    value: Node = None  # type: ignore[assignment]

    def visit_children(await_node, visit) -> None:
        visit(await_node.value)

    def transform_children(await_node, transform) -> Await:
        return await_node.transform_fields( value=transform(await_node.value))

@dataclass
class Slice(Node):
    lower: Optional[Node] = None
    upper: Optional[Node] = None
    step: Optional[Node] = None

    def visit_children(slice, visit) -> None:
        if slice.lower is not None:
            visit(slice.lower)
        if slice.upper is not None:
            visit(slice.upper)
        if slice.step is not None:
            visit(slice.step)

    def transform_children(slice, transform) -> Slice:
        return slice.transform_fields(
            lower=transform(slice.lower) if slice.lower is not None else None,
            upper=transform(slice.upper) if slice.upper is not None else None,
            step=transform(slice.step) if slice.step is not None else None,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Comprehensions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ForClause(Node):
    target: Node = None     # type: ignore[assignment]
    iterable: Node = None   # type: ignore[assignment]
    filters: list[Node] = field(default_factory=list)
    is_async: bool = False

    def visit_children(for_clause, visit) -> None:
        visit(for_clause.target)
        visit(for_clause.iterable)
        for f in for_clause.filters:
            visit(f)

    def transform_children(for_clause, transform) -> ForClause:
        return for_clause.transform_fields(
            target=transform(for_clause.target),
            iterable=transform(for_clause.iterable),
            filters=_transform_node_list(for_clause.filters, transform),
        )

@dataclass
class ListComp(ElemComp):
    pass

@dataclass
class SetComp(ElemComp):
    pass

@dataclass
class DictComp(Node):
    key: Node = None    # type: ignore[assignment]
    value: Node = None  # type: ignore[assignment]
    clauses: list[ForClause] = field(default_factory=list)

    def visit_children(dict_comp, visit) -> None:
        visit(dict_comp.key)
        visit(dict_comp.value)
        for clause in dict_comp.clauses:
            visit(clause)

    def transform_children(dict_comp, transform) -> DictComp:
        return dict_comp.transform_fields(
            key=transform(dict_comp.key),
            value=transform(dict_comp.value),
            clauses=_transform_node_list(dict_comp.clauses, transform),
        )

@dataclass
class GeneratorExpr(ElemComp):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Parameters — one subclass per kind
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Param(Node):
    """Base for all parameter kinds."""
    name: str = ""
    annotation: Optional[Node] = None
    default: Optional[Node] = None

    def visit_children(param, visit) -> None:
        if param.annotation is not None:
            visit(param.annotation)
        if param.default is not None:
            visit(param.default)

    def transform_children(param, transform) -> Param:
        return param.transform_fields(
            annotation=transform(param.annotation) if param.annotation is not None else None,
            default=transform(param.default) if param.default is not None else None,
        )

@dataclass
class PosOnlyParam(Param):
    """Positional-only parameter (before /)."""
    pass

@dataclass
class PosOrKwParam(Param):
    """Normal positional-or-keyword parameter."""
    pass

@dataclass
class KwOnlyParam(Param):
    """Keyword-only parameter (after *)."""
    pass

@dataclass
class VarPositional(Param):
    """*args parameter."""
    pass

@dataclass
class VarKeyword(Param):
    """**kwargs parameter."""
    pass

@dataclass
class Params(Node):
    params: list[Param] = field(default_factory=list)

    def visit_children(params, visit) -> None:
        for p in params.params:
            visit(p)

    def transform_children(params, transform) -> Params:
        return params.transform_fields( params=_transform_node_list(params.params, transform))


# ═══════════════════════════════════════════════════════════════════════════════
# Statements
# ═══════════════════════════════════════════════════════════════════════════════

# No ExprStmt — expressions appear directly in body lists.

@dataclass
class Assign(Node):
    targets: list[Node] = field(default_factory=list)
    value: Node = None  # type: ignore[assignment]

    def visit_children(assign, visit) -> None:
        for t in assign.targets:
            visit(t)
        visit(assign.value)

    def transform_children(assign, transform) -> Assign:
        return assign.transform_fields(
            targets=_transform_node_list(assign.targets, transform),
            value=transform(assign.value),
        )

@dataclass
class Predicate(Node):
    """Prolog-style predicate: head <- body."""
    head: Node = None  # type: ignore[assignment]
    body: Node = None  # type: ignore[assignment]

    def visit_children(predicate, visit) -> None:
        visit(predicate.head)
        visit(predicate.body)

    def transform_children(predicate, transform) -> Predicate:
        return predicate.transform_fields(
            head=transform(predicate.head),
            body=transform(predicate.body),
        )

@dataclass
class AnnAssign(Node):
    target: Node = None      # type: ignore[assignment]
    annotation: Node = None  # type: ignore[assignment]
    value: Optional[Node] = None
    simple: bool = True

    def visit_children(ann_assign, visit) -> None:
        visit(ann_assign.target)
        visit(ann_assign.annotation)
        if ann_assign.value is not None:
            visit(ann_assign.value)

    def transform_children(ann_assign, transform) -> AnnAssign:
        return ann_assign.transform_fields(
            target=transform(ann_assign.target),
            annotation=transform(ann_assign.annotation),
            value=transform(ann_assign.value) if ann_assign.value is not None else None,
        )

@dataclass
class Return(Node):
    value: Optional[Node] = None

    def visit_children(return_node, visit) -> None:
        if return_node.value is not None:
            visit(return_node.value)

    def transform_children(return_node, transform) -> Return:
        return return_node.transform_fields(
            value=transform(return_node.value) if return_node.value is not None else None,
        )

@dataclass
class Pass(Node):
    pass

@dataclass
class Break(Node):
    pass

@dataclass
class Continue(Node):
    pass

@dataclass
class Raise(Node):
    exc: Optional[Node] = None
    cause: Optional[Node] = None

    def visit_children(raise_node, visit) -> None:
        if raise_node.exc is not None:
            visit(raise_node.exc)
        if raise_node.cause is not None:
            visit(raise_node.cause)

    def transform_children(raise_node, transform) -> Raise:
        return raise_node.transform_fields(
            exc=transform(raise_node.exc) if raise_node.exc is not None else None,
            cause=transform(raise_node.cause) if raise_node.cause is not None else None,
        )

@dataclass
class Assert(Node):
    test: Node = None  # type: ignore[assignment]
    msg: Optional[Node] = None

    def visit_children(assert_node, visit) -> None:
        visit(assert_node.test)
        if assert_node.msg is not None:
            visit(assert_node.msg)

    def transform_children(assert_node, transform) -> Assert:
        return assert_node.transform_fields(
            test=transform(assert_node.test),
            msg=transform(assert_node.msg) if assert_node.msg is not None else None,
        )

@dataclass
class Global(Node):
    names: list[str] = field(default_factory=list)

@dataclass
class Nonlocal(Node):
    names: list[str] = field(default_factory=list)


# --- Imports (flattened) ---

@dataclass
class Import(Node):
    module: str = ""
    alias: Optional[str] = None

@dataclass
class ImportFrom(Node):
    module: Optional[str] = None
    name: str = ""
    alias: Optional[str] = None
    level: int = 0


# --- Compound statements ---

@dataclass
class If(Branch):
    pass

@dataclass
class While(Branch):
    pass

@dataclass
class For(Node):
    target: Node = None    # type: ignore[assignment]
    iterable: Node = None  # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)
    is_async: bool = False

    def visit_children(for_node, visit) -> None:
        visit(for_node.target)
        visit(for_node.iterable)
        for child in for_node.body:
            visit(child)
        for child in for_node.orelse:
            visit(child)

    def transform_children(for_node, transform) -> For:
        return for_node.transform_fields(
            target=transform(for_node.target),
            iterable=transform(for_node.iterable),
            body=_transform_node_list(for_node.body, transform),
            orelse=_transform_node_list(for_node.orelse, transform),
        )

@dataclass
class With(Node):
    items: list[tuple[Node, Optional[Node]]] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    is_async: bool = False

    def visit_children(with_node, visit) -> None:
        for ctx, var in with_node.items:
            visit(ctx)
            if var is not None:
                visit(var)
        for child in with_node.body:
            visit(child)

    def transform_children(with_node, transform) -> With:
        new_items, items_changed = [], False
        for ctx, var in with_node.items:
            new_ctx = transform(ctx)
            new_var = transform(var) if var is not None else None
            if new_ctx is not ctx or new_var is not var:
                items_changed = True
            new_items.append((new_ctx, new_var))
        new_body = _transform_node_list(with_node.body, transform)
        return with_node.transform_fields(
            items=new_items if items_changed else with_node.items,
            body=new_body,
        )

@dataclass
class Try(Node):
    body: list[Node] = field(default_factory=list)
    handlers: list[ExceptHandler] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)
    finalbody: list[Node] = field(default_factory=list)
    is_star: bool = False

    def visit_children(try_node, visit) -> None:
        for child in try_node.body:
            visit(child)
        for handler in try_node.handlers:
            visit(handler)
        for child in try_node.orelse:
            visit(child)
        for child in try_node.finalbody:
            visit(child)

    def transform_children(try_node, transform) -> Try:
        return try_node.transform_fields(
            body=_transform_node_list(try_node.body, transform),
            handlers=_transform_node_list(try_node.handlers, transform),
            orelse=_transform_node_list(try_node.orelse, transform),
            finalbody=_transform_node_list(try_node.finalbody, transform),
        )

@dataclass
class ExceptHandler(Node):
    type: Optional[Node] = None
    name: Optional[str] = None
    body: list[Node] = field(default_factory=list)

    def visit_children(except_handler, visit) -> None:
        if except_handler.type is not None:
            visit(except_handler.type)
        for child in except_handler.body:
            visit(child)

    def transform_children(except_handler, transform) -> ExceptHandler:
        return except_handler.transform_fields(
            type=transform(except_handler.type) if except_handler.type is not None else None,
            body=_transform_node_list(except_handler.body, transform),
        )


# --- Definitions ---

@dataclass
class FunctionDef(Node):
    name: str = ""
    params: Params = None     # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)
    decorators: list[Node] = field(default_factory=list)
    returns: Optional[Node] = None
    is_async: bool = False
    type_params: list[Node] = field(default_factory=list)

    def visit_children(function_def, visit) -> None:
        visit(function_def.params)
        for child in function_def.body:
            visit(child)
        for dec in function_def.decorators:
            visit(dec)
        if function_def.returns is not None:
            visit(function_def.returns)
        for tp in function_def.type_params:
            visit(tp)

    def transform_children(function_def, transform) -> FunctionDef:
        return function_def.transform_fields(
            params=transform(function_def.params),
            body=_transform_node_list(function_def.body, transform),
            decorators=_transform_node_list(function_def.decorators, transform),
            returns=transform(function_def.returns) if function_def.returns is not None else None,
            type_params=_transform_node_list(function_def.type_params, transform),
        )

@dataclass
class ClassDef(Node):
    name: str = ""
    bases: list[Node] = field(default_factory=list)
    keywords: list[Keyword] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    decorators: list[Node] = field(default_factory=list)
    type_params: list[Node] = field(default_factory=list)

    def visit_children(class_def, visit) -> None:
        for base in class_def.bases:
            visit(base)
        for kw in class_def.keywords:
            visit(kw)
        for child in class_def.body:
            visit(child)
        for dec in class_def.decorators:
            visit(dec)
        for tp in class_def.type_params:
            visit(tp)

    def transform_children(class_def, transform) -> ClassDef:
        return class_def.transform_fields(
            bases=_transform_node_list(class_def.bases, transform),
            keywords=_transform_node_list(class_def.keywords, transform),
            body=_transform_node_list(class_def.body, transform),
            decorators=_transform_node_list(class_def.decorators, transform),
            type_params=_transform_node_list(class_def.type_params, transform),
        )

@dataclass
class TypeAlias(Node):
    name: Node = None  # type: ignore[assignment]
    type_params: list[Node] = field(default_factory=list)
    value: Node = None  # type: ignore[assignment]

    def visit_children(type_alias, visit) -> None:
        visit(type_alias.name)
        for tp in type_alias.type_params:
            visit(tp)
        visit(type_alias.value)

    def transform_children(type_alias, transform) -> TypeAlias:
        return type_alias.transform_fields(
            name=transform(type_alias.name),
            type_params=_transform_node_list(type_alias.type_params, transform),
            value=transform(type_alias.value),
        )


# --- Type params (3.12+) ---

@dataclass
class TypeVar(Node):
    name: str = ""
    bound: Optional[Node] = None

    def visit_children(type_var, visit) -> None:
        if type_var.bound is not None:
            visit(type_var.bound)

    def transform_children(type_var, transform) -> TypeVar:
        return type_var.transform_fields(
            bound=transform(type_var.bound) if type_var.bound is not None else None,
        )

@dataclass
class ParamSpec(Node):
    name: str = ""

@dataclass
class TypeVarTuple(Node):
    name: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Pattern Matching
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Match(Node):
    subject: Node = None  # type: ignore[assignment]
    cases: list[MatchCase] = field(default_factory=list)

    def visit_children(match, visit) -> None:
        visit(match.subject)
        for case in match.cases:
            visit(case)

    def transform_children(match, transform) -> Match:
        return match.transform_fields(
            subject=transform(match.subject),
            cases=_transform_node_list(match.cases, transform),
        )

@dataclass
class MatchCase(Node):
    pattern: Node = None  # type: ignore[assignment]
    guard: Optional[Node] = None
    body: list[Node] = field(default_factory=list)

    def visit_children(match_case, visit) -> None:
        visit(match_case.pattern)
        if match_case.guard is not None:
            visit(match_case.guard)
        for child in match_case.body:
            visit(child)

    def transform_children(match_case, transform) -> MatchCase:
        return match_case.transform_fields(
            pattern=transform(match_case.pattern),
            guard=transform(match_case.guard) if match_case.guard is not None else None,
            body=_transform_node_list(match_case.body, transform),
        )

@dataclass
class MatchLiteral(Node):
    value: Node = None  # type: ignore[assignment]
    use_is: bool = False

    def visit_children(match_literal, visit) -> None:
        visit(match_literal.value)

    def transform_children(match_literal, transform) -> MatchLiteral:
        return match_literal.transform_fields( value=transform(match_literal.value))

@dataclass
class MatchSequence(Node):
    patterns: list[Node] = field(default_factory=list)

    def visit_children(match_sequence, visit) -> None:
        for p in match_sequence.patterns:
            visit(p)

    def transform_children(match_sequence, transform) -> MatchSequence:
        return match_sequence.transform_fields(
            patterns=_transform_node_list(match_sequence.patterns, transform),
        )

@dataclass
class MatchMapping(Node):
    keys: list[Node] = field(default_factory=list)
    patterns: list[Node] = field(default_factory=list)
    rest: Optional[str] = None

    def visit_children(match_mapping, visit) -> None:
        for k in match_mapping.keys:
            visit(k)
        for p in match_mapping.patterns:
            visit(p)

    def transform_children(match_mapping, transform) -> MatchMapping:
        return match_mapping.transform_fields(
            keys=_transform_node_list(match_mapping.keys, transform),
            patterns=_transform_node_list(match_mapping.patterns, transform),
        )

@dataclass
class MatchClass(Node):
    cls: Node = None  # type: ignore[assignment]
    patterns: list[Node] = field(default_factory=list)
    kwd_attrs: list[str] = field(default_factory=list)
    kwd_patterns: list[Node] = field(default_factory=list)

    def visit_children(match_class, visit) -> None:
        visit(match_class.cls)
        for p in match_class.patterns:
            visit(p)
        for kp in match_class.kwd_patterns:
            visit(kp)

    def transform_children(match_class, transform) -> MatchClass:
        return match_class.transform_fields(
            cls=transform(match_class.cls),
            patterns=_transform_node_list(match_class.patterns, transform),
            kwd_patterns=_transform_node_list(match_class.kwd_patterns, transform),
        )

@dataclass
class MatchStar(Node):
    name: Optional[str] = None

@dataclass
class MatchAs(Node):
    pattern: Optional[Node] = None
    name: Optional[str] = None

    def visit_children(match_as, visit) -> None:
        if match_as.pattern is not None:
            visit(match_as.pattern)

    def transform_children(match_as, transform) -> MatchAs:
        return match_as.transform_fields(
            pattern=transform(match_as.pattern) if match_as.pattern is not None else None,
        )

@dataclass
class MatchOr(Node):
    patterns: list[Node] = field(default_factory=list)

    def visit_children(match_or, visit) -> None:
        for p in match_or.patterns:
            visit(p)

    def transform_children(match_or, transform) -> MatchOr:
        return match_or.transform_fields(
            patterns=_transform_node_list(match_or.patterns, transform),
        )

# ═══════════════════════════════════════════════════════════════════════════════
# Pretty Printer
# ═══════════════════════════════════════════════════════════════════════════════

def dump(node: Node, indent: int = 2, include_loc: bool = False) -> str:
    """Pretty-print a simplified AST node."""

    def _format(n: Any, level: int) -> str:
        if isinstance(n, Node):
            cls_name = n.__class__.__name__
            fields = []
            for f in dataclasses.fields(n):
                if not include_loc and f.name in _LOC_FIELDS:
                    continue
                fields.append((f.name, getattr(n, f.name)))
            if not fields:
                return f"{cls_name}()"
            if len(fields) == 1 and not isinstance(fields[0][1], (list, Node)):
                return f"{cls_name}({fields[0][1]!r})"
            parts = [
                f"{' ' * (level + indent)}{fname}={_format(fval, level + indent)}"
                for fname, fval in fields
            ]
            return f"{cls_name}(\n" + ",\n".join(parts) + ")"
        elif isinstance(n, list):
            if not n:
                return "[]"
            items = [_format(item, level + indent) for item in n]
            if all("\n" not in item for item in items) and sum(len(i) for i in items) < 60:
                return f"[{', '.join(items)}]"
            parts = [f"{' ' * (level + indent)}{item}" for item in items]
            return "[\n" + ",\n".join(parts) + "]"
        elif isinstance(n, tuple):
            return f"({', '.join(_format(item, level + indent) for item in n)})"
        else:
            return repr(n)

    return _format(node, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def simplify(tree: ast.AST) -> Node:
    """Convert a CPython AST tree into a simplified AST."""
    from conversion import visit
    return visit(tree)
