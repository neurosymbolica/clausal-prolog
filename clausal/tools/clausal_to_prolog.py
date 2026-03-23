"""Clausal → Prolog translation (Phase 1.2).

Pipeline: .clausal source → Python AST → Prolog AST → .pl text

Public API:
    emit_term(pterm, op_table)          — Prolog AST term → text
    emit_item(pitem, op_table)          — Prolog AST clause/directive → text
    emit_module(pmodule, op_table)      — full PModule → text
    clausal_source_to_prolog_ast(src)   — .clausal source → PModule
    clausal_source_to_prolog(src, ...)  — .clausal source → .pl text
"""

from __future__ import annotations

import ast as python_ast
import re

from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PModule,
    PTerm, PItem,
)
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_dialect import (
    Dialect,
    pascal_to_snake, snake_to_pascal,
    clausal_var_to_prolog, prolog_var_to_clausal,
    resolve_name,
)

# Re-export naming helpers so tests can import from this module.
__all__ = [
    "emit_term", "emit_item", "emit_module",
    "clausal_source_to_prolog", "clausal_source_to_prolog_ast",
    "pascal_to_snake", "snake_to_pascal",
    "clausal_var_to_prolog", "prolog_var_to_clausal",
]


# ── Prolog text emission ─────────────────────────────────────────────

# Operators that are typically displayed with spaces around them
_INFIX_NO_SPACE = frozenset()  # all infix operators get spaces


def _needs_quoting(name: str) -> bool:
    """True if an atom name needs single-quoting in Prolog."""
    if not name:
        return True
    # Alphanumeric atoms starting with lowercase don't need quoting
    if name[0].islower() and name.replace("_", "a").isalnum():
        return False
    # Pure operator-char atoms don't need quoting
    _OP_CHARS = set("+-*/\\^<>=~:.?@#&")
    if all(c in _OP_CHARS for c in name):
        return False
    # Special atoms
    if name in ("[]", "{}", "!", ",", ";"):
        return False
    return True


def _quote_atom(name: str) -> str:
    """Single-quote an atom, escaping internal single quotes."""
    return "'" + name.replace("\\", "\\\\").replace("'", "\\'") + "'"


def emit_term(term: PTerm, op_table: OperatorTable, *,
              context_prec: int = 1201, context_assoc: str = "") -> str:
    """Render a Prolog AST term as text.

    *context_prec* and *context_assoc* control parenthesization based
    on the enclosing operator's precedence and associativity.
    """
    if isinstance(term, PAtom):
        if term.quoted or _needs_quoting(term.name):
            return _quote_atom(term.name)
        return term.name
    if isinstance(term, PVar):
        return term.name
    if isinstance(term, PNumber):
        if isinstance(term.value, float):
            return repr(term.value)
        return str(term.value)
    if isinstance(term, PString):
        return '"' + term.value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(term, PList):
        return _emit_list(term, op_table)
    if isinstance(term, PCurly):
        inner = emit_term(term.body, op_table)
        return "{" + inner + "}"
    if isinstance(term, PCompound):
        return _emit_compound(term, op_table, context_prec, context_assoc)
    return str(term)


def _emit_list(lst: PList, op_table: OperatorTable) -> str:
    """Render a PList as [a, b, c] or [H|T]."""
    if not lst.elements and lst.tail is None:
        return "[]"
    parts = [emit_term(e, op_table) for e in lst.elements]
    if lst.tail is not None:
        return "[" + ", ".join(parts) + "|" + emit_term(lst.tail, op_table) + "]"
    return "[" + ", ".join(parts) + "]"


def _emit_compound(term: PCompound, op_table: OperatorTable,
                   context_prec: int, context_assoc: str) -> str:
    """Render a PCompound — either as f(a,b) or as infix/prefix operator."""
    functor = term.functor
    arity = len(term.args)

    # Zero-arity compound
    if arity == 0:
        if _needs_quoting(functor):
            return _quote_atom(functor)
        return functor

    # Try infix operator (arity 2)
    if arity == 2:
        entry = op_table.lookup_infix(functor)
        if entry is not None:
            return _emit_infix(term, entry, op_table, context_prec, context_assoc)

    # Try prefix operator (arity 1)
    if arity == 1:
        entry = op_table.lookup_prefix(functor)
        if entry is not None:
            return _emit_prefix(term, entry, op_table, context_prec, context_assoc)

    # Try postfix operator (arity 1)
    if arity == 1:
        entry = op_table.lookup_postfix(functor)
        if entry is not None:
            return _emit_postfix(term, entry, op_table, context_prec, context_assoc)

    # Standard compound: f(a, b, c)
    args_str = ", ".join(emit_term(a, op_table) for a in term.args)
    if _needs_quoting(functor):
        return _quote_atom(functor) + "(" + args_str + ")"
    return functor + "(" + args_str + ")"


def _needs_parens(op_prec: int, op_assoc: str, context_prec: int,
                  context_assoc: str, side: str) -> bool:
    """Determine if an operator expression needs parentheses.

    *side* is 'left' or 'right' (which side of the parent operator this is).
    """
    if op_prec > context_prec:
        return True
    if op_prec == context_prec:
        # Check associativity: xfx means neither side can have equal precedence
        # xfy means right side can, yfx means left side can
        if side == "left" and context_assoc in ("xfx", "xfy"):
            return True
        if side == "right" and context_assoc in ("xfx", "yfx"):
            return True
    return False


def _emit_infix(term: PCompound, entry, op_table: OperatorTable,
                context_prec: int, context_assoc: str) -> str:
    """Render infix operator: left op right."""
    prec = entry.precedence
    spec = entry.specifier  # xfx, xfy, yfx

    # Determine child context for left and right operands
    left_prec = prec if spec.startswith("y") else prec - 1
    right_prec = prec if spec.endswith("y") else prec - 1
    left_assoc = spec if spec.startswith("y") else ""
    right_assoc = spec if spec.endswith("y") else ""

    left_str = emit_term(term.args[0], op_table,
                         context_prec=left_prec, context_assoc=left_assoc)
    right_str = emit_term(term.args[1], op_table,
                          context_prec=right_prec, context_assoc=right_assoc)

    # Comma is special: "a, b" not "a , b"
    # Slash in predicate indicators: "f/2" not "f / 2"
    if term.functor == ",":
        result = left_str + ", " + right_str
    elif term.functor == "/":
        result = left_str + "/" + right_str
    else:
        result = left_str + " " + term.functor + " " + right_str

    # Parenthesize if this operator's precedence exceeds context
    if prec > context_prec:
        return "(" + result + ")"
    if prec == context_prec:
        # Equal precedence: need parens for non-associative positions
        if context_assoc in ("xfx",):
            return "(" + result + ")"
        # For xfy parent, left child with equal prec needs parens
        # For yfx parent, right child with equal prec needs parens
        # But we ARE the child here, so check if we need wrapping
    return result


def _emit_prefix(term: PCompound, entry, op_table: OperatorTable,
                 context_prec: int, context_assoc: str) -> str:
    """Render prefix operator: op arg."""
    prec = entry.precedence
    spec = entry.specifier  # fx or fy

    arg_prec = prec if spec == "fy" else prec - 1
    arg_str = emit_term(term.args[0], op_table, context_prec=arg_prec)

    result = term.functor + " " + arg_str

    if prec > context_prec:
        return "(" + result + ")"
    return result


def _emit_postfix(term: PCompound, entry, op_table: OperatorTable,
                  context_prec: int, context_assoc: str) -> str:
    """Render postfix operator: arg op."""
    prec = entry.precedence
    spec = entry.specifier  # xf or yf

    arg_prec = prec if spec == "yf" else prec - 1
    arg_str = emit_term(term.args[0], op_table, context_prec=arg_prec)

    result = arg_str + " " + term.functor

    if prec > context_prec:
        return "(" + result + ")"
    return result


# ── Item emission ────────────────────────────────────────────────────

def emit_item(item: PItem, op_table: OperatorTable) -> str:
    """Render a single PItem (clause, DCG rule, directive) as Prolog text."""
    if isinstance(item, PClause):
        head_str = emit_term(item.head, op_table)
        if item.body is None:
            return head_str + ".\n"
        body_str = _emit_body(item.body, op_table)
        return head_str + " :-\n    " + body_str + ".\n"
    if isinstance(item, PDCGRule):
        head_str = emit_term(item.head, op_table)
        body_str = _emit_dcg_body(item.body, op_table)
        return head_str + " -->\n    " + body_str + ".\n"
    if isinstance(item, PDirective):
        body_str = emit_term(item.body, op_table)
        return ":- " + body_str + ".\n"
    # PQuery
    body_str = emit_term(item.body, op_table)
    return "?- " + body_str + ".\n"


def _emit_body(body: PTerm, op_table: OperatorTable) -> str:
    """Render a clause body, handling conjunction layout."""
    # Flatten top-level conjunctions for indented layout
    goals = _flatten_conjunction(body)
    if len(goals) == 1:
        return emit_term(goals[0], op_table)
    parts = [emit_term(g, op_table, context_prec=999) for g in goals]
    return (",\n    ").join(parts)


def _emit_dcg_body(body: PTerm, op_table: OperatorTable) -> str:
    """Render a DCG rule body."""
    # DCG bodies use comma-separated items
    goals = _flatten_conjunction(body)
    if len(goals) == 1:
        return emit_term(goals[0], op_table)
    parts = [emit_term(g, op_table, context_prec=999) for g in goals]
    return ", ".join(parts)


def _flatten_conjunction(term: PTerm) -> list[PTerm]:
    """Flatten nested ','(A, B) into a flat list of goals."""
    if isinstance(term, PCompound) and term.functor == "," and len(term.args) == 2:
        return _flatten_conjunction(term.args[0]) + _flatten_conjunction(term.args[1])
    return [term]


# ── Module emission ──────────────────────────────────────────────────

def emit_module(pmodule: PModule, op_table: OperatorTable) -> str:
    """Render a full PModule as Prolog source text."""
    parts = []
    for item in pmodule.items:
        parts.append(emit_item(item, op_table))
    return "\n".join(parts)


# ── Clausal source → Prolog AST conversion ───────────────────────────

def _is_logic_var_name(identifier: str) -> bool:
    """Return True if identifier should be treated as a logic variable."""
    if identifier == "_":
        return True
    if identifier.endswith("__"):
        return False
    if identifier.endswith("_"):
        return True
    return identifier.isupper()


def _leftmost_usub(node):
    """Find the leftmost USub in a Python AST expression (for <- detection).

    Returns (usub_node, depth) or (None, 0).
    """
    if isinstance(node, python_ast.UnaryOp) and isinstance(node.op, python_ast.USub):
        return node, 0
    if isinstance(node, python_ast.BinOp):
        result, depth = _leftmost_usub(node.left)
        if result is not None:
            return result, depth + 1
    if isinstance(node, python_ast.Compare):
        result, depth = _leftmost_usub(node.left)
        if result is not None:
            return result, depth + 1
    return None, 0


class _ClausalToProlog:
    """Convert Python AST (from .clausal source) to Prolog AST.

    Recognizes clausal DSL patterns: trailing-comma facts, <- rules,
    >> DCG rules, -directives.
    """

    def __init__(self, dialect: Dialect):
        self.dialect = dialect
        self._items: list[PItem] = []

    def convert_module(self, tree: python_ast.Module) -> PModule:
        """Convert a full Python AST Module to a PModule."""
        for stmt in tree.body:
            item = self._convert_stmt(stmt)
            if item is not None:
                if isinstance(item, list):
                    self._items.extend(item)
                else:
                    self._items.append(item)
        return PModule(tuple(self._items))

    def _convert_stmt(self, stmt) -> PItem | list[PItem] | None:
        """Convert a top-level statement to PItem(s)."""
        if not isinstance(stmt, python_ast.Expr):
            return None

        value = stmt.value

        # -directive(...): unary minus on a call
        if (isinstance(value, python_ast.UnaryOp)
                and isinstance(value.op, python_ast.USub)
                and isinstance(value.operand, python_ast.Call)
                and isinstance(value.operand.func, python_ast.Name)):
            return self._convert_directive(value.operand)

        # Trailing-comma fact: Foo(1, 2),
        if (isinstance(value, python_ast.Tuple)
                and len(value.elts) == 1
                and isinstance(value.elts[0], python_ast.Call)):
            head = self._convert_head(value.elts[0])
            return PClause(head)

        # head <- body (Compare with Lt followed by USub)
        if isinstance(value, python_ast.Compare):
            arrow = self._detect_arrow(value)
            if arrow is not None:
                head_ast, body_ast = arrow
                head = self._convert_head(head_ast)
                body = self._convert_expr(body_ast)
                return PClause(head, body)

        # head >> body (DCG rule — RShift)
        if (isinstance(value, python_ast.BinOp)
                and isinstance(value.op, python_ast.RShift)):
            head = self._convert_expr(value.left)
            body = self._convert_dcg_body(value.right)
            return PDCGRule(head, body)

        return None

    def _detect_arrow(self, compare: python_ast.Compare):
        """Detect <- pattern in a Compare node."""
        if not compare.ops or not isinstance(compare.ops[0], python_ast.Lt):
            return None
        first_comp = compare.comparators[0]
        usub_node, depth = _leftmost_usub(first_comp)
        if usub_node is None:
            return None
        if depth > 0 or len(compare.ops) > 1:
            return None
        return compare.left, usub_node.operand

    def _convert_directive(self, call: python_ast.Call) -> PItem | list[PItem] | None:
        """Convert a -directive(...) call."""
        name = call.func.id

        if name == "module":
            return self._convert_module_directive(call)
        if name == "import_from":
            return self._convert_import_from(call)
        if name == "import_module":
            return self._convert_import_module(call)
        if name == "private":
            # Private is not emitted in Prolog (module exports handle visibility)
            return None
        if name in ("dynamic", "discontiguous", "table"):
            return self._convert_meta_directive(name, call)
        # Generic directive
        args = tuple(self._convert_expr(a) for a in call.args)
        return PDirective(PCompound(name, args))

    def _convert_module_directive(self, call: python_ast.Call) -> PDirective:
        """Convert -module(name, [exports])."""
        mod_name = self._get_string_or_name(call.args[0])
        exports = []
        if len(call.args) > 1 and isinstance(call.args[1], python_ast.List):
            for elt in call.args[1].elts:
                if isinstance(elt, python_ast.Call) and isinstance(elt.func, python_ast.Name):
                    functor = resolve_name(elt.func.id, self.dialect)
                    arity = len(elt.args)
                    exports.append(PCompound("/", (PAtom(functor), PNumber(arity))))
                elif isinstance(elt, python_ast.Name):
                    functor = resolve_name(elt.id, self.dialect)
                    exports.append(PCompound("/", (PAtom(functor), PNumber(0))))
        export_list = PList(tuple(exports))
        return PDirective(PCompound("module", (PAtom(mod_name), export_list)))

    def _convert_import_from(self, call: python_ast.Call) -> PDirective:
        """Convert -import_from(module, [names])."""
        mod_path = self._get_string_or_name(call.args[0])
        # Convert dotted module path to file path for Prolog
        prolog_path = mod_path.replace(".", "/")

        imports = []
        if len(call.args) > 1 and isinstance(call.args[1], python_ast.List):
            for elt in call.args[1].elts:
                if isinstance(elt, python_ast.Call) and isinstance(elt.func, python_ast.Name):
                    functor = resolve_name(elt.func.id, self.dialect)
                    arity = len(elt.args)
                    imports.append(PCompound("/", (PAtom(functor), PNumber(arity))))
                elif isinstance(elt, python_ast.Name):
                    functor = resolve_name(elt.id, self.dialect)
                    imports.append(PAtom(functor))

        import_list = PList(tuple(imports))
        return PDirective(PCompound("use_module",
                                    (PAtom(prolog_path, quoted=True), import_list)))

    def _convert_import_module(self, call: python_ast.Call) -> PDirective:
        """Convert -import_module(module)."""
        mod_path = self._get_string_or_name(call.args[0])
        prolog_path = mod_path.replace(".", "/")
        return PDirective(PCompound("use_module", (PAtom(prolog_path, quoted=True),)))

    def _convert_meta_directive(self, name: str, call: python_ast.Call) -> PDirective | list[PDirective]:
        """Convert -dynamic(pred/arity), -table(...), -discontiguous(...)."""
        # Handle tabling specially for Scryer
        if name == "table" and self.dialect.name == "scryer":
            # Scryer needs :- use_module(library(tabling)) first, but
            # we just emit the :- table directive for now
            pass

        specs = []
        for arg in call.args:
            spec = self._convert_pred_spec(arg)
            if spec is not None:
                specs.append(spec)

        if len(specs) == 1:
            return PDirective(PCompound(name, (specs[0],)))
        return PDirective(PCompound(name, (PList(tuple(specs)),)))

    def _convert_pred_spec(self, node) -> PTerm | None:
        """Convert a predicate specification like Foo(X, Y) to foo/2."""
        if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Name):
            functor = resolve_name(node.func.id, self.dialect)
            arity = len(node.args)
            return PCompound("/", (PAtom(functor), PNumber(arity)))
        if isinstance(node, python_ast.Name):
            functor = resolve_name(node.id, self.dialect)
            return PAtom(functor)
        return None

    def _convert_head(self, call) -> PTerm:
        """Convert a clause head (a Call node) to a PCompound."""
        if isinstance(call, python_ast.Call) and isinstance(call.func, python_ast.Name):
            functor = resolve_name(call.func.id, self.dialect)
            args = tuple(self._convert_expr(a) for a in call.args)
            if not args:
                return PAtom(functor)
            return PCompound(functor, args)
        return self._convert_expr(call)

    def _convert_expr(self, node) -> PTerm:
        """Convert a Python AST expression node to a Prolog AST term."""
        if isinstance(node, python_ast.Constant):
            return self._convert_constant(node.value)

        if isinstance(node, python_ast.Name):
            return self._convert_name(node.id)

        if isinstance(node, python_ast.Call):
            return self._convert_call(node)

        if isinstance(node, python_ast.List):
            return self._convert_list(node)

        if isinstance(node, python_ast.Tuple):
            # Single-element tuple used for trailing-comma facts in nested context
            if len(node.elts) == 1:
                return self._convert_expr(node.elts[0])
            # Multi-element tuple → Prolog comma-separated (conjunction-like)
            if len(node.elts) >= 2:
                result = self._convert_expr(node.elts[-1])
                for elt in reversed(node.elts[:-1]):
                    result = PCompound(",", (self._convert_expr(elt), result))
                return result
            return PAtom("true")

        if isinstance(node, python_ast.BoolOp):
            return self._convert_boolop(node)

        if isinstance(node, python_ast.UnaryOp):
            return self._convert_unaryop(node)

        if isinstance(node, python_ast.BinOp):
            return self._convert_binop(node)

        if isinstance(node, python_ast.Compare):
            return self._convert_compare(node)

        if isinstance(node, python_ast.IfExp):
            return self._convert_ifexp(node)

        if isinstance(node, python_ast.NamedExpr):
            return self._convert_named_expr(node)

        if isinstance(node, python_ast.Starred):
            # *X in list context — handled by _convert_list
            return self._convert_expr(node.value)

        # Attribute access: mod.pred
        if isinstance(node, python_ast.Attribute):
            base = self._convert_expr(node.value)
            if isinstance(base, PAtom):
                return PAtom(base.name + ":" + node.attr)
            return PCompound(":", (base, PAtom(node.attr)))

        # Fallback
        return PAtom("???")

    def _convert_constant(self, value) -> PTerm:
        """Convert a Python constant to a Prolog term."""
        if isinstance(value, bool):
            return PAtom("true" if value else "false")
        if isinstance(value, int):
            return PNumber(value)
        if isinstance(value, float):
            return PNumber(value)
        if isinstance(value, str):
            return PString(value)
        if value is None:
            return PAtom("none")
        return PAtom(str(value))

    def _convert_name(self, name: str) -> PTerm:
        """Convert a Python name to PVar or PAtom."""
        if name == "_":
            return PVar("_")
        if _is_logic_var_name(name):
            return PVar(clausal_var_to_prolog(name))
        # Atoms: lowercase or PascalCase predicate name
        return PAtom(resolve_name(name, self.dialect))

    def _convert_call(self, node: python_ast.Call) -> PTerm:
        """Convert a function call to a PCompound."""
        if isinstance(node.func, python_ast.Name):
            functor = resolve_name(node.func.id, self.dialect)
        elif isinstance(node.func, python_ast.Attribute):
            # Qualified call: mod.pred(...)
            functor = self._qualified_name(node.func)
        else:
            functor = "???"

        args = tuple(self._convert_expr(a) for a in node.args)
        if not args:
            return PCompound(functor, ())
        return PCompound(functor, args)

    def _qualified_name(self, attr: python_ast.Attribute) -> str:
        """Get a qualified name from an Attribute node."""
        if isinstance(attr.value, python_ast.Name):
            base = resolve_name(attr.value.id, self.dialect)
            pred = resolve_name(attr.attr, self.dialect)
            return base + ":" + pred
        return resolve_name(attr.attr, self.dialect)

    def _convert_list(self, node: python_ast.List) -> PTerm:
        """Convert a Python list literal to a PList.

        Handles [H, *T] → [H|T] (star-unpack as list tail).
        """
        elements = []
        tail = None
        for i, elt in enumerate(node.elts):
            if isinstance(elt, python_ast.Starred):
                # *T is the tail — must be the last element
                tail = self._convert_expr(elt.value)
                # Elements before starred are the head elements
                break
            elements.append(self._convert_expr(elt))
        else:
            # No starred element — proper list
            return PList(tuple(elements))

        return PList(tuple(elements), tail=tail)

    def _convert_boolop(self, node: python_ast.BoolOp) -> PTerm:
        """Convert 'and'/'or' to ','/';'."""
        if isinstance(node.op, python_ast.And):
            op = ","
        else:
            op = ";"

        result = self._convert_expr(node.values[-1])
        for val in reversed(node.values[:-1]):
            result = PCompound(op, (self._convert_expr(val), result))
        return result

    def _convert_unaryop(self, node: python_ast.UnaryOp) -> PTerm:
        """Convert unary operators."""
        if isinstance(node.op, python_ast.Not):
            return PCompound("\\+", (self._convert_expr(node.operand),))
        if isinstance(node.op, python_ast.USub):
            inner = self._convert_expr(node.operand)
            if isinstance(inner, PNumber):
                return PNumber(-inner.value)
            return PCompound("-", (inner,))
        if isinstance(node.op, python_ast.UAdd):
            return self._convert_expr(node.operand)
        if isinstance(node.op, python_ast.Invert):
            return PCompound("\\", (self._convert_expr(node.operand),))
        return self._convert_expr(node.operand)

    def _convert_binop(self, node: python_ast.BinOp) -> PTerm:
        """Convert binary operators to Prolog operators."""
        left = self._convert_expr(node.left)
        right = self._convert_expr(node.right)

        op_map = {
            python_ast.Add: "+",
            python_ast.Sub: "-",
            python_ast.Mult: "*",
            python_ast.Div: "/",
            python_ast.FloorDiv: "//",
            python_ast.Mod: "mod",
            python_ast.Pow: "**",
            python_ast.BitAnd: "/\\",
            python_ast.BitOr: "\\/",
            python_ast.BitXor: "xor",
            python_ast.LShift: "<<",
            python_ast.RShift: ">>",
        }
        op_str = op_map.get(type(node.op), "???")
        return PCompound(op_str, (left, right))

    def _convert_compare(self, node: python_ast.Compare) -> PTerm:
        """Convert comparison operators.

        Handles special clausal patterns:
        - X is Y → X = Y (Unify)
        - X is not Y → dif(X, Y) (DoesNotUnify)
        - X := Expr → X is Expr (Evaluate)
        - X == Y → X == Y (StructuralEq)
        - X != Y → X \\== Y (StructuralNeq)
        """
        # First check for <- arrow (should already be handled at statement level)
        # Handle single comparison
        if len(node.ops) == 1:
            left = self._convert_expr(node.left)
            right = self._convert_expr(node.comparators[0])
            op = node.ops[0]

            if isinstance(op, python_ast.Is):
                # Check for "is not"
                if (isinstance(node.comparators[0], python_ast.Compare)
                        and len(node.comparators[0].ops) == 1
                        and isinstance(node.comparators[0].ops[0], python_ast.Not)):
                    # This shouldn't happen with standard Python parsing
                    pass
                return PCompound("=", (left, right))

            if isinstance(op, python_ast.IsNot):
                return PCompound("dif", (left, right))

            if isinstance(op, python_ast.Eq):
                return PCompound("==", (left, right))

            if isinstance(op, python_ast.NotEq):
                return PCompound("\\==", (left, right))

            if isinstance(op, python_ast.Lt):
                # Check for := (walrus-like evaluation)
                # In clausal, Y := X * 2 is parsed as Compare with LtE
                # Actually in clausal, := is a NamedExpr. Let me check...
                # Actually <- is Lt + USub. Pure Lt is just <.
                return PCompound("<", (left, right))

            if isinstance(op, python_ast.LtE):
                return PCompound("=<", (left, right))

            if isinstance(op, python_ast.Gt):
                return PCompound(">", (left, right))

            if isinstance(op, python_ast.GtE):
                return PCompound(">=", (left, right))

        # Multi-comparison: chain into conjunction
        parts = []
        prev = self._convert_expr(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self._convert_expr(comp)
            if isinstance(op, python_ast.Is):
                parts.append(PCompound("=", (prev, right)))
            elif isinstance(op, python_ast.IsNot):
                parts.append(PCompound("dif", (prev, right)))
            elif isinstance(op, python_ast.Eq):
                parts.append(PCompound("==", (prev, right)))
            elif isinstance(op, python_ast.NotEq):
                parts.append(PCompound("\\==", (prev, right)))
            elif isinstance(op, python_ast.Lt):
                parts.append(PCompound("<", (prev, right)))
            elif isinstance(op, python_ast.LtE):
                parts.append(PCompound("=<", (prev, right)))
            elif isinstance(op, python_ast.Gt):
                parts.append(PCompound(">", (prev, right)))
            elif isinstance(op, python_ast.GtE):
                parts.append(PCompound(">=", (prev, right)))
            prev = right

        if len(parts) == 1:
            return parts[0]
        result = parts[-1]
        for p in reversed(parts[:-1]):
            result = PCompound(",", (p, result))
        return result

    def _convert_ifexp(self, node: python_ast.IfExp) -> PTerm:
        """Convert X if Cond else Y → (Cond -> X ; Y)."""
        cond = self._convert_expr(node.test)
        then = self._convert_expr(node.body)
        else_ = self._convert_expr(node.orelse)
        return PCompound(";", (
            PCompound("->", (cond, then)),
            else_
        ))

    def _convert_dcg_body(self, node) -> PTerm:
        """Convert DCG rule body, wrapping inline goals in {curly}."""
        # For now, treat the same as regular body conversion
        return self._convert_expr(node)

    def _get_string_or_name(self, node) -> str:
        """Extract string from a Constant or Name node."""
        if isinstance(node, python_ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, python_ast.Name):
            return node.id
        # Attribute chain: foo.bar.baz
        if isinstance(node, python_ast.Attribute):
            parts = []
            current = node
            while isinstance(current, python_ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, python_ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return str(node)

    def _convert_named_expr(self, node: python_ast.NamedExpr) -> PTerm:
        """Convert := (walrus operator) to Prolog 'is' (arithmetic evaluation)."""
        target = self._convert_expr(node.target)
        value = self._convert_expr(node.value)
        return PCompound("is", (target, value))


# ── Public API ───────────────────────────────────────────────────────

def clausal_source_to_prolog_ast(source: str, *,
                                  dialect: Dialect | None = None) -> PModule:
    """Parse .clausal source text and return a Prolog AST (PModule).

    Uses Python's parser on the clausal source, then converts the
    Python AST patterns (trailing comma facts, <- rules, -directives)
    directly into Prolog AST nodes.
    """
    if dialect is None:
        dialect = Dialect.iso()
    tree = python_ast.parse(source)
    converter = _ClausalToProlog(dialect)
    return converter.convert_module(tree)


def clausal_source_to_prolog(source: str, *,
                              dialect: Dialect | None = None) -> str:
    """Translate .clausal source text to Prolog source text.

    Full pipeline: .clausal → Python AST → Prolog AST → .pl text.
    """
    if dialect is None:
        dialect = Dialect.iso()
    pmodule = clausal_source_to_prolog_ast(source, dialect=dialect)
    return emit_module(pmodule, dialect.operator_table)
