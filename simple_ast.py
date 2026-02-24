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


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _transform_node_list(lst: list, transform) -> tuple[list, bool]:
    """Transform a list of nodes; returns (new_list, changed).

    Node items replaced by None are removed from the output list.
    Non-Node items are passed through unchanged.
    """
    new_list = []
    changed = False
    for item in lst:
        if isinstance(item, Node):
            new_item = transform(item)
            if new_item is None:
                changed = True
                continue
            if new_item is not item:
                changed = True
            new_list.append(new_item)
        else:
            new_list.append(item)
    return new_list, changed


# ═══════════════════════════════════════════════════════════════════════════════
# Base
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Node:
    """Base class for all simplified AST nodes."""
    lineno: Optional[int] = field(default=None, repr=False, compare=False)
    col_offset: Optional[int] = field(default=None, repr=False, compare=False)
    end_lineno: Optional[int] = field(default=None, repr=False, compare=False)
    end_col_offset: Optional[int] = field(default=None, repr=False, compare=False)

    def visit_children(self, visit) -> None:
        """Visit all direct child nodes. Override in subclasses with children."""
        pass

    def transform_children(self, transform) -> Node:
        """Transform all direct child nodes in place. Override in subclasses."""
        return self


_LOC_FIELDS = frozenset(("lineno", "col_offset", "end_lineno", "end_col_offset"))


def locate(src: ast.AST, dst: Node) -> Node:
    """Copy source location from a CPython AST node to a simplified node."""
    for attr in _LOC_FIELDS:
        if hasattr(src, attr):
            setattr(dst, attr, getattr(src, attr))
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
        left = transform(self.left)
        if left is not self.left:
            self.left = left
        right = transform(self.right)
        if right is not self.right:
            self.right = right
        return self


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
        op = transform(self.operand)
        if op is not self.operand:
            self.operand = op
        return self


@dataclass
class AugAssign(Node):
    """Base for augmented-assignment operators (+=, -=, …)."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.target)
        visit(self.value)

    def transform_children(self, transform) -> AugAssign:
        t = transform(self.target)
        if t is not self.target:
            self.target = t
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self


@dataclass
class AttrNode(Node):
    """Base for attribute-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    attr: str = ""

    def visit_children(self, visit) -> None:
        visit(self.object)

    def transform_children(self, transform) -> AttrNode:
        obj = transform(self.object)
        if obj is not self.object:
            self.object = obj
        return self


@dataclass
class SubscriptNode(Node):
    """Base for subscript-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    index: Node = None   # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.object)
        visit(self.index)

    def transform_children(self, transform) -> SubscriptNode:
        obj = transform(self.object)
        if obj is not self.object:
            self.object = obj
        idx = transform(self.index)
        if idx is not self.index:
            self.index = idx
        return self


@dataclass
class ElementsLiteral(Node):
    """Base for collection literals that hold a flat element list."""
    elements: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for elem in self.elements:
            visit(elem)

    def transform_children(self, transform) -> ElementsLiteral:
        new_elems, changed = _transform_node_list(self.elements, transform)
        if changed:
            self.elements = new_elems
        return self


@dataclass
class PatternList(Node):
    """Base for destructuring assignment targets (tuple/list patterns)."""
    targets: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for t in self.targets:
            visit(t)

    def transform_children(self, transform) -> PatternList:
        new_targets, changed = _transform_node_list(self.targets, transform)
        if changed:
            self.targets = new_targets
        return self


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
        elem = transform(self.element)
        if elem is not self.element:
            self.element = elem
        new_clauses, changed = _transform_node_list(self.clauses, transform)
        if changed:
            self.clauses = new_clauses
        return self


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
        test = transform(self.test)
        if test is not self.test:
            self.test = test
        new_body, c1 = _transform_node_list(self.body, transform)
        if c1:
            self.body = new_body
        new_orelse, c2 = _transform_node_list(self.orelse, transform)
        if c2:
            self.orelse = new_orelse
        return self


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
        new_body, changed = _transform_node_list(self.body, transform)
        if changed:
            self.body = new_body
        return self

@dataclass
class Interactive(Node):
    body: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for child in self.body:
            visit(child)

    def transform_children(self, transform) -> Interactive:
        new_body, changed = _transform_node_list(self.body, transform)
        if changed:
            self.body = new_body
        return self

@dataclass
class Expression(Node):
    body: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.body)

    def transform_children(self, transform) -> Expression:
        body = transform(self.body)
        if body is not self.body:
            self.body = body
        return self


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
        for k in self.keys:
            if k is not None:
                visit(k)
        for v in self.values:
            visit(v)

    def transform_children(self, transform) -> DictLiteral:
        new_keys = []
        keys_changed = False
        for k in self.keys:
            if k is not None:
                nk = transform(k)
                if nk is not k:
                    keys_changed = True
                new_keys.append(nk)
            else:
                new_keys.append(None)
        if keys_changed:
            self.keys = new_keys
        new_vals, vchanged = _transform_node_list(self.values, transform)
        if vchanged:
            self.values = new_vals
        return self


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
        new_parts, changed = _transform_node_list(self.parts, transform)
        if changed:
            self.parts = new_parts
        return self

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
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        if self.format_spec is not None:
            fs = transform(self.format_spec)
            if fs is not self.format_spec:
                self.format_spec = fs
        return self


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
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self

@dataclass
class StarTarget(Node):
    """*name in an assignment target — catch-all."""
    target: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.target)

    def transform_children(self, transform) -> StarTarget:
        t = transform(self.target)
        if t is not self.target:
            self.target = t
        return self


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
        new_cmps, changed = _transform_node_list(self.comparisons, transform)
        if changed:
            self.comparisons = new_cmps
        return self


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
        func = transform(self.func)
        if func is not self.func:
            self.func = func
        new_args, c1 = _transform_node_list(self.args, transform)
        if c1:
            self.args = new_args
        new_kwargs, c2 = _transform_node_list(self.kwargs, transform)
        if c2:
            self.kwargs = new_kwargs
        return self

@dataclass
class Keyword(Node):
    """A single keyword argument. name=None means **splat."""
    name: Optional[str] = None
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> Keyword:
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self

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
        test = transform(self.test)
        if test is not self.test:
            self.test = test
        body = transform(self.body)
        if body is not self.body:
            self.body = body
        orelse = transform(self.orelse)
        if orelse is not self.orelse:
            self.orelse = orelse
        return self

@dataclass
class NamedExpr(Node):
    """:= walrus operator."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.target)
        visit(self.value)

    def transform_children(self, transform) -> NamedExpr:
        t = transform(self.target)
        if t is not self.target:
            self.target = t
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self

@dataclass
class Lambda(Node):
    params: Params = None  # type: ignore[assignment]
    body: Node = None      # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.params)
        visit(self.body)

    def transform_children(self, transform) -> Lambda:
        params = transform(self.params)
        if params is not self.params:
            self.params = params
        body = transform(self.body)
        if body is not self.body:
            self.body = body
        return self

@dataclass
class Yield(Node):
    value: Optional[Node] = None

    def visit_children(self, visit) -> None:
        if self.value is not None:
            visit(self.value)

    def transform_children(self, transform) -> Yield:
        if self.value is not None:
            v = transform(self.value)
            if v is not self.value:
                self.value = v
        return self

@dataclass
class YieldFrom(Node):
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> YieldFrom:
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self

@dataclass
class Await(Node):
    value: Node = None  # type: ignore[assignment]

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> Await:
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self

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
        if self.lower is not None:
            lower = transform(self.lower)
            if lower is not self.lower:
                self.lower = lower
        if self.upper is not None:
            upper = transform(self.upper)
            if upper is not self.upper:
                self.upper = upper
        if self.step is not None:
            step = transform(self.step)
            if step is not self.step:
                self.step = step
        return self


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
        t = transform(self.target)
        if t is not self.target:
            self.target = t
        it = transform(self.iterable)
        if it is not self.iterable:
            self.iterable = it
        new_filters, changed = _transform_node_list(self.filters, transform)
        if changed:
            self.filters = new_filters
        return self

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
        k = transform(self.key)
        if k is not self.key:
            self.key = k
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        new_clauses, changed = _transform_node_list(self.clauses, transform)
        if changed:
            self.clauses = new_clauses
        return self

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
        if self.annotation is not None:
            ann = transform(self.annotation)
            if ann is not self.annotation:
                self.annotation = ann
        if self.default is not None:
            dflt = transform(self.default)
            if dflt is not self.default:
                self.default = dflt
        return self

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
        new_params, changed = _transform_node_list(self.params, transform)
        if changed:
            self.params = new_params
        return self


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
        new_targets, c1 = _transform_node_list(self.targets, transform)
        if c1:
            self.targets = new_targets
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self

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
        t = transform(self.target)
        if t is not self.target:
            self.target = t
        ann = transform(self.annotation)
        if ann is not self.annotation:
            self.annotation = ann
        if self.value is not None:
            v = transform(self.value)
            if v is not self.value:
                self.value = v
        return self

@dataclass
class Return(Node):
    value: Optional[Node] = None

    def visit_children(self, visit) -> None:
        if self.value is not None:
            visit(self.value)

    def transform_children(self, transform) -> Return:
        if self.value is not None:
            v = transform(self.value)
            if v is not self.value:
                self.value = v
        return self

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
        if self.exc is not None:
            exc = transform(self.exc)
            if exc is not self.exc:
                self.exc = exc
        if self.cause is not None:
            cause = transform(self.cause)
            if cause is not self.cause:
                self.cause = cause
        return self

@dataclass
class Assert(Node):
    test: Node = None  # type: ignore[assignment]
    msg: Optional[Node] = None

    def visit_children(self, visit) -> None:
        visit(self.test)
        if self.msg is not None:
            visit(self.msg)

    def transform_children(self, transform) -> Assert:
        test = transform(self.test)
        if test is not self.test:
            self.test = test
        if self.msg is not None:
            msg = transform(self.msg)
            if msg is not self.msg:
                self.msg = msg
        return self

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
        t = transform(self.target)
        if t is not self.target:
            self.target = t
        it = transform(self.iterable)
        if it is not self.iterable:
            self.iterable = it
        new_body, c1 = _transform_node_list(self.body, transform)
        if c1:
            self.body = new_body
        new_orelse, c2 = _transform_node_list(self.orelse, transform)
        if c2:
            self.orelse = new_orelse
        return self

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
        new_items = []
        items_changed = False
        for ctx, var in self.items:
            new_ctx = transform(ctx)
            if new_ctx is not ctx:
                items_changed = True
            new_var = transform(var) if var is not None else None
            if new_var is not var:
                items_changed = True
            new_items.append((new_ctx, new_var))
        if items_changed:
            self.items = new_items
        new_body, changed = _transform_node_list(self.body, transform)
        if changed:
            self.body = new_body
        return self

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
        new_body, c1 = _transform_node_list(self.body, transform)
        if c1:
            self.body = new_body
        new_handlers, c2 = _transform_node_list(self.handlers, transform)
        if c2:
            self.handlers = new_handlers
        new_orelse, c3 = _transform_node_list(self.orelse, transform)
        if c3:
            self.orelse = new_orelse
        new_finalbody, c4 = _transform_node_list(self.finalbody, transform)
        if c4:
            self.finalbody = new_finalbody
        return self

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
        if self.type is not None:
            t = transform(self.type)
            if t is not self.type:
                self.type = t
        new_body, changed = _transform_node_list(self.body, transform)
        if changed:
            self.body = new_body
        return self


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
        params = transform(self.params)
        if params is not self.params:
            self.params = params
        new_body, c1 = _transform_node_list(self.body, transform)
        if c1:
            self.body = new_body
        new_decs, c2 = _transform_node_list(self.decorators, transform)
        if c2:
            self.decorators = new_decs
        if self.returns is not None:
            ret = transform(self.returns)
            if ret is not self.returns:
                self.returns = ret
        new_tps, c3 = _transform_node_list(self.type_params, transform)
        if c3:
            self.type_params = new_tps
        return self

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
        new_bases, c1 = _transform_node_list(self.bases, transform)
        if c1:
            self.bases = new_bases
        new_kws, c2 = _transform_node_list(self.keywords, transform)
        if c2:
            self.keywords = new_kws
        new_body, c3 = _transform_node_list(self.body, transform)
        if c3:
            self.body = new_body
        new_decs, c4 = _transform_node_list(self.decorators, transform)
        if c4:
            self.decorators = new_decs
        new_tps, c5 = _transform_node_list(self.type_params, transform)
        if c5:
            self.type_params = new_tps
        return self

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
        n = transform(self.name)
        if n is not self.name:
            self.name = n
        new_tps, changed = _transform_node_list(self.type_params, transform)
        if changed:
            self.type_params = new_tps
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self


# --- Type params (3.12+) ---

@dataclass
class TypeVar(Node):
    name: str = ""
    bound: Optional[Node] = None

    def visit_children(self, visit) -> None:
        if self.bound is not None:
            visit(self.bound)

    def transform_children(self, transform) -> TypeVar:
        if self.bound is not None:
            b = transform(self.bound)
            if b is not self.bound:
                self.bound = b
        return self

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
        s = transform(self.subject)
        if s is not self.subject:
            self.subject = s
        new_cases, changed = _transform_node_list(self.cases, transform)
        if changed:
            self.cases = new_cases
        return self

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
        p = transform(self.pattern)
        if p is not self.pattern:
            self.pattern = p
        if self.guard is not None:
            g = transform(self.guard)
            if g is not self.guard:
                self.guard = g
        new_body, changed = _transform_node_list(self.body, transform)
        if changed:
            self.body = new_body
        return self

@dataclass
class MatchLiteral(Node):
    value: Node = None  # type: ignore[assignment]
    use_is: bool = False

    def visit_children(self, visit) -> None:
        visit(self.value)

    def transform_children(self, transform) -> MatchLiteral:
        v = transform(self.value)
        if v is not self.value:
            self.value = v
        return self

@dataclass
class MatchSequence(Node):
    patterns: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for p in self.patterns:
            visit(p)

    def transform_children(self, transform) -> MatchSequence:
        new_patterns, changed = _transform_node_list(self.patterns, transform)
        if changed:
            self.patterns = new_patterns
        return self

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
        new_keys, c1 = _transform_node_list(self.keys, transform)
        if c1:
            self.keys = new_keys
        new_patterns, c2 = _transform_node_list(self.patterns, transform)
        if c2:
            self.patterns = new_patterns
        return self

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
        c = transform(self.cls)
        if c is not self.cls:
            self.cls = c
        new_patterns, c1 = _transform_node_list(self.patterns, transform)
        if c1:
            self.patterns = new_patterns
        new_kwd_patterns, c2 = _transform_node_list(self.kwd_patterns, transform)
        if c2:
            self.kwd_patterns = new_kwd_patterns
        return self

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
        if self.pattern is not None:
            p = transform(self.pattern)
            if p is not self.pattern:
                self.pattern = p
        return self

@dataclass
class MatchOr(Node):
    patterns: list[Node] = field(default_factory=list)

    def visit_children(self, visit) -> None:
        for p in self.patterns:
            visit(p)

    def transform_children(self, transform) -> MatchOr:
        new_patterns, changed = _transform_node_list(self.patterns, transform)
        if changed:
            self.patterns = new_patterns
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# Transformer: ast → simple_ast
#
# Each CPython AST type maps to a bare converter function via VISITORS dict.
# visit(node) does a direct hash lookup by type(node).
# ═══════════════════════════════════════════════════════════════════════════════

def visit(node: ast.AST) -> Node:
    """Convert a single CPython AST node. Dispatches by type(node)."""
    converter = VISITORS.get(type(node))
    if converter is None:
        raise NotImplementedError(
            f"No handler for {node.__class__.__name__}: {ast.dump(node)}"
        )
    return converter(node)


def visit_list(nodes: list[ast.AST]) -> list[Node]:
    """Convert a list of CPython AST nodes, flattening any that return lists."""
    result = []
    for n in nodes:
        v = visit(n)
        if isinstance(v, list):
            result.extend(v)
        else:
            result.append(v)
    return result


# ── Modules ──────────────────────────────────────────────────────────────────

def convert_module(node: ast.Module) -> Module:
    return locate(node, Module(body=visit_list(node.body)))

def convert_interactive(node: ast.Interactive) -> Interactive:
    return locate(node, Interactive(body=visit_list(node.body)))

def convert_expression(node: ast.Expression) -> Expression:
    return locate(node, Expression(body=visit(node.body)))


# ── Literals ─────────────────────────────────────────────────────────────────

_CONSTANT_TYPE_MAP: dict[type, type] = {
    bool: BoolLiteral,   # must be before int in isinstance checks, but here we use exact type
    int: IntLiteral,
    float: FloatLiteral,
    complex: ComplexLiteral,
    str: StringLiteral,
    bytes: BytesLiteral,
}

def convert_constant(node: ast.Constant) -> Node:
    v = node.value
    if v is None:
        return locate(node, NoneLiteral())
    if v is ...:
        return locate(node, EllipsisLiteral())
    # bool must be checked before int (bool is a subclass of int)
    if isinstance(v, bool):
        return locate(node, BoolLiteral(value=v))
    cls = _CONSTANT_TYPE_MAP.get(type(v))
    if cls is not None:
        return locate(node, cls(value=v))
    raise NotImplementedError(f"Unknown constant type: {type(v)} ({v!r})")


def convert_joined_str(node: ast.JoinedStr) -> FString:
    return locate(node, FString(parts=visit_list(node.values)))


_CONVERSION_MAP = {-1: None, ord("s"): "s", ord("r"): "r", ord("a"): "a"}

def convert_formatted_value(node: ast.FormattedValue) -> FormattedExpr:
    return locate(node, FormattedExpr(
        value=visit(node.value),
        conversion=_CONVERSION_MAP.get(node.conversion),
        format_spec=visit(node.format_spec) if node.format_spec else None,
    ))


# ── Collections with context ────────────────────────────────────────────────

_LIST_CTX = {ast.Store: lambda elts: ListPattern(targets=elts)}
_TUPLE_CTX = {ast.Store: lambda elts: TuplePattern(targets=elts)}

def convert_list(node: ast.List) -> Node:
    elts = visit_list(node.elts)
    factory = _LIST_CTX.get(type(node.ctx))
    return locate(node, factory(elts) if factory else ListLiteral(elements=elts))

def convert_tuple(node: ast.Tuple) -> Node:
    elts = visit_list(node.elts)
    factory = _TUPLE_CTX.get(type(node.ctx))
    return locate(node, factory(elts) if factory else TupleLiteral(elements=elts))

def convert_set(node: ast.Set) -> SetLiteral:
    return locate(node, SetLiteral(elements=visit_list(node.elts)))

def convert_dict(node: ast.Dict) -> DictLiteral:
    return locate(node, DictLiteral(
        keys=[visit(k) if k else None for k in node.keys],
        values=visit_list(node.values),
    ))


# ── Names / Attributes / Subscripts ─────────────────────────────────────────

_NAME_CTX = {
    ast.Load: lambda id: LoadName(name=id),
    ast.Store: lambda id: StoreName(name=id),
    ast.Del: lambda id: DeleteName(name=id),
}

def convert_name(node: ast.Name) -> Node:
    return locate(node, _NAME_CTX[type(node.ctx)](node.id))


_ATTR_CTX = {
    ast.Load: lambda obj, attr: LoadAttr(object=obj, attr=attr),
    ast.Store: lambda obj, attr: StoreAttr(object=obj, attr=attr),
    ast.Del: lambda obj, attr: DeleteAttr(object=obj, attr=attr),
}

def convert_attribute(node: ast.Attribute) -> Node:
    return locate(node, _ATTR_CTX[type(node.ctx)](visit(node.value), node.attr))


_SUBSCRIPT_CTX = {
    ast.Load: lambda obj, idx: LoadSubscript(object=obj, index=idx),
    ast.Store: lambda obj, idx: StoreSubscript(object=obj, index=idx),
    ast.Del: lambda obj, idx: DeleteSubscript(object=obj, index=idx),
}

def convert_subscript(node: ast.Subscript) -> Node:
    return locate(node, _SUBSCRIPT_CTX[type(node.ctx)](visit(node.value), visit(node.slice)))


_STARRED_CTX = {
    ast.Store: lambda val: StarTarget(target=val),
}

def convert_starred(node: ast.Starred) -> Node:
    val = visit(node.value)
    factory = _STARRED_CTX.get(type(node.ctx))
    return locate(node, factory(val) if factory else StarUnpack(value=val))


def convert_slice(node: ast.Slice) -> Slice:
    return locate(node, Slice(
        lower=visit(node.lower) if node.lower else None,
        upper=visit(node.upper) if node.upper else None,
        step=visit(node.step) if node.step else None,
    ))


# ── Binary Operators ─────────────────────────────────────────────────────────

BINOP_CLASS: dict[type, type] = {
    ast.Add: Add, ast.Sub: Sub, ast.Mult: Mult, ast.Div: Div,
    ast.FloorDiv: FloorDiv, ast.Mod: Mod, ast.Pow: Pow, ast.MatMult: MatMult,
    ast.LShift: LShift, ast.RShift: RShift,
    ast.BitOr: BitOr, ast.BitXor: BitXor, ast.BitAnd: BitAnd,
}

def convert_binop(node: ast.BinOp) -> Node:
    return locate(node, BINOP_CLASS[type(node.op)](
        left=visit(node.left), right=visit(node.right),
    ))


# ── Unary Operators ──────────────────────────────────────────────────────────

UNARYOP_CLASS: dict[type, type] = {
    ast.UAdd: UnaryPlus, ast.USub: Negate, ast.Not: Not, ast.Invert: Invert,
}

def convert_unaryop(node: ast.UnaryOp) -> Node:
    return locate(node, UNARYOP_CLASS[type(node.op)](operand=visit(node.operand)))


# ── Boolean Operators ────────────────────────────────────────────────────────

BOOLOP_CLASS: dict[type, type] = {ast.And: And, ast.Or: Or}

def convert_boolop(node: ast.BoolOp) -> Node:
    cls = BOOLOP_CLASS[type(node.op)]
    values = [visit(v) for v in node.values]
    result = values[0]
    for v in values[1:]:
        result = locate(node, cls(left=result, right=v))
    return result


# ── Comparison Operators ─────────────────────────────────────────────────────

COMPARISON_CLASS: dict[type, type] = {
    ast.Eq: Eq, ast.NotEq: NotEq, ast.Lt: Lt, ast.LtE: LtE,
    ast.Gt: Gt, ast.GtE: GtE, ast.Is: Is, ast.IsNot: IsNot,
    ast.In: In, ast.NotIn: NotIn,
}

def convert_compare(node: ast.Compare) -> Node:
    if len(node.ops) == 1:
        return locate(node, COMPARISON_CLASS[type(node.ops[0])](
            left=visit(node.left), right=visit(node.comparators[0]),
        ))
    all_operands = [visit(node.left)] + [visit(c) for c in node.comparators]
    comparisons = [
        COMPARISON_CLASS[type(op)](left=all_operands[i], right=all_operands[i + 1])
        for i, op in enumerate(node.ops)
    ]
    return locate(node, CompareChain(comparisons=comparisons))


# ── Augmented Assignment ─────────────────────────────────────────────────────

AUGASSIGN_CLASS: dict[type, type] = {
    ast.Add: AddAssign, ast.Sub: SubAssign, ast.Mult: MultAssign,
    ast.Div: DivAssign, ast.FloorDiv: FloorDivAssign, ast.Mod: ModAssign,
    ast.Pow: PowAssign, ast.MatMult: MatMultAssign,
    ast.LShift: LShiftAssign, ast.RShift: RShiftAssign,
    ast.BitOr: BitOrAssign, ast.BitXor: BitXorAssign, ast.BitAnd: BitAndAssign,
}

def convert_augassign(node: ast.AugAssign) -> Node:
    return locate(node, AUGASSIGN_CLASS[type(node.op)](
        target=visit(node.target), value=visit(node.value),
    ))


# ── Expressions ──────────────────────────────────────────────────────────────

def convert_call(node: ast.Call) -> Call:
    kwargs = [
        locate(kw, Keyword(name=kw.arg, value=visit(kw.value)))
        for kw in node.keywords
    ]
    return locate(node, Call(
        func=visit(node.func), args=visit_list(node.args), kwargs=kwargs,
    ))

def convert_ifexp(node: ast.IfExp) -> IfExpr:
    return locate(node, IfExpr(
        test=visit(node.test), body=visit(node.body), orelse=visit(node.orelse),
    ))

def convert_namedexpr(node: ast.NamedExpr) -> NamedExpr:
    return locate(node, NamedExpr(target=visit(node.target), value=visit(node.value)))

def convert_lambda(node: ast.Lambda) -> Lambda:
    return locate(node, Lambda(params=convert_arguments(node.args), body=visit(node.body)))

def convert_yield(node: ast.Yield) -> Yield:
    return locate(node, Yield(value=visit(node.value) if node.value else None))

def convert_yieldfrom(node: ast.YieldFrom) -> YieldFrom:
    return locate(node, YieldFrom(value=visit(node.value)))

def convert_await(node: ast.Await) -> Await:
    return locate(node, Await(value=visit(node.value)))


# ── Comprehensions ───────────────────────────────────────────────────────────

def convert_generators(generators: list[ast.comprehension]) -> list[ForClause]:
    return [
        ForClause(
            target=visit(gen.target), iterable=visit(gen.iter),
            filters=[visit(f) for f in gen.ifs], is_async=bool(gen.is_async),
        )
        for gen in generators
    ]

def convert_listcomp(node: ast.ListComp) -> ListComp:
    return locate(node, ListComp(
        element=visit(node.elt), clauses=convert_generators(node.generators),
    ))

def convert_setcomp(node: ast.SetComp) -> SetComp:
    return locate(node, SetComp(
        element=visit(node.elt), clauses=convert_generators(node.generators),
    ))

def convert_dictcomp(node: ast.DictComp) -> DictComp:
    return locate(node, DictComp(
        key=visit(node.key), value=visit(node.value),
        clauses=convert_generators(node.generators),
    ))

def convert_generatorexp(node: ast.GeneratorExp) -> GeneratorExpr:
    return locate(node, GeneratorExpr(
        element=visit(node.elt), clauses=convert_generators(node.generators),
    ))


# ── Parameters ───────────────────────────────────────────────────────────────

def convert_arguments(args: ast.arguments) -> Params:
    params: list[Param] = []

    for a in args.posonlyargs:
        params.append(PosOnlyParam(
            name=a.arg,
            annotation=visit(a.annotation) if a.annotation else None,
        ))

    for a in args.args:
        params.append(PosOrKwParam(
            name=a.arg,
            annotation=visit(a.annotation) if a.annotation else None,
        ))

    # defaults right-align to the combined posonlyargs + args
    all_positional = params[:]
    n_defaults = len(args.defaults)
    if n_defaults:
        defaults = [visit(d) for d in args.defaults]
        for i, d in enumerate(defaults):
            all_positional[len(all_positional) - n_defaults + i].default = d

    if args.vararg:
        params.append(VarPositional(
            name=args.vararg.arg,
            annotation=visit(args.vararg.annotation) if args.vararg.annotation else None,
        ))

    for i, a in enumerate(args.kwonlyargs):
        default = None
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = visit(args.kw_defaults[i])
        params.append(KwOnlyParam(
            name=a.arg,
            annotation=visit(a.annotation) if a.annotation else None,
            default=default,
        ))

    if args.kwarg:
        params.append(VarKeyword(
            name=args.kwarg.arg,
            annotation=visit(args.kwarg.annotation) if args.kwarg.annotation else None,
        ))

    return Params(params=params)


# ── Statements ───────────────────────────────────────────────────────────────

def convert_expr_stmt(node: ast.Expr) -> Node:
    """No ExprStmt wrapper — return the expression directly."""
    return visit(node.value)

def convert_assign(node: ast.Assign) -> Assign:
    return locate(node, Assign(targets=visit_list(node.targets), value=visit(node.value)))

def convert_annassign(node: ast.AnnAssign) -> AnnAssign:
    return locate(node, AnnAssign(
        target=visit(node.target), annotation=visit(node.annotation),
        value=visit(node.value) if node.value else None, simple=bool(node.simple),
    ))

def convert_delete(node: ast.Delete) -> list[Node]:
    return [visit(t) for t in node.targets]

def convert_return(node: ast.Return) -> Return:
    return locate(node, Return(value=visit(node.value) if node.value else None))

def convert_pass(node: ast.Pass) -> Pass:
    return locate(node, Pass())

def convert_break(node: ast.Break) -> Break:
    return locate(node, Break())

def convert_continue(node: ast.Continue) -> Continue:
    return locate(node, Continue())

def convert_raise(node: ast.Raise) -> Raise:
    return locate(node, Raise(
        exc=visit(node.exc) if node.exc else None,
        cause=visit(node.cause) if node.cause else None,
    ))

def convert_assert(node: ast.Assert) -> Assert:
    return locate(node, Assert(
        test=visit(node.test), msg=visit(node.msg) if node.msg else None,
    ))

def convert_global(node: ast.Global) -> Global:
    return locate(node, Global(names=list(node.names)))

def convert_nonlocal(node: ast.Nonlocal) -> Nonlocal:
    return locate(node, Nonlocal(names=list(node.names)))


# --- Imports (flattened) ---

def convert_import(node: ast.Import) -> list[Import]:
    return [locate(node, Import(module=a.name, alias=a.asname)) for a in node.names]

def convert_importfrom(node: ast.ImportFrom) -> list[ImportFrom]:
    return [
        locate(node, ImportFrom(
            module=node.module, name=a.name, alias=a.asname, level=node.level,
        ))
        for a in node.names
    ]


# --- Compound statements ---

def convert_if(node: ast.If) -> If:
    return locate(node, If(
        test=visit(node.test), body=visit_list(node.body),
        orelse=visit_list(node.orelse),
    ))

def convert_while(node: ast.While) -> While:
    return locate(node, While(
        test=visit(node.test), body=visit_list(node.body),
        orelse=visit_list(node.orelse),
    ))

def convert_for(node: ast.For) -> For:
    return locate(node, For(
        target=visit(node.target), iterable=visit(node.iter),
        body=visit_list(node.body), orelse=visit_list(node.orelse), is_async=False,
    ))

def convert_asyncfor(node: ast.AsyncFor) -> For:
    return locate(node, For(
        target=visit(node.target), iterable=visit(node.iter),
        body=visit_list(node.body), orelse=visit_list(node.orelse), is_async=True,
    ))

def _convert_with_items(node) -> list[tuple[Node, Optional[Node]]]:
    return [
        (visit(item.context_expr), visit(item.optional_vars) if item.optional_vars else None)
        for item in node.items
    ]

def convert_with(node: ast.With) -> With:
    return locate(node, With(
        items=_convert_with_items(node), body=visit_list(node.body), is_async=False,
    ))

def convert_asyncwith(node: ast.AsyncWith) -> With:
    return locate(node, With(
        items=_convert_with_items(node), body=visit_list(node.body), is_async=True,
    ))

def _convert_handler(node: ast.ExceptHandler) -> ExceptHandler:
    return locate(node, ExceptHandler(
        type=visit(node.type) if node.type else None,
        name=node.name, body=visit_list(node.body),
    ))

def convert_try(node: ast.Try) -> Try:
    return locate(node, Try(
        body=visit_list(node.body),
        handlers=[_convert_handler(h) for h in node.handlers],
        orelse=visit_list(node.orelse), finalbody=visit_list(node.finalbody),
        is_star=False,
    ))

def convert_trystar(node: ast.TryStar) -> Try:
    return locate(node, Try(
        body=visit_list(node.body),
        handlers=[_convert_handler(h) for h in node.handlers],
        orelse=visit_list(node.orelse), finalbody=visit_list(node.finalbody),
        is_star=True,
    ))


# --- Definitions ---

def convert_functiondef(node: ast.FunctionDef) -> FunctionDef:
    type_params = visit_list(node.type_params) if hasattr(node, "type_params") else []
    return locate(node, FunctionDef(
        name=node.name, params=convert_arguments(node.args),
        body=visit_list(node.body), decorators=visit_list(node.decorator_list),
        returns=visit(node.returns) if node.returns else None,
        is_async=False, type_params=type_params,
    ))

def convert_asyncfunctiondef(node: ast.AsyncFunctionDef) -> FunctionDef:
    type_params = visit_list(node.type_params) if hasattr(node, "type_params") else []
    return locate(node, FunctionDef(
        name=node.name, params=convert_arguments(node.args),
        body=visit_list(node.body), decorators=visit_list(node.decorator_list),
        returns=visit(node.returns) if node.returns else None,
        is_async=True, type_params=type_params,
    ))

def convert_classdef(node: ast.ClassDef) -> ClassDef:
    kwargs = [locate(kw, Keyword(name=kw.arg, value=visit(kw.value))) for kw in node.keywords]
    type_params = visit_list(node.type_params) if hasattr(node, "type_params") else []
    return locate(node, ClassDef(
        name=node.name, bases=visit_list(node.bases), keywords=kwargs,
        body=visit_list(node.body), decorators=visit_list(node.decorator_list),
        type_params=type_params,
    ))

def convert_typealias(node: ast.TypeAlias) -> TypeAlias:
    return locate(node, TypeAlias(
        name=visit(node.name), type_params=visit_list(node.type_params),
        value=visit(node.value),
    ))


# --- Type params ---

def convert_typevar(node: ast.TypeVar) -> TypeVar:
    return locate(node, TypeVar(name=node.name, bound=visit(node.bound) if node.bound else None))

def convert_paramspec(node: ast.ParamSpec) -> ParamSpec:
    return locate(node, ParamSpec(name=node.name))

def convert_typevartuple(node: ast.TypeVarTuple) -> TypeVarTuple:
    return locate(node, TypeVarTuple(name=node.name))


# ── Pattern Matching ─────────────────────────────────────────────────────────

def convert_match(node: ast.Match) -> Match:
    return locate(node, Match(
        subject=visit(node.subject),
        cases=[_convert_match_case(c) for c in node.cases],
    ))

def _convert_match_case(node: ast.match_case) -> MatchCase:
    return MatchCase(
        pattern=visit(node.pattern),
        guard=visit(node.guard) if node.guard else None,
        body=visit_list(node.body),
    )

def convert_matchvalue(node: ast.MatchValue) -> MatchLiteral:
    return locate(node, MatchLiteral(value=visit(node.value), use_is=False))

def convert_matchsingleton(node: ast.MatchSingleton) -> MatchLiteral:
    v = node.value
    if v is None:
        val = NoneLiteral()
    elif isinstance(v, bool):
        val = BoolLiteral(value=v)
    else:
        val = convert_constant(ast.Constant(value=v))
    return locate(node, MatchLiteral(value=val, use_is=True))

def convert_matchsequence(node: ast.MatchSequence) -> MatchSequence:
    return locate(node, MatchSequence(patterns=visit_list(node.patterns)))

def convert_matchmapping(node: ast.MatchMapping) -> MatchMapping:
    return locate(node, MatchMapping(
        keys=visit_list(node.keys), patterns=visit_list(node.patterns), rest=node.rest,
    ))

def convert_matchclass(node: ast.MatchClass) -> MatchClass:
    return locate(node, MatchClass(
        cls=visit(node.cls), patterns=visit_list(node.patterns),
        kwd_attrs=list(node.kwd_attrs), kwd_patterns=visit_list(node.kwd_patterns),
    ))

def convert_matchstar(node: ast.MatchStar) -> MatchStar:
    return locate(node, MatchStar(name=node.name))

def convert_matchas(node: ast.MatchAs) -> MatchAs:
    return locate(node, MatchAs(
        pattern=visit(node.pattern) if node.pattern else None, name=node.name,
    ))

def convert_matchor(node: ast.MatchOr) -> MatchOr:
    return locate(node, MatchOr(patterns=visit_list(node.patterns)))


# ═══════════════════════════════════════════════════════════════════════════════
# VISITORS dispatch table: ast type → converter function
# ═══════════════════════════════════════════════════════════════════════════════

VISITORS: dict[type, Any] = {
    # Modules
    ast.Module: convert_module,
    ast.Interactive: convert_interactive,
    ast.Expression: convert_expression,
    # Literals
    ast.Constant: convert_constant,
    ast.JoinedStr: convert_joined_str,
    ast.FormattedValue: convert_formatted_value,
    # Collections
    ast.List: convert_list,
    ast.Tuple: convert_tuple,
    ast.Set: convert_set,
    ast.Dict: convert_dict,
    # Names / Attributes / Subscripts
    ast.Name: convert_name,
    ast.Attribute: convert_attribute,
    ast.Subscript: convert_subscript,
    ast.Starred: convert_starred,
    ast.Slice: convert_slice,
    # Operators
    ast.BinOp: convert_binop,
    ast.UnaryOp: convert_unaryop,
    ast.BoolOp: convert_boolop,
    ast.Compare: convert_compare,
    ast.AugAssign: convert_augassign,
    # Expressions
    ast.Call: convert_call,
    ast.IfExp: convert_ifexp,
    ast.NamedExpr: convert_namedexpr,
    ast.Lambda: convert_lambda,
    ast.Yield: convert_yield,
    ast.YieldFrom: convert_yieldfrom,
    ast.Await: convert_await,
    # Comprehensions
    ast.ListComp: convert_listcomp,
    ast.SetComp: convert_setcomp,
    ast.DictComp: convert_dictcomp,
    ast.GeneratorExp: convert_generatorexp,
    # Statements
    ast.Expr: convert_expr_stmt,
    ast.Assign: convert_assign,
    ast.AnnAssign: convert_annassign,
    ast.Delete: convert_delete,
    ast.Return: convert_return,
    ast.Pass: convert_pass,
    ast.Break: convert_break,
    ast.Continue: convert_continue,
    ast.Raise: convert_raise,
    ast.Assert: convert_assert,
    ast.Global: convert_global,
    ast.Nonlocal: convert_nonlocal,
    # Imports
    ast.Import: convert_import,
    ast.ImportFrom: convert_importfrom,
    # Compound statements
    ast.If: convert_if,
    ast.While: convert_while,
    ast.For: convert_for,
    ast.AsyncFor: convert_asyncfor,
    ast.With: convert_with,
    ast.AsyncWith: convert_asyncwith,
    ast.Try: convert_try,
    ast.TryStar: convert_trystar,
    # Definitions
    ast.FunctionDef: convert_functiondef,
    ast.AsyncFunctionDef: convert_asyncfunctiondef,
    ast.ClassDef: convert_classdef,
    ast.TypeAlias: convert_typealias,
    # Type params
    ast.TypeVar: convert_typevar,
    ast.ParamSpec: convert_paramspec,
    ast.TypeVarTuple: convert_typevartuple,
    # Match
    ast.Match: convert_match,
    ast.MatchValue: convert_matchvalue,
    ast.MatchSingleton: convert_matchsingleton,
    ast.MatchSequence: convert_matchsequence,
    ast.MatchMapping: convert_matchmapping,
    ast.MatchClass: convert_matchclass,
    ast.MatchStar: convert_matchstar,
    ast.MatchAs: convert_matchas,
    ast.MatchOr: convert_matchor,
}



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
    return visit(tree)
