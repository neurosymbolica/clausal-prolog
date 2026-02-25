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


from transform_nodes import _transform_node_list.py

# ═══════════════════════════════════════════════════════════════════════════════
# Base
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Node:
    """Base class for all simplified AST nodes."""
    position: Optional[SourcePosition] = field(default=None, repr=False, compare=False)

    def visit_children(self, visit) -> None:
        """Visit all direct child nodes. Override in subclasses with children."""
        pass

    def children(self):
        children = []
        self.visit_children(children.append)
        return children

    def transform_children(self, transform) -> Node:
        """Transform all direct child nodes in place. Override in subclasses."""
        return self

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


def locate(src: ast.AST, dst: Node) -> Node:
    """Copy source location from a CPython AST node to a simplified node.
    Do not use with Modules, Interactive, or Expression nodes.
    """
    dst.position = SourcePosition(src.lineno, src.col_offset, src.end_lineno, src.end_col_offset)
    return dst


# ═══════════════════════════════════════════════════════════════════════════════
# Intermediate base classes — carry shared fields and define visit/transform
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BinOp(Node):
    """Base for all binary operators: left op right."""
    left: Node = None   # type: ignore[assignment]
    right: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.left)
        visit(self.right)

    def transform_children(self, transform) -> BinOp:
        return self.transform_fields(
            left=transform(self.left),
            right=transform(self.right),
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

    def visit_children(self, visit) -> None:
        visit(self.operand)

    def transform_children(self, transform) -> UnaryOp:
        return self.transform_fields( operand=transform(self.operand))


@dataclass
class AugAssign(Node):
    """Base for augmented-assignment operators (+=, -=, …)."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.target)
        visit(self.value)

    def transform_children(self, transform) -> AugAssign:
        return self.transform_fields(
            target=transform(self.target),
            value=transform(self.value),
        )


@dataclass
class AttrNode(Node):
    """Base for attribute-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    attr: str = ""

    def visit_children(self, visit) -> None:
        visit(self.object)

    def transform_children(self, transform) -> AttrNode:
        return self.transform_fields( object=transform(self.object))


@dataclass
class SubscriptNode(Node):
    """Base for subscript-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    index: Node = None   # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.object)
        visit(self.index)

    def transform_children(self, transform) -> SubscriptNode:
        return self.transform_fields(
            object=transform(self.object),
            index=transform(self.index),
        )


@dataclass
class ElementsLiteral(Node):
    """Base for collection literals that hold a flat element list."""
    elements: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for elem in self.elements:
            visit(elem)

    def transform_children(self, transform) -> ElementsLiteral:
        return self.transform_fields(
            elements=_transform_node_list(self.elements, transform),
        )


@dataclass
class PatternList(Node):
    """Base for destructuring assignment targets (tuple/list patterns)."""
    targets: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for target in self.targets:
            visit(target)

    def transform_children(self, transform) -> PatternList:
        return self.transform_fields(
            targets=_transform_node_list(self.targets, transform),
        )


@dataclass
class ElemComp(Node):
    """Base for element-based comprehensions (list/set/generator)."""
    element: Node = None  # type: ignore[assignment]
    clauses: list[ForClause] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        visit(self.element)
        for clause in self.clauses:
            visit(clause)

    def transform_children(self, transform) -> ElemComp:
        return self.transform_fields(
            element=transform(self.element),
            clauses=_transform_node_list(self.clauses, transform),
        )


@dataclass
class Branch(Node):
    """Base for conditional branching statements (if, while)."""
    test: Node = None  # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        visit(self.test)
        for child in self.body:
            visit(child)
        for child in self.orelse:
            visit(child)

    def transform_children(self, transform) -> Branch:
        return self.transform_fields(
            test=transform(self.test),
            body=_transform_node_list(self.body, transform),
            orelse=_transform_node_list(self.orelse, transform),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Modules / Top-level
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Module(Node):
    body: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for child in self.body:
            visit(child)

    def transform_children(self, transform) -> Module:
        return self.transform_fields( body=_transform_node_list(self.body, transform))

@dataclass
class Interactive(Node):
    body: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for child in self.body:
            visit(child)

    def transform_children(self, transform) -> Interactive:
        return self.transform_fields( body=_transform_node_list(self.body, transform))

@dataclass
class Expression(Node):
    body: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.body)

    def transform_children(self, transform) -> Expression:
        return self.transform_fields( body=transform(self.body))


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

    def visit_children(self, visit) -> None:
        for key in self.keys:
            if key is not None:
                visit(key)
        for value in self.values:
            visit(value)

    def transform_children(self, transform) -> DictLiteral:
        new_keys, keys_changed = [], False
        for k in self.keys:
            if k is None:
                new_keys.append(None)
            else:
                new_k = transform(k)
                if new_k is not k:
                    keys_changed = True
                new_keys.append(new_k)
        new_values = _transform_node_list(self.values, transform)
        return self.transform_fields(
            keys=new_keys if keys_changed else self.keys,
            values=new_values,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# F-strings
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FString(Node):
    parts: list[Node] = field(default_factory=list)  # StringLiteral | FormattedExpr

    def visit_children(self, visit) -> None:
        for part in self.parts:
            visit(part)

    def transform_children(self, transform) -> FString:
        return self.transform_fields( parts=_transform_node_list(self.parts, transform))

@dataclass
class FormattedExpr(Node):
    value: Node = None  # type: ignore[assignment]
    conversion: Optional[str] = None   # 's', 'r', 'a', or None
    format_spec: Optional[Node] = None

    def visit_children(self, visit) -> None:
        visit(self.value)
        if self.format_spec is not None:
            visit(self.format_spec)

    def transform_children(self, transform) -> FormattedExpr:
        return self.transform_fields(
            value=transform(self.value),
            format_spec=transform(self.format_spec) if self.format_spec is not None else None,
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

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> StarUnpack:
        return self.transform_fields( value=transform(self.value))

@dataclass
class StarTarget(Node):
    """*name in an assignment target — catch-all."""
    target: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.target)

    def transform_children(self, transform) -> StarTarget:
        return self.transform_fields( target=transform(self.target))


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

    def visit_children(self, visit) -> None:
        for cmp in self.comparisons:
            visit(cmp)

    def transform_children(self, transform) -> CompareChain:
        return self.transform_fields(
            comparisons=_transform_node_list(self.comparisons, transform),
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

    def visit_children(self, visit) -> None:
        visit(self.func)
        for arg in self.args:
            visit(arg)
        for kw in self.kwargs:
            visit(kw)

    def transform_children(self, transform) -> Call:
        return self.transform_fields(
            func=transform(self.func),
            args=_transform_node_list(self.args, transform),
            kwargs=_transform_node_list(self.kwargs, transform),
        )

@dataclass
class Keyword(Node):
    """A single keyword argument. name=None means **splat."""
    name: Optional[str] = None
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> Keyword:
        return self.transform_fields( value=transform(self.value))

@dataclass
class IfExpr(Node):
    """Ternary: body if test else orelse."""
    test: Node = None    # type: ignore[assignment]
    body: Node = None    # type: ignore[assignment]
    orelse: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.test)
        visit(self.body)
        visit(self.orelse)

    def transform_children(self, transform) -> IfExpr:
        return self.transform_fields(
            test=transform(self.test),
            body=transform(self.body),
            orelse=transform(self.orelse),
        )

@dataclass
class NamedExpr(Node):
    """:= walrus operator."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.target)
        visit(self.value)

    def transform_children(self, transform) -> NamedExpr:
        return self.transform_fields(
            target=transform(self.target),
            value=transform(self.value),
        )

@dataclass
class Lambda(Node):
    params: Params = None  # type: ignore[assignment]
    body: Node = None      # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.params)
        visit(self.body)

    def transform_children(self, transform) -> Lambda:
        return self.transform_fields(
            params=transform(self.params),
            body=transform(self.body),
        )

@dataclass
class Yield(Node):
    value: Optional[Node] = None

    def visit_children(self, visit) -> None:
        if self.value is not None:
            visit(self.value)

    def transform_children(self, transform) -> Yield:
        return self.transform_fields(
            value=transform(self.value) if self.value is not None else None,
        )

@dataclass
class YieldFrom(Node):
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> YieldFrom:
        return self.transform_fields( value=transform(self.value))

@dataclass
class Await(Node):
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> Await:
        return self.transform_fields( value=transform(self.value))

@dataclass
class Slice(Node):
    lower: Optional[Node] = None
    upper: Optional[Node] = None
    step: Optional[Node] = None

    def visit_children(self, visit) -> None:
        if self.lower is not None:
            visit(self.lower)
        if self.upper is not None:
            visit(self.upper)
        if self.step is not None:
            visit(self.step)

    def transform_children(self, transform) -> Slice:
        return self.transform_fields(
            lower=transform(self.lower) if self.lower is not None else None,
            upper=transform(self.upper) if self.upper is not None else None,
            step=transform(self.step) if self.step is not None else None,
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

    def visit_children(self, visit) -> None:
        visit(self.target)
        visit(self.iterable)
        for f in self.filters:
            visit(f)

    def transform_children(self, transform) -> ForClause:
        return self.transform_fields(
            target=transform(self.target),
            iterable=transform(self.iterable),
            filters=_transform_node_list(self.filters, transform),
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

    def visit_children(self, visit) -> None:
        visit(self.key)
        visit(self.value)
        for clause in self.clauses:
            visit(clause)

    def transform_children(self, transform) -> DictComp:
        return self.transform_fields(
            key=transform(self.key),
            value=transform(self.value),
            clauses=_transform_node_list(self.clauses, transform),
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

    def visit_children(self, visit) -> None:
        if self.annotation is not None:
            visit(self.annotation)
        if self.default is not None:
            visit(self.default)

    def transform_children(self, transform) -> Param:
        return self.transform_fields(
            annotation=transform(self.annotation) if self.annotation is not None else None,
            default=transform(self.default) if self.default is not None else None,
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

    def visit_children(self, visit) -> None:
        for p in self.params:
            visit(p)

    def transform_children(self, transform) -> Params:
        return self.transform_fields( params=_transform_node_list(self.params, transform))


# ═══════════════════════════════════════════════════════════════════════════════
# Statements
# ═══════════════════════════════════════════════════════════════════════════════

# No ExprStmt — expressions appear directly in body lists.

@dataclass
class Assign(Node):
    targets: list[Node] = field(default_factory=list)
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        for t in self.targets:
            visit(t)
        visit(self.value)

    def transform_children(self, transform) -> Assign:
        return self.transform_fields(
            targets=_transform_node_list(self.targets, transform),
            value=transform(self.value),
        )

@dataclass
class AnnAssign(Node):
    target: Node = None      # type: ignore[assignment]
    annotation: Node = None  # type: ignore[assignment]
    value: Optional[Node] = None
    simple: bool = True

    def visit_children(self, visit) -> None:
        visit(self.target)
        visit(self.annotation)
        if self.value is not None:
            visit(self.value)

    def transform_children(self, transform) -> AnnAssign:
        return self.transform_fields(
            target=transform(self.target),
            annotation=transform(self.annotation),
            value=transform(self.value) if self.value is not None else None,
        )

@dataclass
class Return(Node):
    value: Optional[Node] = None

    def visit_children(self, visit) -> None:
        if self.value is not None:
            visit(self.value)

    def transform_children(self, transform) -> Return:
        return self.transform_fields(
            value=transform(self.value) if self.value is not None else None,
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

    def visit_children(self, visit) -> None:
        if self.exc is not None:
            visit(self.exc)
        if self.cause is not None:
            visit(self.cause)

    def transform_children(self, transform) -> Raise:
        return self.transform_fields(
            exc=transform(self.exc) if self.exc is not None else None,
            cause=transform(self.cause) if self.cause is not None else None,
        )

@dataclass
class Assert(Node):
    test: Node = None  # type: ignore[assignment]
    msg: Optional[Node] = None

    def visit_children(self, visit) -> None:
        visit(self.test)
        if self.msg is not None:
            visit(self.msg)

    def transform_children(self, transform) -> Assert:
        return self.transform_fields(
            test=transform(self.test),
            msg=transform(self.msg) if self.msg is not None else None,
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

    def visit_children(self, visit) -> None:
        visit(self.target)
        visit(self.iterable)
        for child in self.body:
            visit(child)
        for child in self.orelse:
            visit(child)

    def transform_children(self, transform) -> For:
        return self.transform_fields(
            target=transform(self.target),
            iterable=transform(self.iterable),
            body=_transform_node_list(self.body, transform),
            orelse=_transform_node_list(self.orelse, transform),
        )

@dataclass
class With(Node):
    items: list[tuple[Node, Optional[Node]]] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    is_async: bool = False

    def visit_children(self, visit) -> None:
        for ctx, var in self.items:
            visit(ctx)
            if var is not None:
                visit(var)
        for child in self.body:
            visit(child)

    def transform_children(self, transform) -> With:
        new_items, items_changed = [], False
        for ctx, var in self.items:
            new_ctx = transform(ctx)
            new_var = transform(var) if var is not None else None
            if new_ctx is not ctx or new_var is not var:
                items_changed = True
            new_items.append((new_ctx, new_var))
        new_body = _transform_node_list(self.body, transform)
        return self.transform_fields(
            items=new_items if items_changed else self.items,
            body=new_body,
        )

@dataclass
class Try(Node):
    body: list[Node] = field(default_factory=list)
    handlers: list[ExceptHandler] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)
    finalbody: list[Node] = field(default_factory=list)
    is_star: bool = False

    def visit_children(self, visit) -> None:
        for child in self.body:
            visit(child)
        for handler in self.handlers:
            visit(handler)
        for child in self.orelse:
            visit(child)
        for child in self.finalbody:
            visit(child)

    def transform_children(self, transform) -> Try:
        return self.transform_fields(
            body=_transform_node_list(self.body, transform),
            handlers=_transform_node_list(self.handlers, transform),
            orelse=_transform_node_list(self.orelse, transform),
            finalbody=_transform_node_list(self.finalbody, transform),
        )

@dataclass
class ExceptHandler(Node):
    type: Optional[Node] = None
    name: Optional[str] = None
    body: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        if self.type is not None:
            visit(self.type)
        for child in self.body:
            visit(child)

    def transform_children(self, transform) -> ExceptHandler:
        return self.transform_fields(
            type=transform(self.type) if self.type is not None else None,
            body=_transform_node_list(self.body, transform),
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

    def visit_children(self, visit) -> None:
        visit(self.params)
        for child in self.body:
            visit(child)
        for dec in self.decorators:
            visit(dec)
        if self.returns is not None:
            visit(self.returns)
        for tp in self.type_params:
            visit(tp)

    def transform_children(self, transform) -> FunctionDef:
        return self.transform_fields(
            params=transform(self.params),
            body=_transform_node_list(self.body, transform),
            decorators=_transform_node_list(self.decorators, transform),
            returns=transform(self.returns) if self.returns is not None else None,
            type_params=_transform_node_list(self.type_params, transform),
        )

@dataclass
class ClassDef(Node):
    name: str = ""
    bases: list[Node] = field(default_factory=list)
    keywords: list[Keyword] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    decorators: list[Node] = field(default_factory=list)
    type_params: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for base in self.bases:
            visit(base)
        for kw in self.keywords:
            visit(kw)
        for child in self.body:
            visit(child)
        for dec in self.decorators:
            visit(dec)
        for tp in self.type_params:
            visit(tp)

    def transform_children(self, transform) -> ClassDef:
        return self.transform_fields(
            bases=_transform_node_list(self.bases, transform),
            keywords=_transform_node_list(self.keywords, transform),
            body=_transform_node_list(self.body, transform),
            decorators=_transform_node_list(self.decorators, transform),
            type_params=_transform_node_list(self.type_params, transform),
        )

@dataclass
class TypeAlias(Node):
    name: Node = None  # type: ignore[assignment]
    type_params: list[Node] = field(default_factory=list)
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.name)
        for tp in self.type_params:
            visit(tp)
        visit(self.value)

    def transform_children(self, transform) -> TypeAlias:
        return self.transform_fields(
            name=transform(self.name),
            type_params=_transform_node_list(self.type_params, transform),
            value=transform(self.value),
        )


# --- Type params (3.12+) ---

@dataclass
class TypeVar(Node):
    name: str = ""
    bound: Optional[Node] = None

    def visit_children(self, visit) -> None:
        if self.bound is not None:
            visit(self.bound)

    def transform_children(self, transform) -> TypeVar:
        return self.transform_fields(
            bound=transform(self.bound) if self.bound is not None else None,
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

    def visit_children(self, visit) -> None:
        visit(self.subject)
        for case in self.cases:
            visit(case)

    def transform_children(self, transform) -> Match:
        return self.transform_fields(
            subject=transform(self.subject),
            cases=_transform_node_list(self.cases, transform),
        )

@dataclass
class MatchCase(Node):
    pattern: Node = None  # type: ignore[assignment]
    guard: Optional[Node] = None
    body: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        visit(self.pattern)
        if self.guard is not None:
            visit(self.guard)
        for child in self.body:
            visit(child)

    def transform_children(self, transform) -> MatchCase:
        return self.transform_fields(
            pattern=transform(self.pattern),
            guard=transform(self.guard) if self.guard is not None else None,
            body=_transform_node_list(self.body, transform),
        )

@dataclass
class MatchLiteral(Node):
    value: Node = None  # type: ignore[assignment]
    use_is: bool = False

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> MatchLiteral:
        return self.transform_fields( value=transform(self.value))

@dataclass
class MatchSequence(Node):
    patterns: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for p in self.patterns:
            visit(p)

    def transform_children(self, transform) -> MatchSequence:
        return self.transform_fields(
            patterns=_transform_node_list(self.patterns, transform),
        )

@dataclass
class MatchMapping(Node):
    keys: list[Node] = field(default_factory=list)
    patterns: list[Node] = field(default_factory=list)
    rest: Optional[str] = None

    def visit_children(self, visit) -> None:
        for k in self.keys:
            visit(k)
        for p in self.patterns:
            visit(p)

    def transform_children(self, transform) -> MatchMapping:
        return self.transform_fields(
            keys=_transform_node_list(self.keys, transform),
            patterns=_transform_node_list(self.patterns, transform),
        )

@dataclass
class MatchClass(Node):
    cls: Node = None  # type: ignore[assignment]
    patterns: list[Node] = field(default_factory=list)
    kwd_attrs: list[str] = field(default_factory=list)
    kwd_patterns: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        visit(self.cls)
        for p in self.patterns:
            visit(p)
        for kp in self.kwd_patterns:
            visit(kp)

    def transform_children(self, transform) -> MatchClass:
        return self.transform_fields(
            cls=transform(self.cls),
            patterns=_transform_node_list(self.patterns, transform),
            kwd_patterns=_transform_node_list(self.kwd_patterns, transform),
        )

@dataclass
class MatchStar(Node):
    name: Optional[str] = None

@dataclass
class MatchAs(Node):
    pattern: Optional[Node] = None
    name: Optional[str] = None

    def visit_children(self, visit) -> None:
        if self.pattern is not None:
            visit(self.pattern)

    def transform_children(self, transform) -> MatchAs:
        return self.transform_fields(
            pattern=transform(self.pattern) if self.pattern is not None else None,
        )

@dataclass
class MatchOr(Node):
    patterns: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for p in self.patterns:
            visit(p)

    def transform_children(self, transform) -> MatchOr:
        return self.transform_fields(
            patterns=_transform_node_list(self.patterns, transform),
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
