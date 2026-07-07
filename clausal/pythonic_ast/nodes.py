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
from fractions import Fraction
from typing import Any, Optional, ClassVar
from .node_class import node_class


__all__ = [
    # Sentinel
    "REMOVED",
    # Helpers
    "locate",
    "dump",
    "simplify",
    # Base
    "Node",
    # Intermediate bases
    "BinOp", "BoolOp", "CmpOp", "UnaryOp", "AugAssign",
    "AttrNode", "SubscriptNode", "ElementsLiteral", "PatternList",
    "ElemComp", "Branch", "Param",
    # Modules
    "Module", "Interactive", "Expression",
    # Literals
    "IntLiteral", "FloatLiteral", "ComplexLiteral", "RationalLiteral",
    "StringLiteral", "BytesLiteral", "BoolLiteral", "NoneLiteral",
    "EllipsisLiteral", "Literal", "literal_value",
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
    "ArithEq", "ArithNeq", "Lt", "LtE", "Gt", "GtE", "Unify", "DoesNotUnify", "Evaluate",
    "StructuralEq", "StructuralNeq",
    "in_", "NotIn",
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
    "Raise", "assertz", "Global", "Nonlocal",
    # Logical / Prolog
    "Predicate",
    # Module-level items (pipeline split)
    "Directive", "ImportFromDirective", "ImportModuleDirective",
    "ModuleDeclaration", "PrivateDeclaration", "TranslationsDirective",
    "BareAtomRefs", "StrictAtomsDeclaration", "OverwritesDeclaration",
    # A10-F016: these were defined but absent from __all__.
    "SpecializeDirective", "EdcgAccDecl", "EdcgPassDecl", "EdcgPredDecl",
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


from .transform import _transform_node_list

# ═══════════════════════════════════════════════════════════════════════════════
# Base
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Node:
    """Base class for all simplified AST nodes."""
    position: Optional[tuple[int, int, int, int]] = field(
        default=None,
        repr=False,
        compare=False
    )

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
                if not isinstance(
                    old_val,
                    (bool, int, float, str, bytes)
                ) or old_val != new_val:
                    return dataclasses.replace(node, **kwargs)
        return node


_LOC_FIELDS = frozenset(("position",))


def locate(
    src: ast.AST,
    dst: Node
) -> Node:
    """Copy source location from a CPython AST node to a simplified node.
    Do not use with Modules, Interactive, or Expression nodes.
    """
    dst.position = (
        src.lineno,
        src.col_offset,
        src.end_lineno,
        src.end_col_offset
    )
    return dst


# ═══════════════════════════════════════════════════════════════════════════════
# Intermediate base classes — carry shared fields and define visit/transform
# ═══════════════════════════════════════════════════════════════════════════════


@node_class
class BinOp(Node):
    """Base for all binary operators: left op right."""
    left: Node = None   # type: ignore[assignment]
    right: Node = None  # type: ignore[assignment]

    def __str__(bin_op):
        return f"{bin_op.left} {bin_op.op} {bin_op.right}"

    def __unify__(self, other, trail):
        """Structural unification: same operator class, operands unified pairwise.

        Operator nodes are structural terms (matched/constructed, not
        evaluated), so a caller's operator term unifies field-wise with a
        clause's, binding variables in either operand.  Without this the C
        ``do_unify`` falls back to ``==``, which never binds a variable, so a
        clause that builds e.g. ``DA + DB`` cannot unify against another
        operator term of the same shape.  The non-semantic ``position`` field
        is ignored (it is ``compare=False``).  Mirrors ``Compound.__unify__``.
        """
        if not isinstance(other, BinOp):
            return NotImplemented
        if type(self) is not type(other):
            return False  # distinct operators (e.g. Add vs Mult) never unify
        from clausal.logic.variables import unify
        mark = trail.mark()
        if unify(self.left, other.left, trail) and unify(self.right, other.right, trail):
            return True
        trail.undo(mark)
        return False


class BoolOp(BinOp):
    """Base for boolean binary operators (And, Or)."""
    pass


class CmpOp(BinOp):
    """Base for comparison operators (ArithEq, Lt, Unify, In, …)."""
    pass


@node_class
class UnaryOp(Node):
    """Base for unary operators."""
    operand: Node = None  # type: ignore[assignment]

    def __str__(unary_op):
        operand_str = f"({unary_op.operand})" if isinstance(unary_op.operand, BinOp) else str(unary_op.operand)
        if unary_op.op.isalpha():
            return f"{unary_op.op} {operand_str}"
        return f"{unary_op.op}{operand_str}"

    def __unify__(self, other, trail):
        """Structural unification of a unary operator term — see ``BinOp``."""
        if not isinstance(other, UnaryOp):
            return NotImplemented
        if type(self) is not type(other):
            return False
        from clausal.logic.variables import unify
        return unify(self.operand, other.operand, trail)



@node_class
class AugAssign(Node):
    """Base for augmented-assignment operators (+=, -=, …)."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]


@node_class
class AttrNode(Node):
    """Base for attribute-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    attr: str = ""

    def __str__(attr_node):
        return f"{attr_node.object}.{attr_node.attr}"


@node_class
class SubscriptNode(Node):
    """Base for subscript-access nodes (Load/Store/Delete)."""
    object: Node = None  # type: ignore[assignment]
    index: Node = None   # type: ignore[assignment]

    def __str__(subscript):
        return f"{subscript.object}[{subscript.index}]"


@node_class
class ElementsLiteral(Node):
    """Base for collection literals that hold a flat element list.

    A10-F016: uses ``@node_class`` (like the sibling ``PatternList``) so
    ``elements`` is a traversed node-list — ``visit_children`` /
    ``transform_children`` descend into it. Plain ``@dataclass`` inherited
    Node's no-op traversal, silently skipping the elements.
    """
    elements: list[Node] = field(default_factory=list)


@node_class
class PatternList(Node):
    """Base for destructuring assignment targets (tuple/list patterns)."""
    targets: list[Node] = field(default_factory=list)


@node_class
class ElemComp(Node):
    """Base for element-based comprehensions (list/set/generator)."""
    element: Node = None  # type: ignore[assignment]
    clauses: list[ForClause] = field(default_factory=list)


@node_class
class Branch(Node):
    """Base for conditional branching statements (if, while)."""
    test: Node = None  # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Modules / Top-level
# ═══════════════════════════════════════════════════════════════════════════════

@node_class
class Module(Node):
    body: list[Node] = field(default_factory=list)


@node_class
class Interactive(Node):
    body: list[Node] = field(default_factory=list)


@node_class
class Expression(Node):
    body: Node = None  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════════════════════
# Literals
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Literal(Node):
    def __str__(literal):
        return str(literal.value)

@node_class
class IntLiteral(Literal):
    value: int = 0

@node_class
class FloatLiteral(Literal):
    value: float = 0.0

@node_class
class ComplexLiteral(Literal):
    value: complex = 0j

@node_class
class RationalLiteral(Literal):
    value: Fraction = Fraction(0)

@node_class
class StringLiteral(Literal):
    value: str = ""

    def __str__(literal):
        return repr(literal.value)

@node_class
class BytesLiteral(Literal):
    value: bytes = b""

@node_class
class BoolLiteral(Literal):
    value: bool = False

@dataclass
class NoneLiteral(Node):
    def __str__(self): return "None"

@dataclass
class EllipsisLiteral(Node):
    def __str__(self): return "..."


def literal_value(x):
    """Unwrap a *Literal node to its native Python value.
    Returns x unchanged if not a Literal."""
    if isinstance(x, Literal):
        return x.value
    if isinstance(x, NoneLiteral):
        return None
    if isinstance(x, EllipsisLiteral):
        return ...
    return x

@dataclass
class ListLiteral(ElementsLiteral):
    def __str__(ll):
        return "[" + ", ".join(str(e) for e in ll.elements) + "]"

@dataclass
class TupleLiteral(ElementsLiteral):
    def __str__(tl):
        if not tl.elements: return "()"
        if len(tl.elements) == 1: return f"({tl.elements[0]},)"
        return "(" + ", ".join(str(e) for e in tl.elements) + ")"

@dataclass
class SetLiteral(ElementsLiteral):
    def __str__(sl):
        return "{" + ", ".join(str(e) for e in sl.elements) + "}"

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

    def __str__(dl):
        pairs = [f"**{v}" if k is None else f"{k}: {v}" for k, v in zip(dl.keys, dl.values)]
        return "{" + ", ".join(pairs) + "}"

    # No __call__, as can't imagine how that would work

# ═══════════════════════════════════════════════════════════════════════════════
# F-strings
# ═══════════════════════════════════════════════════════════════════════════════

@node_class
class FString(Node):
    parts: list[Node] = field(default_factory=list)  # StringLiteral | FormattedExpr

    def __str__(fstring):
        content = "".join(
            p.value if isinstance(p, StringLiteral) else str(p)
            for p in fstring.parts
        )
        return f'f"{content}"'


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

    def __str__(fe):
        conv = f"!{fe.conversion}" if fe.conversion else ""
        if fe.format_spec is not None:
            spec_content = "".join(
                p.value if isinstance(p, StringLiteral) else str(p)
                for p in fe.format_spec.parts
            )
            spec = f":{spec_content}"
        else:
            spec = ""
        return "{" + str(fe.value) + conv + spec + "}"


# ═══════════════════════════════════════════════════════════════════════════════
# Names / Attributes / Subscripts — split by context
# ═══════════════════════════════════════════════════════════════════════════════


class Name(Node):
    def __str__(load_name):
        return load_name.name

# --- Load ---
@node_class
class LoadName(Name):
    name: str = ""

@dataclass
class LoadAttr(AttrNode):
    pass

@dataclass
class LoadSubscript(SubscriptNode):
    pass

# --- Store ---
@node_class
class StoreName(Name):
    name: str = ""

@dataclass
class StoreAttr(AttrNode):
    pass

@dataclass
class StoreSubscript(SubscriptNode):
    pass

# --- Delete ---
@node_class
class DeleteName(Name):
    name: str = ""

@dataclass
class DeleteAttr(AttrNode):
    pass

@dataclass
class DeleteSubscript(SubscriptNode):
    pass

# --- Starred ---
@node_class
class StarUnpack(Node):
    """*expr in a call or literal — unpacking."""
    value: Node = None  # type: ignore[assignment]

    def __str__(star): return f"*{star.value}"


@node_class
class StarTarget(Node):
    """*name in an assignment target — catch-all."""
    target: Node = None  # type: ignore[assignment]

    def __str__(star): return f"*{star.target}"



# ═══════════════════════════════════════════════════════════════════════════════
# Destructuring patterns (assignment targets that are sequences)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TuplePattern(PatternList):
    def __str__(tp): return ", ".join(str(t) for t in tp.targets)

@dataclass
class ListPattern(PatternList):
    def __str__(lp): return "[" + ", ".join(str(t) for t in lp.targets) + "]"


# ═══════════════════════════════════════════════════════════════════════════════
# Binary Operators
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Add(BinOp):
    op: ClassVar = '+'

@dataclass
class Sub(BinOp):
    op: ClassVar = '-'

@dataclass
class Mult(BinOp):
    op: ClassVar = '*'

@dataclass
class Div(BinOp):
    op: ClassVar = '/'

@dataclass
class FloorDiv(BinOp):
    op: ClassVar = '//'

@dataclass
class Mod(BinOp):
    op: ClassVar = '%'

@dataclass
class Pow(BinOp):
    op: ClassVar = '**'

@dataclass
class MatMult(BinOp):
    op: ClassVar = '@'

@dataclass
class LShift(BinOp):
    op: ClassVar = '<<'

@dataclass
class RShift(BinOp):
    op: ClassVar = '>>'

@dataclass
class BitOr(BinOp):
    op: ClassVar = '|'

@dataclass
class BitXor(BinOp):
    op: ClassVar = '^'

@dataclass
class BitAnd(BinOp):
    op: ClassVar = '&'


# ═══════════════════════════════════════════════════════════════════════════════
# Boolean Operators (binary — chains are nested)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class And(BoolOp):
    op: ClassVar = 'and'

@dataclass
class Or(BoolOp):
    op: ClassVar = 'or'


# ═══════════════════════════════════════════════════════════════════════════════
# Unary Operators
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UnaryPlus(UnaryOp):
    op: ClassVar = '+'

@dataclass
class Negate(UnaryOp):
    op: ClassVar = '-'

@dataclass
class Not(UnaryOp):
    op: ClassVar = 'not'

@dataclass
class Invert(UnaryOp):
    op: ClassVar = '~'


# ═══════════════════════════════════════════════════════════════════════════════
# Comparison Operators (binary — chains become CompareChain)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ArithEq(CmpOp):
    """Arithmetic equality: ``X == Y``.  Posts a CLP(FD/ℤ) constraint (Prolog ``=:=/2``).

    .. warning:: Do **not** rename this to StructuralEq.
       ``==`` in Clausal is *arithmetic* equality, not structural equality.
       True structural equality (Prolog ``==/2``) is the separate ``StructuralEq``
       node / ``structural_eq/2`` builtin.  This class has been misnamed before
       and the confusion led to this guard comment.
    """
    op: ClassVar = '=='

@dataclass
class ArithNeq(CmpOp):
    """Arithmetic inequality: ``X != Y``.  Posts a CLP(FD/ℤ) disequality constraint (Prolog ``=\\=/2``).

    See ``ArithEq`` warning — do **not** rename to StructuralNeq.
    """
    op: ClassVar = '!='

@dataclass
class StructuralEq(CmpOp):
    """Structural equality: Prolog ``==/2``.

    Succeeds iff *left* and *right* are identical after dereferencing variables,
    **without** binding any variables and **without** evaluating arithmetic.
    """
    op: ClassVar = '=='  # same surface syntax, but distinct AST node

@dataclass
class StructuralNeq(CmpOp):
    """Structural inequality: Prolog ``\\==/2``.

    Succeeds iff *left* and *right* are **not** identical after dereferencing,
    **without** binding any variables and **without** evaluating arithmetic.
    """
    op: ClassVar = '!='  # same surface syntax, but distinct AST node

@dataclass
class Lt(CmpOp):
    op: ClassVar = '<'

@dataclass
class LtE(CmpOp):
    op: ClassVar = '<='

@dataclass
class Gt(CmpOp):
    op: ClassVar = '>'

@dataclass
class GtE(CmpOp):
    op: ClassVar = '>='

@dataclass
class Unify(CmpOp):
    """Unification: ``X is Y``. Binds variables to make both sides equal."""
    op: ClassVar = 'is'

@dataclass
class DoesNotUnify(CmpOp):
    """Dif / negation of unification: ``X is not Y``. Succeeds iff X and Y cannot unify."""
    op: ClassVar = 'is not'

@dataclass
class Evaluate(CmpOp):
    """Arithmetic evaluate-and-bind: ``LHS := RHS``. Evaluates RHS as arithmetic, unifies with LHS."""
    op: ClassVar = ':='

@dataclass
class in_(CmpOp):
    op: ClassVar = 'in'

@dataclass
class NotIn(CmpOp):
    op: ClassVar = 'not in'


@node_class
class CompareChain(Node):
    """1 < x < 10 → CompareChain([Lt(1, x), Lt(x, 10)])

    Semantics: each intermediate operand is evaluated only once.
    For single comparisons, the individual ArithEq/Lt/etc. nodes are used directly.
    """
    comparisons: list[Node] = field(default_factory=list)

    def __str__(chain):
        parts = [str(chain.comparisons[0].left)]
        for cmp in chain.comparisons:
            parts.append(cmp.op)
            parts.append(str(cmp.right))
        return " ".join(parts)


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

@node_class
class Call(Node):
    func: Node = None  # type: ignore[assignment]
    args: list[Node] = field(default_factory=list)
    kwargs: list[Keyword] = field(default_factory=list)

    def __str__(call):
        all_args = [str(a) for a in call.args] + [str(kw) for kw in call.kwargs]
        return f"{call.func}({', '.join(all_args)})"


@node_class
class Keyword(Node):
    """A single keyword argument. name=None means **splat."""
    name: Optional[str] = None
    value: Node = None  # type: ignore[assignment]

    def __str__(kw):
        return f"**{kw.value}" if kw.name is None else f"{kw.name}={kw.value}"


@node_class
class IfExpr(Node):
    """Ternary: body if test else orelse."""
    test: Node = None    # type: ignore[assignment]
    body: Node = None    # type: ignore[assignment]
    orelse: Node = None  # type: ignore[assignment]

    def __str__(ife):
        return f"{ife.body} if {ife.test} else {ife.orelse}"


@node_class
class NamedExpr(Node):
    """:= walrus operator."""
    target: Node = None  # type: ignore[assignment]
    value: Node = None   # type: ignore[assignment]

    def __str__(ne):
        return f"({ne.target} := {ne.value})"


@node_class
class Lambda(Node):
    params: Params = None  # type: ignore[assignment]
    body: Node = None      # type: ignore[assignment]

    def __str__(lam):
        params_str = str(lam.params)
        if params_str:
            return f"lambda {params_str}: {lam.body}"
        return f"lambda: {lam.body}"


@dataclass
class Yield(Node):
    value: Optional[Node] = None

    def __str__(y):
        return "yield" if y.value is None else f"yield {y.value}"


@node_class
class YieldFrom(Node):
    value: Node = None  # type: ignore[assignment]

    def __str__(yf): return f"yield from {yf.value}"


@node_class
class Await(Node):
    value: Node = None  # type: ignore[assignment]

    def __str__(aw): return f"await {aw.value}"


@node_class
class Slice(Node):
    lower: Optional[Node] = None
    upper: Optional[Node] = None
    step: Optional[Node] = None

    def __str__(slc):
        lo = "" if slc.lower is None else str(slc.lower)
        hi = "" if slc.upper is None else str(slc.upper)
        if slc.step is None:
            return f"{lo}:{hi}"
        return f"{lo}:{hi}:{slc.step}"


# ═══════════════════════════════════════════════════════════════════════════════
# Comprehensions
# ═══════════════════════════════════════════════════════════════════════════════

@node_class
class ForClause(Node):
    target: Node = None     # type: ignore[assignment]
    iterable: Node = None   # type: ignore[assignment]
    filters: list[Node] = field(default_factory=list)
    is_async: bool = False

    def __str__(fc):
        kw = "async for" if fc.is_async else "for"
        s = f"{kw} {fc.target} in {fc.iterable}"
        for filt in fc.filters:
            s += f" if {filt}"
        return s


@dataclass
class ListComp(ElemComp):
    def __str__(lc):
        clauses = " ".join(str(c) for c in lc.clauses)
        return f"[{lc.element} {clauses}]"

@dataclass
class SetComp(ElemComp):
    def __str__(sc):
        clauses = " ".join(str(c) for c in sc.clauses)
        return "{" + f"{sc.element} {clauses}" + "}"

@node_class
class DictComp(Node):
    key: Node = None    # type: ignore[assignment]
    value: Node = None  # type: ignore[assignment]
    clauses: list[ForClause] = field(default_factory=list)

    def __str__(dc):
        clauses = " ".join(str(c) for c in dc.clauses)
        return "{" + f"{dc.key}: {dc.value} {clauses}" + "}"


@dataclass
class GeneratorExpr(ElemComp):
    def __str__(ge):
        clauses = " ".join(str(c) for c in ge.clauses)
        return f"({ge.element} {clauses})"


# ═══════════════════════════════════════════════════════════════════════════════
# Parameters — one subclass per kind
# ═══════════════════════════════════════════════════════════════════════════════

@node_class
class Param(Node):
    """Base for all parameter kinds."""
    name: str = ""
    annotation: Optional[Node] = None
    default: Optional[Node] = None

    def __str__(param):
        s = param.name
        if param.annotation is not None:
            s += f": {param.annotation}"
            if param.default is not None:
                s += f" = {param.default}"
        elif param.default is not None:
            s += f"={param.default}"
        return s


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
    def __str__(p):
        s = f"*{p.name}"
        if p.annotation is not None:
            s += f": {p.annotation}"
        return s

@dataclass
class VarKeyword(Param):
    """**kwargs parameter."""
    def __str__(p):
        s = f"**{p.name}"
        if p.annotation is not None:
            s += f": {p.annotation}"
        return s

@node_class
class Params(Node):
    params: list[Param] = field(default_factory=list)

    def __str__(params_node):
        result = []
        emitted_slash = False
        emitted_star = False
        has_posonly = any(isinstance(p, PosOnlyParam) for p in params_node.params)
        for p in params_node.params:
            if isinstance(p, PosOnlyParam):
                result.append(str(p))
            elif isinstance(p, PosOrKwParam):
                if has_posonly and not emitted_slash:
                    result.append("/")
                    emitted_slash = True
                result.append(str(p))
            elif isinstance(p, VarPositional):
                if has_posonly and not emitted_slash:
                    result.append("/")
                    emitted_slash = True
                result.append(str(p))
                emitted_star = True
            elif isinstance(p, KwOnlyParam):
                if has_posonly and not emitted_slash:
                    result.append("/")
                    emitted_slash = True
                if not emitted_star:
                    result.append("*")
                    emitted_star = True
                result.append(str(p))
            elif isinstance(p, VarKeyword):
                if has_posonly and not emitted_slash:
                    result.append("/")
                    emitted_slash = True
                result.append(str(p))
        if has_posonly and not emitted_slash:
            result.append("/")
        return ", ".join(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Statements
# ═══════════════════════════════════════════════════════════════════════════════

# No ExprStmt — expressions appear directly in body lists.

@node_class
class Assign(Node):
    targets: list[Node] = field(default_factory=list)
    value: Node = None  # type: ignore[assignment]


@node_class
class Predicate(Node):
    """Prolog-style predicate: head <- body."""
    head: Node = None  # type: ignore[assignment]
    body: Node = None  # type: ignore[assignment]


# ── Module-level items (pipeline split) ──────────────────────────────────────

@node_class
class Directive(Node):
    """Module-level directive: -dynamic, -table, -discontiguous, -shallow."""
    name: str = ""
    specs: list = field(default_factory=list)  # [(functor, arity), ...]

@node_class
class ImportFromDirective(Node):
    """Module-level -import_from(module, [names...])."""
    module: str = ""
    names: list = field(default_factory=list)  # [name_or_alias_tuple, ...]

@node_class
class ImportModuleDirective(Node):
    """Module-level -import_module(module)."""
    module: str = ""

@node_class
class ModuleDeclaration(Node):
    """Module-level -module(name, [exports...]) directive."""
    module_name: str = ""
    exports: list = field(default_factory=list)  # [(functor, fields), ...] or atom strings

@node_class
class PrivateDeclaration(Node):
    """Module-level -private([preds...]) directive."""
    items: list = field(default_factory=list)  # same format as ModuleDeclaration.exports

@node_class
class StrictAtomsDeclaration(Node):
    """Module item: ``-strict_atoms`` directive marker.

    Presence in ``module_items`` switches Phase 2's auto-mint pass
    (``compiler_v2._process_bare_atom_refs``) into strict mode: every
    bare atom reference must be reachable via ``-module``, ``-private``,
    ``-import_from``, a qualified reference, or ``global_atom/2``.  Any
    name that falls through to the global mint becomes a compile-time
    ``NameError`` instead of a silent global default.

    The directive takes no arguments — its mere presence is the signal.
    See Phase 3 of ``implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md``.
    """
    pass


@node_class
class OverwritesDeclaration(Node):
    """Module item: ``-overwrites([atom, ...])`` directive (Phase 4 of
    GLOBAL_ATOMS_DEFAULT.md).

    Suppresses ``ClausalAtomShadowingWarning`` for each listed atom name in
    this module.  Declarative only: does not change ``PredicateMeta``
    creation or alias the local name to the imported one.  The local name
    still creates a distinct per-module class — the directive asserts the
    user accepts that.

    The narrowed Phase-4 trigger means the warning only fires for *atom*
    shadowing (the new global-default case from Phase 2), so listing a
    predicate-functor name here is *unused* — it suppresses nothing and
    earns a ``ClausalUnusedOverwritesWarning``.  See
    ``implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md`` §"Phase
    4: shadowing warning + ``-overwrites``" for the full reasoning.
    """
    items: list = field(default_factory=list)  # bare atom names


@node_class
class BareAtomRefs(Node):
    """Module item: names referenced bare in clause bodies that may need
    auto-minting as global atoms (Phase 2 of GLOBAL_ATOMS_DEFAULT.md).

    Populated by ``EmbedTransformer`` from the union of every per-clause
    ``TermTransformer._bare_atom_refs`` set.  Consumed by
    ``compiler_v2._process_bare_atom_refs`` after declaration processing —
    any name still absent from ``module_dict`` at that point is minted via
    ``predicate_builtins.setdefault`` and the resulting class is assigned
    into ``module_dict``.

    Over-collection (predicate functor names, imported names, builtins) is
    harmless: those names are already in ``module_dict`` by the time the
    auto-mint pass runs, so the skip rule filters them out.
    """
    names: frozenset = field(default_factory=frozenset)

@node_class
class SpecializeDirective(Node):
    """Module-level -specialize(MI, Source, as=Name) directive."""
    mi_name: str = ""           # meta-interpreter predicate name
    source_program: str = ""    # name of predicate/variable providing the object program
    new_name: str = ""          # name for the specialized predicate
    depth: int = 0              # max unfolding depth (0 = shallow, >0 = deep)
    cpd: bool = False           # conjunctive partial deduction (deforestation)

@node_class
class TranslationsDirective(Node):
    """Module-level -translations(lang, {English: Translated, ...})."""
    language: str = ""
    predicate_entries: list = field(default_factory=list)  # [(eng_fun, trans_fun, arity, arg_map)]
    atom_entries: list = field(default_factory=list)        # [(eng_atom, trans_atom)]

@node_class
class EdcgAccDecl(Node):
    """EDCG accumulator declaration: -edcg_acc(name, Val, In, Out, Joiner)."""
    acc_name: str = ""
    val_var: str = ""       # variable name for the accumulated value
    in_var: str = ""        # variable name for input state
    out_var: str = ""       # variable name for output state
    joiner_ast: Node = None  # type: ignore[assignment] — AST of the joiner goal

@node_class
class EdcgPassDecl(Node):
    """EDCG passed-argument declaration: -edcg_pass(name)."""
    pass_name: str = ""

@node_class
class EdcgPredDecl(Node):
    """EDCG predicate declaration: -edcg_pred(name, visible_arity, [acc_or_pass, ...])."""
    pred_name: str = ""
    visible_arity: int = 0
    acc_pass_names: list = field(default_factory=list)  # [str, ...]


@node_class
class AnnAssign(Node):
    target: Node = None      # type: ignore[assignment]
    annotation: Node = None  # type: ignore[assignment]
    value: Optional[Node] = None
    simple: bool = True


@node_class
class Return(Node):
    value: Optional[Node] = None


@dataclass
class Pass(Node):
    pass

@dataclass
class Break(Node):
    pass

@dataclass
class Continue(Node):
    pass

@node_class
class Raise(Node):
    exc: Optional[Node] = None
    cause: Optional[Node] = None

@node_class
class assertz(Node):
    test: Node = None  # type: ignore[assignment]
    msg: Optional[Node] = None


@node_class
class Global(Node):
    names: list[str] = field(default_factory=list)

@node_class
class Nonlocal(Node):
    names: list[str] = field(default_factory=list)


# --- Imports (flattened) ---

@node_class
class Import(Node):
    module: str = ""
    alias: Optional[str] = None

@node_class
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

@node_class
class For(Node):
    target: Node = None    # type: ignore[assignment]
    iterable: Node = None  # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)
    is_async: bool = False

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

@node_class
class Try(Node):
    body: list[Node] = field(default_factory=list)
    handlers: list[ExceptHandler] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)
    finalbody: list[Node] = field(default_factory=list)
    is_star: bool = False


@node_class
class ExceptHandler(Node):
    type: Optional[Node] = None
    name: Optional[str] = None
    body: list[Node] = field(default_factory=list)


# --- Definitions ---

@node_class
class FunctionDef(Node):
    name: str = ""
    params: Params = None     # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)
    decorators: list[Node] = field(default_factory=list)
    returns: Optional[Node] = None
    is_async: bool = False
    type_params: list[Node] = field(default_factory=list)


@node_class
class ClassDef(Node):
    name: str = ""
    bases: list[Node] = field(default_factory=list)
    keywords: list[Keyword] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    decorators: list[Node] = field(default_factory=list)
    type_params: list[Node] = field(default_factory=list)


@node_class
class TypeAlias(Node):
    name: Node = None  # type: ignore[assignment]
    type_params: list[Node] = field(default_factory=list)
    value: Node = None  # type: ignore[assignment]

# --- Type params (3.12+) ---

@node_class
class TypeVar(Node):
    name: str = ""
    bound: Optional[Node] = None

@node_class
class ParamSpec(Node):
    name: str = ""

@node_class
class TypeVarTuple(Node):
    name: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Pattern Matching
# ═══════════════════════════════════════════════════════════════════════════════

@node_class
class Match(Node):
    subject: Node = None  # type: ignore[assignment]
    cases: list[MatchCase] = field(default_factory=list)

@node_class
class MatchCase(Node):
    pattern: Node = None  # type: ignore[assignment]
    guard: Optional[Node] = None
    body: list[Node] = field(default_factory=list)


@node_class
class MatchLiteral(Node):
    value: Node = None  # type: ignore[assignment]
    use_is: bool = False


@node_class
class MatchSequence(Node):
    patterns: list[Node] = field(default_factory=list)

@node_class
class MatchMapping(Node):
    keys: list[Node] = field(default_factory=list)
    patterns: list[Node] = field(default_factory=list)
    rest: Optional[str] = None

@node_class
class MatchClass(Node):
    cls: Node = None  # type: ignore[assignment]
    patterns: list[Node] = field(default_factory=list)
    kwd_attrs: list[str] = field(default_factory=list)
    kwd_patterns: list[Node] = field(default_factory=list)

@node_class
class MatchStar(Node):
    name: Optional[str] = None

@node_class
class MatchAs(Node):
    pattern: Optional[Node] = None
    name: Optional[str] = None

@node_class
class MatchOr(Node):
    patterns: list[Node] = field(default_factory=list)

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
    from .conversion_from_python_ast import visit
    return visit(tree)
